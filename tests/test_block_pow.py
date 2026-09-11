import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "electric_money_v14.py"

spec = importlib.util.spec_from_file_location("electric_money_v14", MODULE_PATH)
em = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = em
spec.loader.exec_module(em)

Block = em.Block


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
