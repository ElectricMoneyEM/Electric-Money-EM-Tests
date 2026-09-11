import importlib.util
import time
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
Block = em.Block
Wallet = em.Wallet
Transaction = em.Transaction
MerkleTree = em.MerkleTree


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


def test_initial_block_reward_is_25_em():
    assert em.block_subsidy(1) == 25 * em.COIN


def test_first_halving_reward_is_correct():
    height = em.HALVING_INTERVAL
    assert em.block_subsidy(height) == (25 * em.COIN) // 2


def test_second_halving_reward_is_correct():
    height = em.HALVING_INTERVAL * 2
    assert em.block_subsidy(height) == (25 * em.COIN) // 4


def test_valid_miner_reward_is_accepted(tmp_path):
    chain = make_chain(tmp_path)
    miner = Wallet()
    block = mine_valid_candidate(chain, miner)

    ok, reason, new_state = chain.validate_block(
        block,
        chain.chain[-1],
        state_before(chain),
        chain.chain,
    )

    assert ok
    assert reason == "ok"

    balances = new_state[0]
    total_issued = new_state[2]

    assert balances[miner.address] == 25 * em.COIN
    assert total_issued == 50 * em.COIN


def test_tampered_miner_reward_is_rejected(tmp_path):
    chain = make_chain(tmp_path)
    miner = Wallet()
    block = mine_valid_candidate(chain, miner)

    block.transactions[-1]["amount"] += 1

    ok, reason, _ = chain.validate_block(
        block,
        chain.chain[-1],
        state_before(chain),
        chain.chain,
    )

    assert not ok
    assert reason == "invalid miner reward"


def test_tampered_reward_issuance_is_rejected(tmp_path):
    chain = make_chain(tmp_path)
    miner = Wallet()
    block = mine_valid_candidate(chain, miner)

    block.transactions[-1]["issuance"] += 1

    ok, reason, _ = chain.validate_block(
        block,
        chain.chain[-1],
        state_before(chain),
        chain.chain,
    )

    assert not ok
    assert reason == "invalid reward issuance"


def test_reward_id_cannot_be_reused_after_reward_tampering(tmp_path):
    chain = make_chain(tmp_path)
    miner = Wallet()
    block = mine_valid_candidate(chain, miner)

    block.transactions[-1]["tx_id"] = "f" * 128

    ok, reason, _ = chain.validate_block(
        block,
        chain.chain[-1],
        state_before(chain),
        chain.chain,
    )

    assert not ok
    assert reason == "invalid Merkle root"


def test_transaction_burn_is_exact():
    tx = Transaction(
        sender_pubkey="a" * 128,
        recipient="b" * 128,
        amount=100_000,
        nonce=0,
        timestamp=1,
    )

    assert tx.burned() == 50


def test_transaction_receiver_tax_is_exact():
    tx = Transaction(
        sender_pubkey="a" * 128,
        recipient="b" * 128,
        amount=100_000,
        nonce=0,
        timestamp=1,
    )

    assert tx.receiver_tax() == 200


def test_transaction_net_amount_is_correct():
    tx = Transaction(
        sender_pubkey="a" * 128,
        recipient="b" * 128,
        amount=100_000,
        nonce=0,
        timestamp=1,
    )

    assert tx.net_amount() == 99_750


def test_annual_levy_split_is_exact():
    balance = 100_000

    treasury_tax, burned = Blockchain._annual_tax_split(balance)

    assert treasury_tax == 200
    assert burned == 50


def test_annual_levy_total_is_exact():
    balance = 100_000

    assert Blockchain._annual_tax_due(balance) == 250


# ============================================================
# INTEGRATED REWARD / LEVY / BURN STATE TRANSITION TESTS
# ============================================================


