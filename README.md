# WISE/NEOWISE Asteroid Miner

A conservative Python pipeline for **orbit-aware archival WISE/NEOWISE screening of MPC asteroids**.

给定 MPC 支持的小行星名称、永久编号或临时编号，本项目会回溯 WISE/NEOWISE 历史覆盖，在轨道预测位置执行 forced aperture photometry，使用同帧随机控制孔径建立经验背景/null，并在 W3 数据可用时给出条件性的 NEATM 尺寸约束。

> **Scientific scope:** this is a screening and diagnostic pipeline, not an automatic secure-detection system. Candidate labels require independent moving-object validation before publication-grade interpretation.

## Highlights

- Orbit-aware WISE/NEOWISE coverage search through IRSA MOST.
- Forced photometry on WISE Merge Level-1b pixels, including catalog non-detections.
- Same-frame random control apertures for empirical noise/null estimation.
- Epoch bootstrap statistics and within-band Benjamini-Hochberg FDR correction.
- W3/W4 static-source contamination checks against AllWISE.
- Separate **formal thermal status** and **follow-up priority**.
- Empirical flux upper limits for non-detections.
- Bandpass-integrated W3 NEATM diameter constraints when geometry is available.
- Reproducible per-target result directories with cached upstream products.

## Quick start

### 1. Create an environment and install

Python 3.11+ is required.

**Linux / macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

**Windows PowerShell**

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

The virtual environment is intentionally ignored by Git and should not be committed.

### 2. Copy the example configuration

```bash
cp target.example.toml my_target.toml
```

On Windows, copy the file in Explorer or PowerShell and edit `my_target.toml`.

At minimum, set:

```toml
[target]
designation = "2023 TP124"
```

`H` and `G` are optional. If omitted, the pipeline attempts to obtain them from MPC.

### 3. Check coverage first

A coverage-only run is a useful first check because it does not download and measure all L1b FITS frames:

```bash
python -m wise_miner my_target.toml --coverage-only
```

### 4. Run the full pipeline

```bash
python -m wise_miner my_target.toml
```

After editable installation, the equivalent console command is:

```bash
wise-neowise-miner my_target.toml
```

Legacy compatibility entry point:

```bash
python run.py my_target.toml
```

### 5. Read the result

The first files to inspect are:

```text
results/<target>/summary.json
results/<target>/report.md
results/<target>/epoch_summary.csv
results/<target>/band_coherence.csv
```

`summary.json` provides the machine-readable headline result; `report.md` is the human-readable summary. A formal non-detection can still have a HIGH follow-up priority if repeated sub-threshold structure is present.

## Documentation

- [Usage guide](docs/USAGE.md) — installation, first run, reruns, testing, and troubleshooting.
- [Configuration reference](docs/CONFIGURATION.md) — every TOML section and parameter.
- [Output reference](docs/OUTPUTS.md) — generated files and important table columns.
- [Scientific scope](docs/SCIENTIFIC_SCOPE.md) — what the pipeline does and does not establish scientifically.
- [Architecture overview](docs/ARCHITECTURE.md) — module boundaries and data flow.
- [Contributing](CONTRIBUTING.md) — development checks and guidance for scientific changes.
- [Changelog](CHANGELOG.md) — release history.

## Current formal status labels

The current v1.2.x target-level thermal labels are:

```text
NO_SIGNIFICANT_THERMAL_DETECTION
W4_WEAK_SINGLE_EPOCH_CANDIDATE
TENTATIVE_W3_CANDIDATE
REPEATABLE_W3_CANDIDATE
REPEATABLE_W4_CANDIDATE
```

W1/W2 may produce `DIAGNOSTIC_BAND_HINT`, but they do **not** promote the overall thermal classification. Low-frame-count excursions may be labeled `LOW_N_HINT` at epoch level.

A separate coherence layer may assign follow-up flags such as:

```text
W3_REPEATABLE_SUBTHRESHOLD
```

For example:

```text
Formal: NO_SIGNIFICANT_THERMAL_DETECTION
Follow-up: HIGH (W3_REPEATABLE_SUBTHRESHOLD)
```

This means repeated same-band structure is worth independent validation; it is **not** a detection claim.

## How the pipeline works

1. Query MPC orbit information, H/G, and observations.
2. Query IRSA MOST for orbit-aware WISE/NEOWISE coverage.
3. Download WISE Merge Level-1b intensity and uncertainty cutouts.
4. Run forced aperture photometry at the MOST-predicted position.
5. Sample random control apertures on each frame to estimate an empirical background/null.
6. Group measurements by WISE band and epoch, then bootstrap epoch statistics.
7. Apply within-band Benjamini-Hochberg FDR correction.
8. Check W3/W4 target apertures against nearby AllWISE static sources.
9. Separate formal thermal status from follow-up/coherence priority.
10. Produce empirical upper limits and, when possible, W3 NEATM diameter constraints.
11. Produce an H–albedo–diameter table whenever H is available.

## Default detection logic

The automated screening is intentionally conservative. Important defaults include:

```text
min_frames_candidate = 5
min_frames_strong    = 8
candidate_q          = 0.05
strong_q             = 0.01
candidate_snr        = 2.0
strong_snr           = 3.0
repeat_min_epochs    = 2
thermal_bands        = [3, 4]
```

Candidate significance uses within-band BH-adjusted q-values by default. Repeatability must occur in the **same thermal band**. Cross-band hints are not combined into a repeatable target-level classification.

The pipeline deliberately never emits `SECURE_DETECTION`.

## Data services

Live runs use public services from:

- Minor Planet Center (orbit and observations APIs)
- NASA/IPAC IRSA MOST (`wise_merge`)
- NASA/IPAC IRSA WISE Merge L1b (`merge_p1bm_frm`)
- NASA/IPAC IRSA AllWISE Source Catalog
- official W3 relative spectral response data

Internet access is therefore required for uncached live runs. Upstream APIs and schemas can change; raw responses and downloaded products are retained in each target result directory to make runs easier to audit.

## Development and tests

Run the regression tests with:

```bash
python -m unittest discover -s tests -v
```

GitHub Actions runs the same test suite on supported Python versions for every push and pull request.

## License

This project is released under the [MIT License](LICENSE). You may use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the software subject to the license terms.

Copyright (c) 2026 yizhizhangxiu.
