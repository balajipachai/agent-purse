"""The purse's spending policy — deliberately separate from agent.py.

Nothing here reads from, or is influenced by, model output, tool arguments,
or seller-supplied text. The hook in `evaluate()` runs *before* the x402
client signs anything (registered via x402Client.on_before_payment_creation)
and can only see the structured payment requirements the seller quoted —
never free text, never a tool argument, never what the model "believes"
its budget is. `record_settlement()` is the only place a 'paid' row is
ever written, and only after the facilitator confirms settlement succeeded.
"""

import os

from x402.schemas.hooks import AbortResult, PaymentCreationContext, PaymentResponseContext

from agent.ledger import Decision, record_decision, total_spent_atomic

# --- Hard policy configuration. Read from environment/config only — never
# from a tool argument, a tool result, or anything the model can write. ---

ALLOWED_NETWORK = os.environ.get("PURSE_ALLOWED_NETWORK", "eip155:84532")  # Base Sepolia only
ALLOWED_ASSET = os.environ.get(
    "PURSE_ALLOWED_ASSET", "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
).lower()  # canonical Base Sepolia testnet USDC — no other asset is ever paid,
# which is also the single check that defeats spam tokens, unverified
# contracts, transfer hooks, and fee-on-transfer tokens all at once: none
# of them are this address, so none of them are ever signed for.

PER_CALL_MAX_ATOMIC = int(os.environ.get("PURSE_PER_CALL_MAX_ATOMIC", "100000"))   # $0.10
TOTAL_BUDGET_ATOMIC = int(os.environ.get("PURSE_TOTAL_BUDGET_ATOMIC", "5000000"))  # $5.00


def resource_url(payment_required) -> str:
    try:
        return payment_required.resource.url
    except AttributeError:
        return "<unknown>"


def resource_description(payment_required) -> str | None:
    try:
        return payment_required.resource.description
    except AttributeError:
        return None


def evaluate(context: PaymentCreationContext) -> AbortResult | None:
    """x402 on_before_payment_creation hook — runs before any signing."""
    req = context.selected_requirements
    seller_url = resource_url(context.payment_required)
    description = resource_description(context.payment_required)
    quoted = int(req.amount)

    def refuse(reason: str) -> AbortResult:
        record_decision(
            Decision(
                seller_url=seller_url,
                resource_description=description,
                network=req.network,
                asset=req.asset,
                quoted_amount_atomic=quoted,
                decision="refused",
                reason=reason,
            )
        )
        return AbortResult(reason=reason)

    if req.network != ALLOWED_NETWORK:
        return refuse(f"network '{req.network}' is not on the allowlist (only {ALLOWED_NETWORK})")

    if req.asset.lower() != ALLOWED_ASSET:
        return refuse(f"asset '{req.asset}' is not on the allowlist (only testnet USDC is accepted)")

    if quoted > PER_CALL_MAX_ATOMIC:
        return refuse(
            f"quoted {quoted} atomic units exceeds the per-call ceiling of {PER_CALL_MAX_ATOMIC}"
        )

    spent_so_far = total_spent_atomic()
    if spent_so_far + quoted > TOTAL_BUDGET_ATOMIC:
        return refuse(
            f"paying {quoted} would bring total spend to {spent_so_far + quoted} atomic units, "
            f"over the {TOTAL_BUDGET_ATOMIC} budget (already spent {spent_so_far})"
        )

    return None  # approved — the x402 client proceeds to sign


def record_settlement(
    context: PaymentResponseContext,
    fallback_seller_url: str | None = None,
    fallback_description: str | None = None,
) -> None:
    """x402 on_payment_response hook — the only place a 'paid' row is
    written, and only once the facilitator confirms settlement.

    context.payment_required is typically None by the time this fires (the
    402 that triggered payment already happened) — the caller passes the
    URL/description captured earlier, in evaluate(), as a fallback.
    """
    req = context.requirements
    seller_url = (
        resource_url(context.payment_required) if context.payment_required else fallback_seller_url
    ) or "<unknown>"
    description = (
        resource_description(context.payment_required) if context.payment_required else fallback_description
    )
    settled = context.settle_response

    if settled is None:
        return

    if settled.success:
        record_decision(
            Decision(
                seller_url=seller_url,
                resource_description=description,
                network=req.network,
                asset=req.asset,
                quoted_amount_atomic=int(settled.amount) if settled.amount else int(req.amount),
                decision="paid",
                reason="payment settled successfully",
                tx_hash=settled.transaction,
            )
        )
    else:
        record_decision(
            Decision(
                seller_url=seller_url,
                resource_description=description,
                network=req.network,
                asset=req.asset,
                quoted_amount_atomic=int(req.amount),
                decision="refused",
                reason=f"settlement failed: {settled.error_message or settled.error_reason}",
            )
        )
