import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "electric_money_v14.py"

spec = importlib.util.spec_from_file_location(
    "electric_money_v14",
    MODULE_PATH,
)

em = importlib.util.module_from_spec(spec)

assert spec.loader is not None
sys.modules[spec.name] = em
spec.loader.exec_module(em)


Blockchain = em.Blockchain
Wallet = em.Wallet


def make_chain(tmp_path, name):
    return Blockchain(
        node_port=0,
        db_file=str(tmp_path / f"{name}.json"),
    )


def test_equal_work_chain_is_not_adopted(tmp_path):
    main = make_chain(tmp_path, "main")
    fork = make_chain(tmp_path, "fork")

    miner_main = Wallet().address
    miner_fork = Wallet().address

    main.mine_pending(miner_main)
    fork.mine_pending(miner_fork)

    assert len(main.chain) == 2
    assert len(fork.chain) == 2

    assert main.chain_work(main.chain) == fork.chain_work(fork.chain)

    old_tip = main.chain[-1].block_hash

    result = main.try_replace_chain(fork.chain)

    assert result is False
    assert main.chain[-1].block_hash == old_tip


def test_lighter_chain_is_not_adopted(tmp_path):
    main = make_chain(tmp_path, "main")
    fork = make_chain(tmp_path, "fork")

    miner_main = Wallet().address
    miner_fork = Wallet().address

    main.mine_pending(miner_main)
    main.mine_pending(miner_main)

    fork.mine_pending(miner_fork)

    assert main.chain_work(main.chain) > fork.chain_work(fork.chain)

    old_tip = main.chain[-1].block_hash

    result = main.try_replace_chain(fork.chain)

    assert result is False
    assert main.chain[-1].block_hash == old_tip


def test_heavier_chain_is_adopted(tmp_path):
    main = make_chain(tmp_path, "main")
    fork = make_chain(tmp_path, "fork")

    miner_main = Wallet().address
    miner_fork = Wallet().address

    main.mine_pending(miner_main)

    fork.mine_pending(miner_fork)
    fork.mine_pending(miner_fork)

    assert fork.chain_work(fork.chain) > main.chain_work(main.chain)

    fork_tip = fork.chain[-1].block_hash

    result = main.try_replace_chain(fork.chain)

    assert result is True
    assert main.chain[-1].block_hash == fork_tip
    assert len(main.chain) == len(fork.chain)


def test_invalid_heavier_chain_is_rejected(tmp_path):
    main = make_chain(tmp_path, "main")
    fork = make_chain(tmp_path, "fork")

    miner_main = Wallet().address
    miner_fork = Wallet().address

    main.mine_pending(miner_main)

    fork.mine_pending(miner_fork)
    fork.mine_pending(miner_fork)

    assert fork.chain_work(fork.chain) > main.chain_work(main.chain)

    old_tip = main.chain[-1].block_hash

    # Tamper with the heavier fork without recalculating its hash.
    fork.chain[1].extra_data = "TAMPERED-REORG-BLOCK"

    result = main.try_replace_chain(fork.chain)

    assert result is False
    assert main.chain[-1].block_hash == old_tip


def test_receive_block_adopts_heavier_fork(tmp_path):
    main = make_chain(tmp_path, "main_receive")
    fork = make_chain(tmp_path, "fork_receive")

    miner_main = Wallet().address
    miner_fork = Wallet().address

    # Main chain has one block.
    main.mine_pending(miner_main)

    # Fork has two blocks.
    fork.mine_pending(miner_fork)
    fork.mine_pending(miner_fork)

    fork_block_1 = fork.chain[1]
    fork_block_2 = fork.chain[2]

    # First fork block has equal work, so it must not replace main.
    result_1 = main.receive_block(fork_block_1)

    assert result_1 == "valid-lighter"
    assert main.chain[-1].block_hash != fork_block_1.block_hash

    # Second fork block makes the fork heavier.
    result_2 = main.receive_block(fork_block_2)

    assert result_2 == "reorged"
    assert main.chain[-1].block_hash == fork_block_2.block_hash
    assert len(main.chain) == 3


def test_reorg_requeues_orphaned_transfer(tmp_path):
    main = make_chain(tmp_path, "main_tx")
    fork = make_chain(tmp_path, "fork_tx")

    sender = Wallet()
    recipient = Wallet()

    # Give the sender funds on both chains.
    main.mine_pending(sender.address)
    fork.mine_pending(sender.address)

    # Create and sign a real transaction.
    tx = em.Transaction(
        sender_pubkey=sender.public_key_hex,
        recipient=recipient.address,
        amount=1 * em.COIN,
        nonce=0,
        timestamp=int(em.time.time()),
    )
    sender.sign_transaction(tx)

    # Put the transaction in the main-chain mempool.
    assert main.add_transaction(tx) is True
    assert tx.tx_id in main.pending

    # Mine the transaction into the current main chain.
    main.mine_pending(sender.address)

    assert tx.tx_id not in main.pending

    # Build a heavier competing chain WITHOUT the transaction.
    fork.mine_pending(sender.address)
    fork.mine_pending(sender.address)

    assert fork.chain_work(fork.chain) > main.chain_work(main.chain)

    # Reorg to the heavier chain.
    result = main.try_replace_chain(fork.chain)

    assert result is True

    # The transaction disappeared from the winning chain,
    # so it must be returned to the mempool.
    assert tx.tx_id not in {
        raw.get("tx_id")
        for block in main.chain
        for raw in block.transactions
    }

    assert tx.tx_id in main.pending


