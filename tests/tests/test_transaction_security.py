import importlib.util
from pathlib import Path
import sys
import time

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "electric_money_v14.py"

spec = importlib.util.spec_from_file_location(
    "electric_money_v14",
    MODULE_PATH,
)

em = importlib.util.module_from_spec(spec)

assert spec.loader is not None

# Required for dataclasses when loading the module dynamically.
sys.modules[spec.name] = em

spec.loader.exec_module(em)

Wallet = em.Wallet
Transaction = em.Transaction
Blockchain = em.Blockchain


def make_transaction(
    sender,
    recipient,
    amount=1000,
    nonce=0,
    timestamp=None,
):
    if timestamp is None:
        timestamp = int(time.time())

    return Transaction(
        sender_pubkey=sender.public_key_hex,
        recipient=recipient.address,
        amount=amount,
        nonce=nonce,
        timestamp=timestamp,
    )


def sign_transaction(sender, recipient, amount=1000, nonce=0, timestamp=None):
    tx = make_transaction(
        sender,
        recipient,
        amount=amount,
        nonce=nonce,
        timestamp=timestamp,
    )

    sender.sign_transaction(tx)

    return tx


def test_valid_transaction_is_accepted():
    sender = Wallet()
    recipient = Wallet()

    tx = sign_transaction(sender, recipient)

    assert tx.is_valid()


def test_amount_tampering_is_rejected():
    sender = Wallet()
    recipient = Wallet()

    tx = sign_transaction(sender, recipient)

    tx.amount += 1

    assert not tx.is_valid()


def test_recipient_tampering_is_rejected():
    sender = Wallet()
    recipient = Wallet()
    attacker = Wallet()

    tx = sign_transaction(sender, recipient)

    tx.recipient = attacker.address

    assert not tx.is_valid()


def test_nonce_tampering_is_rejected():
    sender = Wallet()
    recipient = Wallet()

    tx = sign_transaction(
        sender,
        recipient,
        nonce=0,
    )

    tx.nonce = 1

    assert not tx.is_valid()


def test_timestamp_tampering_is_rejected():
    sender = Wallet()
    recipient = Wallet()

    tx = sign_transaction(sender, recipient)

    tx.timestamp += 1

    assert not tx.is_valid()


def test_signature_tampering_is_rejected():
    sender = Wallet()
    recipient = Wallet()

    tx = sign_transaction(sender, recipient)

    signature = bytearray.fromhex(tx.signature)
    signature[-1] ^= 1
    tx.signature = bytes(signature).hex()

    assert not tx.is_valid()


def test_txid_tampering_is_rejected():
    sender = Wallet()
    recipient = Wallet()

    tx = sign_transaction(sender, recipient)

    original_txid = tx.tx_id

    tx.tx_id = "0" * len(original_txid)

    assert not tx.is_valid()


def test_sender_pubkey_tampering_is_rejected():
    sender = Wallet()
    recipient = Wallet()
    attacker = Wallet()

    tx = sign_transaction(sender, recipient)

    tx.sender_pubkey = attacker.public_key_hex

    assert not tx.is_valid()


def test_negative_nonce_is_rejected():
    sender = Wallet()
    recipient = Wallet()

    tx = sign_transaction(
        sender,
        recipient,
        nonce=0,
    )

    tx.nonce = -1

    assert not tx.is_valid()


def test_invalid_recipient_format_is_rejected():
    sender = Wallet()

    tx = Transaction(
        sender_pubkey=sender.public_key_hex,
        recipient="invalid",
        amount=1000,
        nonce=0,
        timestamp=int(time.time()),
    )

    sender.sign_transaction(tx)

    assert not tx.is_valid()


def test_old_transaction_is_rejected():
    sender = Wallet()
    recipient = Wallet()

    old_timestamp = (
        int(time.time())
        - em.MAX_TX_AGE
        - 1
    )

    tx = sign_transaction(
        sender,
        recipient,
        timestamp=old_timestamp,
    )

    assert not tx.is_valid()


def test_future_transaction_is_rejected():
    sender = Wallet()
    recipient = Wallet()

    future_timestamp = (
        int(time.time())
        + em.MAX_FUTURE_BLOCK_TIME
        + 1
    )

    tx = sign_transaction(
        sender,
        recipient,
        timestamp=future_timestamp,
    )

    assert not tx.is_valid()


def test_replay_with_same_nonce_is_rejected():
    sender = Wallet()
    recipient = Wallet()

    tx = sign_transaction(
        sender,
        recipient,
        nonce=0,
    )

    blockchain = Blockchain(
        node_port=0,
        db_file=None,
    )

    balances = {
        sender.address: 10_000,
    }

    nonces = {
        sender.address: 0,
    }

    ok, reason = blockchain.validate_transaction(
        tx,
        balances=balances,
        nonces=nonces,
        now=tx.timestamp,
    )

    assert ok, reason

    nonces[sender.address] = 1

    replay_ok, _ = blockchain.validate_transaction(
        tx,
        balances=balances,
        nonces=nonces,
        now=tx.timestamp,
    )

    assert not replay_ok


def test_wrong_nonce_is_rejected():
    sender = Wallet()
    recipient = Wallet()

    tx = sign_transaction(
        sender,
        recipient,
        nonce=1,
    )

    blockchain = Blockchain(
        node_port=0,
        db_file=None,
    )

    balances = {
        sender.address: 10_000,
    }

    nonces = {
        sender.address: 0,
    }

    ok, _ = blockchain.validate_transaction(
        tx,
        balances=balances,
        nonces=nonces,
        now=tx.timestamp,
    )

    assert not ok


def test_insufficient_balance_is_rejected():
    sender = Wallet()
    recipient = Wallet()

    tx = sign_transaction(
        sender,
        recipient,
        amount=10_000,
        nonce=0,
    )

    blockchain = Blockchain(
        node_port=0,
        db_file=None,
    )

    balances = {
        sender.address: 9_999,
    }

    nonces = {
        sender.address: 0,
    }

    ok, _ = blockchain.validate_transaction(
        tx,
        balances=balances,
        nonces=nonces,
        now=tx.timestamp,
    )

    assert not ok


def test_zero_amount_is_rejected():
    sender = Wallet()
    recipient = Wallet()

    tx = sign_transaction(
        sender,
        recipient,
        amount=0,
        nonce=0,
    )

    assert not tx.is_valid()


@pytest.mark.parametrize(
    "field,new_value",
    [
        ("amount", 2001),
        ("nonce", 1),
        ("timestamp", int(time.time()) + 1),
    ],
)
def test_signed_transaction_cannot_be_modified(
    field,
    new_value,
):
    sender = Wallet()
    recipient = Wallet()

    tx = sign_transaction(
        sender,
        recipient,
        amount=2000,
        nonce=0,
    )

    setattr(tx, field, new_value)

    assert not tx.is_valid()
