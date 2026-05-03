---
name: hatch-pet
description: "Create, repair, validate, preview, and package Codex-compatible animated pet spritesheets from character art, screenshots, generated images, or visual references. Default to the fast built-in image_gen path: one built-in image generation, deterministic 8x9 normalization, and pet.json packaging. Use CLI/API-key or row-by-row workflows only when explicitly requested."
---

# Hatch Pet

## Goal

Create a Codex-compatible pet quickly. A finished package is only:

```text
${CODEX_HOME:-$HOME/.codex}/pets/<pet-id>/
  pet.json
  spritesheet.webp
```

The spritesheet is a `1536x1872` atlas: 8 columns, 9 rows, `192x208` per cell. Used frames:

```text
idle 6, running-right 8, running-left 8, waving 4, jumping 5,
failed 8, waiting 6, running 6, review 6
```

Default priority is speed. Do not start subagents, do not generate a base image, and do not generate separate row strips unless the user explicitly asks for the slower workflow.

## Default Fast Path

Use Codex built-in `image_gen` once. This path does not require `OPENAI_API_KEY` because image generation is performed by the agent tool, not a local Python API client.

Do not run `scripts/image_gen.py` or `hatch_fast_pet.py` in the default path. Those are CLI/API-key fallbacks only.

1. Prepare the run folder and prompt:

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/hatch-pet"
python "$SKILL_DIR/scripts/prepare_fast_pet_run.py" \
  --pet-name "<Name>" \
  --description "<one sentence>" \
  --pet-notes "<character description>" \
  --reference /absolute/path/to/reference.png \
  --force
```

If the user gives no name, infer a short name from the concept or reference filename. The script prints `run_dir`, `prompt_file`, `source_atlas`, and record/finalize commands.

2. Read `prompt_file`, then call built-in `image_gen` exactly once with that prompt.

If reference images are provided, make them visible to the agent first, then use them as visual references in the built-in generation. Keep the output as one complete 8x9 atlas. Select the original generated file under:

```text
${CODEX_HOME:-$HOME/.codex}/generated_images/.../ig_*.png
```

3. Record the selected built-in output into the run:

```bash
python "$SKILL_DIR/scripts/record_fast_imagegen_result.py" \
  --run-dir "$RUN_DIR" \
  --source /absolute/path/to/generated_images/.../ig_*.png
```

4. Normalize, validate, and package:

```bash
python "$SKILL_DIR/scripts/finalize_fast_pet_run.py" \
  --run-dir "$RUN_DIR" \
  --force
```

This defaults to automatic normalization. It first detects the actual sprite rows and frame blobs, removes edge-connected flat/checkerboard-like backgrounds, fits detected sprites into `192x208` cells, duplicates the nearest same-row frame when the generator leaves a required final frame blank, leaves unused cells transparent, writes `final/spritesheet.webp`, validates it, creates `qa/contact-sheet.png`, and packages `pet.json` plus `spritesheet.webp`. If detection cannot produce a valid atlas, it falls back to proportional 8x9 grid slicing.

## Time Budget

The default path has one image generation call plus local processing. Local processing should finish in seconds. Do not promise that the remote built-in image generation itself is guaranteed to return within 60 seconds; if it is slow or fails, report that blocker instead of expanding into the old multi-agent workflow.

## Prompt Shape

Use the prepared prompt as authoritative. Its shape is:

```text
Generate a clean pixel-art sprite sheet of one consistent character.
If reference images are provided, use them as the character and style reference.
Otherwise use this description: <character description>.

No UI, labels, text, numbers, cards, borders, frame guides, separators, checkerboard pattern, shadows, scenery, or watermarks.
Create exactly 9 action rows in this order with these frame counts:
Idle x6, Run right x8, Run left x8, Waving x4, Jumping x5, Failed x8,
Waiting x6, Running x6, Review x6.

Use an invisible 8 column x 9 row layout, not a drawn grid. Do not draw cell boxes, grid lines, row labels, column labels, gutters, dividers, or guide marks.
Create all 57 required pet drawings. Do not leave any required frame blank, especially the final used frame in each row.
Each row uses the listed frame count from left to right; positions after the last used frame must be completely empty.
Keep each full-body pose separated, centered, and fully inside its slot with a little breathing room.
Use a transparent background if supported; otherwise use one perfectly flat removable solid-color background that does not appear in the character. Never use a checkerboard transparency preview.
Keep the same character proportions, outfit, face, palette, outline, and pixel-art style across all frames.
```

## Visual Rules

- Use compact Codex digital pet style: chunky readable silhouette, thick dark outline, flat pixel-art/cel shading, simple expressive face, tiny limbs.
- Avoid polished illustration, 3D rendering, soft gradients, complex tiny accessories, shadows, glows, motion trails, speed lines, wave marks, loose sparkles, text, labels, UI, grids, and scenery.
- `waving` is shown by paw pose only.
- `jumping` is shown by body position only.
- `failed` may use small attached tears, smoke, or stars only if they touch the pet.
- `review` is shown by lean, blink, eyes, head tilt, or paw position.
- `running-right`, `running-left`, and `running` show locomotion through body and limbs only.

## Acceptance

Before calling the pet done:

- `${CODEX_HOME:-$HOME/.codex}/pets/<pet-id>/pet.json` exists.
- `${CODEX_HOME:-$HOME/.codex}/pets/<pet-id>/spritesheet.webp` exists.
- `final/validation.json` reports `ok: true`.
- `qa/detect-normalization-report.json` or `qa/grid-normalization-report.json` records which normalization path produced the final atlas.
- Inspect `qa/contact-sheet.png` for obvious identity drift, labels, visible grids, or non-transparent unused cells.

If automatic normalization still leaves the contact sheet visually bad, regenerate one full atlas with a tighter prompt. Do not fall back to subagents or row-by-row generation unless the user explicitly chooses the slower workflow.

## Fallbacks

- CLI/API-key fallback: use only when the user explicitly asks for local CLI/API execution and has a valid `OPENAI_API_KEY`.
- Slow row-by-row workflow: use `prepare_pet_run.py`, `pet_job_status.py`, `record_imagegen_result.py`, row repair scripts, and `finalize_pet_run.py` only when the user explicitly asks for maximum QA, row repairs, preview videos, or the old multi-step process.