def test_reorg_rebuilds_state_from_winning_chain(tmp_path):
    main = make_chain(tmp_path, "main_state")
    fork = make_chain(tmp_path, "fork_state")

    sender = Wallet()
    recipient = Wallet()

    # Both chains give the sender the same initial mining reward.
    main.mine_pending(sender.address)
    fork.mine_pending(sender.address)

    tx = em.Transaction(
        sender_pubkey=sender.public_key_hex,
        recipient=recipient.address,
        amount=1 * em.COIN,
        nonce=0,
        timestamp=int(em.time.time()),
    )
    sender.sign_transaction(tx)

    assert main.add_transaction(tx) is True

    # The transaction becomes part of the main chain.
    main.mine_pending(sender.address)

    assert main.balances[recipient.address] == tx.net_amount()
    assert main.nonces[sender.address] == 1

    # The competing chain does not contain the transaction,
    # but becomes heavier.
    fork.mine_pending(sender.address)
    fork.mine_pending(sender.address)

    assert fork.chain_work(fork.chain) > main.chain_work(main.chain)

    result = main.try_replace_chain(fork.chain)

    assert result is True

    # State must now come entirely from the winning chain.
    # V14 removes zero-balance addresses from the balances dictionary.
    assert main.balances.get(recipient.address, 0) == 0
    assert main.nonces.get(sender.address, 0) == 0

    # The winning fork contains three mining rewards for the sender:
    # the first shared block plus two additional fork blocks.
    assert main.balances[sender.address] == 3 * em.BASE_REWARD

    # The orphaned transaction must be pending again.
    assert tx.tx_id in main.pending


def test_out_of_order_block_is_stored_as_orphan(tmp_path):
    main = make_chain(tmp_path, "out_of_order")

    miner = Wallet()

    # Build two blocks on a separate valid chain.
    source = make_chain(tmp_path, "source")

    source.mine_pending(miner.address)
    source.mine_pending(miner.address)

    block_2 = source.chain[2]

    # Block 2 arrives before its parent.
    result = main.receive_block(block_2)

    assert result == "orphan"
    assert block_2.block_hash in main.orphans


def test_known_block_is_ignored(tmp_path):
    main = make_chain(tmp_path, "known")

    miner = Wallet()

    block = main.mine_pending(miner.address)

    result = main.receive_block(block)

    assert result == "known"
    assert block.block_hash not in main.orphans


def test_out_of_order_fork_reorgs_when_parent_arrives(tmp_path):
    main = make_chain(tmp_path, "main_out_of_order")
    fork = make_chain(tmp_path, "fork_out_of_order")

    miner = Wallet()

    # Mine the first block on both chains.
    #
    # With the same miner and no transactions, the first block
    # can be identical when produced within the same timestamp.
    main.mine_pending(miner.address)

    fork.mine_pending(miner.address)
    fork.mine_pending(miner.address)
    fork.mine_pending(miner.address)

    # The deepest block arrives first.
    result_3 = main.receive_block(fork.chain[3])

    assert result_3 == "orphan"
    assert fork.chain[3].block_hash in main.orphans

    # The middle block arrives next.
    #
    # V14 can now connect the received block to the canonical
    # first block and also recover the already stored descendant.
    result_2 = main.receive_block(fork.chain[2])

    assert result_2 == "reorged"

    # The node must now have adopted the heavier fork.
    assert main.chain[-1].block_hash == fork.chain[3].block_hash
    assert len(main.chain) == 4

    # The first block of the fork is already part of the adopted
    # chain, so delivering it again must report "known".
    result_1 = main.receive_block(fork.chain[1])

    assert result_1 == "known"

    # The final chain must remain intact.
    assert main.chain[0].index == 0
    assert main.chain[-1].index == 3


def test_heavier_fork_with_multiple_blocks_is_adopted(tmp_path):
    main = make_chain(tmp_path, "multi_main")
    fork = make_chain(tmp_path, "multi_fork")

    miner_main = Wallet()
    miner_fork = Wallet()

    # Main chain.
    main.mine_pending(miner_main.address)

    # Build a substantially heavier competing fork.
    fork.mine_pending(miner_fork.address)
    fork.mine_pending(miner_fork.address)
    fork.mine_pending(miner_fork.address)
    fork.mine_pending(miner_fork.address)

    assert fork.chain_work(fork.chain) > main.chain_work(main.chain)

    fork_tip = fork.chain[-1].block_hash

    result = main.try_replace_chain(fork.chain)

    assert result is True
    assert main.chain[-1].block_hash == fork_tip
    assert len(main.chain) == 5

    # The adopted chain must replay successfully.
    ok, reason = main.validate_chain(main.chain)

    assert ok is True
    assert reason == "ok"
