# Formula engines: CPU float32 and pinned MLX on Apple Silicon

We run CodeFormulaV2 in float32 on `cpu`, through Docling's MLX engine on `mps`,
and with Docling's unchanged default dtype on `cuda`. We accept the measured
quality/speed tradeoff for agent-readable parsed material, not CPU-identical output.
This records [#25](https://github.com/chilfox/course-material-parser/issues/25)
and [#27](https://github.com/chilfox/course-material-parser/issues/27).

## Rationale and boundaries

An 898-source-page economics parse on an Apple M5 Pro was killed after a 20-minute
agent timeout. Formula enrichment accounted for about 95% of conversion time.
CPU bfloat16 was the measured bottleneck: direct investigation found about 13x
slower PyTorch inference than float32 despite hardware bfloat16 support. The
initialized Docling sample below measured about 10x faster enrichment with float32.
We choose CPU float32 from measurement, not hardware flags.

Docling's Transformers engine refuses MPS for every vision-language model. Its
public MLX engine options enable GPU CodeFormulaV2 without patching Docling.
MLX Granite Docling was similarly fast but rejected for worse output, including
letter-spacing and misspellings. TableFormer still runs on CPU on `mps`, as
forced upstream; revisit after
[docling-project/docling#3202](https://github.com/docling-project/docling/issues/3202)
changes that. No CPU fallback is allowed: unavailable MLX runtime/weights or failed
conversion must produce an actionable error, never silently switch engines.

We rely on `mlx-community/CodeFormulaV2-mlx-bf16`, a community conversion of
`docling-project/CodeFormulaV2` made with `mlx_vlm.convert`, at bf16 precision and
under CDLA-Permissive-2.0. Downloads pin revision
`f29c446f17d772025137fabc11288f07769c316f` to contain community-repository changes.
Docling ignores revisions when loading existing folders: pinning is enforced only
at download, and pre-flight checks folder presence, not completeness, revision or
integrity. Existing folders are skipped; move unverified weights aside to replace
them. `mlx-vlm` is locked and installed only on Apple Silicon macOS.

`download-models`, pre-flight and conversion share model selection and Docling's
`cache_dir/models` (including `DOCLING_CACHE_DIR`). Setup reads current settings;
CPU/CUDA need PyTorch formula weights, MPS needs MLX instead. Setup includes OCR
models when `allow_ocr` is true; pre-flight checks OCR only for `--ocr`, before
creating a destination. Parsing works offline after setup. No new setting is needed.

## Evidence and accepted tradeoff

Original economics measurements used Docling 2.145.0, torch 2.15.0,
transformers 5.22.1 and mlx-vlm 0.7.12 on an M5 Pro, with OCR off. Other stages
used MPS in every variant; pipelines were initialized before timing. The
`doc_enrich` timer measures code/formula enrichment, not isolated neural inference.

| Economics excerpt / formula engine | Enrichment seconds | Conversion seconds | Comparison |
|---|---:|---:|---|
| 10 source pages (120-129), CPU bfloat16 | 64.48 | 66.1 | Reference, 3 formulas |
| Same, CPU float32 | 6.48 | 8.3 | All 3 identical |
| Same, MLX CodeFormulaV2 | 1.49 | 3.3 | All 3 identical |
| Same, MLX Granite Docling (rejected) | 1.34 | 3.2 | Worse text |
| 100 source pages (100-199), CPU float32 | 14.38 | 25.6 | 8 formulas, 1 code item |
| Same, MLX CodeFormulaV2 | 2.15 | 13.0 | All 9 items identical |

Separately, #26 measured the actual all-CPU converter at 92.94 s before versus
9.32 s after float32, with all 3 formula outputs unchanged. These include
initialization and unequal cache/import warmth, unlike the initialized experiment.

The full #27 *Linear Algebra Done Wrong* comparison covered all 284 source pages
in identical contiguous 10-page chunks (29 chunks, last 4 pages), without OCR.
Both actual converters succeeded without errors, each producing **937 formulas
and 4 code items**. CPU float32 took **2487.18 s** (41m 27.18s); MPS/MLX took
**391.34 s** (6m 31.34s), an observed **6.36x** end-to-end ratio. These summed
chunk times include all stages and per-chunk initialization, not isolated formula
inference or a monolithic book conversion. CPU ran first, so import/cache warmth
may favor MPS; chunking may affect output. Cached download metadata matched the
MLX pin, not a fresh integrity audit.

Exact ordered label/source-page/text comparison, without normalization, found
**838/937 formulas identical and 99 formula-text differences**, no code differences,
and no label/page alignment differences. The small economics samples did not
establish general parity; CPU output is not mathematical ground truth either.

The [revised user acceptance](https://github.com/chilfox/course-material-parser/issues/27#issuecomment-6875086457),
also [recorded on #25](https://github.com/chilfox/course-material-parser/issues/25#issuecomment-6875087043),
accepts these 99 differences as a whole for substantial speed and agent readability.
It supersedes exact parity and per-difference approval as release gates, not a claim
that each formula is correct or equivalent. No CPU fallback remains unchanged.
The measurements, comparison counts and limitations above are the maintained
evidence for this decision; the linked issue comments record the acceptance.
No textbook or model weights are committed.
