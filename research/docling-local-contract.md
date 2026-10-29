# Docling local extraction and provenance contract

Research date: 2026-10-29.

Context: [Establish Docling's local extraction and provenance contract](https://github.com/chilfox/course-material-parser/issues/8), within [Specify a simple local Docling course-material skill](https://github.com/chilfox/course-material-parser/issues/1).

Scope: unmodified Docling run locally on macOS or Linux for PDF course material. Research only: no packages or models were installed, PDFs uploaded, conversions run, or benchmarks performed. The researcher profile performed primary-source web research because the standalone research skill was unavailable; the coordinator published this asset.

## Evidence boundary

The documentation and source links below point to mutable pages or `main`, not a pinned release. They establish documented interfaces and source-inspected behavior at research time, not compatibility with every Docling v2 release. A later implementation must lock compatible `docling` and `docling-core` versions and verify the required APIs and serialization behavior against that environment.

The long-document issue cited below specifically reports Docling 2.28.0 and docling-core 2.23.3. It is not evidence about the performance of the current release on the intended materials.

## Summary

Docling's public `DoclingDocument` API exposes recognized text, headings and hierarchy, reading order, structured tables, pictures, and, where available, page and bounding-box provenance. Docling Document JSON is documented as a lossless serialization of that recognized intermediate representation. It is a candidate for proposing and executing textbook splits without converting the PDF again. Markdown alone is not an equivalent structured intermediate.

Formula enrichment can extract LaTeX, and the inspected Markdown serializer emits math delimiters for formula items. Neither this nor any other feature establishes extraction accuracy or an 80% usefulness rate on the intended course material. Page correspondence, visual references, split boundaries, and rendering behavior still need version-pinned validation on representative local PDFs.

## Findings

### Structured document, hierarchy, and reading order

Documented capability: `DocumentConverter().convert(...)` returns a conversion result whose `.document` is a `DoclingDocument`. The v2 representation includes `texts`, `tables`, `pictures`, `groups`, `body`, and page information. Text items include titles, section headings, and formulas. Items reference parents and children; child ordering in the body tree expresses reading order. `iterate_items()` exposes traversal and returns `(item, level)` pairs. The model distinguishes body content from furniture such as headers and footers.

Sources: [Document concepts](https://docling-project.github.io/docling/concepts/docling_document/), [document model source](https://raw.githubusercontent.com/docling-project/docling-core/main/docling_core/types/doc/document.py).

A CLI can expose recognized headings, item identifiers, levels, order, and available provenance to an agent proposing a split. These are recognized structural signals, not authoritative textbook chapter boundaries. Human approval remains a separate product requirement; the representation does not decide the split.

Unknown quality: heading detection, nesting, reading order, multi-column layouts, repeated headers, exercises, and front matter depend on the PDF and pipeline. A tree can be present but wrong or incomplete.

### Intermediate for splitting without reparsing

Documented capability: Docling describes JSON output as a lossless serialization of the Docling Document. The public model provides `save_as_json(...)` and `DoclingDocument.load_from_json(...)`. The model contains recognized structure, item references, tables, and provenance for later inspection.

Sources: [Supported formats](https://docling-project.github.io/docling/usage/supported_formats/), [document model source](https://raw.githubusercontent.com/docling-project/docling-core/main/docling_core/types/doc/document.py).

Limitations:

- Lossless means relative to the serialized Docling Document, not recovery of content that was undetected or misrecognized.
- Markdown is a presentation export, not a substitute for the structured intermediate. A split executor needs an explicit, tested mapping from an approved plan to structured items and Markdown output.
- JSON may embed or reference images depending on export settings. Inspected current source defaults `save_as_json` to embedded images; `load_from_json` defaults to disallowing local image references unless explicitly enabled for trusted inputs. Do not assume every image reference survives a move or a default reload. Retaining the source PDF for later rendering is a separate concern.
- Version compatibility, range selection, and reserialization of complex cross-section items require verification. This research does not establish that arbitrary subtree exports preserve all context exactly.

### Mathematics in Markdown

Documented capability: `PdfPipelineOptions.do_formula_enrichment = True` adds formula understanding for recognized formula items and extracts LaTeX using the CodeFormula model. Most enrichment models are disabled by default and add processing time. The documentation describes crop and repetition-related formula failure modes.

Source: [Enrichments](https://docling-project.github.io/docling/usage/enrichments/).

Source-inspected behavior, not a conversion test: the current `docling-core` Markdown serializer emits `$...$` for an inline `FormulaItem` and `$$...$$` otherwise. If a formula has original content but no decoded text, it emits `<!-- formula-not-decoded -->`. This is an observation about mutable source, not a guarantee for an unspecified installed version.

Source: [Markdown serializer](https://raw.githubusercontent.com/docling-project/docling-core/main/docling_core/transforms/serializer/markdown.py).

Unknown quality: formula detection and LaTeX correctness, especially inline mathematics, scanned equations, equation numbers, multiline expressions, and notation inside table cells, are unverified for the intended PDFs. A Markdown renderer must support the emitted syntax. Enabling enrichment does not prove all mathematics is retained correctly.

### Tables

Documented capability: `TableItem` exposes structured table data and can carry structure annotations. The document schema includes cells, row and column offsets, and optional layout information. Docling exports readable Markdown tables.

Sources: [Document concepts](https://docling-project.github.io/docling/concepts/docling_document/), [document schema](https://docling-project.github.io/docling/reference/docling_document/).

Source-inspected limitation: the current Markdown serializer flattens nested-table contents in certain contexts. Markdown tables cannot generally express every complex table structure faithfully; structured JSON retains distinctions the export may lose.

Source: [Markdown serializer](https://raw.githubusercontent.com/docling-project/docling-core/main/docling_core/transforms/serializer/markdown.py).

Unknown quality: cell matching, merged cells, multipage tables, scientific notation, and reading order require representative samples. Structure support does not prove correct extraction.

### Pages, boxes, and visual references

Documented capability: a document item may have a `prov` list. Each `ProvenanceItem` records `page_no`, a bounding box, and a character span. Bounding boxes include a coordinate origin, `TOPLEFT` or `BOTTOMLEFT`; page size and origin matter when translating a box to rendered pixels. Layout information exists if available. An item can have no provenance or multiple entries.

Sources: [Document concepts](https://docling-project.github.io/docling/concepts/docling_document/), [document schema](https://docling-project.github.io/docling/reference/docling_document/).

The representation includes `PictureItem`s, captions, and references. The inspected Markdown serializer defaults to `<!-- image -->` as a picture placeholder. The official export example demonstrates embedded or external image exports and picture/table crops via `get_image(...)` when images have been generated.

Sources: [Export figures example](https://docling-project.github.io/docling/_generated/examples/export_figures/), [Markdown serializer](https://raw.githubusercontent.com/docling-project/docling-core/main/docling_core/transforms/serializer/markdown.py).

A skill can derive a visual marker from a detected picture's identity and available provenance without permanently extracting every image. A generic placeholder alone does not provide a stable item identity or page number. Page markers need an explicit application contract, including missing or multipage provenance and the difference between printed page labels and physical PDF pages.

Unknowns: detection of every meaningful diagram, plot, screenshot, or slide visual, and correctness of captions and boxes. Page correspondence through Markdown export or section boundaries must be tested, not inferred from provenance existing in JSON.

### On-demand page rendering

Docling option: the official example sets `generate_page_images = True`, `generate_picture_images = True`, and `images_scale`, then accesses `doc.pages[page_no].image.pil_image` and item crops. It describes scale 1 as approximately 72 DPI. This generates images during conversion; it does not demonstrate cheap rendering of an arbitrary page later from image-free JSON.

Source: [Export figures example](https://docling-project.github.io/docling/_generated/examples/export_figures/).

Complementary option: `pypdfium2` exposes public PDFium helpers and Pillow conversion, making it a candidate for rendering a selected page from the retained source PDF without rerunning Docling. Its docs describe prebuilt wheels on multiple platforms and Pillow as optional for image adapters.

Sources: [pypdfium2 introduction](https://pypdfium2.readthedocs.io/en/stable/readme.html), [API](https://pypdfium2.readthedocs.io/en/stable/python_api.html).

Verify Docling page numbering versus renderer indices, rotation, crop boxes, origins, and dimensions on the chosen versions. Renderer selection, licensing/dependency implications, and image lifetime remain decisions, not conclusions of this research.

### OCR, local execution, and model downloads

Documented capability: Docling supports scans through selectable OCR engines. The standard `docling` package includes RapidOCR; Tesseract requires system dependencies, and other engines have their own extras or platform requirements. OCR language selection is engine-specific, with documented `iso:`-prefixed BCP-47 support. An opt-in `replace_broken_text_layer` option addresses pages whose visible text has a broken PDF text layer.

Sources: [Installation](https://docling-project.github.io/docling/getting_started/installation/), [OCR concepts](https://docling-project.github.io/docling/concepts/OCR/).

Privacy boundary: local model execution does not mean zero network traffic. Remote services require explicit opt-in with `enable_remote_services=True`, while model weights may download on first use independently. This project's local-only requirement excludes remote OCR, picture-description, or VLM API configuration.

The documentation provides `docling-tools models download` for prefetching and `artifacts_path`, `--artifacts-path`, or `DOCLING_ARTIFACTS_PATH` for local artifacts. Exact models, OCR-language assets, disk sizes, licenses, and completeness of a prefetch command depend on the pinned pipeline. Installing packages alone does not establish offline readiness.

Source: [Advanced options](https://docling-project.github.io/docling/usage/advanced_options/).

Unknown quality: OCR depends on scans, languages, fonts, annotations, and engine. Successful conversion does not establish adequate extraction of every page or formula.

### macOS, Linux, and hardware

Documented capability: the installation guide lists macOS and Linux on x86_64 and arm64, supports `uv`, and documents a Linux CPU-only PyTorch index. GPU acceleration is optional; accelerator availability and OCR acceleration depend on the host, PyTorch distribution, and OCR engine.

Sources: [Installation](https://docling-project.github.io/docling/getting_started/installation/), [GPU guide](https://docling-project.github.io/docling/usage/gpu/).

Compatibility caveat: the guide says newer PyTorch releases no longer provide Intel macOS wheels and documents a workaround with PyTorch 2.2.2, requiring Python 3.12 or lower. This is documentation-reported, not a tested installation matrix. Resolve and test the actual lock on each supported platform.

No minimum RAM, VRAM, or acceptable runtime for this skill was established. CPU support does not imply that formula enrichment or long textbooks will be fast enough on a particular machine.

### Long-document resources and failures

Documented capability: `convert` accepts a `page_range`, maximum page/file-size limits, and a progress callback. Current advanced docs describe `queue_max_size` and `max_concurrent_results` for buffered/decoded pages, `OMP_NUM_THREADS` for CPU threads, and enrichment continuing after apparent page-processing completion. Progress reporting can include failed or timed-out pages.

Sources: [Converter source](https://raw.githubusercontent.com/docling-project/docling/main/docling/document_converter.py), [advanced options](https://docling-project.github.io/docling/usage/advanced_options/).

Practical evidence, not a benchmark: an upstream issue reports a 3,000-plus-page PDF not finishing after eight hours under Docling 2.28.0 on Windows. A commenter reported similar behavior on macOS; another described splitting into smaller PDFs. These are anecdotes for particular inputs and versions, not universal limits or throughput estimates.

Source: [Docling long-document report](https://github.com/docling-project/docling/issues/1283).

Runtime and memory depend on pages, decoded images, OCR, tables, enrichment, and hardware. Retained page images or embedded JSON images can increase resource use. Inspect conversion status, partial failures, and completion in the chosen version. If page-range conversion becomes necessary, verify numbering, hierarchy, cross-range tables, and assembly; independently converted ranges are not established as equivalent to a full conversion.

## Public API illustration

This illustrates documented/current-source APIs. It was not executed and is not implementation-ready code. It intentionally does not generate persistent images or use remote services.

```python
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import DoclingDocument, PictureItem, TableItem

options = PdfPipelineOptions()
options.do_formula_enrichment = True
# Configure OCR explicitly for the selected source and environment.
# Do not enable remote services.

converter = DocumentConverter(
    format_options={
        InputFormat.PDF: PdfFormatOption(pipeline_options=options)
    }
)
result = converter.convert(Path("source.pdf"))
doc = result.document

# Inspect conversion status/errors as supported by the pinned version
# before treating this output as complete.
doc.save_as_json(Path("document.json"))
doc.save_as_markdown(Path("document.md"))

# Later inspection without converting the PDF again.
loaded = DoclingDocument.load_from_json(Path("document.json"))
for item, level in loaded.iterate_items():
    provenance = [
        (p.page_no, p.bbox, p.charspan)
        for p in getattr(item, "prov", [])
    ]
    if isinstance(item, (PictureItem, TableItem)):
        print(item.self_ref, item.label, level, provenance)
```

Use the retained source PDF for later page rendering. This illustration does not specify splitting, overwrite behavior, temporary-image lifetime, or approval protocol.

## Open questions and decision coverage

The research exposes validation needs, not authority to make product decisions. These questions already fit the map's live tickets:

- [Define representative material and useful-enough parsing](https://github.com/chilfox/course-material-parser/issues/7): real extraction quality, accepted scans/languages, and tolerable failures. No 80% claim is supported here.
- [Define the parse workflow and confirmed textbook split plan](https://github.com/chilfox/course-material-parser/issues/6): item identities and split boundaries, missing provenance, cross-page/nested content, partial conversions, and approved execution.
- [Define stored material, section identity, and page references](https://github.com/chilfox/course-material-parser/issues/5): intermediate persistence, Markdown page markers, printed labels, visual references, and selected renderer/page correspondence.
- [Define reader discovery, retrieval, and context-size protection](https://github.com/chilfox/course-material-parser/issues/2): retrieval and render-request contracts.
- [Choose a safe lifetime for on-demand rendered pages](https://github.com/chilfox/course-material-parser/issues/3): path lifetime and cleanup.
- [Define portable setup and minimal local configuration](https://github.com/chilfox/course-material-parser/issues/9): version lock, model artifacts, OCR languages, hardware/network expectations, and platform constraints.
- [Confirm the minimal architecture and essential verification boundary](https://github.com/chilfox/course-material-parser/issues/4): minimal integration and required round-trip/section-export checks, including no lost or duplicated content in representative cases.

No new independent decision ticket is justified by documentation research alone. Any document-specific fallback or additional normalization should be scoped only when concrete examples expose a need.

## Source selection

Primary Docling documentation, schema, examples, and source were retained. The upstream long-document report is retained only as explicitly version-specific anecdotal evidence. Third-party performance search results were dropped because they do not establish representative performance for this project. An initially attempted `/docling/examples/export_figures/` URL returned HTTP 404; the current generated example linked above was retrieved instead.
