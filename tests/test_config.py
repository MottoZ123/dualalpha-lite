import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research_core.config import PROJECT_ROOT, ProviderConfig, get_app_config, load_env_file


class ConfigTests(unittest.TestCase):
    def test_provider_requires_secret(self):
        cfg = ProviderConfig("deepseek", "", "deepseek-v4-pro", "https://example.test/chat/completions", 10, 1)
        with self.assertRaisesRegex(RuntimeError, "DEEPSEEK_API_KEY"):
            cfg.validate()

    def test_env_loader_does_not_override_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("SAMPLE_KEY=file-value\n", encoding="utf-8")
            with patch.dict(os.environ, {"SAMPLE_KEY": "process-value"}, clear=False):
                load_env_file(path)
                self.assertEqual(os.environ["SAMPLE_KEY"], "process-value")

    def test_blank_optional_paths_use_safe_defaults(self):
        with patch.dict(os.environ, {"RESEARCH_DATA_DIR": "", "RESEARCH_REPORTS_DIR": ""}, clear=False):
            cfg = get_app_config()
            self.assertNotEqual(str(cfg.data_dir), ".")
            self.assertEqual(cfg.reports_dir, PROJECT_ROOT / "AB_Test_Reports")


if __name__ == "__main__":
    unittest.main()
