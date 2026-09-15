# Usage guide

This guide covers the practical workflow for running WISE/NEOWISE Asteroid Miner. For scientific interpretation, also read `SCIENTIFIC_SCOPE.md`.

## 1. Requirements

- Python 3.11 or newer.
- Internet access for uncached MPC/IRSA queries and WISE products.
- Enough local disk space for FITS cutouts. The required space depends on the number of matching frames and the configured cutout size.

A live run can take substantially longer than a coverage-only run because each usable frame may require intensity/uncertainty downloads, photometry, control sampling, and catalog checks.

## 2. Installation

Clone or unpack the repository, then work inside the project directory.

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

### Windows PowerShell

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

`pip install -e .` is recommended for development because edits to the source tree are immediately used by the environment.

For a simple dependency-only install, `requirements.txt` is also provided:

```bash
python -m pip install -r requirements.txt
```

## 3. Prepare a target configuration

Start from `target.example.toml`:

```bash
cp target.example.toml my_target.toml
```

The only required field is the MPC-supported designation:

```toml
[target]
designation = "2023 TP124"
```

Optional `H` and `G` values in the file override values obtained from MPC. This is useful when deliberately reproducing an analysis with fixed physical inputs. Otherwise, omit them and let the pipeline query MPC.

See `CONFIGURATION.md` for the full parameter reference.

## 4. Run coverage-only first

```bash
python -m wise_miner my_target.toml --coverage-only
```

This performs MPC resolution and MOST coverage lookup, writes the coverage products, and stops before downloading/measuring individual L1b frames.

Use this mode to:

- confirm that the designation resolves;
- inspect the number of WISE/NEOWISE frames by band;
- decide whether to narrow the date interval;
- catch very large searches before downloading data.

The coverage table is written to `results/<target>/coverage.csv`.

## 5. Run the full analysis

```bash
python -m wise_miner my_target.toml
```

Equivalent installed command:

```bash
wise-neowise-miner my_target.toml
```

Compatibility command:

```bash
python run.py my_target.toml
```

During the run, the terminal reports progress through MPC lookup, MOST coverage, per-frame photometry, epoch statistics, thermal inference, and report generation.

## 6. Rerunning and cache behavior

Downloads are cached inside the target result directory:

```text
results/<target>/cache/fits/
results/<target>/cache/allwise/
results/<target>/cache/rsr/
```

A rerun with the same target and compatible settings reuses cached products where possible. This reduces repeated network traffic.

Important: result files are overwritten in the same target directory. If you need to preserve multiple configurations for the same target, use a different `[output].root` value or archive the previous result directory before rerunning.

If you change a setting that affects the requested FITS cutout size, the cache filename includes the cutout size, so a separate cutout is downloaded. AllWISE cache filenames encode the query radius, so changing `veto_radius_arcsec` creates a separate cached cone-search response. Analysis-only thresholds such as `min_catalog_snr` are re-applied to the cached table. For strict reproducibility, keep the configuration and result directory together.

## 7. Interpreting the headline result

Start with:

```text
summary.json
report.md
```

The key distinction is:

- **Formal classification**: conservative automated thermal-screening status.
- **Follow-up priority**: independent coherence heuristic indicating whether sub-threshold structure merits additional validation.

A HIGH follow-up priority is not a secure detection.

For frame- and epoch-level details, inspect:

```text
frame_photometry.csv
epoch_summary.csv
band_coherence.csv
allwise_static_source_checks.csv
```

For the meanings of these files and important columns, see `OUTPUTS.md`.

## 8. Limiting large searches

Targets near repeatedly observed sky regions can return many frames. Useful controls are:

```toml
[search]
obs_begin = "2010 01 01 00:00:00"
obs_end = "2020 12 31 23:59:59"
max_frames = 500
```

`max_frames = 0` means no explicit limit. A positive limit is a safety guard: the program raises an error if the usable MOST frame count exceeds it rather than silently truncating the search.

## 9. Reproducibility

The photometric control sampling and epoch bootstrap use deterministic NumPy random generators seeded by:

```toml
[photometry]
random_seed = 20260913
```

Keep this value fixed when comparing runs where all other inputs are intended to remain identical.

For a candidate or high-priority follow-up flag, freeze the original screening configuration before performing confirmatory analyses. Do not tune the screening thresholds on the candidate and then reuse the resulting significance as if it had been predeclared.

## 10. Running tests

```bash
python -m unittest discover -s tests -v
```

The tests are regression tests for core classification/statistical behavior and the H–diameter relation. They do not exercise live MPC/IRSA network services.

## 11. CLI reference

```bash
python -m wise_miner --help
python -m wise_miner --version
```

Current options:

```text
config             TOML configuration path; defaults to target.example.toml
--coverage-only    stop after MPC + MOST coverage lookup
--version          print package version and exit
```

## 12. Common problems

### `designation is required`

The TOML file has no non-empty `[target].designation` field.

### MPC orbit lookup fails or returns no orbit

Confirm that the designation is accepted by MPC. Temporary network/service failures can also occur. Raw API responses are retained where available.

### MOST returns too many frames

Narrow `obs_begin`/`obs_end`, or set a deliberate `max_frames` guard after inspecting coverage.

### A frame is marked `FAILED`

Individual frames can fail because of network errors, malformed products, missing calibration metadata, incomplete apertures, or upstream data issues. The pipeline continues with other frames and records the error in `frame_photometry.csv`.

### No W3 NEATM result is produced

The thermal fit requires usable W3 epoch measurements with finite observing geometry. A run can still produce photometric results, upper limits, and H-only diameter relations without a W3 fit.

### Results change after changing thresholds

That is expected. Detection/follow-up thresholds are analysis choices. Treat exploratory threshold changes separately from confirmatory inference and retain the exact configuration used for any reported result.
