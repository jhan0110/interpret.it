"""Generate a 10-pack via the content pipeline and print to stdout.

Side-effect-free preview. Useful for iterating on the prompt without
running the full session flow.

Run inside the analysis container:

    docker compose exec analysis python -m scripts.preview_generation \\
        --topic logistics --level 3 --duration medium

Defaults USE_MOCKS=1 (deterministic fake output). Set USE_MOCKS=0 +
ANTHROPIC_API_KEY for real generation.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from app.content.generate import GenerateParams, generate_segments
from app.content.topics import TOPICS


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="preview_generation")
    p.add_argument("--topic", required=True, action="append", choices=list(TOPICS))
    p.add_argument("--level", type=int, required=True, choices=[1, 2, 3, 4, 5])
    p.add_argument(
        "--duration", required=True, choices=["short", "medium", "long"]
    )
    p.add_argument("--direction", default="en-ko", choices=["en-ko", "ko-en"])
    p.add_argument("--n", type=int, default=10)
    p.add_argument("--context", default=None, help="Optional 'current context' string")
    args = p.parse_args(argv)

    params = GenerateParams(
        topics=tuple(args.topic),
        user_level=args.level,
        duration=args.duration,
        direction=args.direction,
        n=args.n,
        current_context=args.context,
    )
    result = generate_segments(params)
    out = {
        "scenario_summary": result.scenario_summary,
        "prompt_template_hash": result.prompt_template_hash,
        "prompt_vars_hash": result.prompt_vars_hash,
        "segments": [asdict(s) for s in result.segments],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
