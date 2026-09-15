# Scientific scope and candidate-validation notes

## What the current v1.2.x pipeline does well

- Resolves MPC-supported asteroid designations and retrieves orbit/H/G context.
- Uses MOST for orbit-aware WISE/NEOWISE coverage instead of a fixed sky cone.
- Measures L1b pixels even when no Single Exposure catalog source exists.
- Uses same-frame random apertures to construct an empirical background/null.
- Applies minimum frame counts and within-band BH-FDR correction.
- Keeps W1/W2 diagnostic-only for the overall thermal status.
- Requires same-band repeatability for repeatable thermal candidate labels.
- Separates formal detection status from a follow-up/coherence priority layer.
- Checks W3/W4 target apertures for nearby cataloged AllWISE static sources.
- Produces empirical upper limits when no formal candidate is present.
- Produces H-only diameter relations independently of infrared detection.
- Uses bandpass-integrated W3 NEATM rather than a single monochromatic W3 point.

## What it deliberately does not automate

- Secure-detection claims.
- Publication-grade moving-object validation.
- Full asteroid-rest-frame shift-and-stack analysis.
- Native-frame pseudo-track null experiments.
- PRF subtraction of static sources.
- Pixel-level source injection/recovery.
- W1/W2 thermal diameter inference.
- Gaia re-astrometry or MPC astrometric submission.
- Publication-grade W4 red-source calibration.

## Recommended workflow after a candidate or high-priority follow-up flag

Freeze the screening configuration before performing independent validation. Do not tune the original screening thresholds on the candidate and then reuse the resulting significance as if it were predeclared.

Recommended order:

1. Inspect the relevant L1b images, uncertainty maps, and masks.
2. Apply a predeclared static-source veto/subtraction rule.
3. Build asteroid-rest-frame stacks by independent epochs.
4. Compare matched-filter and aperture measurements.
5. Construct a native-frame pseudo-track null with identical sampling.
6. Check temporal coherence with median, trimmed-mean, split-exposure, and leave-one-out diagnostics.
7. Run pixel-level PRF/source injection and recovery.
8. Only then perform the final physical interpretation and publication-grade thermal fit.

The goal is to keep exploratory screening statistics separate from confirmatory significance.

## Interpretation of the follow-up layer

The v1.2.x coherence layer combines all pre-defined epochs within a band using an equal-weight one-sided Stouffer screening p-value and separately checks robust-positive behavior. It is intentionally independent from the formal target classification.

A result such as:

```text
Formal: NO_SIGNIFICANT_THERMAL_DETECTION
Follow-up: HIGH (W3_REPEATABLE_SUBTHRESHOLD)
```

means that the target failed the strict formal candidate threshold but shows repeated, same-direction W3 structure that merits independent validation. It is not a discovery significance and should not be reported as one.
