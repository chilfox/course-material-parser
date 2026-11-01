"""Replace a file whole, so a reader never sees it half-written."""

import os
import tempfile
from pathlib import Path


def write_atomically(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` through a temporary file in the same folder and a rename.

    Readers and overlapping writers see either the old file or the new one, never a partial
    one, without a lock. The temporary file is hidden (``.<stem>-...tmp``) and removed if
    the write fails.
    """
    with tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=f".{path.stem}-", suffix=".tmp", delete=False
    ) as handle:
        try:
            handle.write(data)
        except BaseException:
            handle.close()
            os.unlink(handle.name)
            raise
    os.replace(handle.name, path)
