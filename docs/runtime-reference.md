# Configuration and runtime reference

For users configuring or troubleshooting the skill. For first-time setup, follow
[the README](../README.md#1-make-the-skill-available-to-your-agent); for commands, see the [CLI reference](cli-reference.md).

## Settings

Settings live in `settings.toml` in the skill directory, regardless of the working
directory used to run a command. Copy [settings.example.toml](../settings.example.toml)
to create it. The file is git-ignored.

| Key | Required / default | Meaning |
|---|---|---|
| `library_root` | Required | Absolute path to an existing directory; `~` is expanded. All parsed material is stored here. |
| `device` | Required | `cpu`, `mps`, or `cuda`. Used for parsing and model setup, not for reading stored material. |
| `allow_ocr` | Optional; `true` | Allows parsing with OCR. Setting it to `false` forbids `--ocr` and excludes OCR models from model downloads. |
| `combined_read_max_chars` | Optional; `60000` | Positive integer limiting a combined chapter read. Larger chapter reads require `read get --confirm`; individual reading units and slides are not limited. |

Missing files, invalid TOML, unknown keys, missing required keys, and invalid values
produce `settings_error`. The library directory is never created automatically.
The user manages these settings; the agent relays setup errors rather than editing
the file.

After changing `device` or `allow_ocr`, run
`uv run --project <skill-dir> download-models` to fetch any newly required models.
Downloads require the user's agreement when performed by the agent.

## Device

The configured `device` decides what is used.
It is never chosen automatically:

- `mps` on Apple Silicon.
  The formula model (CodeFormulaV2) runs on the GPU through Docling's MLX engine.
  Table structure still runs on CPU (an upstream limitation); other stages use MPS.
  An unavailable `mlx-vlm` runtime is a `settings_error`: run `uv sync` on Apple Silicon macOS.
  Missing MLX weights are `models_missing`. Neither condition falls back to CPU.
- `cuda` on Linux with an NVIDIA GPU.
  Linux uses the default PyPI PyTorch build.
- `cpu` works on every supported platform. The formula model uses float32 to avoid slow CPU bfloat16 inference.

On `cuda`, the formula model keeps Docling's default dtype.

## Models

`download-models` reads `device` and `allow_ocr` from `settings.toml` and downloads only the
models they need (about 1.2 GB without OCR, for either formula engine). Models go to Docling's `cache_dir/models`, normally
`~/.cache/docling/models`; `DOCLING_CACHE_DIR` overrides the cache directory. Conversion reads
that same directory, so parsing needs no network after setup.

From any working directory, run `uv run --project <skill-dir> download-models`.
Setup validates settings and device availability, prints each model fetched or skipped
and the directory used, and never deletes models.
`parse start` checks model folders immediately after device availability and before destination
checks. Missing folders are reported without creating an interrupted parse or failed material.
RapidOCR is checked only for a parse with `--ocr`.

| Model | Approximate size | Used for |
|---|---|---|
| `docling-layout-heron` | 164 MB | Page layout, all devices |
| TableFormer (`docling-models`) | 342 MB | Table structure, all devices |
| `DocumentFigureClassifier-v2.5` | 32 MB | Picture classification, all devices |
| PyTorch CodeFormulaV2 | 610 MB | Formula enrichment on `cpu` (float32) and `cuda` (default dtype) only |
| MLX CodeFormulaV2 | 611 MB | Formula enrichment on `mps` only, replacing the PyTorch model |
| RapidOCR | 61 MB | OCR (downloaded only when `allow_ocr = true`) |

The MLX weights are the community conversion `mlx-community/CodeFormulaV2-mlx-bf16`,
not Granite Docling. Downloads pin revision `f29c446f17d772025137fabc11288f07769c316f`.
The pin is enforced when downloading, not when loading an existing folder: pre-flight checks
folder presence, not revision or file integrity. Existing model folders are skipped; to replace
unverified weights, move their folder aside and re-run setup.
`mlx-vlm` is a locked dependency installed only on Apple Silicon macOS.

Docling chooses the OCR engine automatically.
With the locked dependencies (no ocrmac, onnxruntime, or EasyOCR installed), it chooses RapidOCR with the torch backend, which `download-models` fetches when OCR is allowed.

This was verified with Docling 2.145 on Apple Silicon: both test fixture PDFs (one with a text layer and one image-only) converted with formula enrichment and OCR on.
The Hugging Face hub was set to offline mode and its cache was empty.
Docling finds the models only when it's given this download directory (`artifacts_path`).
Otherwise it looks in the Hugging Face cache, which fails offline.

## Errors

Agent CLIs return a JSON error on stderr and exit with code 1.

| Code | Meaning / fix |
|---|---|
| `settings_error` | Fix missing or invalid `settings.toml`, or choose an available device. |
| `models_missing` | Required model folders are missing; run `uv run --project <skill-dir> download-models`. |
| `conversion_failed` | Conversion failed; the material is marked failed. Retry with a new destination. |

## OCR selection

Allowing OCR does not enable it for every parse. Without an explicit OCR flag,
`parse start` checks the PDF's text layer. When more than half its pages have no
text layer, it returns `ocr_required` rather than converting.

- `--ocr` converts with OCR; it returns `ocr_disabled` if `allow_ocr = false`.
- `--no-ocr` converts without OCR and skips the text-layer check, for example when
  only source-page renders matter.

## Further reading

- [CLI reference](cli-reference.md) — commands and input/output conventions.
- [Formula-engine decision](adr/0001-formula-engines.md) — rationale, measurements,
  and accepted tradeoffs behind CPU float32 and MLX.
