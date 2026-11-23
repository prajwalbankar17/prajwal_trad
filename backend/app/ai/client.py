"""Anthropic Claude client.

Constraints this wrapper enforces, because the AI must never be a route to the
trading system:

* **Read-only context.** The caller assembles a plain dict of already-computed
  numbers. The model receives text. It has no tools, no database handle, no
  shell, and no order interface.
* **Everything is recorded.** Prompt name and version, model, input context,
  output, token counts, estimated cost and latency go to `ai_analysis` and
  `ai_usage_logs` whether the call succeeds or fails.
* **Budget is enforced before the call.** Month-to-date spend is checked
  against AI_MONTHLY_BUDGET_USD and the call is refused if it would exceed it.
* **Blocked, not faked.** Without ANTHROPIC_API_KEY the feature raises
  `FeatureBlockedError`. It never returns a canned "analysis".
"""

from __future__ import annotations

import time
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.prompts import Prompt
from app.core.config import settings
from app.core.exceptions import FeatureBlockedError
from app.core.logging import get_logger
from app.core.market_calendar import now_ist
from app.models.ai import AIAnalysis, AIUsageLog

log = get_logger(__name__)

AI_NOT_CONFIGURED = (
    "AI research is not available: ANTHROPIC_API_KEY is not set, or AI_ENABLED "
    "is false. Set both to enable it. No analysis is simulated when the key is "
    "absent."
)

# USD per million tokens. Verify against current Anthropic pricing before
# relying on the cost figures; they are estimates for budgeting, not billing.
PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-5": (15.0, 75.0),
    "claude-sonnet-5-5": (3.0, 15.0),
    "claude-haiku-5-5": (0.80, 4.0),
}
DEFAULT_PRICING = (3.0, 15.0)


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    in_rate, out_rate = PRICING.get(model, DEFAULT_PRICING)
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000


def month_to_date_spend(db: Session) -> float:
    start = now_ist().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = db.scalar(
        select(func.coalesce(func.sum(AIUsageLog.estimated_cost_usd), 0)).where(
            AIUsageLog.called_at >= start
        )
    )
    return float(total or 0)


class ClaudeClient:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.model = settings.ANTHROPIC_MODEL

    @property
    def available(self) -> bool:
        return settings.ai_configured

    def status(self) -> dict:
        spend = month_to_date_spend(self.db) if self.available else 0.0
        return {
            "enabled": self.available,
            "model": self.model if self.available else None,
            "blocked_reason": None if self.available else AI_NOT_CONFIGURED,
            "monthly_budget_usd": settings.AI_MONTHLY_BUDGET_USD,
            "month_to_date_spend_usd": round(spend, 4),
            "budget_remaining_usd": round(
                max(settings.AI_MONTHLY_BUDGET_USD - spend, 0), 4
            ),
            "constraints": [
                "Read-only: no tools, no database access, no shell.",
                "Cannot place, modify or cancel any order.",
                "Output is labelled research, never a trading instruction.",
            ],
        }

    def run(
        self,
        prompt: Prompt,
        context: dict,
        *,
        user_id: uuid.UUID | None = None,
        related_signal_id: uuid.UUID | None = None,
        related_strategy_id: uuid.UUID | None = None,
        related_backtest_job_id: uuid.UUID | None = None,
        max_tokens: int = 1500,
    ) -> AIAnalysis:
        if not self.available:
            raise FeatureBlockedError(AI_NOT_CONFIGURED, details={"docs": "docs/AI_INTEGRATION.md"})

        spend = month_to_date_spend(self.db)
        if spend >= settings.AI_MONTHLY_BUDGET_USD:
            raise FeatureBlockedError(
                f"AI monthly budget of ${settings.AI_MONTHLY_BUDGET_USD} is exhausted "
                f"(${spend:.4f} spent). Raise AI_MONTHLY_BUDGET_USD to continue.",
                details={"month_to_date_spend_usd": round(spend, 4)},
            )

        analysis = AIAnalysis(
            task=prompt.task,
            model=self.model,
            user_id=user_id,
            input_context={"prompt": prompt.name, "version": prompt.version, **context},
            related_signal_id=related_signal_id,
            related_strategy_id=related_strategy_id,
            related_backtest_job_id=related_backtest_job_id,
            is_research_only=True,
        )
        self.db.add(analysis)
        self.db.flush()

        started = time.perf_counter()
        usage = AIUsageLog(
            analysis_id=analysis.id, model=self.model, called_at=now_ist()
        )

        try:
            import anthropic

            client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            response = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=prompt.system,
                messages=[{"role": "user", "content": prompt.render(context)}],
            )
            text = "".join(
                block.text for block in response.content if getattr(block, "type", "") == "text"
            )
            analysis.output_text = text
            usage.input_tokens = response.usage.input_tokens
            usage.output_tokens = response.usage.output_tokens
            usage.success = True
        except FeatureBlockedError:
            raise
        except Exception as exc:
            analysis.error = f"{type(exc).__name__}: {exc}"
            usage.success = False
            usage.error = analysis.error
            log.exception("ai_call_failed", task=prompt.task)
        finally:
            usage.latency_ms = int((time.perf_counter() - started) * 1000)
            usage.estimated_cost_usd = estimate_cost(
                self.model, usage.input_tokens, usage.output_tokens
            )
            self.db.add(usage)
            self.db.commit()
            self.db.refresh(analysis)

        return analysis


def validate_output(analysis: AIAnalysis) -> dict:
    """Deterministic checks applied to whatever the model said.

    The platform does not act on AI output, but the output is shown to a human
    who might - so overconfident language is flagged rather than passed through
    unremarked.
    """
    text = (analysis.output_text or "").lower()
    warnings: list[str] = []

    overconfident = [
        "guaranteed", "risk-free", "cannot lose", "will definitely",
        "sure shot", "100% accurate", "no risk",
    ]
    for phrase in overconfident:
        if phrase in text:
            warnings.append(f"Output contains overconfident language: '{phrase}'.")

    if any(word in text for word in ("buy now", "place the order", "enter immediately")):
        warnings.append(
            "Output reads as a trading instruction. It is research commentary; "
            "the platform does not act on it."
        )

    return {
        "validated": not warnings,
        "warnings": warnings,
        "label": "AI-generated research. Not a trading instruction.",
    }
