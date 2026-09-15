# Configuration reference

Configuration files use TOML. `target.example.toml` contains all supported sections with documented defaults.

Unless explicitly supplied, values shown below are the defaults implemented by the dataclasses in `wise_miner/config.py`.

## `[target]`

### `designation` — required string

MPC-supported asteroid name, permanent number, or provisional designation.

```toml
[target]
designation = "2023 TP124"
```

### `H` — optional float

Absolute magnitude used for H-linked diameter/albedo products and NEATM. When omitted, the pipeline attempts to obtain H from MPC. If no H is available, H-only products are skipped and NEATM can use `assumed_pv_if_H_missing`.

### `G` — optional float

HG phase-slope parameter. When omitted, the pipeline attempts to obtain it from MPC; if unavailable, the runtime falls back to `0.15`.

## `[search]`

### `obs_begin`, `obs_end` — strings, default `""`

Optional MOST observation time bounds using the format accepted by IRSA MOST, for example:

```toml
obs_begin = "2010 01 01 00:00:00"
obs_end = "2020 12 31 23:59:59"
```

Empty values leave the corresponding bound open.

### `bands` — list of integers, default `[3, 4, 2, 1]`

WISE bands requested from MOST. W3/W4 are the thermal screening bands by default. W1/W2 remain useful diagnostic bands.

### `min_qual_frame` — integer, default `5`

Minimum MOST `qual_frame` value accepted when building the usable frame list.

### `epoch_gap_days` — float, default `30.0`

Time gap used to split measurements into epochs independently within each band.

### `max_frames` — integer, default `0`

Safety limit for the total usable MOST frame count. `0` disables the limit. When a positive limit is exceeded, the program raises an error; it does not silently truncate the data.

## `[photometry]`

### `cutout_size_pix` — integer, default `180`

Requested square L1b cutout size in pixels. It must be large enough to contain the target aperture and the background annulus.

### `controls_per_frame` — integer, default `80`

Number of random control apertures attempted per frame. More controls better sample the empirical frame background at the cost of additional computation.

### `control_exclusion_arcsec` — float, default `30.0`

Minimum angular separation between the target position and a random control aperture center.

### `bootstrap_n` — integer, default `10000`

Number of epoch-level empirical-null bootstrap draws.

### `random_seed` — integer, default `20260913`

Seed for control-aperture placement. Epoch bootstrap uses a deterministic offset of this seed.

### `save_control_samples` — boolean, default `false`

When true, writes every accepted control-aperture flux to `frame_control_samples.csv`. This can make result directories substantially larger.

## `[contamination]`

### `enabled` — boolean, default `true`

Enable AllWISE static-source checks for W3/W4 target positions.

### `veto_radius_arcsec` — float, default `12.0`

Cone-search radius and contamination veto radius around the predicted target position.

### `min_catalog_snr` — float, default `2.0`

Minimum AllWISE band S/N that makes a nearby catalog source relevant to the contamination check. Extended-source or contamination/confusion flags can also make a source relevant.

### `exclude_contaminated_thermal_frames` — boolean, default `true`

When true, W3/W4 frames marked as statically contaminated are removed before epoch statistics are computed.

## `[detection]`

These parameters control automated screening. Changing them changes the scientific decision rule; record and freeze the values used for any reported analysis.

### `min_frames_candidate` — integer, default `5`

Minimum usable frames required for an epoch to enter the normal candidate decision path.

### `min_frames_strong` — integer, default `8`

Minimum usable frames required for `STRONG_EPOCH` status.

### `candidate_p`, `strong_p` — floats, defaults `0.05`, `0.01`

Raw one-sided empirical p thresholds. Raw p is used for low-N hints; normal candidate/strong thermal decisions use q-values when BH-FDR is enabled.

### `candidate_snr`, `strong_snr` — floats, defaults `2.0`, `3.0`

Minimum empirical S/N for candidate and strong epoch labels.

### `use_bh_fdr` — boolean, default `true`

Apply Benjamini-Hochberg multiple-testing correction separately within each WISE band.

### `candidate_q`, `strong_q` — floats, defaults `0.05`, `0.01`

BH-adjusted q-value thresholds when `use_bh_fdr = true`.

### `thermal_bands` — list of integers, default `[3, 4]`

Bands allowed to promote the target-level thermal status. W1/W2 are diagnostic by default.

### `repeat_min_epochs` — integer, default `2`

Number of qualifying epochs required in the **same band** for a repeatable target-level candidate classification.

### `min_effective_n_warning` — float, default `3.0`

Diagnostic warning threshold. It does not itself veto a candidate.

### Follow-up/coherence settings

The follow-up layer is intentionally independent from formal detection status.

```toml
followup_enabled = true
followup_bands = [3, 4]
followup_min_epochs = 2
followup_epoch_p_max = 0.25
followup_combined_p_max = 0.10
followup_positive_fraction_min = 0.55
followup_jackknife_positive_fraction_min = 0.80
followup_min_effective_n = 3.0
```

A robust-positive epoch must have positive weighted flux, median frame flux, trimmed-mean frame flux, sufficient positive-frame fraction, sufficient leave-one-out positivity, enough effective frames, and a raw p-value below `followup_epoch_p_max`. The all-predefined-epochs Stouffer p is then compared with `followup_combined_p_max`.

This is a screening heuristic, not discovery significance.

## `[thermal]`

### `enabled` — boolean, default `true`

Enable W3 NEATM fitting when usable W3 epochs exist.

### `eta_grid` — list of floats, default `[0.8, 1.0, 1.2, 1.4]`

Beaming-parameter values evaluated independently.

### `emissivity` — float, default `0.90`

Thermal emissivity used by NEATM.

### `w3_calibration_fraction` — float, default `0.05`

Fractional W3 calibration term added in quadrature during the fit.

### `assumed_pv_if_H_missing` — float, default `0.10`

Visible albedo used by the thermal model only when H is unavailable.

### `max_diameter_km` — float, default `50.0`

Upper diameter bound for the scalar NEATM optimization and one-sided limit search.

## `[output]`

### `root` — string, default `"results"`

Parent directory for per-target results.

### `make_plots` — boolean, default `true`

Generate `epochs_W*.png` summary plots.
