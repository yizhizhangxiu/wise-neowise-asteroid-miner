"""WISE L1b cutout access, forced photometry, and static-source checks."""

from __future__ import annotations

import gzip
import math
import warnings
from io import BytesIO
from pathlib import Path

import numpy as np
import requests
from astropy.io import fits
from astropy.io.votable import parse_single_table
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_scales

from .util import request_get, safe_float, safe_str

IRSA_IBE_DATA = (
    "https://irsa.ipac.caltech.edu/ibe/data/wise/merge/merge_p1bm_frm"
)
IRSA_GATOR = "https://irsa.ipac.caltech.edu/cgi-bin/Gator/nph-query"
ALLWISE_CATALOG = "allwise_p3as_psd"

# Aperture radii/corrections follow the WISE single-exposure photometric setup
# used by this project. Background is estimated from a wide local annulus.
AP_RADIUS_ARCSEC = {1: 8.25, 2: 8.25, 3: 8.25, 4: 16.5}
AP_CORR_MAG = {1: 0.222, 2: 0.280, 3: 0.665, 4: 0.616}
BG_IN_ARCSEC = 50.0
BG_OUT_ARCSEC = 70.0

# Zero-magnitude flux densities used to convert MAGZP-calibrated DN to mJy.
# W3 matches the power-law/color-correction flux basis used in thermal.py.
F0_JY = {1: 309.540, 2: 171.787, 3: 29.0448, 4: 8.363}


def build_product_url(frame: dict, product: str, size_pix: int) -> str:
    """Build an IRSA IBE URL for an intensity or uncertainty L1b cutout."""
    scan = frame["scan_id"]
    frame_num = int(frame["frame_num"])
    band = int(frame["band"])
    group = scan[-2:]
    suffix = "int-1b.fits" if product == "int" else "unc-1b.fits.gz"
    filename = f"{scan}{frame_num:03d}-w{band}-{suffix}"
    base = f"{IRSA_IBE_DATA}/{group}/{scan}/{frame_num:03d}/{filename}"
    return (
        f"{base}?center={frame['ra']:.10f},{frame['dec']:.10f}"
        f"&size={int(size_pix)}pix&gzip=false"
    )


def _decode(content: bytes) -> bytes:
    """Decompress gzip content when the response is gzip-encoded."""
    return gzip.decompress(content) if content[:2] == b"\x1f\x8b" else content


