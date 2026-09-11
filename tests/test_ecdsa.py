import hashlib
import importlib.util
from pathlib import Path

import pytest


# Load the actual Electric Money V14 source file.
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "electric_money_v14.py"

spec = importlib.util.spec_from_file_location("electric_money_v14", SOURCE)
em = importlib.util.module_from_spec(spec)
spec.loader.exec_module(em)

Wallet = em.Wallet
Transaction = em.Transaction


def test_secp256k1_curve_is_used():
    wallet = Wallet()

    assert wallet._private_key.curve.name == "SECP256k1"


def test_wallet_sign_and_verify():
    wallet = Wallet()

    message = b"Electric Money ECDSA test"

    signature = wallet.sign(message)

    assert Wallet.verify(
        wallet.public_key_hex,
        message,
        signature,
    )


def test_wrong_message_is_rejected():
    wallet = Wallet()

    message = b"original message"
    wrong_message = b"modified message"

    signature = wallet.sign(message)

    assert not Wallet.verify(
        wallet.public_key_hex,
        wrong_message,
        signature,
    )


def test_wrong_public_key_is_rejected():
    wallet_a = Wallet()
    wallet_b = Wallet()

    message = b"Electric Money"

    signature = wallet_a.sign(message)

    assert not Wallet.verify(
        wallet_b.public_key_hex,
        message,
        signature,
    )


def test_tampered_signature_is_rejected():
    wallet = Wallet()

    message = b"Electric Money"

    signature = wallet.sign(message)

    tampered = bytearray.fromhex(signature)
    tampered[0] ^= 1

    assert not Wallet.verify(
        wallet.public_key_hex,
        message,
        bytes(tampered).hex(),
    )


def test_malformed_signature_is_rejected():
    wallet = Wallet()

    message = b"Electric Money"

    assert not Wallet.verify(
        wallet.public_key_hex,
        message,
        "00",
    )


def test_public_key_tampering_is_rejected():
    wallet = Wallet()

    message = b"Electric Money"

    signature = wallet.sign(message)

    public_key = bytearray.fromhex(wallet.public_key_hex)

    public_key[-1] ^= 1

    assert not Wallet.verify(
        bytes(public_key).hex(),
        message,
        signature,
    )


def test_deterministic_signature():
    wallet = Wallet()

    message = b"deterministic Electric Money message"

    signature_1 = wallet.sign(message)
    signature_2 = wallet.sign(message)

    assert signature_1 == signature_2


def test_different_messages_produce_different_signatures():
    wallet = Wallet()

    signature_1 = wallet.sign(b"message one")
    signature_2 = wallet.sign(b"message two")

    assert signature_1 != signature_2


def test_address_derivation():
    wallet = Wallet()

    expected = hashlib.sha3_512(
        bytes.fromhex(wallet.public_key_hex)
    ).hexdigest()

    assert wallet.address == expected


def test_transaction_signature_verifies():
    sender = Wallet()
    recipient = Wallet()

    tx = Transaction(
        sender_pubkey=sender.public_key_hex,
        recipient=recipient.address,
        amount=1000,
        nonce=1,
    )

    signed_tx = sender.sign_transaction(tx)

    assert Wallet.verify(
        sender.public_key_hex,
        signed_tx.signing_bytes(),
        signed_tx.signature,
    )


@pytest.mark.parametrize(
    "field, new_value",
    [
        ("amount", 2000),
        ("nonce", 999),
        ("timestamp", 9999999999),
        ("recipient", "tampered_recipient"),
    ],
)
def test_transaction_tampering_is_rejected(field, new_value):
    sender = Wallet()
    recipient = Wallet()

    tx = Transaction(
        sender_pubkey=sender.public_key_hex,
        recipient=recipient.address,
        amount=1000,
        nonce=1,
    )

    sender.sign_transaction(tx)

    original_signature = tx.signature

    setattr(tx, field, new_value)

    assert not Wallet.verify(
        sender.public_key_hex,
        tx.signing_bytes(),
        original_signature,
    )


def test_transaction_sender_pubkey_tampering_is_rejected():
    sender = Wallet()
    attacker = Wallet()
    recipient = Wallet()

    tx = Transaction(
        sender_pubkey=sender.public_key_hex,
        recipient=recipient.address,
        amount=1000,
        nonce=1,
    )

    sender.sign_transaction(tx)

    original_signature = tx.signature

    tx.sender_pubkey = attacker.public_key_hex

    assert not Wallet.verify(
        attacker.public_key_hex,
        tx.signing_bytes(),
        original_signature,
    )


def test_transaction_txid_changes_when_signature_changes():
    sender = Wallet()
    recipient = Wallet()

    tx = Transaction(
        sender_pubkey=sender.public_key_hex,
        recipient=recipient.address,
        amount=1000,
        nonce=1,
    )

    sender.sign_transaction(tx)

    original_txid = tx.tx_id

    tampered_signature = bytearray.fromhex(tx.signature)
    tampered_signature[0] ^= 1
    tx.signature = bytes(tampered_signature).hex()

    new_txid = tx.calculate_id()

    assert new_txid != original_txid


def test_direct_secp256k1_round_trip():
    private_key = em.SigningKey.generate(curve=em.SECP256k1)

    public_key = private_key.verifying_key

    message = b"direct secp256k1 test"

    signature = private_key.sign_deterministic(
        message,
        hashfunc=hashlib.sha3_512,
    )

    assert public_key.verify(
        signature,
        message,
        hashfunc=hashlib.sha3_512,
    )
