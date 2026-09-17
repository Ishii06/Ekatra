"""Run the fixed Ekatra workflow from the command line.

Usage:

    python -m ekatra.graph

This writes the resulting state as JSON to stdout. No API calls are made.
"""

from __future__ import annotations

import json

from ekatra.graph import build_graph
from ekatra.state.state import create_initial_state

EXAMPLE = "Build a simple todo application."


def main() -> None:
    graph = build_graph()
    result = graph.invoke(create_initial_state(EXAMPLE))
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()