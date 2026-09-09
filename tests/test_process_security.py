"""Process boundary tests; no scrapers, browser, crontab or notifications run."""
import importlib.util
import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"dotenv": types.SimpleNamespace(load_dotenv=lambda *a: None)}):
        spec.loader.exec_module(module)
    return module

class ProcessSecurityTest(unittest.TestCase):
    def test_browser_url_is_one_literal_argument(self):
        module = load_script("application_tracker")
        url = "http://localhost:8080/' ; $(never-execute)"
        with patch.object(module.subprocess, "run") as run:
            module.open_tracker_browser(url)
            self.assertEqual(run.call_args.args[0], ["xdg-open", url])
            self.assertFalse(run.call_args.kwargs["shell"])
        with patch.object(module.subprocess, "run", side_effect=FileNotFoundError):
            module.open_tracker_browser(url)

    def test_scheduler_preserves_arguments_and_working_directory(self):
        module = load_script("cron_scheduler")
        odd = Path("/tmp/work space;$(never-execute)")
        with patch.object(module, "ROOT", odd), patch.object(module, "SCRIPTS_DIR", odd / "scripts"):
            tasks = module.get_daily_commands() + module.get_weekly_commands()
            for task in tasks:
                with patch.object(module.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
                    self.assertEqual(module.run_task(task)["status"], "success")
                    self.assertEqual(run.call_args.args[0], task["cmd"])
                    self.assertIsInstance(task["cmd"], list)
                    self.assertEqual(task["cmd"][1].split("/scripts/")[0], str(odd))
                    self.assertFalse(run.call_args.kwargs["shell"])
                    self.assertEqual(run.call_args.kwargs["cwd"], odd)

    def test_daily_command_metacharacters_are_literal(self):
        module = load_script("daily_job_scraping")
        argv = [sys.executable, "/tmp/path with spaces/script.py", "$(never-execute);*"]
        with patch.object(module.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertTrue(module.run_command(argv, "fixture"))
            self.assertEqual(run.call_args.args[0], argv)
            self.assertFalse(run.call_args.kwargs["shell"])

if __name__ == "__main__":
    unittest.main()
