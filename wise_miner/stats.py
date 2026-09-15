"""Epoch statistics, multiple-testing correction, and screening classification."""

from __future__ import annotations

from statistics import NormalDist

import numpy as np

from .util import robust_sigma


def summarize_epoch(
    frame_rows: list[dict],
    controls_by_key: dict[tuple, list[float]],
    bootstrap_n: int,
    rng: np.random.Generator,
) -> dict:
    """Combine frame photometry and construct an empirical epoch null.

    The target statistic is an inverse-variance weighted mean. Each null draw
    samples one same-frame control aperture per real frame, recenters that
    frame's controls by their median, and combines the samples with the exact
    target weights. This preserves frame-to-frame background heterogeneity.
    """
    usable = [
        row
        for row in frame_rows
        if np.isfinite(row.get("target_flux_corrected_mjy", np.nan))
        and np.isfinite(row.get("sigma_use_mjy", np.nan))
        and row["sigma_use_mjy"] > 0
    ]
    if not usable:
        return {}

    flux = np.array(
        [row["target_flux_corrected_mjy"] for row in usable], dtype=float
    )
    sigma = np.array([row["sigma_use_mjy"] for row in usable], dtype=float)

    raw_weights = 1.0 / sigma**2
    if not np.isfinite(raw_weights).all() or np.sum(raw_weights) <= 0:
        return {}
    weights = raw_weights / np.sum(raw_weights)
    target = float(np.sum(weights * flux))

    # Effective N exposes epochs dominated by a small number of high-weight
    # frames even when the literal frame count appears adequate.
    effective_n = float(1.0 / np.sum(weights**2))
    positive_fraction = float(np.mean(flux > 0))
    median_flux = float(np.median(flux))

    if len(flux) >= 5:
        k = int(np.floor(0.2 * len(flux)))
        sorted_flux = np.sort(flux)
        core = (
            sorted_flux[k : len(sorted_flux) - k]
            if len(sorted_flux) - 2 * k >= 1
            else sorted_flux
        )
        trimmed20 = float(np.mean(core))
    else:
        trimmed20 = float(np.mean(flux))

    leave_one_out: list[float] = []
    if len(flux) >= 2:
        for index in range(len(flux)):
            keep = np.ones(len(flux), dtype=bool)
            keep[index] = False
            local_weights = raw_weights[keep]
            local_weights /= np.sum(local_weights)
            leave_one_out.append(float(np.sum(local_weights * flux[keep])))

    jackknife_positive_fraction = (
        float(np.mean(np.asarray(leave_one_out) > 0))
        if leave_one_out
        else np.nan
    )
    jackknife_min_flux = (
        float(np.min(leave_one_out)) if leave_one_out else np.nan
    )
    jackknife_max_flux = (
        float(np.max(leave_one_out)) if leave_one_out else np.nan
    )

    null_draws: list[float] = []
    for _ in range(int(bootstrap_n)):
        sampled_controls: list[float] = []
        valid_draw = True
        for row in usable:
            key = (row["scan_id"], int(row["frame_num"]), int(row["band"]))
            controls = controls_by_key.get(key, [])
            if not controls:
                valid_draw = False
                break

            values = np.asarray(controls, dtype=float)
            values = values[np.isfinite(values)]
            if len(values) == 0:
                valid_draw = False
                break

            sampled_controls.append(
                float(rng.choice(values) - np.median(values))
            )

        if valid_draw:
            null_draws.append(
                float(np.sum(weights * np.asarray(sampled_controls)))
            )

    null = np.asarray(null_draws, dtype=float)
    null = null[np.isfinite(null)]
    if len(null) < 100:
        return {}

    # The +1 correction prevents a finite Monte Carlo sample from returning an
    # exact p=0 when no bootstrap draw exceeds the observed target statistic.
    n_exceed = int(np.count_nonzero(null >= target))
    p_value = (n_exceed + 1.0) / (len(null) + 1.0)
    null_sigma = robust_sigma(null)
    empirical_snr = (
        target / null_sigma
        if np.isfinite(null_sigma) and null_sigma > 0
        else np.nan
    )

    # One-sided upper limits are measured relative to the empirical null rather
    # than assuming a Gaussian background distribution.
    q05 = float(np.quantile(null, 0.05))
    flux_ul95 = max(0.0, target - q05)
    flux_ul3sigma = max(0.0, target) + 3.0 * null_sigma

    z_equiv = (
        float(NormalDist().inv_cdf(1 - p_value))
        if 0 < p_value < 1
        else np.nan
    )

    return {
        "n_frames": len(usable),
        "effective_n": effective_n,
        "max_weight_fraction": float(np.max(weights)),
        "positive_fraction": positive_fraction,
        "median_frame_flux_mjy": median_flux,
        "trimmed20_frame_flux_mjy": trimmed20,
        "jackknife_positive_fraction": jackknife_positive_fraction,
        "jackknife_min_flux_mjy": jackknife_min_flux,
        "jackknife_max_flux_mjy": jackknife_max_flux,
        "flux_mjy": target,
        "null_median_mjy": float(np.median(null)),
        "null_sigma_mjy": null_sigma,
        "empirical_p_one_sided": p_value,
        "empirical_z_equiv": z_equiv,
        "empirical_snr": empirical_snr,
        "flux_ul95_mjy": flux_ul95,
        "flux_ul3sigma_mjy": flux_ul3sigma,
        "bh_q_value": np.nan,
        "classification": "UNCLASSIFIED",
    }


