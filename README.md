# Course material parser

A local agent skill that parses course PDFs (lecture slides and textbooks) with
[Docling](https://github.com/docling-project/docling) into parsed material, and gives agents
two CLIs: `parse` to create parsed material and `read` to read it. Everything runs locally.

Supported platforms: Apple Silicon macOS and Linux (x86_64 and arm64). You need
[uv](https://docs.astral.sh/uv/).

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

   The comments in `settings.example.toml` explain each key and which `device` fits your
   platform.

3. Download the Docling models once:

   ```sh
   uv run docling-tools models download
   ```

After setup, parsing needs no network.

## Device

The configured `device` decides what is used. It is never chosen automatically:

- `mps` on Apple Silicon. Docling doesn't support MPS for the formula model
  (CodeFormulaV2), so that model always runs on CPU there. All other stages use MPS.
- `cuda` on Linux with an NVIDIA GPU. Linux uses the default PyPI PyTorch build.
- `cpu` works everywhere, but formula enrichment is always on, so long textbooks are slow
  on CPU.

## Models

`docling-tools models download` saves about 1.4 GB to `~/.cache/docling/models`. Its
default set includes every model the parser uses:

| Model | Used for |
|---|---|
| `docling-layout-heron` | Page layout |
| TableFormer (`docling-models`) | Table structure |
| `DocumentFigureClassifier-v2.5` | Picture classification |
| CodeFormulaV2 | Formula enrichment (LaTeX) |
| RapidOCR | OCR |

Docling chooses the OCR engine automatically. With the locked dependencies (no ocrmac,
onnxruntime, or EasyOCR installed), it chooses RapidOCR with the torch backend, which is in
the default download.

This was verified with Docling 2.145 on Apple Silicon: both test fixture PDFs (one with a
text layer and one image-only) converted with formula enrichment and OCR on. The
Hugging Face hub was set to offline mode and its cache was empty. Docling finds the
models only when it's given this download directory (`artifacts_path`). Otherwise it looks
in the Hugging Face cache, which fails offline.

## Usage

Agents run the CLIs from any working directory:

```sh
uv run --project <skill-dir> parse --help
uv run --project <skill-dir> read --help
```
