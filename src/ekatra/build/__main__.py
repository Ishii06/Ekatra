"""CLI: ``python -m ekatra.build "<website description>"``."""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

from ekatra.build.live import BuildConfig, build_project
from ekatra.config.settings import get_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ekatra.build",
        description="Build a working website with Gemini-driven Ekatra agents.",
    )
    parser.add_argument("description", help="what the website should do")
    parser.add_argument("--strategy", choices=("adaptive", "fixed"), default="adaptive")
    parser.add_argument("--out", help="output folder (default: projects/<name>-<strategy>)")
    parser.add_argument("--max-agents", type=int, default=3, help="max agents per spawnable role")
    parser.add_argument("--repair-rounds", type=int, default=2)
    parser.add_argument("--no-smoke-test", action="store_true",
                        help="do not run the generated app during the build")
    args = parser.parse_args(argv)

    if not get_settings().has_api_key():
        print("GEMINI_API_KEY is not set (add it to .env).", file=sys.stderr)
        return 2
    slug = re.sub(r"[^a-z0-9]+", "-", args.description.lower()).strip("-")[:32] or "site"
    out = Path(args.out) if args.out else Path("projects") / f"{slug}-{args.strategy}-{int(time.time()) % 100000}"
    print(f"Building into {out} ...", flush=True)
    result = build_project(
        args.description,
        out_dir=out,
        strategy=args.strategy,
        config=BuildConfig(max_agents_per_role=args.max_agents, repair_rounds=args.repair_rounds,
                            smoke_test=not args.no_smoke_test),
        progress=lambda message: print(message, flush=True),
    )
    task, agent, adaptive = result.metrics.task, result.metrics.agent, result.metrics.adaptive
    print(f"\nDone in {result.metrics.timing['duration_seconds']:.0f}s: "
          f"{task['completed_tasks']}/{task['total_tasks']} tasks, "
          f"{adaptive['spawn_events']} spawned, {adaptive['reassignment_events']} reassigned, "
          f"peak {agent['peak_active_agents']} agents active.")
    high = [i for i in result.final_issues if i["severity"] == "high"]
    print(f"Static validation: {len(result.final_issues)} issue(s), {len(high)} high.")
    for issue in result.final_issues[:8]:
        print(f"  - [{issue['severity']}] {issue['file']}: {issue['description']}")
    print(f"\nRun it:  cd {out} && pip install -r requirements.txt && uvicorn backend.main:app --reload")
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