def benjamini_hochberg_qvalues(pvalues: list[float]) -> np.ndarray:
    """Return Benjamini-Hochberg FDR-adjusted q-values, preserving NaNs."""
    p = np.asarray(pvalues, dtype=float)
    q = np.full(len(p), np.nan, dtype=float)
    finite_idx = np.flatnonzero(np.isfinite(p))
    if len(finite_idx) == 0:
        return q

    values = p[finite_idx]
    local_order = np.argsort(values)
    ordered = values[local_order]
    m = len(ordered)

    adjusted = ordered * m / np.arange(1, m + 1, dtype=float)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    adjusted = np.clip(adjusted, 0.0, 1.0)

    restored = np.empty(m, dtype=float)
    restored[local_order] = adjusted
    q[finite_idx] = restored
    return q


def classify_epochs(epoch_rows: list[dict], detection_cfg) -> list[dict]:
    """Assign epoch labels after within-band multiple-testing correction."""
    # Each WISE band is treated as its own pre-defined testing family; combining
    # bands here would change the intended decision rule and repeatability logic.
    for band in sorted({int(row["band"]) for row in epoch_rows}):
        indices = [
            i for i, row in enumerate(epoch_rows) if int(row["band"]) == band
        ]
        pvalues = [
            epoch_rows[i].get("empirical_p_one_sided", np.nan) for i in indices
        ]
        qvalues = (
            benjamini_hochberg_qvalues(pvalues)
            if detection_cfg.use_bh_fdr
            else np.asarray(pvalues, dtype=float)
        )
        for i, q_value in zip(indices, qvalues):
            epoch_rows[i]["bh_q_value"] = (
                float(q_value) if np.isfinite(q_value) else np.nan
            )
            epoch_rows[i]["multiple_testing_family_n"] = len(indices)

    thermal_bands = {int(band) for band in detection_cfg.thermal_bands}

    for row in epoch_rows:
        band = int(row["band"])
        n_frames = int(row.get("n_frames", 0))
        p_value = float(row.get("empirical_p_one_sided", np.nan))
        q_value = float(row.get("bh_q_value", np.nan))
        snr = float(row.get("empirical_snr", np.nan))
        flux = float(row.get("flux_mjy", np.nan))
        effective_n = float(row.get("effective_n", np.nan))

        warnings: list[str] = []
        if (
            np.isfinite(effective_n)
            and effective_n < detection_cfg.min_effective_n_warning
        ):
            warnings.append("LOW_EFFECTIVE_N")
        if n_frames < detection_cfg.min_frames_candidate:
            warnings.append("LOW_FRAME_COUNT")
        row["quality_warning"] = ";".join(warnings)

        if n_frames < detection_cfg.min_frames_candidate:
            if (
                np.isfinite(flux)
                and flux > 0
                and np.isfinite(p_value)
                and p_value <= detection_cfg.candidate_p
            ):
                row["classification"] = "LOW_N_HINT"
            else:
                row["classification"] = "NON_DETECTION_EPOCH"
            continue

        # W1/W2 can flag interesting behavior but do not promote thermal status
        # because reflected sunlight can be important at these wavelengths.
        if band not in thermal_bands:
            if (
                np.isfinite(flux)
                and flux > 0
                and np.isfinite(q_value)
                and q_value <= detection_cfg.candidate_q
                and np.isfinite(snr)
                and snr >= detection_cfg.candidate_snr
            ):
                row["classification"] = "DIAGNOSTIC_BAND_HINT"
            else:
                row["classification"] = "NON_DETECTION_EPOCH"
            continue

        strong = (
            n_frames >= detection_cfg.min_frames_strong
            and np.isfinite(flux)
            and flux > 0
            and np.isfinite(q_value)
            and q_value <= detection_cfg.strong_q
            and np.isfinite(snr)
            and snr >= detection_cfg.strong_snr
        )
        candidate = (
            np.isfinite(flux)
            and flux > 0
            and np.isfinite(q_value)
            and q_value <= detection_cfg.candidate_q
            and np.isfinite(snr)
            and snr >= detection_cfg.candidate_snr
        )

        if strong:
            row["classification"] = "STRONG_EPOCH"
        elif candidate:
            row["classification"] = "CANDIDATE_EPOCH"
        else:
            row["classification"] = "NON_DETECTION_EPOCH"

    return epoch_rows


