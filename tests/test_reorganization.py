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
    main = make_chain(tmp_path, "main.json")
    fork = make_chain(tmp_path, "fork.json")

    miner_a = Wallet()
    miner_b = Wallet()

    # Main chain: genesis + 1 block
    mine_block(main, miner_a)

    # Alternative chain: same genesis + 2 valid blocks
    mine_block(fork, miner_b)
    mine_block(fork, miner_b)

    candidate = list(fork.chain)

    assert candidate[0].block_hash == main.chain[0].block_hash

    assert main.chain_work(candidate) > main.cumulative_work

    assert fork.validate_chain(candidate)[0]

    assert main.try_replace_chain(candidate) is True

    assert main.chain[-1].block_hash == fork.chain[-1].block_hash

    assert main.cumulative_work == main.chain_work(candidate)


def test_invalid_heavier_chain_is_rejected(tmp_path):
    main = make_chain(tmp_path, "main.json")
    fork = make_chain(tmp_path, "fork.json")

    miner_a = Wallet()
    miner_b = Wallet()

    # Main chain: genesis + 1 block
    mine_block(main, miner_a)

    # Alternative chain: genesis + 2 blocks
    mine_block(fork, miner_b)
    mine_block(fork, miner_b)

    alternative = list(fork.chain)

    # The chain has more cumulative work,
    # but we deliberately corrupt the second block.
    alternative[-1].previous_hash = "f" * 128

    assert main.chain_work(alternative) > main.cumulative_work

    assert main.try_replace_chain(alternative) is False

    assert main.chain[-1].block_hash != alternative[-1].block_hash
