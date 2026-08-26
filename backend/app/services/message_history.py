"""Shared conversation-history prompt rendering.

Used by the grounded-answer flow and the study-plan flow so the
``label：excerpt`` rendering and char budgeting stay identical everywhere.
"""

from collections.abc import Sequence
from typing import Protocol


class MessageLike(Protocol):
    # Read-only properties so concrete models with narrower literal types
    # (e.g. ConversationMessage.role as Literal["user", "assistant"]) satisfy
    # the protocol despite attribute invariance.
    @property
    def role(self) -> str: ...

    @property
    def content(self) -> str: ...


def render_message_history(
    messages: Sequence[MessageLike],
    *,
    assistant_label: str,
    max_messages: int,
    max_chars: int,
) -> str:
    """Render recent messages as ``label：excerpt`` lines under a char budget.

    ``messages`` must be ordered oldest→newest; only the last ``max_messages``
    are considered, and once the budget is exhausted the remaining older-side
    messages are skipped rather than split mid-sentence.
    """
    recent = list(messages)[-max_messages:]
    rendered: list[str] = []
    remaining = max_chars
    for message in recent:
        label = "学习者" if message.role == "user" else assistant_label
        content = message.content.strip()
        if not content or remaining <= 0:
            continue
        excerpt = content[:remaining]
        rendered.append(f"{label}：{excerpt}")
        remaining -= len(excerpt)
    return "\n\n".join(rendered)
