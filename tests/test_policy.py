"""Pure unit tests for the spending policy — no network, no LLM, no wallet.
Each test isolates the ledger to a temp file so runs never touch (or are
polluted by) the real purse_ledger.db used by live demo runs.
"""

from types import SimpleNamespace

import pytest

from agent import ledger, policy


@pytest.fixture(autouse=True)
def isolated_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "DB_PATH", tmp_path / "test_ledger.db")
    ledger.init_db()


def _req(network="eip155:84532", asset=None, amount="20000"):
    return SimpleNamespace(network=network, asset=asset or policy.ALLOWED_ASSET, amount=amount)


def _payment_required(url="http://seller.example/data", description="test resource"):
    return SimpleNamespace(resource=SimpleNamespace(url=url, description=description))


def _before_context(**req_kwargs):
    return SimpleNamespace(
        selected_requirements=_req(**req_kwargs),
        payment_required=_payment_required(),
    )


def test_approves_payment_within_ceiling_and_budget():
    result = policy.evaluate(_before_context(amount="20000"))
    assert result is None


def test_refuses_wrong_network():
    result = policy.evaluate(_before_context(network="eip155:8453"))  # mainnet, not testnet
    assert result is not None
    assert "allowlist" in result.reason


def test_refuses_wrong_asset():
    result = policy.evaluate(_before_context(asset="0x1234567890123456789012345678901234567890"))
    assert result is not None
    assert "allowlist" in result.reason


def test_refuses_over_per_call_ceiling(monkeypatch):
    monkeypatch.setattr(policy, "PER_CALL_MAX_ATOMIC", 100_000)
    result = policy.evaluate(_before_context(amount="4990000"))  # the $4.99 rogue quote
    assert result is not None
    assert "ceiling" in result.reason


def test_refuses_when_cumulative_budget_would_be_exceeded(monkeypatch):
    monkeypatch.setattr(policy, "TOTAL_BUDGET_ATOMIC", 50_000)
    # Simulate 40_000 already spent in a *previous* process — write it directly.
    ledger.record_decision(
        ledger.Decision(
            seller_url="http://seller.example/already-paid",
            resource_description=None,
            network=policy.ALLOWED_NETWORK,
            asset=policy.ALLOWED_ASSET,
            quoted_amount_atomic=40_000,
            decision="paid",
            reason="payment settled successfully",
            tx_hash="0xdeadbeef",
        )
    )
    result = policy.evaluate(_before_context(amount="20000"))  # 40_000 + 20_000 > 50_000
    assert result is not None
    assert "budget" in result.reason


def test_spend_is_persisted_and_read_back_fresh():
    assert ledger.total_spent_atomic() == 0
    ledger.record_decision(
        ledger.Decision(
            seller_url="http://seller.example/paid",
            resource_description=None,
            network=policy.ALLOWED_NETWORK,
            asset=policy.ALLOWED_ASSET,
            quoted_amount_atomic=15_000,
            decision="paid",
            reason="payment settled successfully",
            tx_hash="0xabc",
        )
    )
    # A fresh query (no cached variable) reflects the persisted row.
    assert ledger.total_spent_atomic() == 15_000


def test_refused_attempts_never_count_toward_spend():
    ledger.record_decision(
        ledger.Decision(
            seller_url="http://seller.example/refused",
            resource_description=None,
            network=policy.ALLOWED_NETWORK,
            asset="0xnotusdc",
            quoted_amount_atomic=999_000,
            decision="refused",
            reason="asset not on allowlist",
        )
    )
    assert ledger.total_spent_atomic() == 0


def test_ledger_rejects_non_integer_amount():
    with pytest.raises(TypeError):
        ledger.record_decision(
            ledger.Decision(
                seller_url="http://seller.example/bad",
                resource_description=None,
                network=policy.ALLOWED_NETWORK,
                asset=policy.ALLOWED_ASSET,
                quoted_amount_atomic=0.02,  # float — must be rejected
                decision="paid",
                reason="should never be accepted",
            )
        )


def test_paid_fetch_tool_has_no_spend_control_argument():
    from agent.buyer import fetch_paid_data

    schema = fetch_paid_data.input_schema
    properties = schema.get("properties", schema)  # tolerate either shape
    field_names = set(properties.keys())
    assert field_names == {"url"}, f"tool exposes unexpected fields: {field_names}"
