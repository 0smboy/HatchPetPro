#!/usr/bin/env python3
"""Explain why the default fast path cannot be run as a local command."""

from __future__ import annotations

import json


def main() -> None:
    raise SystemExit(
        json.dumps(
            {
                "ok": False,
                "error": "hatch_fast_pet.py is not the default path",
                "reason": (
                    "The fast no-API-key workflow must call Codex built-in image_gen from the agent. "
                    "A local Python script cannot access that logged-in tool session."
                ),
                "use": [
                    "prepare_fast_pet_run.py",
                    "built-in image_gen exactly once",
                    "record_fast_imagegen_result.py",
                    "finalize_fast_pet_run.py",
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
