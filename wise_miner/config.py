"""TOML-backed configuration models for the screening pipeline.

Defaults live here so the runtime, example configuration, and documentation can
refer to one set of scientific/operational assumptions.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TargetConfig:
    """Target identity and optional photometric phase parameters."""

    designation: str
    H: float | None = None
    G: float | None = None


@dataclass
class SearchConfig:
    """MOST coverage-search and epoch-grouping settings."""

    obs_begin: str = ""
    obs_end: str = ""
    bands: list[int] = field(default_factory=lambda: [3, 4, 2, 1])
    min_qual_frame: int = 5
    epoch_gap_days: float = 30.0
    max_frames: int = 0


@dataclass
class PhotometryConfig:
    """L1b cutout, control-aperture, and bootstrap settings."""

    cutout_size_pix: int = 180
    controls_per_frame: int = 80
    control_exclusion_arcsec: float = 30.0
    bootstrap_n: int = 10000
    random_seed: int = 20260913
    save_control_samples: bool = False


@dataclass
class ContaminationConfig:
    """AllWISE static-source checking and thermal-frame veto settings."""

    enabled: bool = True
    veto_radius_arcsec: float = 12.0
    min_catalog_snr: float = 2.0
    exclude_contaminated_thermal_frames: bool = True


@dataclass
class DetectionConfig:
    """Formal epoch/target screening and independent follow-up thresholds."""

    min_frames_candidate: int = 5
    min_frames_strong: int = 8

    candidate_p: float = 0.05
    strong_p: float = 0.01
    candidate_snr: float = 2.0
    strong_snr: float = 3.0

    use_bh_fdr: bool = True
    candidate_q: float = 0.05
    strong_q: float = 0.01

    thermal_bands: list[int] = field(default_factory=lambda: [3, 4])
    repeat_min_epochs: int = 2

    # Diagnostic only: low effective N is reported but does not veto a result.
    min_effective_n_warning: float = 3.0

    # This layer prioritizes validation work; it never changes formal status.
    followup_enabled: bool = True
    followup_bands: list[int] = field(default_factory=lambda: [3, 4])
    followup_min_epochs: int = 2
    followup_epoch_p_max: float = 0.25
    followup_combined_p_max: float = 0.10
    followup_positive_fraction_min: float = 0.55
    followup_jackknife_positive_fraction_min: float = 0.80
    followup_min_effective_n: float = 3.0


@dataclass
class ThermalConfig:
    """W3 NEATM model assumptions and numerical bounds."""

    enabled: bool = True
    eta_grid: list[float] = field(default_factory=lambda: [0.8, 1.0, 1.2, 1.4])
    emissivity: float = 0.90
    w3_calibration_fraction: float = 0.05
    assumed_pv_if_H_missing: float = 0.10
    max_diameter_km: float = 50.0


@dataclass
class OutputConfig:
    """Result-directory and plotting settings."""

    root: str = "results"
    make_plots: bool = True


@dataclass
class Config:
    """Complete parsed pipeline configuration."""

    target: TargetConfig
    search: SearchConfig
    photometry: PhotometryConfig
    contamination: ContaminationConfig
    detection: DetectionConfig
    thermal: ThermalConfig
    output: OutputConfig


def load_config(path: str | Path) -> Config:
    """Load a TOML file into typed configuration sections.

    Only ``[target].designation`` is mandatory. Missing optional sections use
    the dataclass defaults above; unknown keys naturally raise ``TypeError`` so
    configuration typos are not silently ignored.
    """
    p = Path(path)
    with p.open("rb") as f:
        data = tomllib.load(f)

    if "target" not in data or not data["target"].get("designation"):
        raise ValueError("[target] designation is required")

    return Config(
        target=TargetConfig(**data["target"]),
        search=SearchConfig(**data.get("search", {})),
        photometry=PhotometryConfig(**data.get("photometry", {})),
        contamination=ContaminationConfig(**data.get("contamination", {})),
        detection=DetectionConfig(**data.get("detection", {})),
        thermal=ThermalConfig(**data.get("thermal", {})),
        output=OutputConfig(**data.get("output", {})),
    )
