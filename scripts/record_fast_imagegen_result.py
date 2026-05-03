#!/usr/bin/env python3
"""Record one built-in image_gen atlas for a fast hatch-pet run."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or "~/.codex").expanduser().resolve()


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_request(run_dir: Path) -> dict[str, object]:
    request_path = run_dir / "pet_request.json"
    if not request_path.is_file():
        raise SystemExit(f"pet_request.json not found: {request_path}")
    return json.loads(request_path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument(
        "--allow-any-source",
        action="store_true",
        help="Allow a source outside ${CODEX_HOME:-$HOME/.codex}/generated_images.",
    )
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    source = Path(args.source).expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"source image not found: {source}")

    generated_root = codex_home() / "generated_images"
    if not args.allow_any_source and not is_relative_to(source, generated_root):
        raise SystemExit(
            f"source is not under {generated_root}; pass --allow-any-source only for a deliberate local test"
        )

    request = load_request(run_dir)
    target = Path(str(request.get("source_atlas") or run_dir / "generated" / "source-atlas.png"))
    if not target.is_absolute():
        target = run_dir / target
    target = target.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    if source != target:
        shutil.copy2(source, target)

    source_hash = file_sha256(source)
    target_hash = file_sha256(target)
    if source_hash != target_hash:
        raise SystemExit("copied source hash does not match target hash")

    metadata = {
        "ok": True,
        "mode": "fast-single-atlas",
        "source_provenance": "built-in-image_gen",
        "source_path": str(source),
        "target_path": str(target),
        "source_sha256": source_hash,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    (target.parent / "source-atlas.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )

    request["image_generation"] = {
        "mode": "built-in-image_gen",
        "requires_openai_api_key": False,
        "selected_source": str(source),
        "source_sha256": source_hash,
        "recorded_at": metadata["recorded_at"],
    }
    (run_dir / "pet_request.json").write_text(
        json.dumps(request, indent=2) + "\n", encoding="utf-8"
    )

    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
