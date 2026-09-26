# The Coin Purse — An Agent That Pays but Can't Be Drained

An LLM research agent (Claude, tool-calling) that buys data from x402-gated
endpoints with a small testnet USDC purse — and a policy layer, kept
deliberately separate from the agent code, that no prompt, tool argument,
or seller-supplied text can talk its way past. Built for the
**Road to Devcon VI: x402 Pay-Per-Call** track.

Arjun's rule: he wants to wake up to useful research, a readable record of
every coin spent, and proof the agent refused the rogue stall.

## How spending is enforced

All policy lives in `agent/policy.py` — nothing in `agent/agent.py` (the
only file that knows an LLM exists) or `agent/buyer.py` (the paid-fetch
tool) makes a spending decision. The policy hook is registered on the x402
client via `x402Client.on_before_payment_creation(policy.evaluate)`, which
the SDK calls **before it signs anything** — returning `AbortResult` blocks
the payment outright (raises `PaymentAbortedError`, caught in `buyer.py`
and turned into a clear refusal string, never a stack trace).

The SDK ships its own default spend-control filter; `buyer.py` explicitly
disables it (`client.set_spend_controls(False)`) so every decision
genuinely flows through this repo's own policy code, not an SDK default.

`evaluate()` checks, in order, against a fresh SQLite read every time — no
in-memory running total:

1. **Network allowlist** — only `eip155:84532` (Base Sepolia).
2. **Asset allowlist** — only the canonical testnet USDC contract. This one
   check is also what defeats spam tokens, unverified contracts, transfer
   hooks, and fee-on-transfer tokens: none of them are this address, so
   none of them are ever signed for, regardless of which specific way they'd
   otherwise misbehave.
3. **Per-call ceiling** — `PURSE_PER_CALL_MAX_ATOMIC` (default $0.10),
   compared in integer atomic units.
4. **Cumulative budget** — `total_spent_atomic()` (summed fresh from
   `purse_ledger.db`, confirmed-paid rows only) + the new quote must stay
   under `PURSE_TOTAL_BUDGET_ATOMIC` (default $5.00).

The `fetch_paid_data` tool's only argument is `url` — there is no field the
model can set to raise a limit, and the limits themselves are read from
environment/config, never from a tool result or model output.

## Repo layout

- `agent/policy.py` — the spending policy (see above). No agent/LLM code.
- `agent/ledger.py` — durable SQLite decision record (`purse_ledger.db`,
  gitignored — a fresh run creates it).
- `agent/buyer.py` — wires the x402 client + policy hooks; exposes
  `fetch_paid_data` as the only paid tool.
- `agent/agent.py` — the actual research agent (Claude, tool-calling).
- `sellers/honest_stall.py` — two reasonably-priced, correctly-configured
  x402 sellers.
- `sellers/rogue_stall.py` — one seller, three distinct abuses: an
  overpriced route ($4.99), a route quoting an unrecognized token, and a
  route whose resource description tries to talk the agent into raising
  its own budget.
- `tests/test_policy.py` — pure unit tests for the policy (no network, no
  LLM, no wallet).
- `scripts/run_demo.py` — runs the agent for real and writes
  `decision_records/sample_run.md`.

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: seller addresses, a funded Base Sepolia testnet wallet
# (EVM_PRIVATE_KEY — get test USDC from https://faucet.circle.com/), and
# an ANTHROPIC_API_KEY
```

Start both stalls (separate terminals):

```bash
uvicorn sellers.honest_stall:app --port 9001 --env-file .env
uvicorn sellers.rogue_stall:app --port 9002 --env-file .env
```

Run the agent for real:

```bash
python3 -m scripts.run_demo
```

This prints the agent's research summary and writes the full decision
record — every payment attempt, paid or refused, with a reason and (for
paid ones) the settlement transaction hash — to
`decision_records/sample_run.md`.

## Tests

```bash
pytest tests/ -v
```

## Stack

- Claude (`claude-sonnet-4-6`, tool-calling) via the `anthropic` Python SDK
- x402 Python SDK (`x402[evm,httpx]`), x402.org testnet facilitator, Base
  Sepolia, testnet USDC
- SQLite for the durable decision ledger
