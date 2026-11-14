# CLI reference

For developers and users inspecting the tools behind the skill. Normal skill use is
through requests to your agent; start with [the README](../README.md).

The skill uses `parse` to create parsed material and `read` to access it. Its agent-facing
procedures live in [parsing](../references/parsing.md) and
[reading](../references/reading.md); this page describes the command interface rather
than replacing those instructions.

## Invocation and conventions

Run commands from any working directory, replacing `<skill-dir>` with the path to the
repository root:

```sh
uv run --project <skill-dir> parse --help
uv run --project <skill-dir> read --help
uv run --project <skill-dir> download-models --help
```

Use `parse <command> --help` or `read <command> --help` for exact arguments and output
details. In the examples below, prepend `uv run --project <skill-dir>` to each command.

- `MATERIAL` is a material id: its destination path relative to `library_root`, such
  as `economics/textbook`. `--dest` identifies material being parsed; `--source`
  identifies material being read.
- `ID` identifies a chapter or reading unit within one textbook. Get ids from `read toc`.
- `SPEC` selects source-PDF pages counted from 1: `28`, `15-30`, or `3,7,15-18`.
  Ranges are inclusive; printed page labels are not used.
- Settings always come from the skill directory's `settings.toml`, not the current
  working directory. See [configuration and runtime](runtime-reference.md).

## Creating parsed material: `parse`

| Command | Purpose |
|---|---|
| `parse start --pdf PATH --dest MATERIAL --type slides` | Convert a deck and make it ready to read. |
| `parse start --pdf PATH --dest MATERIAL --type textbook` | Convert a textbook once and leave its extraction pending split approval. |
| `parse inspect --dest MATERIAL` | Return a pending textbook's structure index. |
| `parse inspect --dest MATERIAL --pages SPEC` | Return extracted content for selected source pages to check split boundaries. |
| `parse propose --dest MATERIAL --plan PATH` | Validate a JSON split plan and save its snapshot and split proposal. |
| `parse finalize --dest MATERIAL --confirm` | Apply the last proposed snapshot after user approval and make the textbook ready to read. |

### Starting a parse

The destination must not already exist; missing parent folders are created. A long PDF
can take minutes to convert. The agent workflow calls for a timeout of at least
20 minutes.

`start` accepts mutually exclusive `--ocr` and `--no-ocr` flags. With neither flag, it
checks for a text layer and may return `ocr_required`. See
[OCR selection](runtime-reference.md#ocr-selection).

A successful slide parse produces one Markdown deck with source-page markers.
A textbook parse returns its structure index, including the `extraction_id` needed
by its split plan. Detected headings are evidence for planning, not an authoritative
outline; `inspect --pages` lets the agent check the stored extraction without another
conversion.

### Proposing and finalizing a textbook split

The sequence is:

```text
start → inspect → write split plan → propose → user approval → finalize
                                      ↑            |
                                      └─ changes ──┘
```

`parse propose --help` defines the complete JSON plan format. A plan names the extraction
it belongs to and organizes standalone reading units and chapters in reading order,
with chapter units nested under their chapters. Units select inclusive source-page
ranges and must cover every page. Adjacent units may share their boundary page.

A valid proposal saves a snapshot and writes `split-proposal.md` in the pending material.
Its JSON result includes an `overview` for the agent to show unchanged. When the proposal
tree exceeds 40 lines, the overview includes a shortened tree and a link to the complete
proposal. An invalid plan returns `invalid_plan` without replacing the previous snapshot
or proposal file.

`--confirm` asserts that the user approved the latest proposal; it is not an interactive
prompt. Finalization uses the saved snapshot, not the current contents of the original
plan file. Any changes require proposing again and obtaining new approval. A ready
textbook cannot be finalized again.

## Reading parsed material: `read`

| Command | Purpose |
|---|---|
| `read list [PREFIX]` | List ready materials, optionally within a library folder. |
| `read toc --source MATERIAL` | Return a textbook's chapters and units; for slides, return the type and page count. |
| `read get --source MATERIAL --id ID` | Print a textbook reading unit or a chapter's units joined in order. |
| `read get --source MATERIAL` | Print a whole slide deck. |
| `read get --source MATERIAL --pages SPEC` | Print selected slides in the requested page order. |
| `read render --source MATERIAL --pages SPEC` | Render source pages to PNG files and return their paths. |
| `read clean-renders --source MATERIAL` | Delete one material's page renders, only when the user asks. |
| `read clean-renders --all --confirm` | Delete page renders for every ready material, only when the user asks. |

Only ready material is listed: pending textbooks, failed material, and interrupted parses
are omitted. A list prefix matches whole folder names: `ml` matches `ml/prml`, not
`mlx/prml`.

Textbooks require `--id`; `--pages` applies only to slides for `get`. These selectors
cannot be combined. A chapter read exceeding `combined_read_max_chars` returns
`too_large`; re-run with `--confirm` only when the whole chapter is needed. Reading
units and slides are not size-limited.

### Markdown markers and visuals

`read get` prints Markdown without a JSON wrapper:

- `<page N>` means the following content comes from source page N.
- `<visual>` marks a picture and is followed by its detected caption, if any.

Render the source page when understanding its visual content is necessary. Rendered
PNGs stay available until the user asks for cleanup; rendering a page again recreates
its file.

## Model setup: `download-models`

```sh
uv run --project <skill-dir> download-models
```

Downloads missing models selected by `device` and `allow_ocr`, preserving existing
models. The agent must obtain the user's agreement before downloading. See the
[model reference](runtime-reference.md#models) for sizes, cache location, and offline
behavior.

## Output and errors

The `parse` and `read` commands return JSON on stdout, except `read get`, which prints
Markdown, and `--help`, which prints usage text. Failures leave stdout empty, write one
JSON error object to stderr, and exit with code 1:

```json
{"error":"settings_error","message":"..."}
```

Errors can include additional detail fields. Use the message to identify the required
fix. Common cases:

| Code | Action |
|---|---|
| `settings_error` | Ask the user to fix settings or choose an available device. |
| `models_missing` | Ask the user to run model setup, or obtain agreement to run it. |
| `destination_exists` | Choose a different destination with the user. |
| `ocr_required` | Decide whether to use OCR or explicitly skip the text-layer check. |
| `ocr_disabled` | OCR is forbidden by the user's settings. |
| `invalid_plan` | Correct the reported split-plan problems and propose again. |
| `too_large` | Read fewer units, or confirm that the whole chapter is needed. |
| `conversion_failed` | Conversion failed and material is marked failed; retry with a new destination. |

For more setup detail, see [configuration and runtime errors](runtime-reference.md#errors).
