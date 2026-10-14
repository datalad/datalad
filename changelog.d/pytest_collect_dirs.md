### 🧪 Tests

- DataLad's pytest plugin no longer forces collection into every directory, so a
  bare `pytest` in a DataLad (or extension) checkout stops descending into
  `.venv/`, `.tox/` and `build/`.
  [PR #7943](https://github.com/datalad/datalad/pull/7943)
  (by [@just-meng](https://github.com/just-meng))
