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

    assert main.chain_work(main.chain) == main.chain_work(fork.chain)

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

    assert main.chain_work(main.chain) > main.chain_work(fork.chain)

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
    main = make_chain(tmp_path, "main")
    fork = make_chain(tmp_path, "fork")

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
