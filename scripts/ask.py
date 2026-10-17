"""Ask the deterministic CivicMind pipeline a question (water + traffic slice).

Usage (from the repository root):
    .venv-py313/Scripts/python.exe scripts/ask.py "Water consumption in August 2025?"
    .venv-py313/Scripts/python.exe scripts/ask.py --json "Top 3 cities by speeding deaths in 2024"

Prints the templated answer (or the refusal code and reason); --json prints the full answer
record (value, unit, periods, method, caveats, evidence with SHA-256, trace). Read-only: no
network, no model, nothing written.
"""

from __future__ import annotations

import argparse
import json
import sys

from civicmind.orchestrator.pipeline import ROOT, answer_question


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question")
    parser.add_argument("--json", action="store_true", help="print the full answer record")
    args = parser.parse_args(argv)
    answer = answer_question(args.question, ROOT)
    if args.json:
        print(json.dumps(answer.to_dict(), indent=2, ensure_ascii=False, default=str))
    else:
        print(answer.text)
        if answer.status == "answered":
            for caveat in answer.caveats[:3]:
                print(f"  - {caveat}")
    return 0 if answer.status == "answered" else 2


if __name__ == "__main__":
    sys.exit(main())
