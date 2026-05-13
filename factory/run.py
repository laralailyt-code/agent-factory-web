"""CLI entry: python -m factory.run "你的需求"."""
from __future__ import annotations
import sys
import uuid
from .graph import build_graph
from .llm import is_mock


def main():
    # Windows cmd defaults to cp950 — force UTF-8 so emojis + 中文 print cleanly.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

    if len(sys.argv) < 2:
        print("usage: python -m factory.run \"你的需求描述\"")
        sys.exit(1)

    user_request = " ".join(sys.argv[1:])
    job_id = f"job_{uuid.uuid4().hex[:8]}"

    print()
    print("=" * 60)
    print("  AGENT FACTORY")
    print(f"  job_id: {job_id}")
    print(f"  mode:   {'MOCK (no API key)' if is_mock() else 'REAL (Anthropic API)'}")
    print(f"  input:  {user_request}")
    print("=" * 60)
    print()

    graph = build_graph()

    initial_state = {
        "job_id": job_id,
        "user_request": user_request,
        "iteration": 0,
        "log": [],
    }

    final_state = graph.invoke(initial_state)

    print()
    for line in final_state.get("log", []):
        print(line)
    print()
    print("=" * 60)
    print("  DONE")
    print(f"  agent_type:  {final_state.get('prd', {}).get('agent_type', '?')}")
    print(f"  files:       {len(final_state.get('files', {}))}")
    print(f"  tests:       {final_state.get('test_results', {})}")
    print(f"  deploy_url:  {final_state.get('deploy_url', 'n/a')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
