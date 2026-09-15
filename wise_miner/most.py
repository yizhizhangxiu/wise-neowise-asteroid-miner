"""IRSA Moving Object Search Tool (MOST) coverage helpers."""

from __future__ import annotations

import warnings
from io import BytesIO
from pathlib import Path
from typing import Iterable

import numpy as np
import requests
from astropy.io.votable import parse_single_table
from astropy.table import Table

from .util import request_get, safe_float, safe_int, safe_str

IRSA_MOST = "https://irsa.ipac.caltech.edu/cgi-bin/MOST/nph-most"


def find_col(tab: Table, candidates: Iterable[str]) -> str | None:
    """Return the first case-insensitive matching VOTable column name."""
    lookup = {str(c).lower(): c for c in tab.colnames}
    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]
    return None


def query_most(
    session: requests.Session,
    designation: str,
    outdir: Path,
    obs_begin: str = "",
    obs_end: str = "",
) -> Table:
    """Query MOST for orbit-aware WISE coverage and persist the raw VOTable."""
    params = {
        "catalog": "wise_merge",
        "input_type": "name_input",
        "obj_name": designation,
        "output_mode": "VOTable",
    }
    if obs_begin.strip():
        params["obs_begin"] = obs_begin.strip()
    if obs_end.strip():
        params["obs_end"] = obs_end.strip()

    response = request_get(session, IRSA_MOST, params=params, timeout=300)
    (outdir / "most_coverage.xml").write_bytes(response.content)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return parse_single_table(BytesIO(response.content)).to_table(
            use_names_over_ids=True
        )


def parse_frames(
    tab: Table,
    bands: list[int],
    min_qual_frame: int,
    max_frames: int = 0,
) -> list[dict]:
    """Normalize, quality-filter, and deduplicate WISE frame rows from MOST.

    The optional ``max_frames`` value is a guardrail, not a truncation limit:
    exceeding it raises so the user can deliberately narrow the search.
    """
    cols = {
        "ra": find_col(tab, ["ra_obj", "ra"]),
        "dec": find_col(tab, ["dec_obj", "dec"]),
        "mjd": find_col(tab, ["mjd_obs", "mjd"]),
        "band": find_col(tab, ["band"]),
        "scan": find_col(tab, ["scan_id"]),
        "frame": find_col(tab, ["frame_num"]),
        "qual": find_col(tab, ["qual_frame"]),
        "date": find_col(tab, ["date_obs"]),
        "r": find_col(tab, ["sun_dist", "r"]),
        "delta": find_col(tab, ["geo_dist", "delta"]),
        "phase": find_col(tab, ["phase", "phase_angle"]),
        "image_set": find_col(tab, ["image_set"]),
    }
    required = ["ra", "dec", "mjd", "band", "scan", "frame"]
    if any(cols[key] is None for key in required):
        raise RuntimeError(
            "MOST response does not contain the required WISE columns."
        )

    wanted = {int(band) for band in bands}
    rows: list[dict] = []
    seen: set[tuple[str, int, int]] = set()
    for row in tab:
        band = safe_int(row[cols["band"]], -1)
        qual = (
            safe_int(row[cols["qual"]], -1)
            if cols["qual"] is not None
            else 10
        )
        if band not in wanted or qual < min_qual_frame:
            continue

        scan = safe_str(row[cols["scan"]])
        frame_num = safe_int(row[cols["frame"]])
        key = (scan, frame_num, band)
        if not scan or frame_num is None or key in seen:
            continue
        seen.add(key)

        rows.append(
            {
                "ra": safe_float(row[cols["ra"]]),
                "dec": safe_float(row[cols["dec"]]),
                "mjd": safe_float(row[cols["mjd"]]),
                "band": band,
                "scan_id": scan,
                "frame_num": frame_num,
                "qual_frame": qual,
                "date_obs": (
                    safe_str(row[cols["date"]])
                    if cols["date"] is not None
                    else ""
                ),
                "r_au": (
                    safe_float(row[cols["r"]])
                    if cols["r"] is not None
                    else np.nan
                ),
                "delta_au": (
                    safe_float(row[cols["delta"]])
                    if cols["delta"] is not None
                    else np.nan
                ),
                "phase_deg": (
                    safe_float(row[cols["phase"]])
                    if cols["phase"] is not None
                    else np.nan
                ),
                "image_set": (
                    safe_int(row[cols["image_set"]], -1)
                    if cols["image_set"] is not None
                    else -1
                ),
            }
        )

    rows.sort(key=lambda item: (item["mjd"], item["band"]))
    if max_frames and len(rows) > max_frames:
        raise RuntimeError(
            f"MOST returned {len(rows)} usable frames, larger than search.max_frames="
            f"{max_frames}. Narrow the date range or set max_frames=0."
        )
    return rows


def split_epochs(frames: list[dict], gap_days: float) -> list[list[dict]]:
    """Split time-ordered rows whenever adjacent observations exceed ``gap_days``."""
    if not frames:
        return []

    ordered = sorted(frames, key=lambda item: item["mjd"])
    groups = [[ordered[0]]]
    for row in ordered[1:]:
        if row["mjd"] - groups[-1][-1]["mjd"] > gap_days:
            groups.append([row])
        else:
            groups[-1].append(row)
    return groups
