# Changelog

## 1.2.2

Documentation and maintainability release; scientific screening thresholds and thermal-model behavior are unchanged.

- Added a practical usage guide covering installation, coverage-only checks, full runs, cache behavior, reproducibility, testing, and common failure modes.
- Added a complete TOML configuration reference, output-file reference, and architecture overview under `docs/`.
- Reworked the README around a short quick-start path and linked the detailed documentation.
- Added `CONTRIBUTING.md` with development checks and guidance for scientific changes.
- Expanded `target.example.toml` into a self-documenting reference configuration while keeping the example target files concise.
- Added module/function docstrings and focused comments around non-obvious statistical, photometric, network, and thermal-model choices.
- Removed or rewrote comments that merely repeated code or mixed documentation languages without adding technical context.
- Centralized the package version for packaging by making `pyproject.toml` read `wise_miner.__version__` dynamically.
- Added configuration-loading regression tests and expanded CI with compile/CLI smoke checks.
- Included the AllWISE cone-search radius in cache filenames so reruns with a changed contamination radius cannot silently reuse an incompatible cached response.
- Added the MIT License and declared the package license in project metadata.


## 1.2.1

Repository-maintenance release; scientific screening thresholds and thermal-model logic are unchanged.

- Removed the bundled `.venv` and generated/cache artifacts from the distributable project.
- Added a repository-level `.gitignore` and `.gitattributes`.
- Reworked the README so the current v1.2.x classification names are presented first; obsolete v1.0-era target labels were removed from current usage documentation.
- Moved scientific validation notes to `docs/SCIENTIFIC_SCOPE.md` and updated their version wording.
- Added `pyproject.toml` metadata and an installable `wise-neowise-miner` console entry point.
- Added `python -m wise_miner` support and `--version`.
- Centralized project name/version metadata in `wise_miner/__init__.py` so runtime banners and User-Agent strings do not drift independently.
- Updated platform launch scripts so they no longer depend on a committed `.venv` path.
- Added GitHub Actions unit-test coverage for Python 3.11, 3.12, and 3.13.

## 1.2.0

- Added independent formal-status vs follow-up-priority logic.
- Added `band_coherence.csv`.
- Added same-band Stouffer screening p across all pre-defined epochs.
- Added robust-positive epoch checks using median, trimmed mean, positive fraction, effective N and leave-one-out stability.
- Added `W3_REPEATABLE_SUBTHRESHOLD` high-priority follow-up flag.
- Formal v1.1 detection thresholds are unchanged.
- Added TP124-like regression test.

## 1.1.0

- Added `[detection]` configuration section.
- Added minimum epoch frame-count requirements.
- Added within-band Benjamini-Hochberg FDR q-values.
- W1/W2 no longer promote the overall thermal-detection classification.
- Same-band repeatability is required.
- Added explicit weak single-epoch W4 label.
- Added effective frame count, max frame weight, positive fraction, trimmed-mean and leave-one-out diagnostics.
- Added 2023 TO119-like regression tests.
- Expanded report with q-values and robustness diagnostics.
