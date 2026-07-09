"""
Scheduler adapter — implements SchedulerPort.
Loads job configs from YAML, runs scrapers on schedule.
"""
import json
import yaml
import asyncio
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime, timedelta

from core.models import ScrapeJob, ScrapeResult
from core.ports import SchedulerPort


class SchedulerAdapter:
    """
    YAML-driven job scheduler.
    Loads jobs from config/jobs.yaml, tracks state in data/schedule_state.json.
    """

    def __init__(
        self,
        config_path: Optional[Path] = None,
        state_path: Optional[Path] = None,
    ):
        self.config_path = config_path or Path(__file__).parent.parent.parent / "config" / "jobs.yaml"
        self.state_path = state_path or Path(__file__).parent.parent.parent / "data" / "schedule_state.json"
        self.jobs: Dict[str, ScrapeJob] = {}
        self._state: Dict[str, dict] = {}
        self._load_config()
        self._load_state()

    def _load_config(self):
        """Load job definitions from YAML config."""
        if not self.config_path.exists():
            print(f"[Scheduler] No config found at {self.config_path}")
            return

        with open(self.config_path) as f:
            config = yaml.safe_load(f)

        for job_data in config.get("jobs", []):
            job = ScrapeJob(
                name=job_data["name"],
                category=job_data["category"],
                engine=job_data["engine"],
                url=job_data["url"],
                schedule=job_data.get("schedule", "0 0 * * *"),
                enabled=job_data.get("enabled", True),
                rate_limit=job_data.get("rate_limit", 2.0),
                max_pages=job_data.get("max_pages", 10),
                params=job_data.get("params", {}),
                scraper_module=job_data.get("scraper_module"),
                scraper_class=job_data.get("scraper_class"),
            )
            self.jobs[job.name] = job

        print(f"[Scheduler] Loaded {len(self.jobs)} jobs from config")

    def _load_state(self):
        """Load last-run state from disk."""
        if self.state_path.exists():
            with open(self.state_path) as f:
                self._state = json.load(f)
            # Apply state to jobs
            for name, state in self._state.items():
                if name in self.jobs:
                    self.jobs[name].last_run = state.get("last_run")
                    self.jobs[name].run_count = state.get("run_count", 0)
                    self.jobs[name].error_count = state.get("error_count", 0)

    def _save_state(self):
        """Persist job state to disk."""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        state = {}
        for name, job in self.jobs.items():
            state[name] = {
                "last_run": job.last_run,
                "run_count": job.run_count,
                "error_count": job.error_count,
            }
        with open(self.state_path, "w") as f:
            json.dump(state, f, indent=2, default=str)

    def schedule(self, job: ScrapeJob) -> str:
        """Add a job to the scheduler."""
        self.jobs[job.name] = job
        self._save_state()
        return job.name

    def cancel(self, job_id: str) -> bool:
        """Cancel (disable) a job."""
        if job_id in self.jobs:
            self.jobs[job_id].enabled = False
            self._save_state()
            return True
        return False

    def get_pending_jobs(self) -> List[ScrapeJob]:
        """Get all jobs that are due to run."""
        return [job for job in self.jobs.values() if job.is_due()]

    def mark_completed(self, job_id: str, result: ScrapeResult):
        """Mark a job as completed."""
        if job_id in self.jobs:
            job = self.jobs[job_id]
            job.last_run = datetime.now().isoformat()
            job.run_count += 1
            if not result.success:
                job.error_count += 1
            self._save_state()

    def enable_job(self, job_id: str):
        """Enable a disabled job."""
        if job_id in self.jobs:
            self.jobs[job_id].enabled = True
            self._save_state()

    def get_status(self) -> List[Dict]:
        """Get status of all jobs."""
        return [
            {
                "name": job.name,
                "category": job.category,
                "engine": job.engine,
                "schedule": job.schedule,
                "enabled": job.enabled,
                "last_run": job.last_run,
                "is_due": job.is_due(),
                "run_count": job.run_count,
                "error_count": job.error_count,
            }
            for job in self.jobs.values()
        ]

    def print_schedule(self):
        """Print human-readable schedule."""
        print("\n" + "=" * 70)
        print("  SCRAPE JOB SCHEDULE")
        print("=" * 70)
        for job in self.jobs.values():
            status = "ON" if job.enabled else "OFF"
            due = "DUE" if job.is_due() else "waiting"
            last = job.last_run or "never"
            print(f"  [{status:3s}] {job.name:25s} | {job.schedule:15s} | {due:7s} | last: {last}")
        print("=" * 70)
