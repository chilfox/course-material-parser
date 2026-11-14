# Reading parsed material

1. Learn the page numbers and the markers in `get` output, once per session:

   ```sh
   uv run --project <skill-dir> read --help
   ```

2. Find the material:

   ```sh
   uv run --project <skill-dir> read list
   ```

3. Show its table of contents:

   ```sh
   uv run --project <skill-dir> read toc --source MATERIAL
   ```

4. Read what the task needs.
   For a textbook, read a unit or a chapter by its id:

   ```sh
   uv run --project <skill-dir> read get --source MATERIAL --id ID
   ```

   Read only the units the task needs.
   For a task about a whole chapter, read the chapter id, and on `too_large` re-run with `--confirm`.

   For slides, read the whole deck, or some pages:

   ```sh
   uv run --project <skill-dir> read get --source MATERIAL
   uv run --project <skill-dir> read get --source MATERIAL --pages SPEC
   ```

5. To see source pages as images, render them and view the PNG files:

   ```sh
   uv run --project <skill-dir> read render --source MATERIAL --pages SPEC
   ```
