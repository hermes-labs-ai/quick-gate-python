# Reliability Lab fixtures

Two throwaway projects used only to generate the Hermes Reliability Lab's Quick
Gate captures (`node scripts/capture-quick-gate-fixture.mjs` in the site repo).
Not part of the package, not covered by the CI test matrix, not installed.

- `clean/` — `pygate run --mode canary` passes: no lint or type findings.
- `broken/` — the same shape with one real type error (`greeting()` is
  annotated `-> str` and returns `42`). `pygate run --mode canary` fails on
  the typecheck gate; lint stays clean.

Regenerate nothing by hand here; these are inputs, not outputs.
