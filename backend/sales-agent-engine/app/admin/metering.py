"""Usage metering: every completed model call is recorded with the run it belongs to."""

from __future__ import annotations

from typing import Any

from app.models.router import UsageMeter
from app.models.types import Completion, TaskSpec
from app.platform.langgraph_runtime import current_context


def usage_meter(store: Any) -> UsageMeter:
    async def meter(task: TaskSpec, completion: Completion, duration_ms: int) -> None:
        try:
            ctx = current_context()  # only inside an agent run
        except Exception:
            ctx = None
        await store.record_model_call(
            tenant_id=getattr(ctx, "tenant_id", None),
            user_id=getattr(ctx, "user_id", None),
            session_id=getattr(ctx, "session_id", None),
            purpose=task.purpose,
            provider=completion.provider,
            model=completion.model,
            input_tokens=completion.usage.input_tokens,
            output_tokens=completion.usage.output_tokens,
            duration_ms=duration_ms,
        )

    return meter