def test_real_transfer_updates_balance_treasury_and_burn(tmp_path):
    chain = make_chain(tmp_path)

    sender = Wallet()
    receiver = Wallet()
    miner = Wallet()

    now = int(time.time())
    amount = 1_000_000

    # Move an existing amount from the genesis allocation into
    # the synthetic sender wallet so total supply is preserved.
    chain.balances["Miner_Genesis"] -= amount
    chain.balances[sender.address] = amount

    chain.nonces[sender.address] = 0

    # Prevent the synthetic test wallet and genesis wallet from
    # becoming due for the annual levy during this block.
    chain.wallet_tax_anchor["Miner_Genesis"] = now
    chain.wallet_tax_anchor[sender.address] = now

    tx = Transaction(
        sender_pubkey=sender.public_key_hex,
        recipient=receiver.address,
        amount=amount,
        nonce=0,
        timestamp=now,
    )

    sender.sign_transaction(tx)

    assert chain.add_transaction(tx)

    issued_before = chain.total_issued
    burned_before = chain.total_burned
    treasury_before = chain.treasury_balance

    chain.mine_pending(miner.address)

    expected_burn = 500
    expected_treasury = 2_000
    expected_net = 997_500

    assert chain.balances[sender.address] == 0
    assert chain.balances[receiver.address] == expected_net

    assert chain.total_burned - burned_before == expected_burn
    assert chain.treasury_balance - treasury_before == expected_treasury

    # The transfer itself must not create new issuance.
    # The block reward, however, legitimately issues 25 EM.
    assert chain.total_issued - issued_before == 25 * em.COIN

    # The miner receives the normal block subsidy.
    assert chain.balances[miner.address] == 25 * em.COIN


def test_transfer_sender_pays_full_amount(tmp_path):
    chain = make_chain(tmp_path)

    sender = Wallet()
    receiver = Wallet()
    miner = Wallet()

    now = int(time.time())
    amount = 2_000_000

    chain.balances["Miner_Genesis"] -= amount
    chain.balances[sender.address] = amount

    chain.nonces[sender.address] = 0
    chain.wallet_tax_anchor["Miner_Genesis"] = now
    chain.wallet_tax_anchor[sender.address] = now

    tx = Transaction(
        sender_pubkey=sender.public_key_hex,
        recipient=receiver.address,
        amount=amount,
        nonce=0,
        timestamp=now,
    )

    sender.sign_transaction(tx)

    assert chain.add_transaction(tx)

    chain.mine_pending(miner.address)

    assert chain.balances[sender.address] == 0

    # Receiver gets only amount minus Treasury tax and burn.
    assert chain.balances[receiver.address] == (
        amount
        - tx.receiver_tax()
        - tx.burned()
    )


def test_annual_levy_really_changes_wallet_state():
    address = "a" * 128

    balance = 1_000_000
    anchor = 10_000
    timestamp = anchor + em.YEAR_SECONDS

    balances = {
        address: balance,
    }

    anchors = {
        address: anchor,
    }

    treasury_before = 0

    treasury_after, burned, new_anchors = (
        Blockchain._apply_annual_wallet_taxes(
            balances,
            anchors,
            treasury_before,
            timestamp,
        )
    )

    assert balances[address] == 997_500
    assert treasury_after == 2_000
    assert burned == 500
    assert new_anchors[address] == timestamp


def test_annual_levy_does_not_apply_before_anniversary():
    address = "b" * 128

    balance = 1_000_000
    anchor = 10_000
    timestamp = anchor + em.YEAR_SECONDS - 1

    balances = {
        address: balance,
    }

    anchors = {
        address: anchor,
    }

    treasury_after, burned, new_anchors = (
        Blockchain._apply_annual_wallet_taxes(
            balances,
            anchors,
            0,
            timestamp,
        )
    )

    assert balances[address] == balance
    assert treasury_after == 0
    assert burned == 0
    assert new_anchors[address] == anchor


def test_annual_levy_anchor_advances_by_exact_years():
    address = "c" * 128

    balance = 1_000_000
    anchor = 10_000
    timestamp = anchor + (2 * em.YEAR_SECONDS) + 123

    balances = {
        address: balance,
    }

    anchors = {
        address: anchor,
    }

    treasury_after, burned, new_anchors = (
        Blockchain._apply_annual_wallet_taxes(
            balances,
            anchors,
            0,
            timestamp,
        )
    )

    # First year:
    # Treasury = 2,000
    # Burn = 500
    # Remaining = 997,500
    #
    # Second year:
    # Treasury = 1,995
    # Burn = 498
    #
    # Final:
    # Treasury = 3,995
    # Burn = 998
    # Balance = 995,007

    assert balances[address] == 995_007
    assert treasury_after == 3_995
    assert burned == 998
    assert new_anchors[address] == anchor + (2 * em.YEAR_SECONDS)


