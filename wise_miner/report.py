"""Markdown report and diagnostic plot generation."""

from __future__ import annotations

from pathlib import Path
import numpy as np


def build_report(
    outdir: Path,
    resolved: dict,
    frame_rows: list[dict],
    epoch_rows: list[dict],
    overall: str,
    neatm_rows: list[dict],
    H: float | None,
    G: float,
    coherence_rows: list[dict],
    followup_priority: str,
    followup_reason: str,
) -> None:
    """Write the human-readable Markdown summary for one completed run."""
    bands = sorted(set(int(r["band"]) for r in frame_rows))
    lines = [
        "# WISE/NEOWISE archival screening report",
        "",
        f"- Target: `{resolved.get('unpacked_designation') or resolved.get('query_designation')}`",
        f"- Query designation: `{resolved.get('query_designation')}`",
        f"- MPC orbit found: `{resolved.get('orbit_found')}`",
        f"- H used: `{H}`",
        f"- G used: `{G}`",
        f"- Usable L1b frames measured: `{len(frame_rows)}`",
        f"- Bands present: `{bands}`",
        f"- Formal thermal classification: **{overall}**",
        f"- Follow-up priority: **{followup_priority}** (`{followup_reason}`)",
        "",
        "> Formal status and follow-up priority are intentionally separate.",
        "> A HIGH follow-up priority is not a detection claim.",
        "> W1/W2 diagnostic positives do not promote the overall thermal label.",
        "",
        "## Epoch results",
        "",
        "| band | epoch | N | effN | +frac | flux mJy | null sigma | raw p | BH q | 95% UL | class | warnings |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]

    for r in epoch_rows:
        q = r.get("bh_q_value", np.nan)
        lines.append(
            f"| W{r['band']} | {r['epoch_id']} | {r['n_frames']} | "
            f"{r.get('effective_n', np.nan):.3g} | "
            f"{r.get('positive_fraction', np.nan):.3g} | "
            f"{r['flux_mjy']:.5g} | {r['null_sigma_mjy']:.5g} | "
            f"{r['empirical_p_one_sided']:.5g} | {q:.5g} | "
            f"{r['flux_ul95_mjy']:.5g} | {r['classification']} | "
            f"{r.get('quality_warning','')} |"
        )

    lines += [
        "",
        "### Multiple testing",
        "",
        "Empirical p-values are Benjamini-Hochberg FDR adjusted separately "
        "within each WISE band. Candidate labels use the adjusted q-value by default.",
        "",
        "### Repeatability",
        "",
        "Only W3/W4 participate in the automated thermal label. Repeatability "
        "must occur within the same band; cross-band hints are not combined.",
        "",
        "## Band coherence / follow-up layer",
        "",
        "| band | epochs | robust-positive | Stouffer p (all epochs) | flag | priority |",
        "|---:|---:|---:|---:|---|---|",
    ]

    for c in coherence_rows:
        lines.append(
            f"| W{c['band']} | {c['n_epochs']} | "
            f"{c['n_robust_positive_epochs']} | "
            f"{c['stouffer_p_all_epochs']:.5g} | "
            f"{c['followup_flag']} | {c['followup_priority']} |"
        )

    lines += [
        "",
        "The coherence layer is a screening heuristic only. It combines all "
        "pre-defined epochs in a band with equal-weight one-sided Stouffer p, "
        "and separately counts robust-positive epochs using median/trimmed mean, "
        "positive fraction, effective N and leave-one-out checks. It does not "
        "alter the formal detection status.",
        "",
        "## W3 NEATM",
        "",
    ]

    if neatm_rows:
        lines += [
            "| eta | Dbest km | pVbest | D95 km | pV(D95) | chi2 |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
        for r in neatm_rows:
            lines.append(
                f"| {r['eta']:.2f} | {r['D_best_km']:.4g} | "
                f"{r['pV_best']:.4g} | {r['D95_one_sided_km']:.4g} | "
                f"{r['pV_at_D95']:.4g} | {r['chi2_min']:.4g} |"
            )
        lines += [
            "",
            "`D_best` is conditional on the W3 thermal interpretation. "
            "If W3 is not a thermal candidate, use `D95_one_sided_km` as "
            "the primary result and treat Dbest only as the likelihood minimum.",
        ]
    else:
        lines.append(
            "No W3 thermal solution was produced (no usable W3 epoch, "
            "missing geometry, or thermal modeling disabled)."
        )

    lines += [
        "",
        "## Interpretation rules",
        "",
        "- `NO_SIGNIFICANT_THERMAL_DETECTION`: use upper limits.",
        "- `W4_WEAK_SINGLE_EPOCH_CANDIDATE`: inspect W4 background/frames; do not call it a detection.",
        "- `TENTATIVE_W3_CANDIDATE`: perform independent moving-object validation.",
        "- `REPEATABLE_W3_CANDIDATE` / `REPEATABLE_W4_CANDIDATE`: same-band repeatability; still not automatically secure.",
        "- `LOW_N_HINT`: too few real frames to trigger an automated candidate.",
        "- `DIAGNOSTIC_BAND_HINT`: W1/W2-only positive, excluded from thermal classification.",
        "",
        "## Robustness diagnostics",
        "",
        "- `effN = 1/sum(w^2)`: effective number of weighted frames.",
        "- `+frac`: fraction of individual frame fluxes above zero.",
        "- `max_weight_fraction`: largest single-frame contribution to the weighted mean.",
        "- `median_frame_flux_mjy`, `trimmed20_frame_flux_mjy`, and `jackknife_*` are available in `epoch_summary.csv`.",
        "",
        "## Files",
        "",
        "- `coverage.csv`: MOST WISE/NEOWISE coverage",
        "- `frame_photometry.csv`: frame-level forced photometry",
        "- `epoch_summary.csv`: empirical epoch statistics, BH q-values and upper limits",
        "- `band_coherence.csv`: independent same-band follow-up/coherence diagnostics",
        "- `allwise_static_source_checks.csv`: W3/W4 static-source flags",
        "- `h_albedo_diameter.csv`: H-only diameter table",
        "- `w3_neatm_results.csv`: conditional W3 NEATM solutions",
        "",
    ]
    (outdir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def plot_epochs(outdir: Path, epoch_rows: list[dict]) -> None:
    """Write one simple epoch-flux diagnostic plot per WISE band."""
    if not epoch_rows:
        return
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return

    for band in sorted(set(int(r["band"]) for r in epoch_rows)):
        rows = [r for r in epoch_rows if int(r["band"]) == band]
        x = np.arange(len(rows))
        y = np.array([r["flux_mjy"] for r in rows])
        e = np.array([r["null_sigma_mjy"] for r in rows])

        fig, ax = plt.subplots(figsize=(7, 4))
        ax.errorbar(x, y, yerr=e, fmt="o")
        ax.axhline(0, linewidth=1)
        ax.set_xticks(x)
        ax.set_xticklabels(
            [str(r["epoch_id"]) for r in rows],
            rotation=45,
            ha="right",
        )
        ax.set_xlabel("Epoch")
        ax.set_ylabel("Forced flux (mJy)")
        ax.set_title(f"WISE W{band} epoch forced photometry")
        fig.tight_layout()
        fig.savefig(outdir / f"epochs_W{band}.png", dpi=150)
        plt.close(fig)
