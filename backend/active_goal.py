"""Structured, durable session goals and their agent-visible system context."""

from __future__ import annotations

from datetime import datetime, timezone
import re
import uuid
from typing import Any, Dict, Mapping

MAX_GOAL_TITLE_CHARS = 120
MAX_GOAL_SUMMARY_CHARS = 600


def _compact_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _bounded_sentence(value: str, limit: int) -> str:
    value = _compact_whitespace(value)
    if len(value) <= limit:
        return value
    shortened = value[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"{shortened or value[:limit - 1].rstrip()}…"


def _title_from_instruction(instruction: str) -> str:
    """Return a compact, deterministic UI caption without an LLM dependency."""
    text = _compact_whitespace(instruction)
    first_sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
    return _bounded_sentence(first_sentence, MAX_GOAL_TITLE_CHARS)


def normalize_active_goal(goal: Any) -> Dict[str, Any] | None:
    """Return bounded goal fields and transparently upgrade legacy ``text`` data."""
    if not isinstance(goal, Mapping):
        return None
    raw_instruction = _compact_whitespace(
        str(goal.get("raw_instruction") or goal.get("text") or "")
    )
    summary = _bounded_sentence(
        str(goal.get("summary") or raw_instruction), MAX_GOAL_SUMMARY_CHARS
    )
    title = _bounded_sentence(
        str(goal.get("title") or _title_from_instruction(summary)), MAX_GOAL_TITLE_CHARS
    )
    if not title or not summary:
        return None
    return {
        "id": str(goal.get("id") or "legacy-goal"),
        "title": title,
        "summary": summary,
        "raw_instruction": raw_instruction,
        "created_at": str(goal.get("created_at") or ""),
        "updated_at": str(goal.get("updated_at") or ""),
        "nudges_used": int(goal.get("nudges_used") or 0),
        "last_nudge": goal.get("last_nudge"),
    }


def create_active_goal(instruction: str) -> Dict[str, Any]:
    """Create the session representation for a user-provided goal.

    ``raw_instruction`` is retained for audit/debugging only. Agent context and
    UI indicators consume the bounded ``title`` and ``summary`` fields instead.
    """
    raw_instruction = instruction.strip()
    summary = _bounded_sentence(raw_instruction, MAX_GOAL_SUMMARY_CHARS)
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": f"goal_{uuid.uuid4().hex[:12]}",
        "title": _title_from_instruction(raw_instruction),
        "summary": summary,
        "raw_instruction": raw_instruction,
        "created_at": now,
        "updated_at": now,
        "nudges_used": 0,
        "last_nudge": None,
    }


def render_active_goal_system_message(goal: Any) -> str:
    """Render trusted agent context without exposing a slash-command literal.

    Embedded in the per-turn Agent State system message so the objective is
    re-injected on every LLM call, after history filtering and compaction.
    """
    normalized = normalize_active_goal(goal)
    if not normalized:
        return ""
    return (
        "## Active Goal\n"
        "[SYSTEM] The user has set the following active goal for this session. "
        "Treat it as durable operational context until it is replaced or cleared.\n"
        f"Title: {normalized['title']}\n"
        f"Instructions: {normalized['summary']}"
    )


def render_active_goal_event(goal: Any) -> str:
    """Render the auditable goal-update event stored in conversation history."""
    normalized = normalize_active_goal(goal)
    if not normalized:
        return "[SYSTEM] Active goal updated."
    return (
        "[SYSTEM] Active goal updated.\n"
        f"Goal: {normalized['title']}\n"
        f"Operational direction: {normalized['summary']}"
    )
