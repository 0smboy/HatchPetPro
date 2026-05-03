#!/usr/bin/env python3
"""Normalize one generated atlas into a packaged Codex pet."""

from __future__ import annotations

import argparse
from collections import deque
import json
import math
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image


COLUMNS = 8
ROWS = 9
CELL_WIDTH = 192
CELL_HEIGHT = 208
ATLAS_WIDTH = COLUMNS * CELL_WIDTH
ATLAS_HEIGHT = ROWS * CELL_HEIGHT
ROW_SPECS = [
    ("idle", 0, 6),
    ("running-right", 1, 8),
    ("running-left", 2, 8),
    ("waving", 3, 4),
    ("jumping", 4, 5),
    ("failed", 5, 8),
    ("waiting", 6, 6),
    ("running", 7, 6),
    ("review", 8, 6),
]


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(command))
    return subprocess.run(command, check=check, text=True)


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or "~/.codex").expanduser().resolve()


def color_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def alpha_has_transparency(image: Image.Image) -> bool:
    alpha = image.getchannel("A")
    extrema = alpha.getextrema()
    return bool(extrema and extrema[0] < 255)


def remove_edge_connected_background(image: Image.Image, threshold: float) -> Image.Image:
    """Remove only background-colored pixels connected to the outer edge."""

    rgba = image.convert("RGBA")
    width, height = rgba.size
    if width == 0 or height == 0:
        return rgba

    pixels = rgba.load()
    corner_colors = [
        pixels[0, 0][:3],
        pixels[width - 1, 0][:3],
        pixels[0, height - 1][:3],
        pixels[width - 1, height - 1][:3],
    ]

    def is_background(x: int, y: int) -> bool:
        red, green, blue, alpha = pixels[x, y]
        if alpha == 0:
            return True
        rgb = (red, green, blue)
        return any(color_distance(rgb, corner) <= threshold for corner in corner_colors)

    queue: deque[tuple[int, int]] = deque()
    visited = bytearray(width * height)

    def enqueue(x: int, y: int) -> None:
        index = y * width + x
        if not visited[index] and is_background(x, y):
            visited[index] = 1
            queue.append((x, y))

    for x in range(width):
        enqueue(x, 0)
        enqueue(x, height - 1)
    for y in range(height):
        enqueue(0, y)
        enqueue(width - 1, y)

    while queue:
        x, y = queue.popleft()
        red, green, blue, _alpha = pixels[x, y]
        pixels[x, y] = (red, green, blue, 0)
        if x > 0:
            enqueue(x - 1, y)
        if x + 1 < width:
            enqueue(x + 1, y)
        if y > 0:
            enqueue(x, y - 1)
        if y + 1 < height:
            enqueue(x, y + 1)

    return rgba


def alpha_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    return image.getchannel("A").getbbox()


