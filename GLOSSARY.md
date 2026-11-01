# Course Material Parsing

Course PDFs and their parsed representations for later reading by agents.

## Language

**Source PDF**:
The original PDF of lecture slides or a textbook from which content is parsed.

**Source page**:
A physical page of a source PDF, counted from 1, distinct from any page label printed on it. The only meaning of "page" in this project; printed page labels are never used.
_Avoid_: printed page, page label

**Parsed material**:
The readable representation of a source PDF, including its text, structure, and references to visual content.

**Split plan**:
A proposed organization of a textbook's content into chapters and sections for separate reading.

**Reading unit**:
A separately readable portion of a textbook, normally a main numbered section or a named portion such as a chapter introduction or references.

**Interrupted parse**:
A material folder left without `material.json` because a parse stopped part way. Readers ignore it, and a new destination may not be nested inside it.
_Avoid_: partial material, broken material

**Visual**:
A picture in parsed material, written as a `<visual>` marker followed by its detected caption, if any. Its content is understood by rendering the source page it sits under.
_Avoid_: figure, image placeholder

**Material id**:
The identity of one parsed material: its destination path relative to the library root.

**Unit id**:
An identifier, unique within one parsed material, that names a chapter or reading unit for reading.

**Boundary-page overlap**:
Intentional inclusion of the same source-PDF page in adjacent textbook reading units when their boundary falls within that page.

**Page render**:
An image of one source page of a parsed material, produced on request and kept until the user asks for it to be cleared.
_Avoid_: extracted image, temporary image
