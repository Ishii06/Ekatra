"""Structured agent message model for Ekatra agent communication.

Communication is plain, deterministic data that flows between agents through
the in-memory :class:`~ekatra.orchestration.bus.MessageBus`. It is fully
independent from any LLM: no model output is required to create, validate,
route, or observe a message in this milestone.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

# Recipient marker for a message broadcast to every registered agent.
BROADCAST_RECIPIENT = "*"


class MessageType(str, Enum):
    """The fixed set of message types used by the Ekatra workflow."""

    TASK_ASSIGNMENT = "TASK_ASSIGNMENT"
    STATUS_UPDATE = "STATUS_UPDATE"
    RESULT = "RESULT"
    REVIEW_REQUEST = "REVIEW_REQUEST"
    REVIEW_FEEDBACK = "REVIEW_FEEDBACK"
    ERROR = "ERROR"
    INFORMATION = "INFORMATION"


class AgentMessage(BaseModel):
    """A single structured message exchanged between agents.

    Attributes:
        message_id: Stable, deterministic identifier unique within a run.
        sender_agent: ID of the sending agent.
        recipient_agent: ID of the receiving agent, or ``*`` for a broadcast.
        message_type: One of :class:`MessageType`.
        content: Human-readable message body.
        related_task_id: ID of the task this message refers to, if any.
        timestamp: ISO-8601 timestamp assigned by the bus.
    """

    model_config = ConfigDict(frozen=True)

    message_id: str
    sender_agent: str
    recipient_agent: str
    message_type: MessageType
    content: str
    related_task_id: str | None = None
    timestamp: str

    @field_validator("message_id", "sender_agent", "recipient_agent", "content")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict for storage in the shared state."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentMessage":
        """Rebuild a message from a serialized dict (see :meth:`to_dict`)."""
        payload = dict(data)
        payload["message_type"] = MessageType(payload["message_type"])
        return cls(**payload)


__all__ = ["AgentMessage", "BROADCAST_RECIPIENT", "MessageType"]