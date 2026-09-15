"""H/albedo diameter relations and bandpass-integrated W3 NEATM fitting."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import requests
from scipy.optimize import brentq, minimize_scalar

from .util import request_get

W3_RSR_URL = (
    "https://irsa.ipac.caltech.edu/data/WISE/docs/release/"
    "All-Sky/expsup/figures/RSR-W3.txt"
)
# W3 color-correction factor used by the adopted power-law flux-density basis.
W3_FC_CONST = 0.9169


def h_diameter_table(H: float, pvs=None) -> list[dict]:
    """Return diameters implied by H for a grid of visible geometric albedos."""
    if pvs is None:
        pvs = [0.02, 0.04, 0.05, 0.07, 0.10, 0.15, 0.20, 0.25, 0.40]
    scale = 1329.0 * 10.0 ** (-H / 5.0)
    return [
        {"H": H, "pV": float(pv), "diameter_km": scale / math.sqrt(float(pv))}
        for pv in pvs
    ]


def load_w3_rsr(
    session: requests.Session,
    cache_dir: Path,
) -> tuple[np.ndarray, np.ndarray]:
    """Load and cache the official W3 relative spectral response table."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "RSR-W3.txt"
    if path.exists():
        content = path.read_text(encoding="utf-8", errors="replace")
    else:
        response = request_get(session, W3_RSR_URL, timeout=180)
        content = response.text
        path.write_text(content, encoding="utf-8")

    rows: list[tuple[float, float]] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("\\"):
            continue

        values: list[float] = []
        for token in stripped.replace(",", " ").split():
            try:
                values.append(float(token))
            except ValueError:
                continue
        if len(values) >= 2:
            rows.append((values[0], values[1]))

    array = np.asarray(rows, dtype=float)
    if len(array) < 10:
        raise RuntimeError("Could not parse W3 RSR")

    good = (
        np.isfinite(array[:, 0])
        & np.isfinite(array[:, 1])
        & (array[:, 0] > 0)
        & (array[:, 1] >= 0)
    )
    array = array[good]
    array = array[np.argsort(array[:, 0])]
    return array[:, 0], array[:, 1]


def _planck_nu(lam_m: np.ndarray, temperature_k: np.ndarray) -> np.ndarray:
    """Evaluate Planck spectral radiance B_nu for many temperatures/wavelengths."""
    h = 6.62607015e-34
    c = 299792458.0
    k = 1.380649e-23

    wavelength = lam_m[None, :]
    frequency = c / wavelength
    temperature = temperature_k[:, None]

    # A large finite exponent avoids overflow for the unilluminated T=0 cells.
    exponent = np.full((len(temperature_k), len(lam_m)), 700.0)
    positive_temperature = temperature[:, 0] > 1e-8
    if np.any(positive_temperature):
        exponent[positive_temperature, :] = (
            h * frequency / (k * temperature[positive_temperature, :])
        )
    exponent = np.clip(exponent, 1e-12, 700)

    radiance = (2 * h * frequency**3 / c**2) / np.expm1(exponent)
    radiance[~positive_temperature, :] = 0
    return radiance


def neatm_spectrum_mjy(
    lam_um: np.ndarray,
    D_km: float,
    r_au: float,
    delta_au: float,
    phase_deg: float,
    eta: float,
    *,
    H: float | None,
    G: float,
    emissivity: float,
    assumed_pv: float,
    ntheta: int = 28,
    nphi: int = 56,
) -> tuple[np.ndarray, float]:
    """Numerically integrate a simple NEATM thermal spectrum over the visible disk."""
    if H is not None:
        h_scale = 1329.0 * 10 ** (-H / 5)
        pv = float(np.clip((h_scale / D_km) ** 2, 1e-5, 1.0))
    else:
        pv = float(assumed_pv)

    sigma_sb = 5.670374419e-8
    solar_constant = 1361.0
    au_m = 149597870700.0
    phase_integral = 0.290 + 0.684 * G
    bond_albedo = float(np.clip(phase_integral * pv, 0.0, 0.8))
    subsolar_temperature = (
        (1 - bond_albedo)
        * solar_constant
        / (eta * emissivity * sigma_sb * r_au**2)
    ) ** 0.25

    alpha = np.deg2rad(phase_deg)
    dtheta = 0.5 * np.pi / ntheta
    dphi = 2 * np.pi / nphi
    theta = (np.arange(ntheta) + 0.5) * dtheta
    phi = (np.arange(nphi) + 0.5) * dphi

    sin_theta = np.sin(theta)[:, None]
    cos_theta = np.cos(theta)[:, None]
    cos_phi = np.cos(phi)[None, :]
    mu_observer = np.broadcast_to(cos_theta, (ntheta, nphi))
    mu_sun = np.clip(
        sin_theta * cos_phi * np.sin(alpha) + cos_theta * np.cos(alpha),
        0,
        None,
    )

    temperature = np.zeros_like(mu_sun)
    illuminated = mu_sun > 0
    temperature[illuminated] = (
        subsolar_temperature * mu_sun[illuminated] ** 0.25
    )

    radius_m = D_km * 500.0
    surface_element = (
        radius_m**2
        * np.broadcast_to(sin_theta, (ntheta, nphi))
        * dtheta
        * dphi
    )
    radiance = _planck_nu(lam_um * 1e-6, temperature.ravel())
    flux = (
        emissivity
        * np.sum(
            radiance * (mu_observer * surface_element).ravel()[:, None],
            axis=0,
        )
        / (delta_au * au_m) ** 2
    )
    return flux / 1e-29, pv


