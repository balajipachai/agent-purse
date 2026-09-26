"""Runs the agent against both stalls for real and writes the resulting
decision record into decision_records/sample_run.md — the deliverable the
brief asks for. Requires both sellers running (see README) and a funded
testnet wallet.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from agent.agent import RESEARCH_QUESTION, run_research
from agent.ledger import all_decisions, total_spent_atomic

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "decision_records" / "sample_run.md"


def _format_atomic_usdc(amount: int) -> str:
    return f"${amount / 1_000_000:.6f}".rstrip("0").rstrip(".")


def render_record(summary: str) -> str:
    decisions = all_decisions()
    lines = [
        "# Sample decision record — real testnet run",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat()}",
        "",
        f"**Research question:** {RESEARCH_QUESTION}",
        "",
        "## Agent's research summary",
        "",
        summary,
        "",
        "## Every payment decision, in order",
        "",
        "| # | Seller URL | Resource | Quoted | Decision | Reason | Tx |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, d in enumerate(decisions, start=1):
        tx = f"`{d['tx_hash'][:14]}...`" if d["tx_hash"] else "—"
        reason = d["reason"].replace("|", "\\|")
        desc = (d["resource_description"] or "").replace("|", "\\|")
        lines.append(
            f"| {i} | {d['seller_url']} | {desc} | "
            f"{_format_atomic_usdc(d['quoted_amount_atomic'])} | {d['decision']} | {reason} | {tx} |"
        )
    lines += [
        "",
        f"**Total spent this run:** {_format_atomic_usdc(total_spent_atomic())} testnet USDC",
    ]
    return "\n".join(lines)


async def main() -> None:
    summary = await run_research()
    print(summary)
    print()
    record = render_record(summary)
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(record)
    print(f"Decision record written to {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
