"""In-memory message bus for agent communication.

The bus is deterministic and single-threaded: messages are routed synchronously
to recipient inboxes and accumulated in a global history. Reading marks a
message as delivered but never removes it from history, so the workflow can
always expose the complete conversation through the state ``communication``
field.

The bus is pure infrastructure. In this milestone it is rebuilt by each graph
node from the accumulated state so the fixed workflow stays stateless.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from ekatra.orchestration.message import (
    BROADCAST_RECIPIENT,
    AgentMessage,
    MessageType,
)

NowType = Callable[[], str]


def _default_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MessageBus:
    """Routes and records messages between registered agents.

    Args:
        agent_ids: Agent IDs allowed to send and receive on this bus.
        now: Optional timestamp provider (injected for deterministic tests).
    """

    def __init__(
        self,
        agent_ids: Iterable[str] = (),
        now: NowType | None = None,
    ) -> None:
        self._agents: set[str] = set(agent_ids)
        self._history: list[AgentMessage] = []
        self._inbox: dict[str, list[AgentMessage]] = {}
        self._now = now or _default_now

    # -- registration / validation ------------------------------------------

    def register_agent(self, agent_id: str) -> None:
        """Register an agent ID as an allowed sender and recipient."""
        if not agent_id or not isinstance(agent_id, str):
            raise ValueError(f"Invalid agent ID: {agent_id!r}")
        self._agents.add(agent_id)

    def _require_known(self, agent_id: str) -> None:
        if agent_id not in self._agents:
            raise ValueError(f"Unknown agent: {agent_id!r}")

    def registered_agent_ids(self) -> list[str]:
        """Return the registered agent IDs in sorted order."""
        return sorted(self._agents)

    # -- sending -------------------------------------------------------------

    def send(
        self,
        sender: str,
        recipient: str,
        message_type: MessageType,
        content: str,
        related_task_id: str | None = None,
    ) -> AgentMessage:
        """Send a single message from one agent to another.

        Raises:
            ValueError: If the sender is unknown, the recipient is unknown
                (and not a broadcast), or the message payload is invalid.
        """
        self._require_known(sender)
        if recipient == BROADCAST_RECIPIENT:
            raise ValueError("Use broadcast() to target every agent")
        if recipient not in self._agents:
            raise ValueError(f"Unknown recipient: {recipient!r}")

        message = AgentMessage(
            message_id=f"MSG-{len(self._history) + 1:04d}",
            sender_agent=sender,
            recipient_agent=recipient,
            message_type=message_type,
            content=content,
            related_task_id=related_task_id,
            timestamp=self._now(),
        )
        self._history.append(message)
        self._inbox.setdefault(recipient, []).append(message)
        return message

    def broadcast(
        self,
        sender: str,
        message_type: MessageType,
        content: str,
        related_task_id: str | None = None,
    ) -> list[AgentMessage]:
        """Send the same message to every registered agent except the sender.

        Each recipient receives its own directional message in deterministic
        (sorted ID) order.
        """
        self._require_known(sender)
        recipients = [aid for aid in sorted(self._agents) if aid != sender]
        return [self.send(sender, aid, message_type, content, related_task_id) for aid in recipients]

    # -- retrieval -----------------------------------------------------------

    def read(self, agent_id: str) -> list[AgentMessage]:
        """Return and mark-deliver all undelivered messages for an agent.

        Messages stay in the global history after being read.
        """
        self._require_known(agent_id)
        return self._inbox.pop(agent_id, [])

    def unread(self, agent_id: str) -> list[AgentMessage]:
        """Return undelivered messages for an agent without consuming them."""
        self._require_known(agent_id)
        return list(self._inbox.get(agent_id, []))

    def messages_for(self, agent_id: str) -> list[AgentMessage]:
        """Return every message ever addressed to an agent."""
        return [m for m in self._history if m.recipient_agent == agent_id]

    def history(self) -> list[AgentMessage]:
        """Return the complete message history in sending order."""
        return list(self._history)

    # -- metrics -------------------------------------------------------------

    def total(self) -> int:
        """Total number of messages sent on this bus."""
        return len(self._history)

    def count_by_type(self) -> dict[str, int]:
        """Number of messages per message type."""
        counts: dict[str, int] = {}
        for message in self._history:
            key = message.message_type.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    def count_by_recipient(self) -> dict[str, int]:
        """Number of addressed messages received per agent."""
        counts: dict[str, int] = {aid: 0 for aid in self._agents}
        for message in self._history:
            if message.recipient_agent != BROADCAST_RECIPIENT:
                counts[message.recipient_agent] = counts.get(message.recipient_agent, 0) + 1
        return counts

    def count_by_task(self) -> dict[str, int]:
        """Number of messages referencing each task ID."""
        counts: dict[str, int] = {}
        for message in self._history:
            if message.related_task_id:
                counts[message.related_task_id] = counts.get(message.related_task_id, 0) + 1
        return counts

    # -- serialization -------------------------------------------------------

    def to_dicts(self) -> list[dict[str, Any]]:
        """Serialize the full history to JSON-safe dicts (see ``to_dict``)."""
        return [m.to_dict() for m in self._history]

    @classmethod
    def from_dicts(
        cls,
        message_dicts: Iterable[dict[str, Any]],
        agent_ids: Iterable[str] = (),
        *,
        now: NowType | None = None,
    ) -> "MessageBus":
        """Rebuild a bus from serialized history (e.g. the state field).

        New messages continue numbering after the restored history, keeping
        ``message_id`` stable across the whole run.
        """
        bus = cls(agent_ids=agent_ids, now=now)
        bus._history = [AgentMessage.from_dict(d) for d in message_dicts]
        return bus

    def __len__(self) -> int:
        return len(self._history)

    def __repr__(self) -> str:
        return f"<MessageBus agents={len(self._agents)} messages={len(self._history)}>"


__all__ = ["MessageBus"]