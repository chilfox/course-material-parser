---
name: course-material-parser
description: Course textbooks and lecture slides parsed for reading. Use for any task on their content, or to parse a course PDF only when the user explicitly asks to parse it.
---

# Course material parser

Parsed material lives in a library reached through two CLIs, `parse` and `read`.
Run them from any directory, where `<skill-dir>` is the directory holding this file:

```sh
uv run --project <skill-dir> parse ...
uv run --project <skill-dir> read ...
```

Learn everything about the library from the CLIs: their output, `--help`, and error messages.

`settings_error` and `models_missing` are setup problems for the user: relay the message and its fix, and leave `settings.toml` to the user.
Run `uv run --project <skill-dir> download-models` only after the user agrees, since it downloads over 1 GB of models.

## Workflows

- Working with course material's content: read [references/reading.md](references/reading.md).
- Parsing a PDF, only when the user explicitly asks to parse it: read [references/parsing.md](references/parsing.md).
