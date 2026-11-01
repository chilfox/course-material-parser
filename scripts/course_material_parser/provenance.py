"""Check that every body item of a converted document traces to a source page.

Parsed material places content under the source page it comes from, so a body item
without page provenance could only be dropped or misplaced. The parse fails instead.
"""

from collections import Counter

from docling_core.types.doc import DocItem, DoclingDocument, FormulaItem, PictureItem, TableItem

# Singular and plural noun per reported kind, in reporting order.
_KIND_NOUNS = {
    "text": ("text item", "text items"),
    "table": ("table", "tables"),
    "formula": ("formula", "formulas"),
    "picture": ("picture", "pictures"),
    "other": ("other item", "other items"),
}


def missing_provenance(doc: DoclingDocument) -> str | None:
    """Describe the body items of ``doc`` that have no source page, or return ``None``.

    Furniture (running headers and footers) is never written, so it is not checked.
    The description gives the count per kind, for example
    ``3 text items, 1 formula have no source page``.
    """
    counts = Counter(
        _kind(item)
        for item, _level in doc.iterate_items()
        if isinstance(item, DocItem) and not item.prov
    )
    if not counts:
        return None
    parts = [
        f"{counts[kind]} {singular if counts[kind] == 1 else plural}"
        for kind, (singular, plural) in _KIND_NOUNS.items()
        if counts[kind]
    ]
    verb = "has" if counts.total() == 1 else "have"
    return f"{', '.join(parts)} {verb} no source page"


def _kind(item: DocItem) -> str:
    # FormulaItem is a kind of TextItem, so it is matched before falling back to text.
    if isinstance(item, FormulaItem):
        return "formula"
    if isinstance(item, TableItem):
        return "table"
    if isinstance(item, PictureItem):
        return "picture"
    if hasattr(item, "text"):
        return "text"
    return "other"
