"""Shared numeric helpers for the deterministic scoring models."""


def clamp100(value: float) -> float:
    """Clamp a value into the [0, 100] score range."""
    return max(0.0, min(100.0, value))


__all__ = ["clamp100"]