def w3_equivalent_mjy(
    lam_um: np.ndarray,
    response: np.ndarray,
    spectrum_mjy: np.ndarray,
) -> float:
    """Integrate a model F_nu spectrum onto the W3 calibrated flux-density basis."""
    # With a constant F_nu spectrum this convention returns 0.9169 * F_nu,
    # matching the W3 basis paired with F0=29.0448 Jy in wise.py.
    numerator = np.trapezoid(response * spectrum_mjy / lam_um, lam_um)
    denominator = np.trapezoid(response / lam_um, lam_um)
    return float(W3_FC_CONST * numerator / denominator)


def fit_w3_neatm(
    session: requests.Session,
    epoch_rows: list[dict],
    *,
    H: float | None,
    G: float,
    eta_grid: list[float],
    emissivity: float,
    cal_fraction: float,
    assumed_pv: float,
    max_diameter_km: float,
    cache_dir: Path,
) -> list[dict]:
    """Fit diameter independently for each eta using usable W3 epochs.

    The upper limit uses ``Delta chi^2 = 2.71`` above the minimum as a one-sided
    profile-likelihood diagnostic. Results remain conditional on the adopted
    thermal model and on interpreting the measured W3 signal thermally.
    """
    rows = [
        row
        for row in epoch_rows
        if int(row.get("band", -1)) == 3
        and np.isfinite(row.get("flux_mjy", np.nan))
        and np.isfinite(row.get("null_sigma_mjy", np.nan))
        and row.get("null_sigma_mjy", 0) > 0
        and np.isfinite(row.get("r_au", np.nan))
        and np.isfinite(row.get("delta_au", np.nan))
        and np.isfinite(row.get("phase_deg", np.nan))
    ]
    if not rows:
        return []

    wavelength_um, response = load_w3_rsr(session, cache_dir)
    h_scale = 1329.0 * 10 ** (-H / 5) if H is not None else None
    min_diameter = max(0.02, h_scale if h_scale is not None else 0.02)
    max_diameter = float(max_diameter_km)

    output: list[dict] = []
    for eta in eta_grid:
        prediction_cache: dict[tuple[float, str], tuple[float, float]] = {}

        def predict(diameter_km: float, row: dict) -> tuple[float, float]:
            key = (round(float(diameter_km), 6), row["epoch_id"])
            if key not in prediction_cache:
                spectrum, pv = neatm_spectrum_mjy(
                    wavelength_um,
                    diameter_km,
                    row["r_au"],
                    row["delta_au"],
                    row["phase_deg"],
                    float(eta),
                    H=H,
                    G=G,
                    emissivity=emissivity,
                    assumed_pv=assumed_pv,
                )
                prediction_cache[key] = (
                    w3_equivalent_mjy(wavelength_um, response, spectrum),
                    pv,
                )
            return prediction_cache[key]

        def chi2(diameter_km: float) -> float:
            total = 0.0
            for row in rows:
                model_flux, _ = predict(diameter_km, row)
                observed_flux = float(row["flux_mjy"])
                sigma = math.sqrt(
                    float(row["null_sigma_mjy"]) ** 2
                    + (
                        cal_fraction
                        * max(abs(observed_flux), abs(model_flux))
                    )
                    ** 2
                )
                total += ((observed_flux - model_flux) / sigma) ** 2
            return total

        optimum = minimize_scalar(
            chi2,
            bounds=(min_diameter, max_diameter),
            method="bounded",
        )
        best_diameter = float(optimum.x)
        chi2_min = float(optimum.fun)
        _, best_pv = predict(best_diameter, rows[0])

        target_chi2 = chi2_min + 2.71
        diameter_95 = np.nan
        if best_diameter < max_diameter and chi2(max_diameter) > target_chi2:
            try:
                diameter_95 = float(
                    brentq(
                        lambda diameter: chi2(diameter) - target_chi2,
                        best_diameter,
                        max_diameter,
                    )
                )
            except Exception:
                # An unavailable profile root should omit D95 rather than fail
                # an otherwise usable thermal fit.
                pass

        pv_95 = (
            (h_scale / diameter_95) ** 2
            if h_scale is not None and np.isfinite(diameter_95)
            else np.nan
        )
        output.append(
            {
                "eta": float(eta),
                "D_best_km": best_diameter,
                "pV_best": best_pv if H is not None else np.nan,
                "chi2_min": chi2_min,
                "n_w3_epochs": len(rows),
                "D95_one_sided_km": diameter_95,
                "pV_at_D95": pv_95,
                "H_used": H,
                "G_used": G,
                "w3_calibration_fraction": cal_fraction,
            }
        )

    return output
