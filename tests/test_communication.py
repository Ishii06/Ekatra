"""Milestone 4 tests: structured agent communication through the message bus.

Covers the message model, the in-memory bus (sending, broadcasting, retrieval,
history preservation, deterministic failures), agent-level send/receive, and
the fixed workflow's observable communication history.
"""

from __future__ import annotations

import pytest

PROJECT_DESCRIPTION = "Build a simple todo application."

# Deterministic timestamp provider so bus tests are fully reproducible.
FIXED_TIMESTAMP = "2026-01-01T00:00:00+00:00"


def _bus(*agent_ids: str):
    from ekatra.orchestration import MessageBus

    return MessageBus(agent_ids=agent_ids, now=lambda: FIXED_TIMESTAMP)


# 1. message creation --------------------------------------------------------

def test_message_creation_is_deterministic() -> None:
    """A message production is fully deterministic and validated."""
    from ekatra.orchestration import AgentMessage, MessageType

    message = AgentMessage(
        message_id="MSG-0001",
        sender_agent="PM-1",
        recipient_agent="ARCH-1",
        message_type=MessageType.TASK_ASSIGNMENT,
        content="Assigned TASK-1 to you.",
        related_task_id="TASK-1",
        timestamp=FIXED_TIMESTAMP,
    )

    assert message.message_id == "MSG-0001"
    assert message.sender_agent == "PM-1"
    assert message.recipient_agent == "ARCH-1"
    assert message.message_type is MessageType.TASK_ASSIGNMENT
    assert message.related_task_id == "TASK-1"
    assert message.timestamp == FIXED_TIMESTAMP
    assert len(message.message_type.value) > 0


def test_message_rejects_blank_fields() -> None:
    """Blank sender / recipient / content are rejected deterministically."""
    from ekatra.orchestration import AgentMessage, MessageType

    with pytest.raises(ValueError):
        AgentMessage(
            message_id="MSG-1",
            sender_agent=" ",
            recipient_agent="ARCH-1",
            message_type=MessageType.RESULT,
            content="ok",
            timestamp=FIXED_TIMESTAMP,
        )

    with pytest.raises(ValueError):
        AgentMessage(
            message_id="MSG-1",
            sender_agent="PM-1",
            recipient_agent="ARCH-1",
            message_type=MessageType.ERROR,
            content="",
            timestamp=FIXED_TIMESTAMP,
        )


def test_message_serialization_roundtrip() -> None:
    """to_dict() is JSON-safe and from_dict() restores the same message."""
    from ekatra.orchestration import AgentMessage, MessageType

    message = AgentMessage(
        message_id="MSG-0007",
        sender_agent="QA-1",
        recipient_agent="BACKEND-1",
        message_type=MessageType.REVIEW_FEEDBACK,
        content="All checks passed.",
        related_task_id="TASK-4",
        timestamp=FIXED_TIMESTAMP,
    )
    restored = AgentMessage.from_dict(message.to_dict())

    assert restored == message
    assert restored.message_type is MessageType.REVIEW_FEEDBACK
    assert isinstance(message.to_dict()["message_type"], str)


# 2. direct send -------------------------------------------------------------

def test_direct_send_routes_to_delivery_and_history() -> None:
    """send() records the message in history and delivers it to the inbox."""
    from ekatra.orchestration import MessageType

    bus = _bus("PM-1", "ARCH-1")
    sent = bus.send(
        "PM-1",
        "ARCH-1",
        MessageType.INFORMATION,
        "hello architect",
    )

    assert sent.message_id == "MSG-0001"
    assert bus.total() == 1
    assert bus.read("ARCH-1") == [sent]
    assert bus.messages_for("ARCH-1") == [sent]


def test_send_generates_sequential_ids_and_timestamps() -> None:
    """Message IDs are sequential and timestamps come from the bus clock."""
    from ekatra.orchestration import MessageType

    bus = _bus("PM-1", "ARCH-1", "BACKEND-1")
    first = bus.send("PM-1", "ARCH-1", MessageType.RESULT, "a")
    second = bus.send("PM-1", "BACKEND-1", MessageType.RESULT, "b")

    assert [first.message_id, second.message_id] == ["MSG-0001", "MSG-0002"]
    assert first.timestamp == FIXED_TIMESTAMP == second.timestamp


# 3. broadcast ---------------------------------------------------------------

def test_broadcast_reaches_all_except_sender() -> None:
    """Broadcast delivers a directional message to every agent but the sender."""
    from ekatra.orchestration import MessageType

    bus = _bus("PM-1", "ARCH-1", "BACKEND-1", "FRONTEND-1")
    sent = bus.broadcast("PM-1", MessageType.STATUS_UPDATE, "planning complete")

    assert [m.recipient_agent for m in sent] == ["ARCH-1", "BACKEND-1", "FRONTEND-1"]
    assert bus.total() == 3
    assert len(bus.read("BACKEND-1")) == 1
    assert bus.read("PM-1") == []