def overall_classification(epoch_rows: list[dict], detection_cfg) -> str:
    """Reduce epoch labels to the conservative target-level thermal status."""
    thermal_bands = {int(band) for band in detection_cfg.thermal_bands}
    by_band: dict[int, list[dict]] = {}
    for row in epoch_rows:
        band = int(row["band"])
        if band in thermal_bands:
            by_band.setdefault(band, []).append(row)

    qualifying = {"STRONG_EPOCH", "CANDIDATE_EPOCH"}

    # Repeatability must be demonstrated independently within one thermal band.
    for band, rows in by_band.items():
        n_good = sum(row.get("classification") in qualifying for row in rows)
        if n_good >= detection_cfg.repeat_min_epochs:
            return f"REPEATABLE_W{band}_CANDIDATE"

    # W3 is the primary automated thermal band in this implementation.
    if any(
        row.get("classification") in qualifying for row in by_band.get(3, [])
    ):
        return "TENTATIVE_W3_CANDIDATE"

    # A lone W4 excess remains explicitly weak pending independent validation.
    if any(
        row.get("classification") in qualifying for row in by_band.get(4, [])
    ):
        return "W4_WEAK_SINGLE_EPOCH_CANDIDATE"

    return "NO_SIGNIFICANT_THERMAL_DETECTION"


def stouffer_combined_p(pvalues: list[float]) -> float:
    """Combine pre-defined one-sided p-values with equal-weight Stouffer Z.

    This is a follow-up screening diagnostic only, not formal discovery
    significance.
    """
    values = np.asarray(pvalues, dtype=float)
    values = values[
        np.isfinite(values) & (values > 0) & (values < 1)
    ]
    if len(values) == 0:
        return np.nan

    normal = NormalDist()
    z_values = np.asarray(
        [normal.inv_cdf(1.0 - float(p)) for p in values], dtype=float
    )
    combined_z = float(np.sum(z_values) / np.sqrt(len(z_values)))
    return float(1.0 - normal.cdf(combined_z))


