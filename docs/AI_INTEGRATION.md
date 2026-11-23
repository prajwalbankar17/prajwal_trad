# AI Integration

Claude is a **research assistant that reads**. It analyses data the platform
has already computed and returns commentary. It is not part of the trading
path, and cannot be.

## Status: blocked on an API key

Without `ANTHROPIC_API_KEY` and `AI_ENABLED=true`, every AI route raises
`FeatureBlockedError` and the UI renders a blocked-feature panel. **No analysis
is ever simulated.**

```
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-5-5
AI_ENABLED=true
AI_MONTHLY_BUDGET_USD=20
```

## Hard limits

The AI **cannot**:

- place, modify or cancel any order — it has no order interface at all
- read or write the database — it receives a dict and returns a string
- execute SQL or shell commands — it is given no tools
- change risk limits or broker credentials
- delete any record
- bypass paper-trading controls

These are not prompt instructions. They are the absence of capability: the
client calls `messages.create()` with a system prompt and one user message, and
no `tools` parameter. There is nothing for the model to call.

## What it is used for

| Task | Prompt | Input |
|---|---|---|
| Explain a signal | `explain_signal` v1 | Instrument, strategy, levels, every condition evaluated, indicator values |
| Review a backtest | `analyse_backtest` v1 | Metrics, coverage, in-sample vs out-of-sample |
| Analyse failed trades | `analyse_failed_trades` v1 | Losing trades with exit reasons and MAE/MFE |
| Market summary | `market_summary` v1 | Session stats from our own data |
| Compare strategies | `strategy_comparison` v1 | Metrics table |

Every prompt carries the same system preamble: analyse only what you are given,
say so when the data is insufficient, and never claim profitability from a small
sample.

## Prompt versioning

Prompts are `Prompt(name, version, task, system, template)` in
`app/ai/prompts.py`, and both name and version are recorded with the output. A
prompt can change without making last month's analysis unexplainable.

## Recording

Every call writes two rows — on failure as well as success:

**`ai_analysis`** — task, prompt name and version, model, input context,
output, relations to signal/strategy/backtest, `is_research_only`, error.

**`ai_usage_logs`** — model, timestamp, input/output/cache tokens, estimated
cost, latency, success, error.

## Cost control

Month-to-date spend is checked **before** the call. Exceeding
`AI_MONTHLY_BUDGET_USD` raises `FeatureBlockedError` with the current spend.
`GET /ai/usage` reports totals and recent calls; the AI Research page shows
budget, spend and remaining.

Cost is estimated from published per-million-token rates in
`app/ai/client.py`. **These are estimates for budgeting, not billing** — verify
against current Anthropic pricing.

## Output validation

`validate_output()` runs deterministic checks on whatever the model said and
flags:

- overconfident language ("guaranteed", "risk-free", "cannot lose", "100%
  accurate")
- instruction-shaped text ("buy now", "place the order", "enter immediately")

The platform never acts on AI output, but a human reads it and might — so
overconfidence is flagged rather than passed through unremarked. Everything is
labelled *AI-generated research. Not a trading instruction.*

## MCP

The specification calls for read-only MCP integrations. Not implemented. If
added, it must be **read-only market data and analytics**: no SQL execution, no
shell, no order interface, no credential access. The boundary above is the
requirement, whatever the transport.

## Cost expectations

At Sonnet rates, a signal explanation with ~2,000 input and ~600 output tokens
costs roughly $0.015. A $20 monthly budget is on the order of a thousand
explanations. Use the cheapest model that does the job — the prompts are not
demanding.
