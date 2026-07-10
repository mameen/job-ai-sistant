from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HERMES_PKG = REPO / "agentic" / "hermes"
if str(HERMES_PKG) not in sys.path:
    sys.path.insert(0, str(HERMES_PKG))

# Import after path setup — manage.py helpers
sys.path.insert(0, str(REPO / "agentic" / "hermes" / "admin"))
import manage as manage_mod  # noqa: E402


class ConfigTemplateTests(unittest.TestCase):
    def test_dotenv_skips_empty_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dotenv = Path(tmp) / ".env"
            dotenv.write_text(
                "OLLAMA_BASE_URL=\nOLLAMA_MODEL=custom-model\n",
                encoding="utf-8",
            )
            saved = dict(os.environ)
            try:
                for key in ("OLLAMA_BASE_URL", "OLLAMA_MODEL"):
                    os.environ.pop(key, None)
                manage_mod._load_dotenv(dotenv)
                self.assertNotIn("OLLAMA_BASE_URL", os.environ)
                self.assertEqual(os.environ.get("OLLAMA_MODEL"), "custom-model")
            finally:
                for key in ("OLLAMA_BASE_URL", "OLLAMA_MODEL"):
                    os.environ.pop(key, None)
                os.environ.update(saved)

    def test_deep_merge_roles_local(self) -> None:
        base = {"ollama": {"base_url": "http://localhost:11434/v1", "default_model": "a"}}
        override = {"ollama": {"default_model": "b"}}
        merged = manage_mod._deep_merge_dict(base, override)
        self.assertEqual(merged["ollama"]["base_url"], "http://localhost:11434/v1")
        self.assertEqual(merged["ollama"]["default_model"], "b")

    def test_example_templates_exist(self) -> None:
        self.assertTrue((REPO / ".env.example").is_file())
        self.assertTrue(
            (
                REPO / "agentic/hermes/admin/config/hermes_roles.local.yaml.example"
            ).is_file()
        )
        secrets = REPO / "agentic/hermes/kb/scaffold/private/secrets"
        self.assertTrue((secrets / "oauth_gmail.example.json").is_file())


if __name__ == "__main__":
    unittest.main()
