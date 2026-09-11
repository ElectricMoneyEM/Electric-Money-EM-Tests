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
Block = em.Block
Wallet = em.Wallet
Transaction = em.Transaction


def make_chain(tmp_path):
    return Blockchain(
        node_port=0,
        db_file=str(tmp_path / "test_chain.json"),
    )


def state_before(chain):
    return (
        chain.balances,
        chain.nonces,
        chain.total_issued,
        chain.total_burned,
        chain.treasury_balance,
        chain.miner_work,
        chain.wallet_tax_anchor,
    )


def mine_valid_candidate(chain, miner):
    block = chain.build_candidate_block(miner.address)
    block.mine()
    return block


def test_initial_block_reward_is_25_em():
    assert em.block_subsidy(1) == 25 * em.COIN


def test_first_halving_reward_is_correct():
    height = em.HALVING_INTERVAL

    assert em.block_subsidy(height) == (25 * em.COIN) // 2


def test_second_halving_reward_is_correct():
    height = em.HALVING_INTERVAL * 2

    assert em.block_subsidy(height) == (25 * em.COIN) // 4


def test_valid_miner_reward_is_accepted(tmp_path):
    chain = make_chain(tmp_path)
    miner = Wallet()

    block = mine_valid_candidate(chain, miner)

    ok, reason, new_state = chain.validate_block(
        block,
        chain.chain[-1],
        state_before(chain),
        chain.chain,
    )

    assert ok
    assert reason == "ok"

    balances = new_state[0]
    total_issued = new_state[2]

    assert balances[miner.address] == 25 * em.COIN
    assert total_issued == 50 * em.COIN


def test_tampered_miner_reward_is_rejected(tmp_path):
    chain = make_chain(tmp_path)
    miner = Wallet()

    block = mine_valid_candidate(chain, miner)

    block.transactions[-1]["amount"] += 1

    ok, reason, _ = chain.validate_block(
        block,
        chain.chain[-1],
        state_before(chain),
        chain.chain,
    )

    assert not ok
    assert reason == "invalid block hash"


def test_tampered_reward_issuance_is_rejected(tmp_path):
    chain = make_chain(tmp_path)
    miner = Wallet()

    block = mine_valid_candidate(chain, miner)

    block.transactions[-1]["issuance"] += 1

    ok, reason, _ = chain.validate_block(
        block,
        chain.chain[-1],
        state_before(chain),
        chain.chain,
    )

    assert not ok
    assert reason == "invalid block hash"


def test_reward_id_cannot_be_reused_after_reward_tampering(tmp_path):
    chain = make_chain(tmp_path)
    miner = Wallet()

    block = mine_valid_candidate(chain, miner)

    block.transactions[-1]["tx_id"] = "f" * 128

    ok, reason, _ = chain.validate_block(
        block,
        chain.chain[-1],
        state_before(chain),
        chain.chain,
    )

    assert not ok
    assert reason == "invalid Merkle root"


def test_transaction_burn_is_exact():
    tx = Transaction(
        sender_pubkey="a" * 128,
        recipient="b" * 128,
        amount=100_000,
        nonce=0,
        timestamp=1,
    )

    assert tx.burned() == 50


def test_transaction_receiver_tax_is_exact():
    tx = Transaction(
        sender_pubkey="a" * 128,
        recipient="b" * 128,
        amount=100_000,
        nonce=0,
        timestamp=1,
    )

    assert tx.receiver_tax() == 200


def test_transaction_net_amount_is_correct():
    tx = Transaction(
        sender_pubkey="a" * 128,
        recipient="b" * 128,
        amount=100_000,
        nonce=0,
        timestamp=1,
    )

    assert tx.net_amount() == 99_750


def test_annual_levy_split_is_exact():
    balance = 100_000

    treasury_tax, burned = Blockchain._annual_tax_split(balance)

    assert treasury_tax == 200
    assert burned == 50


def test_annual_levy_total_is_exact():
    balance = 100_000

    assert Blockchain._annual_tax_due(balance) == 250
