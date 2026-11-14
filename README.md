# Course material parser

A local agent skill that parses course PDFs (lecture slides and textbooks) with [Docling](https://github.com/docling-project/docling) into parsed material, and gives agents two CLIs: `parse` to create parsed material and `read` to read it.
Everything runs locally.

Supported platforms: Apple Silicon macOS and Linux (x86_64 and arm64).
You need [uv](https://docs.astral.sh/uv/).

## Setup

Run these steps from the skill directory (the repository root):

1. Install Python 3.12 and the locked dependencies:

   ```sh
   uv sync
   ```

2. Create your settings, then set `library_root` and `device`:

   ```sh
   cp settings.example.toml settings.toml
   ```

   The comments in `settings.example.toml` explain each key and which `device` fits your platform.

3. Download the models your settings need (re-run after changing `device` or `allow_ocr`):

   ```sh
   uv run download-models
   ```

Setup validates settings and device availability, skips models already present, and never deletes
models. It prints each model fetched or skipped and the directory used.
After setup, parsing needs no network. Before creating anything, `parse start` checks that the
models it needs are present and reports `models_missing` with the setup command if not.

## Device

The configured `device` decides what is used.
It is never chosen automatically:

- `mps` on Apple Silicon.
  Docling doesn't support MPS for the formula model (CodeFormulaV2), so that model always runs on CPU there.
  The formula model uses float32; table structure also runs on CPU (an upstream limitation).
  Other stages use MPS.
- `cuda` on Linux with an NVIDIA GPU.
  Linux uses the default PyPI PyTorch build.
- `cpu` works everywhere. The formula model uses float32 to avoid slow CPU bfloat16 inference.

On `cuda`, the formula model keeps Docling's default dtype.

## Models

`download-models` reads `device` and `allow_ocr` from `settings.toml` and downloads only the
models they need (about 1.2 GB without OCR). Models go to Docling's `cache_dir/models`, normally
`~/.cache/docling/models`; `DOCLING_CACHE_DIR` overrides the cache directory. Conversion reads
that same directory, so parsing needs no network after setup.

From any working directory, run `uv run --project <skill-dir> download-models`.
`parse start` checks model folders immediately after device availability and before destination
checks. Missing folders are reported without creating an interrupted parse or failed material.
RapidOCR is checked only for a parse with `--ocr`.

| Model | Used for |
|---|---|
| `docling-layout-heron` | Page layout |
| TableFormer (`docling-models`) | Table structure |
| `DocumentFigureClassifier-v2.5` | Picture classification |
| CodeFormulaV2 | Formula enrichment (LaTeX) |
| RapidOCR | OCR (downloaded only when `allow_ocr = true`) |

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

## Usage

Agents run the CLIs from any working directory:

```sh
uv run --project <skill-dir> parse --help
uv run --project <skill-dir> read --help
```
