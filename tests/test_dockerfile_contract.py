import json
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_GUNICORN_COMMAND = [
    "gunicorn",
    "config.wsgi:application",
    "--bind",
    "0.0.0.0:8000",
    "--workers",
    "2",
    "--threads",
    "4",
    "--timeout",
    "120",
    "--access-logfile",
    "-",
]


class DockerfileContractTest(unittest.TestCase):
    def test_default_command_is_single_line_json_gunicorn_instruction(self):
        dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")
        command_lines = [
            line for line in dockerfile.splitlines() if line.startswith("CMD ")
        ]

        self.assertEqual(len(command_lines), 1)
        payload = command_lines[0].removeprefix("CMD ")
        try:
            command = json.loads(payload)
        except json.JSONDecodeError as error:
            self.fail(f"Dockerfile CMD 必須是單行有效 JSON：{error}")

        self.assertEqual(command, EXPECTED_GUNICORN_COMMAND)

    def test_nuclei_templates_are_pinned_and_verified(self):
        """模板治理：版本鎖定、內容驗證，不可退回 `nuclei -update-templates || true`。"""
        dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")
        instructions = "\n".join(
            line for line in dockerfile.splitlines() if not line.lstrip().startswith("#")
        )
        self.assertNotIn("-update-templates", instructions)
        self.assertRegex(dockerfile, r"ARG NUCLEI_TEMPLATES_VERSION=v\d+\.\d+\.\d+\n")
        self.assertRegex(dockerfile, r"ARG NUCLEI_TEMPLATES_CHECKSUM_SHA256=[0-9a-f]{64}\n")
        self.assertIn("ENV ARGUS_NUCLEI_TEMPLATES_DIR=/opt/nuclei-templates", dockerfile)
        start = dockerfile.index("RUN mkdir -p /opt/nuclei-templates")
        step = dockerfile[start:dockerfile.index("\n\n", start)]
        self.assertIn("sha256sum -c", step)
        self.assertIn("sha1sum -c", step)
        self.assertNotIn("|| true", step)
        settings_py = (REPOSITORY_ROOT / "backend/config/settings.py").read_text(encoding="utf-8")
        self.assertIn('"ARGUS_NUCLEI_TEMPLATES_DIR", "/opt/nuclei-templates"', settings_py)


if __name__ == "__main__":
    unittest.main()
