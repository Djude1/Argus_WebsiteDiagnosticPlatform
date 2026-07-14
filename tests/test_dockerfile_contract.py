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


if __name__ == "__main__":
    unittest.main()