def test_reward_increases_total_issued_exactly_once(tmp_path):
    chain = make_chain(tmp_path)
    miner = Wallet()

    issued_before = chain.total_issued

    block = mine_valid_candidate(chain, miner)

    ok, reason, new_state = chain.validate_block(
        block,
        chain.chain[-1],
        state_before(chain),
        chain.chain,
    )

    assert ok
    assert reason == "ok"

    issued_after = new_state[2]

    assert issued_after - issued_before == 25 * em.COIN


def test_final_supply_unit_can_be_issued_without_exceeding_cap(tmp_path):
    chain = make_chain(tmp_path)

    miner = Wallet()
    timestamp = int(time.time())

    state = (
        {},
        {},
        em.MAX_SUPPLY - 1,
        0,
        0,
        {},
        {miner.address: timestamp},
    )

    issuance = 1

    reward = {
        "type": "reward",
        "tx_id": chain.reward_id(
            miner.address,
            issuance,
            issuance,
            1,
        ),
        "recipient": miner.address,
        "amount": issuance,
        "issuance": issuance,
    }

    block = Block(
        index=1,
        previous_hash=chain.chain[-1].block_hash,
        transactions=[reward],
        timestamp=timestamp,
        nonce=0,
        difficulty=chain.expected_difficulty(chain.chain, 1),
        merkle_root=MerkleTree.compute_root(
            [reward["tx_id"]]
        ),
        extra_data="ELECTRIC-MONEY-CAP-TEST",
    )

    block.mine()

    ok, reason, new_state = chain.validate_block(
        block,
        chain.chain[-1],
        state,
        chain.chain,
        now=timestamp,
    )

    assert ok
    assert reason == "ok"
    assert new_state[2] == em.MAX_SUPPLY


def test_reward_cannot_issue_above_hard_cap(tmp_path):
    chain = make_chain(tmp_path)

    miner = Wallet()
    timestamp = int(time.time())

    state = (
        {},
        {},
        em.MAX_SUPPLY,
        0,
        0,
        {},
        {miner.address: timestamp},
    )

    reward = {
        "type": "reward",
        "tx_id": chain.reward_id(
            miner.address,
            1,
            1,
            1,
        ),
        "recipient": miner.address,
        "amount": 1,
        "issuance": 1,
    }

    block = Block(
        index=1,
        previous_hash=chain.chain[-1].block_hash,
        transactions=[reward],
        timestamp=timestamp,
        nonce=0,
        difficulty=chain.expected_difficulty(chain.chain, 1),
        merkle_root=MerkleTree.compute_root(
            [reward["tx_id"]]
        ),
        extra_data="ELECTRIC-MONEY-CAP-TEST",
    )

    block.mine()

    ok, reason, _ = chain.validate_block(
        block,
        chain.chain[-1],
        state,
        chain.chain,
        now=timestamp,
    )

    assert not ok

    # Once the hard cap is already reached, consensus issuance is zero.
    assert reason == "invalid reward issuance"


def test_treasury_distribution_uses_verified_miner_work():
    miner_a = "a" * 128
    miner_b = "b" * 128

    balances = {
        miner_a: 0,
        miner_b: 0,
    }

    miner_work = {
        miner_a: 1,
        miner_b: 3,
    }

    treasury = 10_000

    remaining, remaining_work = Blockchain._distribute_treasury(
        balances,
        treasury,
        miner_work,
    )

    assert remaining == 0
    assert remaining_work == {}

    assert balances[miner_a] == 2_500
    assert balances[miner_b] == 7_500


def test_monthly_treasury_sweep_occurs_at_epoch():
    miner = "d" * 128

    balances = {
        miner: 0,
    }

    miner_work = {
        miner: 1,
    }

    treasury = 10_000

    block_index = em.MINER_REWARD_EPOCH_BLOCKS

    remaining, remaining_work = Blockchain._end_month_if_needed(
        balances,
        treasury,
        miner_work,
        block_index,
    )

    assert remaining == 0
    assert remaining_work == {}
    assert balances[miner] == 10_000
