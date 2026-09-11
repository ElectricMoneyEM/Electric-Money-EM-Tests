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


def make_chain(tmp_path, name="chain.json"):
    return Blockchain(
        node_port=0,
        db_file=str(tmp_path / name),
    )


def mine_block(chain, miner):
    return chain.mine_pending(miner.address)


def test_equal_work_chain_is_not_adopted(tmp_path):
    chain = make_chain(tmp_path)
    miner = Wallet()

    mine_block(chain, miner)

    original_chain = list(chain.chain)
    original_work = chain.cumulative_work

    candidate = list(original_chain)

    assert chain.chain_work(candidate) == original_work

    assert chain.try_replace_chain(candidate) is False

    assert chain.chain == original_chain


def test_lighter_valid_chain_is_not_adopted(tmp_path):
    chain = make_chain(tmp_path)
    miner = Wallet()

    mine_block(chain, miner)

    original_chain = list(chain.chain)

    lighter_candidate = list(original_chain[:-1])

    assert chain.chain_work(lighter_candidate) < chain.chain_work(
        original_chain
    )

    assert chain.try_replace_chain(lighter_candidate) is False

    assert chain.chain == original_chain


def test_heavier_valid_chain_is_adopted(tmp_path):
    chain = make_chain(tmp_path)

    miner_a = Wallet()
    miner_b = Wallet()

    mine_block(chain, miner_a)

    original_tip = chain.chain[-1].block_hash
    original_work = chain.cumulative_work

    alternative = list(chain.chain)

    block = chain.build_candidate_block(miner_b.address)

    # Force the alternative block to use a higher valid PoW difficulty.
    block.difficulty = block.difficulty + 1
    block.mine()

    alternative.append(block)

    assert alternative[-1].previous_hash == original_tip
    assert chain.chain_work(alternative) > original_work

    assert chain.validate_chain(alternative)[0]

    assert chain.try_replace_chain(alternative) is True

    assert chain.chain[-1].block_hash == block.block_hash
    assert chain.cumulative_work == chain.chain_work(alternative)


def test_invalid_heavier_chain_is_rejected(tmp_path):
    chain = make_chain(tmp_path)

    miner_a = Wallet()
    miner_b = Wallet()

    mine_block(chain, miner_a)

    alternative = list(chain.chain)

    block = chain.build_candidate_block(miner_b.address)

    block.difficulty = block.difficulty + 1
    block.mine()

    # The block has valid PoW, but we deliberately break its linkage.
    block.previous_hash = "f" * 128

    alternative.append(block)

    assert chain.chain_work(alternative) > chain.cumulative_work

    assert chain.try_replace_chain(alternative) is False

    assert chain.chain[-1].block_hash != block.block_hash
