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


def make_chain(tmp_path):
    return Blockchain(
        node_port=0,
        db_file=str(tmp_path / "chain.json"),
    )


def test_random_bytes_do_not_crash_block_parser():
    garbage_inputs = [
        b"",
        b"\x00",
        b"\xff",
        b"\x00" * 10,
        b"\xff" * 100,
        b"\x00" * 1024,
        b"\xff" * 1024,
        bytes(range(256)),
    ]

    for data in garbage_inputs:
        try:
            em.Block.from_dict(data)
        except Exception:
            pass


def test_malformed_block_dicts_do_not_crash(tmp_path):
    chain = make_chain(tmp_path)

    malformed_blocks = [
        {},
        {"index": None},
        {"index": "abc"},
        {"index": -1},
        {"previous_hash": None},
        {"previous_hash": 123},
        {"timestamp": None},
        {"timestamp": "abc"},
        {"difficulty": None},
        {"difficulty": "abc"},
        {"transactions": None},
        {"transactions": "not-a-list"},
        {"transactions": {}},
        {"nonce": None},
        {"nonce": "abc"},
        {"hash": None},
        {"hash": ""},
    ]

    for data in malformed_blocks:
        try:
            block = em.Block.from_dict(data)
            chain.validate_block(block)
        except Exception:
            pass


def test_malformed_transactions_do_not_crash(tmp_path):
    chain = make_chain(tmp_path)

    malformed_transactions = [
        {},
        {"sender": None},
        {"sender": ""},
        {"sender": 123},
        {"recipient": None},
        {"recipient": ""},
        {"recipient": 123},
        {"amount": None},
        {"amount": -1},
        {"amount": "abc"},
        {"amount": 0},
        {"nonce": None},
        {"nonce": -1},
        {"nonce": "abc"},
        {"signature": None},
        {"signature": ""},
        {"signature": 123},
    ]

    for data in malformed_transactions:
        try:
            tx = em.Transaction.from_dict(data)
            chain.add_transaction(tx)
        except Exception:
            pass


def test_extreme_numeric_values_do_not_crash(tmp_path):
    chain = make_chain(tmp_path)

    extreme_values = [
        -10**100,
        -10**50,
        -1,
        0,
        1,
        10**50,
        10**100,
    ]

    for value in extreme_values:
        try:
            tx_data = {
                "sender": "",
                "recipient": "",
                "amount": value,
                "nonce": value,
                "signature": "",
            }

            tx = em.Transaction.from_dict(tx_data)
            chain.add_transaction(tx)
        except Exception:
            pass


def test_malformed_chain_lists_do_not_crash(tmp_path):
    chain = make_chain(tmp_path)

    candidates = [
        [],
        [None],
        [123],
        [{}],
        [chain.chain[0], None],
        [chain.chain[0], {}],
        [chain.chain[0], 123],
    ]

    for candidate in candidates:
        try:
            chain.validate_chain(candidate)
        except Exception:
            pass
