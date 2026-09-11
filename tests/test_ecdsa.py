import hashlib
import importlib.util
from pathlib import Path
import sys

import pytest
from ecdsa import SECP256k1, SigningKey


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "electric_money_v14.py"

spec = importlib.util.spec_from_file_location(
    "electric_money_v14",
    MODULE_PATH,
)

em = importlib.util.module_from_spec(spec)

assert spec.loader is not None

# Necessario per il corretto funzionamento di @dataclass
sys.modules[spec.name] = em

spec.loader.exec_module(em)

Wallet = em.Wallet
Transaction = em.Transaction


def make_transaction(
    sender,
    recipient,
    amount=1000,
    nonce=1,
    timestamp=1_700_000_000,
):
    return Transaction(
        sender_pubkey=sender.public_key_hex,
        recipient=recipient.address,
        amount=amount,
        nonce=nonce,
        timestamp=timestamp,
    )


def test_secp256k1_curve_is_used():
    wallet = Wallet()

    assert wallet._private_key.curve.name == SECP256k1.name


def test_wallet_sign_and_verify():
    wallet = Wallet()

    message = b"Electric Money"
    signature = wallet.sign(message)

    assert Wallet.verify(
        wallet.public_key_hex,
        message,
        signature,
    )


def test_wrong_message_is_rejected():
    wallet = Wallet()

    signature = wallet.sign(b"Electric Money")

    assert not Wallet.verify(
        wallet.public_key_hex,
        b"Tampered message",
        signature,
    )


def test_wrong_public_key_is_rejected():
    wallet = Wallet()
    other_wallet = Wallet()

    message = b"Electric Money"
    signature = wallet.sign(message)

    assert not Wallet.verify(
        other_wallet.public_key_hex,
        message,
        signature,
    )


def test_tampered_signature_is_rejected():
    wallet = Wallet()

    message = b"Electric Money"
    signature = wallet.sign(message)

    tampered = bytearray.fromhex(signature)
    tampered[-1] ^= 1

    assert not Wallet.verify(
        wallet.public_key_hex,
        message,
        bytes(tampered).hex(),
    )


def test_malformed_signature_is_rejected():
    wallet = Wallet()

    assert not Wallet.verify(
        wallet.public_key_hex,
        b"Electric Money",
        "00",
    )


def test_public_key_tampering_is_rejected():
    wallet = Wallet()
    other_wallet = Wallet()

    message = b"Electric Money"
    signature = wallet.sign(message)

    # Use another valid public key instead of randomly corrupting
    # a key and creating an invalid elliptic-curve point.
    assert not Wallet.verify(
        other_wallet.public_key_hex,
        message,
        signature,
    )


def test_deterministic_signature():
    wallet = Wallet()

    message = b"Electric Money deterministic test"

    sig1 = wallet.sign(message)
    sig2 = wallet.sign(message)

    assert sig1 == sig2


def test_different_messages_produce_different_signatures():
    wallet = Wallet()

    sig1 = wallet.sign(b"message one")
    sig2 = wallet.sign(b"message two")

    assert sig1 != sig2


def test_address_derivation():
    wallet = Wallet()

    expected = hashlib.sha3_512(
        bytes.fromhex(wallet.public_key_hex)
    ).hexdigest()

    assert wallet.address == expected
    assert Wallet.address_from_pubkey(
        wallet.public_key_hex
    ) == expected


def test_transaction_signature_verifies():
    sender = Wallet()
    recipient = Wallet()

    tx = make_transaction(
        sender,
        recipient,
    )

    sender.sign_transaction(tx)

    assert Wallet.verify(
        sender.public_key_hex,
        tx.signing_bytes(),
        tx.signature,
    )


@pytest.mark.parametrize(
    "field,new_value",
    [
        ("amount", 2000),
        ("nonce", 999),
        ("timestamp", 1_700_000_001),
        ("recipient", "b" * 128),
    ],
)
def test_transaction_tampering_is_rejected(field, new_value):
    sender = Wallet()
    recipient = Wallet()

    tx = make_transaction(
        sender,
        recipient,
    )

    sender.sign_transaction(tx)

    setattr(tx, field, new_value)

    assert not Wallet.verify(
        sender.public_key_hex,
        tx.signing_bytes(),
        tx.signature,
    )


def test_transaction_sender_pubkey_tampering_is_rejected():
    sender = Wallet()
    attacker = Wallet()
    recipient = Wallet()

    tx = make_transaction(
        sender,
        recipient,
    )

    sender.sign_transaction(tx)

    tx.sender_pubkey = attacker.public_key_hex

    assert not Wallet.verify(
        tx.sender_pubkey,
        tx.signing_bytes(),
        tx.signature,
    )


def test_transaction_txid_changes_when_signature_changes():
    sender = Wallet()
    recipient = Wallet()

    tx = make_transaction(
        sender,
        recipient,
    )

    sender.sign_transaction(tx)

    original_txid = tx.tx_id

    tampered_signature = bytearray.fromhex(
        tx.signature
    )

    tampered_signature[-1] ^= 1

    tx.signature = bytes(tampered_signature).hex()

    assert tx.calculate_id() != original_txid


def test_direct_secp256k1_library_round_trip():
    signing_key = SigningKey.generate(
        curve=SECP256k1
    )

    verifying_key = signing_key.verifying_key

    message = b"Electric Money / SECP256k1"

    signature = signing_key.sign_deterministic(
        message,
        hashfunc=hashlib.sha3_512,
    )

    assert verifying_key.verify(
        signature,
        message,
        hashfunc=hashlib.sha3_512,
    )
