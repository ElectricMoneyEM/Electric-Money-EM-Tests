import importlib.util
from pathlib import Path
import random
import string
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


def make_chain(tmp_path):
    return Blockchain(
        node_port=0,
        db_file=str(tmp_path / "chain.json"),
    )


def random_string(rng, max_length=300):
    length = rng.randint(0, max_length)

    alphabet = (
        string.ascii_letters
        + string.digits
        + string.punctuation
        + " \t\n"
    )

    return "".join(rng.choice(alphabet) for _ in range(length))


def random_value(rng):
    values = [
        None,
        True,
        False,
        0,
        1,
        -1,
        rng.randint(-10**12, 10**12),
        10**100,
        -10**100,
        "",
        random_string(rng),
        [],
        {},
        [None, 1, "x"],
        {"random": "value"},
    ]

    return rng.choice(values)


def random_transaction_dict(rng):
    return {
        "sender_pubkey": random_value(rng),
        "recipient": random_value(rng),
        "amount": random_value(rng),
        "nonce": random_value(rng),
        "timestamp": random_value(rng),
        "signature": random_value(rng),
        "tx_id": random_value(rng),
    }


def random_block_dict(rng):
    return {
        "index": random_value(rng),
        "previous_hash": random_value(rng),
        "timestamp": random_value(rng),
        "difficulty": random_value(rng),
        "nonce": random_value(rng),
        "transactions": random_value(rng),
        "merkle_root": random_value(rng),
        "hash": random_value(rng),
        "miner": random_value(rng),
        "reward": random_value(rng),
    }


def test_random_transaction_inputs_do_not_crash(tmp_path):
    rng = random.Random(0xE11EC7)

    chain = make_chain(tmp_path)

    for _ in range(500):
        data = random_transaction_dict(rng)

        try:
            tx = em.Transaction.from_dict(data)
        except (
            KeyError,
            TypeError,
            ValueError,
            AttributeError,
        ):
            continue

        try:
            result = chain.validate_transaction(tx)
        except (
            KeyError,
            TypeError,
            ValueError,
            AttributeError,
            IndexError,
        ):
            assert False, (
                "Random transaction caused an unexpected exception:\n"
                f"{data!r}"
            )

        assert isinstance(result, tuple)
        assert result[0] is False


def test_random_block_inputs_do_not_crash(tmp_path):
    rng = random.Random(0xB10C2026)

    chain = make_chain(tmp_path)

    for _ in range(500):
        data = random_block_dict(rng)

        try:
            block = em.Block.from_dict(data)
        except (
            KeyError,
            TypeError,
            ValueError,
            AttributeError,
        ):
            continue

        try:
            result = chain.validate_block(block)
        except (
            KeyError,
            TypeError,
            ValueError,
            AttributeError,
            IndexError,
        ):
            assert False, (
                "Random block caused an unexpected exception:\n"
                f"{data!r}"
            )

        assert isinstance(result, tuple)
        assert result[0] is False


def test_random_chain_candidates_do_not_crash(tmp_path):
    rng = random.Random(0xC41A2026)

    chain = make_chain(tmp_path)

    for _ in range(300):
        candidate = []

        length = rng.randint(0, 5)

        for _ in range(length):
            data = random_block_dict(rng)

            try:
                block = em.Block.from_dict(data)
            except (
                KeyError,
                TypeError,
                ValueError,
                AttributeError,
            ):
                block = random_value(rng)

            candidate.append(block)

        try:
            result = chain.validate_chain(candidate)
        except (
            KeyError,
            TypeError,
            ValueError,
            AttributeError,
            IndexError,
        ):
            assert False, (
                "Random chain candidate caused an unexpected exception:\n"
                f"{candidate!r}"
            )

        assert isinstance(result, tuple)
        assert result[0] is False