def band_coherence_summary(epoch_rows: list[dict], detection_cfg) -> list[dict]:
    """Build the independent same-band follow-up/coherence summary.

    Robust-positive epochs must pass several sign/stability checks. The Stouffer
    statistic uses *all* pre-defined epochs in the band, not only favorable
    epochs, to avoid an obvious selection bias in this screening layer.
    """
    if not getattr(detection_cfg, "followup_enabled", True):
        return []

    allowed_bands = {int(band) for band in detection_cfg.followup_bands}
    output: list[dict] = []

    for band in sorted(allowed_bands):
        rows = [row for row in epoch_rows if int(row["band"]) == band]
        if not rows:
            continue

        combined_p = stouffer_combined_p(
            [
                float(row.get("empirical_p_one_sided", np.nan))
                for row in rows
            ]
        )

        robust_positive: list[dict] = []
        for row in rows:
            p_value = float(row.get("empirical_p_one_sided", np.nan))
            flux = float(row.get("flux_mjy", np.nan))
            median_flux = float(row.get("median_frame_flux_mjy", np.nan))
            trimmed_flux = float(row.get("trimmed20_frame_flux_mjy", np.nan))
            positive_fraction = float(row.get("positive_fraction", np.nan))
            jackknife_fraction = float(
                row.get("jackknife_positive_fraction", np.nan)
            )
            effective_n = float(row.get("effective_n", np.nan))

            good = (
                np.isfinite(flux)
                and flux > 0
                and np.isfinite(median_flux)
                and median_flux > 0
                and np.isfinite(trimmed_flux)
                and trimmed_flux > 0
                and np.isfinite(positive_fraction)
                and positive_fraction
                >= detection_cfg.followup_positive_fraction_min
                and np.isfinite(jackknife_fraction)
                and jackknife_fraction
                >= detection_cfg.followup_jackknife_positive_fraction_min
                and np.isfinite(effective_n)
                and effective_n >= detection_cfg.followup_min_effective_n
                and np.isfinite(p_value)
                and p_value <= detection_cfg.followup_epoch_p_max
            )
            if good:
                robust_positive.append(row)

        coherent = (
            len(robust_positive) >= detection_cfg.followup_min_epochs
            and np.isfinite(combined_p)
            and combined_p <= detection_cfg.followup_combined_p_max
        )

        if coherent and band == 3:
            flag = "W3_REPEATABLE_SUBTHRESHOLD"
            priority = "HIGH"
        elif coherent:
            flag = f"W{band}_REPEATABLE_SUBTHRESHOLD"
            priority = "HIGH"
        elif any(
            row.get("classification") in {"STRONG_EPOCH", "CANDIDATE_EPOCH"}
            for row in rows
        ):
            flag = f"W{band}_FORMAL_EPOCH_CANDIDATE"
            priority = "MEDIUM"
        elif robust_positive:
            flag = f"W{band}_ROBUST_POSITIVE_HINT"
            priority = "MEDIUM" if band == 3 else "LOW"
        else:
            flag = "NONE"
            priority = "LOW"

        output.append(
            {
                "band": band,
                "n_epochs": len(rows),
                "n_robust_positive_epochs": len(robust_positive),
                "robust_positive_epoch_ids": ",".join(
                    str(row["epoch_id"]) for row in robust_positive
                ),
                "stouffer_p_all_epochs": combined_p,
                "coherent_subthreshold": int(coherent),
                "followup_flag": flag,
                "followup_priority": priority,
                "note": (
                    "Screening-only coherence metric; not formal detection "
                    "significance."
                ),
            }
        )

    return output


def overall_followup_priority(
    coherence_rows: list[dict],
    formal_status: str,
) -> tuple[str, str]:
    """Select the highest follow-up priority while preserving formal status."""
    rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    best_priority = "LOW"
    best_reason = "No robust repeated thermal-band coherence."

    for row in coherence_rows:
        priority = row.get("followup_priority", "LOW")
        if rank.get(priority, 0) > rank.get(best_priority, 0):
            best_priority = priority
            best_reason = row.get("followup_flag", "")

    if formal_status.startswith("REPEATABLE_"):
        return "HIGH", formal_status

    if formal_status in {
        "TENTATIVE_W3_CANDIDATE",
        "W4_WEAK_SINGLE_EPOCH_CANDIDATE",
    } and rank[best_priority] < rank["MEDIUM"]:
        return "MEDIUM", formal_status

    return best_priority, best_reason
