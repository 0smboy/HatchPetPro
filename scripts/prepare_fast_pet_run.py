#!/usr/bin/env python3
"""Prepare a fast built-in image_gen Codex pet spritesheet run."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
import re
from pathlib import Path
import shlex


ROW_SPECS = [
    {"state": "idle", "row": 0, "frames": 6},
    {"state": "running-right", "row": 1, "frames": 8},
    {"state": "running-left", "row": 2, "frames": 8},
    {"state": "waving", "row": 3, "frames": 4},
    {"state": "jumping", "row": 4, "frames": 5},
    {"state": "failed", "row": 5, "frames": 8},
    {"state": "waiting", "row": 6, "frames": 6},
    {"state": "running", "row": 7, "frames": 6},
    {"state": "review", "row": 8, "frames": 6},
]


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or "~/.codex").expanduser().resolve()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "pet"


def title_from_slug(value: str) -> str:
    words = [word for word in re.split(r"[^A-Za-z0-9]+", value) if word]
    return " ".join(words[:4]).title() if words else ""


def infer_name(pet_name: str, pet_notes: str, references: list[Path]) -> str:
    if pet_name.strip():
        return pet_name.strip()
    if references:
        candidate = title_from_slug(references[0].stem)
        if candidate:
            return candidate
    candidate = title_from_slug(pet_notes)
    return candidate or "Quick Pet"


def build_prompt(description: str, references: list[Path], style_notes: str) -> str:
    reference_line = (
        "Reference images are attached; use them as the character and style reference."
        if references
        else f"No reference image is provided; use this description: {description}"
    )
    extra_style = f"\nExtra style constraints: {style_notes.strip()}" if style_notes.strip() else ""
    return f"""Generate a clean pixel-art sprite sheet of one consistent character.
{reference_line}

No UI, labels, text, numbers, cards, borders, frame guides, shadows, scenery, or watermarks.
Create exactly 9 action rows in this order with these frame counts:
Idle x6, Run right x8, Run left x8, Waving x4, Jumping x5, Failed x8,
Waiting x6, Running x6, Review x6.

Arrange the whole image as one 8 column x 9 row sprite-sheet grid.
Each row uses the listed frame count from left to right; cells after the last used frame must be empty.
Keep the same character proportions, outfit, face, palette, outline, and pixel-art style across all frames.
Use a transparent background if supported; otherwise use one perfectly flat removable solid-color background that does not appear in the character.
Keep poses separated and centered.
Use compact Codex digital pet style: chunky readable silhouette, thick dark outline, flat pixel-art/cel shading, simple expressive face, tiny limbs.
Avoid polished illustration, 3D rendering, soft gradients, complex tiny accessories, shadows, glows, motion trails, speed lines, wave marks, loose sparkles, text, labels, UI, grids, and scenery.
Waving is paw pose only. Jumping is body position only. Running rows use limbs only. Review uses focus/lean/eyes/head tilt only.{extra_style}
""".strip() + "\n"


def shell_join(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pet-name", default="")
    parser.add_argument("--description", default="")
    parser.add_argument("--pet-notes", default="")
    parser.add_argument("--style-notes", default="")
    parser.add_argument("--reference", action="append", default=[])
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    references = [Path(raw).expanduser().resolve() for raw in args.reference]
    missing = [str(path) for path in references if not path.is_file()]
    if missing:
        raise SystemExit("reference image not found: " + ", ".join(missing))

    display_name = infer_name(args.pet_name, args.pet_notes or args.description, references)
    description = (
        args.description.strip()
        or args.pet_notes.strip()
        or f"{display_name}, a small pixel-art Codex companion."
    )
    pet_id = slugify(display_name)

    if args.output_dir:
        run_dir = Path(args.output_dir).expanduser().resolve()
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = codex_home() / "pet-runs" / f"{pet_id}-fast-{stamp}"

    if run_dir.exists() and any(run_dir.iterdir()) and not args.force:
        raise SystemExit(f"{run_dir} already exists and is not empty; pass --force to reuse it")

    prompt_dir = run_dir / "prompts"
    generated_dir = run_dir / "generated"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    generated_dir.mkdir(parents=True, exist_ok=True)

    prompt = build_prompt(description, references, args.style_notes)
    prompt_file = prompt_dir / "spritesheet.txt"
    prompt_file.write_text(prompt, encoding="utf-8")

    source_atlas = generated_dir / "source-atlas.png"
    record_command = [
        "python",
        str(Path(__file__).resolve().parent / "record_fast_imagegen_result.py"),
        "--run-dir",
        str(run_dir),
        "--source",
        "/absolute/path/to/generated_images/.../ig_*.png",
    ]
    finalize_command = [
        "python",
        str(Path(__file__).resolve().parent / "finalize_fast_pet_run.py"),
        "--run-dir",
        str(run_dir),
        "--force",
    ]

    request = {
        "mode": "fast-single-atlas",
        "pet_id": pet_id,
        "display_name": display_name,
        "description": description,
        "pet_notes": args.pet_notes.strip(),
        "style_notes": args.style_notes.strip(),
        "references": [str(path) for path in references],
        "row_specs": ROW_SPECS,
        "target": {"columns": 8, "rows": 9, "cell_width": 192, "cell_height": 208},
        "prompt_file": str(prompt_file),
        "source_atlas": str(source_atlas),
        "image_generation": {
            "mode": "built-in-image_gen",
            "requires_openai_api_key": False,
            "selected_source": "",
        },
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    (run_dir / "pet_request.json").write_text(
        json.dumps(request, indent=2) + "\n", encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "ok": True,
                "run_dir": str(run_dir),
                "prompt_file": str(prompt_file),
                "source_atlas": str(source_atlas),
                "built_in_imagegen": {
                    "prompt_file": str(prompt_file),
                    "reference_images": [str(path) for path in references],
                    "selected_source_hint": str(codex_home() / "generated_images" / "..." / "ig_*.png"),
                    "requires_openai_api_key": False,
                },
                "record_command": record_command,
                "record_command_shell": shell_join(record_command),
                "finalize_command": finalize_command,
                "finalize_command_shell": shell_join(finalize_command),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
