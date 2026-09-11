import importlib.util
from pathlib import Path
import sys
import time


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
Transaction = em.Transaction
Wallet = em.Wallet


def make_chain(tmp_path):
    return Blockchain(
        node_port=0,
        db_file=str(tmp_path / "chain.json"),
    )


def test_invalid_transaction_amounts_are_rejected():
    wallet = Wallet()

    invalid_amounts = [
        -10**100,
        -1,
        0,
        em.MAX_TX_AMOUNT + 1,
        10**100,
    ]

    now = int(time.time())

    for amount in invalid_amounts:
        tx = Transaction(
            sender_pubkey=wallet.public_key_hex,
            recipient="a" * 128,
            amount=amount,
            nonce=0,
            timestamp=now,
            signature="00",
            tx_id="",
        )

        assert tx.is_valid(now=now) is False


def test_invalid_transaction_nonces_are_rejected():
    wallet = Wallet()
    now = int(time.time())

    invalid_nonces = [
        -1,
        -10**50,
        10**100,
    ]

    for nonce in invalid_nonces:
        tx = Transaction(
            sender_pubkey=wallet.public_key_hex,
            recipient="a" * 128,
            amount=1,
            nonce=nonce,
            timestamp=now,
            signature="00",
            tx_id="",
        )

        assert tx.is_valid(now=now) is False


def test_invalid_transaction_addresses_are_rejected():
    wallet = Wallet()
    now = int(time.time())

    invalid_addresses = [
        "",
        "x",
        "0" * 127,
        "0" * 129,
        "g" * 128,
        123,
        None,
    ]

    for recipient in invalid_addresses:
        tx = Transaction(
            sender_pubkey=wallet.public_key_hex,
            recipient=recipient,
            amount=1,
            nonce=0,
            timestamp=now,
            signature="00",
            tx_id="",
        )

        assert tx.is_valid(now=now) is False


def test_invalid_transaction_timestamps_are_rejected():
    wallet = Wallet()
    now = int(time.time())

    invalid_timestamps = [
        now - em.MAX_TX_AGE - 1,
        now + em.MAX_FUTURE_BLOCK_TIME + 1,
    ]

    for timestamp in invalid_timestamps:
        tx = Transaction(
            sender_pubkey=wallet.public_key_hex,
            recipient="a" * 128,
            amount=1,
            nonce=0,
            timestamp=timestamp,
            signature="00",
            tx_id="",
        )

        assert tx.is_valid(now=now) is False


def test_invalid_transaction_keys_and_signatures_are_rejected():
    now = int(time.time())

    invalid_cases = [
        ("", "00"),
        ("0" * 127, "00"),
        ("0" * 129, "00"),
        ("g" * 128, "00"),
        ("0" * 128, ""),
        ("0" * 128, "not-hex"),
        ("0" * 128, 123),
        (None, "00"),
    ]

    for sender_pubkey, signature in invalid_cases:
        tx = Transaction(
            sender_pubkey=sender_pubkey,
            recipient="a" * 128,
            amount=1,
            nonce=0,
            timestamp=now,
            signature=signature,
            tx_id="",
        )

        assert tx.is_valid(now=now) is False


def test_invalid_transaction_ids_are_rejected():
    wallet = Wallet()
    now = int(time.time())

    tx = Transaction(
        sender_pubkey=wallet.public_key_hex,
        recipient="a" * 128,
        amount=1,
        nonce=0,
        timestamp=now,
        signature="00",
        tx_id="",
    )

    assert tx.is_valid(now=now) is False

    tx.tx_id = "0" * 128

    assert tx.is_valid(now=now) is False


def test_malformed_transactions_are_rejected_by_blockchain(tmp_path):
    chain = make_chain(tmp_path)
    wallet = Wallet()

    now = int(time.time())

    malformed_transactions = [
        Transaction(
            sender_pubkey=wallet.public_key_hex,
            recipient="a" * 128,
            amount=0,
            nonce=0,
            timestamp=now,
            signature="00",
            tx_id="",
        ),
        Transaction(
            sender_pubkey=wallet.public_key_hex,
            recipient="a" * 128,
            amount=-1,
            nonce=0,
            timestamp=now,
            signature="00",
            tx_id="",
        ),
        Transaction(
            sender_pubkey=wallet.public_key_hex,
            recipient="a" * 128,
            amount=1,
            nonce=-1,
            timestamp=now,
            signature="00",
            tx_id="",
        ),
    ]

    for tx in malformed_transactions:
        ok, reason = chain.validate_transaction(tx, now=now)

        assert ok is False
        assert isinstance(reason, str)
        assert reason


def test_invalid_public_keys_are_rejected_without_exception():
    invalid_keys = [
        "",
        "x",
        "0" * 127,
        "0" * 129,
        "g" * 128,
        None,
        123,
    ]

    for public_key in invalid_keys:
        try:
            result = Wallet.address_from_pubkey(public_key)
        except (ValueError, TypeError):
            continue

        assert False, (
            "Invalid public key was accepted: "
            f"{public_key!r} -> {result!r}"
        )


def test_malformed_block_dictionaries_are_rejected(tmp_path):
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
        {"transactions": "invalid"},
        {"transactions": {}},
        {"nonce": None},
        {"nonce": "abc"},
        {"merkle_root": None},
    ]

    for data in malformed_blocks:
        try:
            block = em.Block.from_dict(data)
        except (KeyError, TypeError, ValueError):
            continue

        try:
            result = chain.validate_block(block)
        except (KeyError, TypeError, ValueError, IndexError):
            assert False, (
                "Malformed block caused an unexpected validation exception"
            )

        assert result[0] is False
