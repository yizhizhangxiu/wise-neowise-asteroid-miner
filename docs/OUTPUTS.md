# Output reference

Each target is written under:

```text
<output.root>/<safe_target_name>/
```

The target name is sanitized for use as a directory name.

## Headline products

### `summary.json`

Compact machine-readable run summary. Important fields include:

- `designation`
- `H_used`, `G_used`
- `coverage_frames`, `measured_frames`, `epoch_count`
- `classification`
- `followup_priority`, `followup_reason`
- selected detection-logic parameters

### `report.md`

Human-readable report containing epoch results, multiple-testing notes, repeatability rules, coherence/follow-up results, W3 NEATM results, robustness diagnostics, and interpretation cautions.

## Upstream-resolution products

### `target_resolved.json`

Resolved MPC context and the H/G values selected for use by the pipeline.

### `mpc_orbit_raw.json`

Raw MPC orbit API payload retained for auditability.

### `mpc_observations.json`

MPC observation API response, or a recorded error if that non-critical lookup failed.

### `most_coverage.xml`

Raw MOST VOTable response.

### `coverage.csv`

Filtered/deduplicated usable frame list. Typical fields include predicted target RA/Dec, MJD, band, scan/frame identifiers, quality, geometry, and image-set metadata when present.

## Frame-level products

### `frame_photometry.csv`

One row per attempted frame. Successful rows include fields such as:

- `target_flux_raw_mjy`
- `target_sigma_formal_mjy`
- `control_n`
- `control_median_mjy`
- `control_mad_sigma_mjy`
- `target_flux_corrected_mjy`
- `sigma_use_mjy`
- `frame_empirical_snr`
- local cached FITS paths
- W3/W4 static-source check fields

Failed frames are retained with `frame_failed = 1` and `frame_error` rather than aborting the entire target.

### `frame_control_samples.csv`

Only written when `save_control_samples = true`. Contains every saved random control-aperture flux.

### `allwise_static_source_checks.csv`

W3/W4 contamination-check summary for each attempted thermal frame. Useful fields include:

- `static_check_done`
- `static_contaminated`
- `static_nearest_sep_arcsec`
- `static_designation`
- `static_catalog_snr`
- `static_ext_flg`
- `static_cc_char`

## Epoch-level products

### `epoch_summary.csv`

The main statistical table. Important fields include:

- `n_frames`: usable frames after any static-source veto.
- `effective_n`: inverse-concentration effective sample size from normalized inverse-variance weights.
- `max_weight_fraction`: largest single-frame normalized weight.
- `positive_fraction`: fraction of usable frame fluxes above zero.
- `median_frame_flux_mjy`: median corrected frame flux.
- `trimmed20_frame_flux_mjy`: 20% trimmed mean when enough frames exist.
- `jackknife_positive_fraction`: fraction of leave-one-out epoch fluxes remaining positive.
- `flux_mjy`: inverse-variance weighted epoch flux.
- `null_sigma_mjy`: robust sigma of the empirical bootstrap null.
- `empirical_p_one_sided`: one-sided empirical p-value.
- `empirical_snr`: epoch flux divided by robust null sigma.
- `flux_ul95_mjy`: empirical one-sided 95% flux upper limit.
- `flux_ul3sigma_mjy`: conventional robust 3-sigma diagnostic upper limit.
- `bh_q_value`: within-band BH-adjusted q-value.
- `classification`: epoch-level screening label.
- `quality_warning`: semicolon-separated diagnostic warnings.

### `band_coherence.csv`

Independent follow-up/coherence layer. It summarizes robust-positive epochs per configured follow-up band and computes an equal-weight one-sided Stouffer p-value using **all predefined epochs** in that band.

This file is a prioritization aid, not formal discovery significance.

## Physical products

### `h_albedo_diameter.csv`

H-only diameter values across a grid of assumed visible albedos, using:

```text
D[km] = 1329 / sqrt(pV) * 10^(-H/5)
```

Empty when H is unavailable.

### `w3_neatm_results.csv`

Conditional W3 NEATM results for each configured beaming parameter `eta`. Typical fields include:

- `D_best_km`
- `pV_best`
- `chi2_min`
- `n_w3_epochs`
- `D95_one_sided_km`
- `pV_at_D95`
- model inputs recorded with the fit

For a non-detection, `D95_one_sided_km` is usually the more relevant size constraint. For a candidate, `D_best_km` remains conditional on the thermal interpretation and should not be treated as a publication-grade diameter without independent validation.

## Plots

### `epochs_W*.png`

Per-band epoch flux plots with empirical null-sigma error bars. They are diagnostic summaries, not substitutes for inspection of native WISE images.

## Cache directory

```text
cache/
├── fits/
├── allwise/
└── rsr/
```

These files allow reruns to reuse downloaded data. They are intentionally stored under `results/`, which is ignored by Git.
