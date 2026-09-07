# Reliability Lab fixtures

Two throwaway projects used to test and generate the Hermes Reliability Lab's
Quick Gate captures (`node scripts/capture-quick-gate-fixture.mjs` in the site
repo). They are copied into temporary directories by `tests/test_evidence.py`;
they are not installed with the package.

- `clean/` — `pygate run --mode canary` passes: no lint or type findings.
- `broken/` — the same shape with one real type error (`greeting()` is
  annotated `-> str` and returns `42`). `pygate run --mode canary` fails on
  the typecheck gate; lint stays clean.

Regenerate nothing by hand here; these are inputs, not outputs.
