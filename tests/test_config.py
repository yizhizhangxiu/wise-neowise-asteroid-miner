import tempfile
import unittest
from pathlib import Path

from wise_miner.config import load_config


class ConfigTests(unittest.TestCase):
    def _write(self, text: str) -> Path:
        tmp = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".toml",
            encoding="utf-8",
            delete=False,
        )
        tmp.write(text)
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return Path(tmp.name)

    def test_minimal_config_uses_defaults(self):
        path = self._write('[target]\ndesignation = "2023 TP124"\n')
        cfg = load_config(path)
        self.assertEqual(cfg.target.designation, "2023 TP124")
        self.assertEqual(cfg.search.bands, [3, 4, 2, 1])
        self.assertEqual(cfg.photometry.bootstrap_n, 10000)
        self.assertTrue(cfg.detection.use_bh_fdr)

    def test_overrides_are_applied(self):
        path = self._write(
            '[target]\ndesignation = "1 Ceres"\nH = 3.34\n'
            '[search]\nmax_frames = 25\n'
            '[output]\nroot = "custom-results"\n'
        )
        cfg = load_config(path)
        self.assertAlmostEqual(cfg.target.H, 3.34)
        self.assertEqual(cfg.search.max_frames, 25)
        self.assertEqual(cfg.output.root, "custom-results")

    def test_designation_is_required(self):
        path = self._write("[target]\n")
        with self.assertRaisesRegex(ValueError, "designation is required"):
            load_config(path)


if __name__ == "__main__":
    unittest.main()