# 4. retrieval ---------------------------------------------------------------

def test_read_marks_delivered_but_history_retains_every_message() -> None:
    """Reading never removes messages from the global history."""
    from ekatra.orchestration import MessageType

    bus = _bus("PM-1", "ARCH-1")
    sent = bus.send("PM-1", "ARCH-1", MessageType.RESULT, "design ready")

    assert bus.unread("ARCH-1") == [sent]
    assert bus.read("ARCH-1") == [sent]
    assert bus.unread("ARCH-1") == []
    assert bus.messages_for("ARCH-1") == [sent]
    assert bus.history() == [sent]


# 5. deterministic failure ----------------------------------------------------

def test_unknown_sender_is_rejected() -> None:
    """Sending from an unregistered agent fails deterministically."""
    from ekatra.orchestration import MessageType

    bus = _bus("PM-1")
    with pytest.raises(ValueError, match="Unknown agent"):
        bus.send("INTRUDER", "PM-1", MessageType.ERROR, "who am I?")


def test_unknown_recipient_is_rejected() -> None:
    """Sending to an unregistered agent fails deterministically."""
    from ekatra.orchestration import MessageType

    bus = _bus("PM-1")
    with pytest.raises(ValueError, match="Unknown recipient"):
        bus.send("PM-1", "GHOST", MessageType.RESULT, "lost message")


def test_read_unknown_agent_is_rejected() -> None:
    """Reading mail for an unregistered agent fails deterministically."""
    from ekatra.orchestration import MessageType

    bus = _bus("PM-1")
    bus.send("PM-1", "PM-1", MessageType.INFORMATION, "self note")
    with pytest.raises(ValueError, match="Unknown agent"):
        bus.unread("GHOST")


def test_broadcast_uses_send_semantics() -> None:
    """Broadcast cannot target the literal broadcast marker as a recipient."""
    from ekatra.orchestration import BROADCAST_RECIPIENT, MessageType

    bus = _bus("PM-1")
    with pytest.raises(ValueError, match="broadcast"):
        bus.send("PM-1", BROADCAST_RECIPIENT, MessageType.STATUS_UPDATE, "nope")


# 6. counts ------------------------------------------------------------------

def test_counts_by_type_recipient_and_task() -> None:
    """The bus exposes deterministic aggregate counts."""
    from ekatra.orchestration import MessageType

    bus = _bus("PM-1", "ARCH-1", "BACKEND-1")
    bus.send("PM-1", "ARCH-1", MessageType.TASK_ASSIGNMENT, "take TASK-1", related_task_id="TASK-1")
    bus.send("PM-1", "BACKEND-1", MessageType.TASK_ASSIGNMENT, "take TASK-2", related_task_id="TASK-2")
    bus.send("ARCH-1", "PM-1", MessageType.RESULT, "done", related_task_id="TASK-1")

    assert bus.count_by_type() == {"TASK_ASSIGNMENT": 2, "RESULT": 1}
    assert bus.count_by_recipient() == {"PM-1": 1, "ARCH-1": 1, "BACKEND-1": 1}
    assert bus.count_by_task() == {"TASK-1": 2, "TASK-2": 1}


# 7. history rebuild (state round-trip) ---------------------------------------

def test_rebuilt_bus_continues_message_numbering() -> None:
    """A bus restored from serialized history keeps generating unique IDs."""
    from ekatra.orchestration import MessageBus, MessageType

    bus = _bus("PM-1", "ARCH-1")
    bus.send("PM-1", "ARCH-1", MessageType.RESULT, "first")
    bus.send("PM-1", "ARCH-1", MessageType.RESULT, "second")

    rebuilt = MessageBus.from_dicts(
        bus.to_dicts(),
        agent_ids=["PM-1", "ARCH-1"],
        now=lambda: FIXED_TIMESTAMP,
    )
    third = rebuilt.send("PM-1", "ARCH-1", MessageType.INFORMATION, "third")

    assert third.message_id == "MSG-0003"
    assert len(rebuilt.history()) == 3


# 7b. agent-level send / receive ---------------------------------------------

def test_agent_send_and_read_roundtrip() -> None:
    """Agents exchange and read messages through the attached bus."""
    from ekatra.agents.roles import ArchitectAgent, ProjectManagerAgent
    from ekatra.orchestration import MessageBus, MessageType
    from ekatra.orchestration.message import BROADCAST_RECIPIENT

    bus = MessageBus(now=lambda: FIXED_TIMESTAMP)
    pm = ProjectManagerAgent(agent_id="PM-1")
    architect = ArchitectAgent(agent_id="ARCH-1")
    pm.attach_bus(bus)
    architect.attach_bus(bus)

    pm.send(
        MessageType.TASK_ASSIGNMENT,
        "Assigned TASK-1 (architect) to you.",
        related_task_id="TASK-1",
        recipient="ARCH-1",
    )

    mail = architect.read()
    assert len(mail) == 1
    assert mail[0].sender_agent == "PM-1"
    assert mail[0].recipient_agent == "ARCH-1"
    assert mail[0].message_type is MessageType.TASK_ASSIGNMENT
    assert mail[0].related_task_id == "TASK-1"


