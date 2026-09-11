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


Block = em.Block
Blockchain = em.Blockchain
MerkleTree = em.MerkleTree
Wallet = em.Wallet


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


def test_mined_block_satisfies_proof_of_work():
    block = Block(
        index=1,
        previous_hash="0" * 128,
        transactions=[{"tx_id": "test"}],
        timestamp=1,
        nonce=0,
        difficulty=2,
        merkle_root="test",
        extra_data="test",
    )

    block.mine()

    assert block.block_hash
    assert block.block_hash == block.calculate_hash()
    assert block.block_hash.startswith("0" * block.difficulty)


def test_tampered_block_hash_is_detected():
    block = Block(
        index=1,
        previous_hash="0" * 128,
        transactions=[{"tx_id": "test"}],
        timestamp=1,
        nonce=0,
        difficulty=2,
        merkle_root="test",
        extra_data="test",
    )

    block.mine()

    original_hash = block.block_hash

    block.extra_data = "tampered"

    assert block.block_hash == original_hash
    assert block.calculate_hash() != block.block_hash


def test_valid_mined_block_is_accepted_by_consensus(tmp_path):
    chain = make_chain(tmp_path)
    miner = Wallet()

    block = mine_valid_candidate(chain, miner)

    ok, reason, _ = chain.validate_block(
        block,
        chain.chain[-1],
        state_before(chain),
        chain.chain,
    )

    assert ok
    assert reason == "ok"


def test_wrong_previous_hash_is_rejected(tmp_path):
    chain = make_chain(tmp_path)
    miner = Wallet()

    block = mine_valid_candidate(chain, miner)

    block.previous_hash = "f" * 128

    ok, reason, _ = chain.validate_block(
        block,
        chain.chain[-1],
        state_before(chain),
        chain.chain,
    )

    assert not ok
    assert reason == "invalid previous hash"


def test_invalid_merkle_root_is_rejected(tmp_path):
    chain = make_chain(tmp_path)
    miner = Wallet()

    block = mine_valid_candidate(chain, miner)

    block.merkle_root = "f" * 128

    ok, reason, _ = chain.validate_block(
        block,
        chain.chain[-1],
        state_before(chain),
        chain.chain,
    )

    assert not ok
    assert reason == "invalid Merkle root"


def test_invalid_proof_of_work_is_rejected(tmp_path):
    chain = make_chain(tmp_path)
    miner = Wallet()

    block = mine_valid_candidate(chain, miner)

    original_nonce = block.nonce

    while True:
        block.nonce += 1
        candidate_hash = block.calculate_hash()

        if not candidate_hash.startswith("0" * block.difficulty):
            block.block_hash = candidate_hash
            break

    assert block.nonce != original_nonce
    assert block.block_hash == block.calculate_hash()
    assert not block.block_hash.startswith("0" * block.difficulty)

    ok, reason, _ = chain.validate_block(
        block,
        chain.chain[-1],
        state_before(chain),
        chain.chain,
    )

    assert not ok
    assert reason == "invalid proof of work"


def test_unexpected_difficulty_is_rejected(tmp_path):
    chain = make_chain(tmp_path)
    miner = Wallet()

    block = mine_valid_candidate(chain, miner)

    block.difficulty += 1

    ok, reason, _ = chain.validate_block(
        block,
        chain.chain[-1],
        state_before(chain),
        chain.chain,
    )

    assert not ok
    assert reason == "unexpected difficulty"


def test_invalid_index_is_rejected(tmp_path):
    chain = make_chain(tmp_path)
    miner = Wallet()

    block = mine_valid_candidate(chain, miner)

    block.index += 1

    ok, reason, _ = chain.validate_block(
        block,
        chain.chain[-1],
        state_before(chain),
        chain.chain,
    )

    assert not ok
    assert reason == "invalid index"


def test_future_timestamp_is_rejected(tmp_path):
    chain = make_chain(tmp_path)
    miner = Wallet()

    block = mine_valid_candidate(chain, miner)

    block.timestamp = 10_000_000_000

    ok, reason, _ = chain.validate_block(
        block,
        chain.chain[-1],
        state_before(chain),
        chain.chain,
        now=1_000_000_000,
    )

    assert not ok
    assert reason == "timestamp too far in future"