def load_cutout(
    session: requests.Session,
    frame: dict,
    product: str,
    size_pix: int,
    cache_dir: Path,
) -> tuple[np.ndarray, fits.Header, Path]:
    """Load a cached or remote L1b cutout and return data, header, and path."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    scan = frame["scan_id"]
    frame_num = int(frame["frame_num"])
    band = int(frame["band"])
    path = cache_dir / (
        f"{scan}_{frame_num:03d}_w{band}_{product}_{size_pix}px.fits"
    )

    if path.exists():
        content = path.read_bytes()
    else:
        response = request_get(
            session,
            build_product_url(frame, product, size_pix),
            timeout=180,
        )
        content = _decode(response.content)
        path.write_bytes(content)

    with fits.open(BytesIO(content), memmap=False) as hdul:
        return (
            np.asarray(hdul[0].data, dtype=float),
            hdul[0].header.copy(),
            path,
        )


def _aperture_measure(
    image_mjy: np.ndarray,
    unc_mjy: np.ndarray,
    x: float,
    y: float,
    pixscale: float,
    band: int,
) -> tuple[float, float, bool]:
    """Measure one aperture with a local-annulus background subtraction."""
    yy, xx = np.indices(image_mjy.shape, dtype=float)
    radius_arcsec = np.hypot(xx - x, yy - y) * pixscale

    aperture = radius_arcsec <= AP_RADIUS_ARCSEC[band]
    background = (
        (radius_arcsec >= BG_IN_ARCSEC) & (radius_arcsec <= BG_OUT_ARCSEC)
    )

    good_image = np.isfinite(image_mjy)
    good_unc = np.isfinite(unc_mjy) & (unc_mjy > 0)
    if np.count_nonzero(aperture & good_image) < 0.95 * max(
        1, np.count_nonzero(aperture)
    ):
        return np.nan, np.nan, False
    if np.count_nonzero(background & good_image) < 0.90 * max(
        1, np.count_nonzero(background)
    ):
        return np.nan, np.nan, False

    background_values = image_mjy[background & good_image]
    background_median = float(np.median(background_values))
    aperture_values = image_mjy[aperture & good_image] - background_median
    flux = float(np.sum(aperture_values))

    aperture_correction = 10.0 ** (0.4 * AP_CORR_MAG[band])
    flux *= aperture_correction

    variance = float(np.sum(unc_mjy[aperture & good_unc] ** 2))
    if len(background_values) >= 10:
        # Propagate uncertainty in the locally estimated background level. The
        # MAD term makes this less sensitive to a few bright background pixels.
        median = np.median(background_values)
        mad = np.median(np.abs(background_values - median))
        sigma_background = 1.4826 * mad
        n_aperture = np.count_nonzero(aperture & good_image)
        n_background = len(background_values)
        variance += (
            n_aperture * sigma_background / math.sqrt(n_background)
        ) ** 2

    sigma = math.sqrt(max(variance, 0.0)) * aperture_correction
    return flux, sigma, True


def measure_frame(
    session: requests.Session,
    frame: dict,
    *,
    size_pix: int,
    n_controls: int,
    exclusion_arcsec: float,
    rng: np.random.Generator,
    cache_dir: Path,
) -> tuple[dict, list[float]]:
    """Measure the target and random same-frame control apertures.

    The returned target flux is corrected by the median control-aperture flux.
    ``sigma_use_mjy`` is the larger of the formal aperture uncertainty and the
    robust control-aperture scatter, preventing an unrealistically small formal
    uncertainty from dominating later epoch weights.
    """
    data_dn, header, intensity_path = load_cutout(
        session, frame, "int", size_pix, cache_dir
    )
    unc_dn, _, uncertainty_path = load_cutout(
        session, frame, "unc", size_pix, cache_dir
    )

    magzp = safe_float(header.get("MAGZP"))
    if not np.isfinite(magzp):
        raise RuntimeError("FITS header has no finite MAGZP")

    band = int(frame["band"])
    mjy_per_dn = F0_JY[band] * 1000.0 * 10.0 ** (-0.4 * magzp)
    image = data_dn * mjy_per_dn
    uncertainty = unc_dn * mjy_per_dn

    wcs = WCS(header).celestial
    x0, y0 = wcs.world_to_pixel_values(frame["ra"], frame["dec"])
    x0 = float(np.asarray(x0).reshape(-1)[0])
    y0 = float(np.asarray(y0).reshape(-1)[0])
    pixscale = float(np.nanmedian(proj_plane_pixel_scales(wcs)) * 3600.0)

    target_flux, target_sigma, ok = _aperture_measure(
        image, uncertainty, x0, y0, pixscale, band
    )
    if not ok:
        raise RuntimeError("target aperture/background annulus incomplete")

    # Controls need enough margin for their full background annulus, not only
    # the source aperture. This avoids edge-clipped controls biasing the null.
    margin_arcsec = BG_OUT_ARCSEC + 2.0 * pixscale
    margin_pix = margin_arcsec / pixscale
    ny, nx = image.shape

    controls: list[float] = []
    attempts = 0
    max_attempts = max(1000, n_controls * 100)
    while len(controls) < n_controls and attempts < max_attempts:
        attempts += 1
        if nx <= 2 * margin_pix or ny <= 2 * margin_pix:
            break

        x = rng.uniform(margin_pix, nx - margin_pix)
        y = rng.uniform(margin_pix, ny - margin_pix)
        if math.hypot(x - x0, y - y0) * pixscale < exclusion_arcsec:
            continue

        flux, _, good = _aperture_measure(
            image, uncertainty, x, y, pixscale, band
        )
        if good and np.isfinite(flux):
            controls.append(float(flux))

    control_array = np.asarray(controls, dtype=float)
    control_median = (
        float(np.median(control_array)) if len(control_array) else np.nan
    )
    control_sigma = (
        float(1.4826 * np.median(np.abs(control_array - control_median)))
        if len(control_array) >= 3
        else np.nan
    )
    corrected_flux = (
        target_flux - control_median
        if np.isfinite(control_median)
        else target_flux
    )
    sigma_use = np.nanmax([target_sigma, control_sigma])

    row = dict(frame)
    row.update(
        {
            "magzp": magzp,
            "pixel_scale_arcsec": pixscale,
            "target_flux_raw_mjy": target_flux,
            "target_sigma_formal_mjy": target_sigma,
            "control_n": len(control_array),
            "control_median_mjy": control_median,
            "control_mad_sigma_mjy": control_sigma,
            "target_flux_corrected_mjy": corrected_flux,
            "sigma_use_mjy": sigma_use,
            "frame_empirical_snr": (
                corrected_flux / sigma_use
                if np.isfinite(sigma_use) and sigma_use > 0
                else np.nan
            ),
            "intensity_cache": str(intensity_path),
            "uncertainty_cache": str(uncertainty_path),
        }
    )
    return row, controls


def query_allwise_contamination(
    session: requests.Session,
    frame: dict,
    *,
    radius_arcsec: float,
    min_catalog_snr: float,
    cache_dir: Path,
) -> dict:
    """Check whether a W3/W4 target aperture overlaps a relevant AllWISE source."""
    band = int(frame["band"])
    if band not in (3, 4):
        return {
            "static_check_done": 0,
            "static_contaminated": 0,
            "static_nearest_sep_arcsec": np.nan,
        }

    cache_dir.mkdir(parents=True, exist_ok=True)
    scan = frame["scan_id"]
    frame_num = int(frame["frame_num"])
    radius_tag = f"{radius_arcsec:.3f}".replace(".", "p")
    cache = cache_dir / (
        f"{scan}_{frame_num:03d}_w{band}_r{radius_tag}as_allwise.xml"
    )

    columns = (
        f"designation,ra,dec,w{band}mpro,w{band}sigmpro,w{band}snr,"
        f"w{band}rchi2,cc_flags,ext_flg,ph_qual"
    )
    if cache.exists():
        content = cache.read_bytes()
    else:
        params = {
            "catalog": ALLWISE_CATALOG,
            "spatial": "cone",
            "radius": f"{radius_arcsec:.3f}",
            "radunits": "arcsec",
            "objstr": f"{frame['ra']:.10f} {frame['dec']:.10f}",
            "outfmt": "3",
            "selcols": columns,
            "outrows": "5000",
        }
        response = request_get(session, IRSA_GATOR, params=params, timeout=180)
        content = response.content
        cache.write_bytes(content)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            table = parse_single_table(BytesIO(content)).to_table(
                use_names_over_ids=True
            )
    except Exception as exc:
        return {
            "static_check_done": 0,
            "static_contaminated": 0,
            "static_nearest_sep_arcsec": np.nan,
            "static_error": str(exc),
        }

    if len(table) == 0:
        return {
            "static_check_done": 1,
            "static_contaminated": 0,
            "static_nearest_sep_arcsec": np.nan,
        }

    ra0 = math.radians(frame["ra"])
    dec0 = math.radians(frame["dec"])
    best = None

    for row in table:
        try:
            ra = math.radians(float(row["ra"]))
            dec = math.radians(float(row["dec"]))
            cos_sep = (
                math.sin(dec0) * math.sin(dec)
                + math.cos(dec0) * math.cos(dec) * math.cos(ra - ra0)
            )
            separation = math.degrees(
                math.acos(max(-1.0, min(1.0, cos_sep)))
            ) * 3600.0
        except Exception:
            continue

        snr = safe_float(row[f"w{band}snr"])
        extended = int(safe_float(row["ext_flg"], 0))
        flags = safe_str(row["cc_flags"], "")
        cc_char = flags[band - 1] if len(flags) >= band else ""

        # A source is relevant if it has measurable band flux, is extended, or
        # carries a contamination/confusion flag in the band under inspection.
        relevant = (
            (np.isfinite(snr) and snr >= min_catalog_snr)
            or extended > 0
            or cc_char not in ("", "0")
        )
        if not relevant:
            continue

        if best is None or separation < best["static_nearest_sep_arcsec"]:
            best = {
                "static_check_done": 1,
                "static_contaminated": int(separation <= radius_arcsec),
                "static_nearest_sep_arcsec": separation,
                "static_designation": safe_str(row["designation"]),
                "static_catalog_snr": snr,
                "static_ext_flg": extended,
                "static_cc_char": cc_char,
            }

    return best or {
        "static_check_done": 1,
        "static_contaminated": 0,
        "static_nearest_sep_arcsec": np.nan,
    }