def test_agent_broadcast_and_self_exclusion() -> None:
    """broadcast() from an agent skips the sender itself."""
    from ekatra.agents.roles import ProjectManagerAgent
    from ekatra.orchestration import MessageBus, MessageType

    bus = MessageBus(now=lambda: FIXED_TIMESTAMP)
    pm = ProjectManagerAgent(agent_id="PM-1")
    architect = ProjectManagerAgent(agent_id="ARCH-1")
    pm.attach_bus(bus)
    architect.attach_bus(bus)

    sent = pm.broadcast(MessageType.STATUS_UPDATE, "planning complete")

    assert {m.recipient_agent for m in sent} == {"ARCH-1"}
    assert pm.read() == []


def test_agent_without_bus_cannot_communicate() -> None:
    """Sending without an attached bus fails, never silently."""
    from ekatra.agents.roles import ArchitectAgent
    from ekatra.orchestration import MessageType

    agent = ArchitectAgent(agent_id="ARCH-1")
    with pytest.raises(RuntimeError, match="bus"):
        agent.send(MessageType.RESULT, "hello", recipient="PM-1")


# 8. workflow communication --------------------------------------------------

def test_workflow_produces_structured_communication() -> None:
    """The fixed workflow emits a deterministic structured message history."""
    from ekatra.graph import run
    from ekatra.orchestration import MessageType
    from ekatra.state.state import create_initial_state

    result = run(create_initial_state(PROJECT_DESCRIPTION))
    communication = result["communication"]

    assert len(communication) == 45
    assert set(m["message_type"] for m in communication) == {
        MessageType.STATUS_UPDATE.value,
        MessageType.TASK_ASSIGNMENT.value,
        MessageType.RESULT.value,
        MessageType.REVIEW_FEEDBACK.value,
    }

    # Deterministic sequential message ids.
    assert [m["message_id"] for m in communication] == [
        f"MSG-{i:04d}" for i in range(1, 46)
    ]

    # PM plans first, then assigns one task per role.
    assert communication[0]["sender_agent"] == "PM-1"
    assert communication[0]["message_type"] == "STATUS_UPDATE"
    assignments = [m for m in communication if m["message_type"] == "TASK_ASSIGNMENT"]
    assert len(assignments) == 5
    assert {m["related_task_id"] for m in assignments} == {
        f"TASK-{i}" for i in range(1, 6)
    }
    assert {m["recipient_agent"] for m in assignments} == {
        "ARCH-1", "BACKEND-1", "FRONTEND-1", "QA-1", "SECURITY-1",
    }

    # QA issues review feedback to the implementation agents.
    feedback = [m for m in communication if m["message_type"] == "REVIEW_FEEDBACK"]
    assert len(feedback) == 2
    assert {m["sender_agent"] for m in feedback} == {"QA-1"}
    assert {m["recipient_agent"] for m in feedback} == {"BACKEND-1", "FRONTEND-1"}

    # Every communicated sender and recipient is a real pool agent.
    known = {"PM-1", "ARCH-1", "FRONTEND-1", "BACKEND-1", "QA-1", "SECURITY-1"}
    assert {m["sender_agent"] for m in communication} <= known
    assert {m["recipient_agent"] for m in communication} <= known


# 9. state contains communication ---------------------------------------------

def test_state_exposes_communication_history() -> None:
    """Final EkatraState carries the full JSON-safe communication history."""
    import json

    from ekatra.graph import run
    from ekatra.state.state import create_initial_state

    result = run(create_initial_state(PROJECT_DESCRIPTION))

    assert "communication" in result
    assert isinstance(result["communication"], list)
    assert len(result["communication"]) > 0

    for message in result["communication"]:
        assert set(message) == {
            "message_id", "sender_agent", "recipient_agent",
            "message_type", "content", "related_task_id", "timestamp",
        }
    # JSON-safe for logging / experiments.
    assert json.dumps(result["communication"])


# 10. no LLM needed ----------------------------------------------------------

def test_communication_requires_no_llm() -> None:
    """The whole workflow (and its messaging) runs with mock strategy."""
    from ekatra.config.settings import Settings
    from ekatra.graph import run
    from ekatra.state.state import create_initial_state

    assert Settings().gemini_api_key == ""

    result = run(create_initial_state(PROJECT_DESCRIPTION))
    assert result["current_step"] == "security"
    assert len(result["communication"]) == 45
    assert len(result["messages"]) == 6
    assert result["adaptive_decisions"] == []