def fit_to_cell(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    bbox = alpha_bbox(rgba)
    target = Image.new("RGBA", (CELL_WIDTH, CELL_HEIGHT), (0, 0, 0, 0))
    if bbox is None:
        return target

    sprite = rgba.crop(bbox)
    max_width = CELL_WIDTH - 8
    max_height = CELL_HEIGHT - 8
    scale = min(max_width / sprite.width, max_height / sprite.height)
    if abs(scale - 1.0) > 0.01:
        resample = Image.Resampling.NEAREST if scale > 1 else Image.Resampling.LANCZOS
        sprite = sprite.resize(
            (max(1, round(sprite.width * scale)), max(1, round(sprite.height * scale))),
            resample,
        )
    left = (CELL_WIDTH - sprite.width) // 2
    top = (CELL_HEIGHT - sprite.height) // 2
    target.alpha_composite(sprite, (left, top))
    return target


def normalize_source_atlas(source_path: Path, *, background_threshold: float) -> Image.Image:
    with Image.open(source_path) as opened:
        source = opened.convert("RGBA")

    if not alpha_has_transparency(source):
        source = remove_edge_connected_background(source, background_threshold)

    atlas = Image.new("RGBA", (ATLAS_WIDTH, ATLAS_HEIGHT), (0, 0, 0, 0))
    for _state, row, frame_count in ROW_SPECS:
        top = round(row * source.height / ROWS)
        bottom = round((row + 1) * source.height / ROWS)
        for column in range(frame_count):
            left = round(column * source.width / COLUMNS)
            right = round((column + 1) * source.width / COLUMNS)
            cell = source.crop((left, top, right, bottom))
            fitted = fit_to_cell(cell)
            atlas.alpha_composite(fitted, (column * CELL_WIDTH, row * CELL_HEIGHT))
    return atlas


def save_atlas(atlas: Image.Image, png_path: Path, webp_path: Path) -> None:
    png_path.parent.mkdir(parents=True, exist_ok=True)
    atlas.save(png_path)
    webp_path.parent.mkdir(parents=True, exist_ok=True)
    atlas.save(webp_path, format="WEBP", lossless=True, quality=100, method=6)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--source-atlas", default="")
    parser.add_argument("--package-dir", default="")
    parser.add_argument("--background-threshold", type=float, default=32.0)
    parser.add_argument("--skip-contact-sheet", action="store_true")
    parser.add_argument("--skip-package", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    scripts_dir = Path(__file__).resolve().parent
    run_dir = Path(args.run_dir).expanduser().resolve()
    request = load_json(run_dir / "pet_request.json")
    pet_id = str(request.get("pet_id") or "")
    display_name = str(request.get("display_name") or pet_id)
    description = str(request.get("description") or "")
    if not pet_id or not display_name or not description:
        raise SystemExit("pet_request.json is missing pet_id, display_name, or description")

    source_atlas = (
        Path(args.source_atlas).expanduser().resolve()
        if args.source_atlas
        else Path(str(request.get("source_atlas") or "")).expanduser().resolve()
    )
    if not source_atlas.is_file():
        raise SystemExit(f"source atlas not found: {source_atlas}")

    final_dir = run_dir / "final"
    qa_dir = run_dir / "qa"
    final_png = final_dir / "spritesheet.png"
    final_webp = final_dir / "spritesheet.webp"
    validation_path = final_dir / "validation.json"
    contact_sheet = qa_dir / "contact-sheet.png"

    if final_webp.exists() and not args.force:
        raise SystemExit(f"{final_webp} already exists; pass --force to overwrite")

    atlas = normalize_source_atlas(source_atlas, background_threshold=args.background_threshold)
    save_atlas(atlas, final_png, final_webp)

    run(
        [
            sys.executable,
            str(scripts_dir / "validate_atlas.py"),
            str(final_webp),
            "--json-out",
            str(validation_path),
        ]
    )

    if not args.skip_contact_sheet:
        run(
            [
                sys.executable,
                str(scripts_dir / "make_contact_sheet.py"),
                str(final_webp),
                "--output",
                str(contact_sheet),
            ]
        )

    package_dir = None
    if not args.skip_package:
        package_dir = (
            Path(args.package_dir).expanduser().resolve()
            if args.package_dir
            else codex_home() / "pets" / pet_id
        )
        package_command = [
            sys.executable,
            str(scripts_dir / "package_custom_pet.py"),
            "--pet-name",
            pet_id,
            "--display-name",
            display_name,
            "--description",
            description,
            "--spritesheet",
            str(final_webp),
            "--force",
        ]
        if args.package_dir:
            package_command.extend(["--output-dir", str(package_dir)])
        run(package_command)

    summary = {
        "ok": True,
        "mode": "fast-single-atlas",
        "run_dir": str(run_dir),
        "source_atlas": str(source_atlas),
        "spritesheet": str(final_webp),
        "validation": str(validation_path),
        "contact_sheet": None if args.skip_contact_sheet else str(contact_sheet),
        "package": None if args.skip_package else str(package_dir),
    }
    qa_dir.mkdir(parents=True, exist_ok=True)
    summary_path = qa_dir / "fast-run-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
