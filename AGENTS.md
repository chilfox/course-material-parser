## About this repo

A local agent skill (the repository root is the skill directory) that parses course PDFs
(lecture slides and textbooks) with Docling into parsed material. It gives agents two CLIs,
`parse` and `read`, to create and read that material. Spec: GitHub issue #10.

## Testing

- `uv run pytest`: default test suite. It never runs Docling.
- `uv run ruff check . && uv run ruff format --check .`: lint and format check.
- `uv run pytest -m docling`: opt-in real Docling smoke test. It needs the models from
  `uv run docling-tools models download`.

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues using `gh`. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context domain docs: root `GLOSSARY.md` and `docs/adr/`. See `docs/agents/domain.md`.
