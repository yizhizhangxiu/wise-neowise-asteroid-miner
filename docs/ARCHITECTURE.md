# Architecture overview

The project is intentionally a small, linear scientific pipeline. `wise_miner/pipeline.py` is the orchestration layer; scientific/network responsibilities are kept in separate modules so the statistical rules can be tested without live services.

## Runtime flow

```text
TOML config
   |
   v
config.load_config
   |
   v
mpc.query_mpc ------------------> target_resolved.json / MPC raw responses
   |
   v
most.query_most -> most.parse_frames -> coverage.csv
   |
   v
wise.measure_frame -------------> frame_photometry.csv
   |                                  |
   |                                  +-> random same-frame controls
   |                                  +-> AllWISE static-source checks
   v
most.split_epochs
   |
   v
stats.summarize_epoch ----------> epoch empirical null / upper limits
   |
   v
stats.classify_epochs ----------> within-band BH-FDR + epoch labels
   |
   +-> stats.overall_classification
   +-> stats.band_coherence_summary
   |
   v
thermal.fit_w3_neatm -----------> conditional W3 physical constraints
   |
   v
report.build_report / plot_epochs
   |
   v
summary.json + report.md + tables + plots
```

## Module responsibilities

### `wise_miner/config.py`

Defines TOML-backed dataclasses and their defaults. Scientific thresholds should be added here rather than hidden inside pipeline code.

### `wise_miner/mpc.py`

Resolves target metadata and H/G context from the Minor Planet Center. Raw upstream responses are retained to make parsing decisions auditable.

### `wise_miner/most.py`

Queries IRSA MOST and normalizes the returned WISE frame table. It also defines the simple time-gap epoch grouping used later in the pipeline.

### `wise_miner/wise.py`

Owns L1b product access, WCS conversion, forced aperture photometry, same-frame random controls, and AllWISE static-source contamination checks.

### `wise_miner/stats.py`

Contains the main screening decision logic. It deliberately has no network dependencies. This is where epoch bootstrap/null statistics, BH-FDR, formal labels, and follow-up/coherence rules live.

### `wise_miner/thermal.py`

Contains H/albedo diameter conversion and the W3 bandpass-integrated NEATM calculation. It does not decide whether a signal is a secure detection.

### `wise_miner/report.py`

Formats already-computed results into Markdown and diagnostic plots. Scientific decisions should not be introduced in this presentation layer.

### `wise_miner/pipeline.py`

Connects the modules, persists intermediate products, and prints progress. Whenever possible, new scientific calculations should remain in their domain module rather than expanding this file.

## Design rules for future changes

1. Keep **screening** and **confirmation** conceptually separate.
2. Do not turn follow-up heuristics into formal detection status implicitly.
3. Preserve raw/cached upstream products needed to audit a result.
4. Prefer testable pure functions for statistical decision rules.
5. Document units in field names (`_mjy`, `_arcsec`, `_km`, `_au`, `_deg`) when adding new outputs.
6. Comments should explain assumptions, provenance, or non-obvious choices rather than restating code.
7. Add a regression test when changing a classification threshold or decision path.
