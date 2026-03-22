#!/usr/bin/env python3
"""Build a JSON evidence pack from accepted chapter prose."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from evidence_tools import BASE_DIR, EVAL_LOG_DIR, build_evidence_pack


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assemble a prose-level evidence pack for novel evaluation.",
    )
    parser.add_argument(
        "--novel",
        action="store_true",
        help="Build the full novel evidence pack. Present for forward compatibility.",
    )
    parser.add_argument(
        "--output",
        default=str(EVAL_LOG_DIR / "evidence_pack.json"),
        help="Output path for the evidence pack JSON.",
    )
    args = parser.parse_args()

    pack = build_evidence_pack()
    pack["generated_at"] = datetime.now().isoformat()
    pack["source_root"] = str(BASE_DIR)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(pack, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
