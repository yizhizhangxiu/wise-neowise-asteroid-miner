"""Top-level orchestration for the archival screening workflow."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import requests

from . import __package_name__, __project_name__, __version__
from .config import Config
from .mpc import query_mpc
from .most import query_most, parse_frames, split_epochs
from .report import build_report, plot_epochs
from .stats import (summarize_epoch, classify_epochs, overall_classification, band_coherence_summary, overall_followup_priority)
from .thermal import h_diameter_table, fit_w3_neatm
from .util import jsonable, slugify, write_csv
from .wise import measure_frame, query_allwise_contamination


USER_AGENT = (
    f"{__package_name__}/{__version__} "
    "(archival moving-object forced photometry)"
)


def _median_finite(rows, key):
    """Return the median finite value for ``key`` across row dictionaries."""
    a = np.array([r.get(key, np.nan) for r in rows], dtype=float)
    a = a[np.isfinite(a)]
    return float(np.median(a)) if len(a) else np.nan


def run_pipeline(cfg: Config, coverage_only: bool = False) -> Path:
    """Run the configured target workflow and return its result directory."""
    outdir = Path(cfg.output.root) / slugify(cfg.target.designation)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "cache" / "fits").mkdir(parents=True, exist_ok=True)
    (outdir / "cache" / "allwise").mkdir(parents=True, exist_ok=True)
    (outdir / "cache" / "rsr").mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    print("=" * 78)
    print(f"{__project_name__} v{__version__}")
    print(f"Target: {cfg.target.designation}")
    print(f"Output: {outdir}")
    print("=" * 78)

    print("\n[1/6] MPC target/orbit lookup...")
    resolved = query_mpc(session, cfg.target.designation, outdir)
    H = cfg.target.H if cfg.target.H is not None else resolved.get("H")
    G = cfg.target.G if cfg.target.G is not None else resolved.get("G")
    G = 0.15 if G is None else float(G)
    resolved["H_used"] = H
    resolved["G_used"] = G
    (outdir / "target_resolved.json").write_text(
        json.dumps(jsonable(resolved), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"    MPC orbit found: {resolved['orbit_found']}")
    print(f"    H={H}, G={G}")

    print("\n[2/6] IRSA MOST wise_merge coverage...")
    tab = query_most(
        session,
        cfg.target.designation,
        outdir,
        cfg.search.obs_begin,
        cfg.search.obs_end,
    )
    frames = parse_frames(
        tab,
        cfg.search.bands,
        cfg.search.min_qual_frame,
        cfg.search.max_frames,
    )
    write_csv(frames, outdir / "coverage.csv")
    counts = {}
    for f in frames:
        counts[f["band"]] = counts.get(f["band"], 0) + 1
    print(f"    usable coverage rows: {len(frames)}; by band={counts}")

    if H is not None:
        write_csv(h_diameter_table(float(H)), outdir / "h_albedo_diameter.csv")
    else:
        (outdir / "h_albedo_diameter.csv").write_text("", encoding="utf-8")

    if coverage_only:
        print("\nCoverage-only mode complete.")
        return outdir

    print("\n[3/6] L1b forced photometry + same-frame controls...")
    rng = np.random.default_rng(cfg.photometry.random_seed)
    frame_rows = []
    controls_by_key = {}
    control_rows = []

    for i, frame in enumerate(frames, 1):
        key = (frame["scan_id"], int(frame["frame_num"]), int(frame["band"]))
        print(
            f"  [{i:04d}/{len(frames):04d}] W{frame['band']} "
            f"MJD={frame['mjd']:.6f} {frame['scan_id']}/{frame['frame_num']:03d}",
            flush=True,
        )
        try:
            row, controls = measure_frame(
                session,
                frame,
                size_pix=cfg.photometry.cutout_size_pix,
                n_controls=cfg.photometry.controls_per_frame,
                exclusion_arcsec=cfg.photometry.control_exclusion_arcsec,
                rng=rng,
                cache_dir=outdir / "cache" / "fits",
            )
            controls_by_key[key] = controls

            if cfg.contamination.enabled and int(frame["band"]) in (3, 4):
                check = query_allwise_contamination(
                    session,
                    frame,
                    radius_arcsec=cfg.contamination.veto_radius_arcsec,
                    min_catalog_snr=cfg.contamination.min_catalog_snr,
                    cache_dir=outdir / "cache" / "allwise",
                )
                row.update(check)
            else:
                row.update(
                    {
                        "static_check_done": 0,
                        "static_contaminated": 0,
                        "static_nearest_sep_arcsec": np.nan,
                    }
                )

            frame_rows.append(row)
            if cfg.photometry.save_control_samples:
                for j, x in enumerate(controls):
                    control_rows.append(
                        {
                            "scan_id": frame["scan_id"],
                            "frame_num": frame["frame_num"],
                            "band": frame["band"],
                            "control_index": j,
                            "flux_mjy": x,
                        }
                    )
            print(
                f"      flux={row['target_flux_corrected_mjy']:+.4g} mJy, "
                f"sigma={row['sigma_use_mjy']:.4g}, "
                f"S/N={row['frame_empirical_snr']:.2f}, "
                f"static={row.get('static_contaminated',0)}"
            )
        except Exception as exc:
            fail = dict(frame)
            fail.update({"frame_failed": 1, "frame_error": str(exc)})
            frame_rows.append(fail)
            print(f"      FAILED: {exc}")

    write_csv(frame_rows, outdir / "frame_photometry.csv")
    if cfg.photometry.save_control_samples:
        write_csv(control_rows, outdir / "frame_control_samples.csv")

    static_rows = [
        {
            k: r.get(k)
            for k in (
                "mjd", "band", "scan_id", "frame_num",
                "static_check_done", "static_contaminated",
                "static_nearest_sep_arcsec", "static_designation",
                "static_catalog_snr", "static_ext_flg", "static_cc_char",
            )
        }
        for r in frame_rows
        if int(r.get("band", -1)) in (3, 4)
    ]
    write_csv(static_rows, outdir / "allwise_static_source_checks.csv")

    print("\n[4/6] Epoch empirical nulls and upper limits...")
    epoch_rows = []
    epoch_rng = np.random.default_rng(cfg.photometry.random_seed + 1)

    for band in sorted(set(int(f["band"]) for f in frames)):
        measured = [
            r for r in frame_rows
            if int(r.get("band", -1)) == band
            and "target_flux_corrected_mjy" in r
        ]
        groups = split_epochs(measured, cfg.search.epoch_gap_days)
        for j, group in enumerate(groups, 1):
            clean = list(group)
            if (
                band in (3, 4)
                and cfg.contamination.exclude_contaminated_thermal_frames
            ):
                clean = [
                    r for r in clean
                    if not int(r.get("static_contaminated", 0))
                ]
            if not clean:
                continue

            s = summarize_epoch(
                clean,
                controls_by_key,
                cfg.photometry.bootstrap_n,
                epoch_rng,
            )
            if not s:
                continue
            eid = f"W{band}_E{j}"
            s.update(
                {
                    "band": band,
                    "epoch_number": j,
                    "epoch_id": eid,
                    "mjd_start": min(r["mjd"] for r in clean),
                    "mjd_end": max(r["mjd"] for r in clean),
                    "r_au": _median_finite(clean, "r_au"),
                    "delta_au": _median_finite(clean, "delta_au"),
                    "phase_deg": _median_finite(clean, "phase_deg"),
                    "n_frames_before_static_veto": len(group),
                    "n_frames_after_static_veto": len(clean),
                }
            )
            epoch_rows.append(s)
            print(
                f"    {eid}: N={s['n_frames']}, effN={s['effective_n']:.2f}, "
                f"flux={s['flux_mjy']:+.4g}, "
                f"raw-p={s['empirical_p_one_sided']:.4g}, "
                f"UL95={s['flux_ul95_mjy']:.4g} mJy"
            )

    # Classification waits until every epoch is known so BH-FDR uses the full
    # pre-defined testing family within each band.
    epoch_rows = classify_epochs(epoch_rows, cfg.detection)
    write_csv(epoch_rows, outdir / "epoch_summary.csv")
    overall = overall_classification(epoch_rows, cfg.detection)

    print("\n    Final epoch labels after within-band BH-FDR:")
    for s in epoch_rows:
        q = s.get("bh_q_value", np.nan)
        print(
            f"      {s['epoch_id']}: N={s['n_frames']}, "
            f"p={s['empirical_p_one_sided']:.4g}, q={q:.4g}, "
            f"effN={s['effective_n']:.2f}, {s['classification']}"
            + (
                f" [{s['quality_warning']}]"
                if s.get("quality_warning") else ""
            )
        )
    print(f"    overall thermal classification: {overall}")

    coherence_rows = band_coherence_summary(epoch_rows, cfg.detection)
    write_csv(coherence_rows, outdir / "band_coherence.csv")
    followup_priority, followup_reason = overall_followup_priority(
        coherence_rows, overall
    )

    print("\n    Independent follow-up/coherence layer:")
    for c in coherence_rows:
        print(
            f"      W{c['band']}: robust+={c['n_robust_positive_epochs']}/"
            f"{c['n_epochs']}, Stouffer-p(all epochs)="
            f"{c['stouffer_p_all_epochs']:.4g}, "
            f"{c['followup_flag']} -> {c['followup_priority']}"
        )
    print(
        f"    follow-up priority: {followup_priority} "
        f"({followup_reason})"
    )

    print("\n[5/6] W3 NEATM physical inference...")
    neatm_rows = []
    if cfg.thermal.enabled:
        try:
            neatm_rows = fit_w3_neatm(
                session,
                epoch_rows,
                H=float(H) if H is not None else None,
                G=G,
                eta_grid=cfg.thermal.eta_grid,
                emissivity=cfg.thermal.emissivity,
                cal_fraction=cfg.thermal.w3_calibration_fraction,
                assumed_pv=cfg.thermal.assumed_pv_if_H_missing,
                max_diameter_km=cfg.thermal.max_diameter_km,
                cache_dir=outdir / "cache" / "rsr",
            )
        except Exception as exc:
            print(f"    NEATM failed: {exc}")
    write_csv(neatm_rows, outdir / "w3_neatm_results.csv")
    for r in neatm_rows:
        print(
            f"    eta={r['eta']:.1f}: Dbest={r['D_best_km']:.3g} km, "
            f"D95={r['D95_one_sided_km']:.3g} km"
        )

    print("\n[6/6] Report...")
    build_report(
        outdir,
        resolved,
        [r for r in frame_rows if "target_flux_corrected_mjy" in r],
        epoch_rows,
        overall,
        neatm_rows,
        float(H) if H is not None else None,
        G,
        coherence_rows,
        followup_priority,
        followup_reason,
    )
    if cfg.output.make_plots:
        plot_epochs(outdir, epoch_rows)

    summary = {
        "designation": cfg.target.designation,
        "H_used": H,
        "G_used": G,
        "coverage_frames": len(frames),
        "measured_frames": sum("target_flux_corrected_mjy" in r for r in frame_rows),
        "epoch_count": len(epoch_rows),
        "classification": overall,
        "followup_priority": followup_priority,
        "followup_reason": followup_reason,
        "detection_logic": {
            "min_frames_candidate": cfg.detection.min_frames_candidate,
            "min_frames_strong": cfg.detection.min_frames_strong,
            "use_bh_fdr": cfg.detection.use_bh_fdr,
            "thermal_bands": cfg.detection.thermal_bands,
            "repeat_min_epochs_same_band": cfg.detection.repeat_min_epochs,
            "followup_enabled": cfg.detection.followup_enabled,
            "followup_combined_p_max": cfg.detection.followup_combined_p_max,
        },
    }
    (outdir / "summary.json").write_text(
        json.dumps(jsonable(summary), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n" + "=" * 78)
    print(f"Formal classification: {overall}")
    print(f"Follow-up priority: {followup_priority} ({followup_reason})")
    print(f"Report: {outdir / 'report.md'}")
    print("=" * 78)
    return outdir
