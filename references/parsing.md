# Parsing a course PDF

## 1. Ask for the destination and type

List the existing materials to see how the library is organized:

```sh
uv run --project <skill-dir> read list
```

Look at the PDF's first page as text to learn its course and title, and suggest the destination and type from it.
Then ask the user in one message for the destination (MATERIAL, for example `economics/mankiw-principles-10e`) and the type (`slides` or `textbook`), suggesting both.
Start only after the user answers.

## 2. Start

Converting a long PDF takes minutes; run `parse start` with a timeout of at least 20 minutes.

```sh
uv run --project <skill-dir> parse start --pdf PATH --dest MATERIAL --type TYPE
```

On `destination_exists`, relay the message and ask the user for another destination.

Slides are ready to read once this succeeds; continue at step 8.
A textbook is left pending, and the output is its structure index; continue with step 3.

## 3. Find the textbook's structure

A unit starts on the source page of its heading in the structure index.
Where the index is doubtful (a missing or out-of-order number, a duplicated heading, a chapter with no detected sections), check the pages themselves:

```sh
uv run --project <skill-dir> parse inspect --dest MATERIAL --pages SPEC
```

This step is done when every unit you will plan has a start page found in the index or in inspected pages.

## 4. Write the split plan

Write the plan as JSON at any path, in the format given by `parse propose --help`.
Organize it like this:

- Each main numbered section is one unit holding its subsections, regardless of length.
  A chapter without numbered sections is one unit, titled with the chapter's title.
- Content before a chapter's first section is the chapter's introduction unit.
- Chapter-end material is at most two units: a summary unit (summaries, key concepts) and an exercises unit (review questions, problems, answers), each only when present.
  Quizzes and exercises inside a section stay in that section.

Ids:

| Item | Id |
|---|---|
| Chapter 2, appendix A | `chapter-02`, `chapter-a` |
| Numbered section 2.1 | `2-1` |
| Chapter 2 introduction, summary, exercises | `2-intro`, `2-summary`, `2-exercises` |
| Only unit of chapter 2, which has no numbered sections | `chapter-02-content` |
| Standalone unit outside chapters | a plain name: `front-matter`, `glossary`, `index`, `references` |

Titles are the book's heading text without its number, all of a unit's headings joined with `; ` when it holds several.
An introduction unit, which has no heading of its own, is titled `Introduction`.

## 5. Propose

```sh
uv run --project <skill-dir> parse propose --dest MATERIAL --plan PATH
```

## 6. Ask for approval

Show the user the `overview` from a valid `propose` unchanged.
Add `Limitations: ...` only when it affects the decision, and end with:

Reply approve, or describe changes.

Explain the process only when asked.

This step ends when the user replies approve to the latest split proposal.
If they describe changes instead, edit the plan and return to step 5.

## 7. Finalize

```sh
uv run --project <skill-dir> parse finalize --dest MATERIAL --confirm
```

## 8. Report

Tell the user MATERIAL is ready. To read it, follow [reading.md](reading.md).
