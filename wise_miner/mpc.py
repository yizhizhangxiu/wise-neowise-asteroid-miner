"""Minor Planet Center lookup helpers."""

from __future__ import annotations

import json
from pathlib import Path

import requests

from .util import jsonable, request_get, safe_float

MPC_GET_ORB = "https://data.minorplanetcenter.net/api/get-orb"
MPC_GET_OBS = "https://data.minorplanetcenter.net/api/get-obs"


def query_mpc(
    session: requests.Session,
    designation: str,
    outdir: Path,
) -> dict:
    """Resolve orbit/H/G context and retain MPC API responses on disk.

    Orbit resolution is the critical lookup. Observation retrieval is useful
    provenance but is treated as non-fatal so a temporary observation-API
    problem does not prevent the rest of the archival search.
    """
    resolved = {
        "query_designation": designation,
        "H": None,
        "G": None,
        "packed_designation": None,
        "unpacked_designation": designation,
        "orbit_found": False,
    }

    response = request_get(
        session,
        MPC_GET_ORB,
        json_payload={"desig": designation},
        timeout=120,
    )
    payload = response.json()
    (outdir / "mpc_orbit_raw.json").write_text(
        json.dumps(jsonable(payload), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # MPC response schemas have changed historically; parsing is deliberately
    # defensive, while the unmodified payload above remains available to audit.
    try:
        records = payload[0].get("mpc_orb", [])
        if records:
            orbit = records[0]
            resolved["orbit_found"] = True
            magnitude = orbit.get("magnitude_data", {}) or {}
            h = safe_float(magnitude.get("H", orbit.get("H")))
            g = safe_float(magnitude.get("G", orbit.get("G")))
            resolved["H"] = h if h == h else None
            resolved["G"] = g if g == g else None
            designation_data = orbit.get("designation_data", {}) or {}
            resolved["packed_designation"] = designation_data.get(
                "packed_primary_provisional_designation"
            )
            resolved["unpacked_designation"] = (
                designation_data.get("unpacked_primary_provisional_designation")
                or designation
            )
    except (AttributeError, IndexError, KeyError, TypeError):
        pass

    try:
        response = request_get(
            session,
            MPC_GET_OBS,
            json_payload={
                "desigs": [designation],
                "output_format": ["ADES_DF"],
                "ades_version": "2022",
            },
            timeout=120,
        )
        obs_payload = response.json()
    except Exception as exc:
        obs_payload = {"error": str(exc)}

    (outdir / "mpc_observations.json").write_text(
        json.dumps(jsonable(obs_payload), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return resolved
