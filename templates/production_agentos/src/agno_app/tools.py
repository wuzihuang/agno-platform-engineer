"""Small, typed tools with explicit identity and side-effect boundaries."""

from __future__ import annotations

import hashlib

from agno.run import RunContext
from agno.tools import tool


def get_runtime_context(run_context: RunContext) -> dict[str, object]:
    """Return non-sensitive facts about the current authenticated run."""
    return {
        "authenticated": bool(run_context.user_id),
        "has_session": bool(run_context.session_id),
    }


@tool(requires_confirmation=True)
def request_human_handoff(
    run_context: RunContext,
    reason: str,
    idempotency_key: str,
) -> dict[str, str]:
    """Queue a human handoff in session state after the user confirms it.

    This starter intentionally does not call an external ticket system. Replace
    the session-state implementation with an idempotent business-service API.
    """
    if not run_context.user_id:
        return {
            "status": "rejected",
            "message": "Authenticated user identity is required.",
        }

    normalized_key = idempotency_key.strip()
    if not normalized_key:
        return {
            "status": "rejected",
            "message": "A non-empty idempotency key is required.",
        }

    if run_context.session_state is None:
        return {
            "status": "rejected",
            "message": "Session state is unavailable for this run.",
        }

    requests = run_context.session_state.setdefault("handoff_requests", [])
    for existing in requests:
        if existing.get("idempotency_key") == normalized_key:
            return {
                "status": "duplicate",
                "request_id": existing["request_id"],
                "message": "This handoff request was already queued.",
            }

    digest = hashlib.sha256(
        f"{run_context.user_id}:{normalized_key}".encode("utf-8")
    ).hexdigest()[:16]
    request_id = f"handoff_{digest}"
    requests.append(
        {
            "request_id": request_id,
            "idempotency_key": normalized_key,
            "reason": reason[:1000],
        }
    )
    run_context.session_state["handoff_requests"] = requests

    return {
        "status": "queued_in_session",
        "request_id": request_id,
        "message": "Queued in Agent session state; connect a real ticket service before production.",
    }
