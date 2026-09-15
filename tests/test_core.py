import unittest
from types import SimpleNamespace

from wise_miner.thermal import h_diameter_table
from wise_miner.stats import (
    benjamini_hochberg_qvalues,
    classify_epochs,
    overall_classification,
    stouffer_combined_p,
    band_coherence_summary,
    overall_followup_priority,
)


def cfg():
    return SimpleNamespace(
        min_frames_candidate=5,
        min_frames_strong=8,
        candidate_p=0.05,
        strong_p=0.01,
        candidate_snr=2.0,
        strong_snr=3.0,
        use_bh_fdr=True,
        candidate_q=0.05,
        strong_q=0.01,
        thermal_bands=[3, 4],
        repeat_min_epochs=2,
        min_effective_n_warning=3.0,
        followup_enabled=True,
        followup_bands=[3, 4],
        followup_min_epochs=2,
        followup_epoch_p_max=0.25,
        followup_combined_p_max=0.10,
        followup_positive_fraction_min=0.55,
        followup_jackknife_positive_fraction_min=0.80,
        followup_min_effective_n=3.0,
    )


def epoch(band, eid, p, flux, n=11, effn=10, posf=0.63,
          med=0.3, trim=0.3, jack=1.0, snr=1.5):
    return {
        "band": band,
        "epoch_id": eid,
        "n_frames": n,
        "effective_n": effn,
        "positive_fraction": posf,
        "median_frame_flux_mjy": med,
        "trimmed20_frame_flux_mjy": trim,
        "jackknife_positive_fraction": jack,
        "flux_mjy": flux,
        "empirical_p_one_sided": p,
        "empirical_snr": snr,
    }


class CoreTests(unittest.TestCase):
    def test_h_relation(self):
        rows = h_diameter_table(17.48, [0.10])
        self.assertAlmostEqual(rows[0]["diameter_km"], 1.341, places=2)

    def test_bh(self):
        q = benjamini_hochberg_qvalues([0.01, 0.04, 0.20, 0.50])
        self.assertAlmostEqual(q[0], 0.04, places=8)

    def test_stouffer_tp124_values(self):
        p = stouffer_combined_p([0.10009, 0.176682])
        self.assertAlmostEqual(p, 0.05913, places=4)

    def test_tp124_formal_non_detection_high_followup(self):
        rows = [
            epoch(3, "W3_E1", 0.10009, 0.42097, snr=1.97),
            epoch(3, "W3_E2", 0.176682, 0.21171, n=13, effn=12.3,
                  posf=0.615, med=0.270, trim=0.245, snr=1.14),
        ]
        classify_epochs(rows, cfg())
        formal = overall_classification(rows, cfg())
        self.assertEqual(formal, "NO_SIGNIFICANT_THERMAL_DETECTION")

        coh = band_coherence_summary(rows, cfg())
        w3 = [r for r in coh if r["band"] == 3][0]
        self.assertEqual(w3["followup_flag"], "W3_REPEATABLE_SUBTHRESHOLD")
        self.assertEqual(w3["followup_priority"], "HIGH")

        priority, reason = overall_followup_priority(coh, formal)
        self.assertEqual(priority, "HIGH")
        self.assertEqual(reason, "W3_REPEATABLE_SUBTHRESHOLD")

    def test_w4_one_positive_one_negative_not_repeatable(self):
        rows = [
            epoch(4, "W4_E1", 0.695, -0.69, n=12, effn=11,
                  posf=0.33, med=-0.67, trim=-0.02, jack=0.08),
            epoch(4, "W4_E2", 0.0597, 3.30, n=17, effn=15,
                  posf=0.647, med=4.25, trim=3.65, jack=1.0, snr=2.03),
        ]
        classify_epochs(rows, cfg())
        coh = band_coherence_summary(rows, cfg())
        w4 = [r for r in coh if r["band"] == 4][0]
        self.assertEqual(w4["coherent_subthreshold"], 0)

    def test_to119_like_low_n_w1(self):
        rows = [
            {
                "band": 1, "epoch_id": "W1_E10", "n_frames": 2,
                "flux_mjy": 28.364, "empirical_p_one_sided": 0.034397,
                "empirical_snr": 9.8, "effective_n": 1.8,
                "positive_fraction": 1.0, "median_frame_flux_mjy": 28.0,
                "trimmed20_frame_flux_mjy": 28.0,
                "jackknife_positive_fraction": 1.0,
            },
            epoch(4, "W4_E1", 0.038296, 5.1878, n=15, effn=10,
                  posf=0.65, med=4.0, trim=4.0, jack=1.0, snr=2.94),
        ]
        classify_epochs(rows, cfg())
        self.assertEqual(rows[0]["classification"], "LOW_N_HINT")
        self.assertEqual(
            overall_classification(rows, cfg()),
            "W4_WEAK_SINGLE_EPOCH_CANDIDATE",
        )


if __name__ == "__main__":
    unittest.main()
