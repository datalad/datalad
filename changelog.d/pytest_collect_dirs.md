### 🏠 Internal

- DataLad's pytest plugin no longer forces collection into every directory, so a
  bare `pytest` in a DataLad (or extension) checkout stops descending into
  `.venv/`, `.tox/` and `build/`.
  (by [@just-meng](https://github.com/just-meng))
