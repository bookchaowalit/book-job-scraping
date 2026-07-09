"""
Anti-detection utilities — randomize fingerprints to avoid bot detection.
"""

import random
import hashlib
import time


def random_delay(min_sec: float = 1.0, max_sec: float = 5.0):
    """Sleep for random duration to mimic human behavior."""
    import asyncio
    delay = random.uniform(min_sec, max_sec)
    return asyncio.sleep(delay)


def random_viewport() -> dict:
    """Get a random browser viewport size."""
    viewports = [
        {"width": 1920, "height": 1080},
        {"width": 1366, "height": 768},
        {"width": 1536, "height": 864},
        {"width": 1440, "height": 900},
        {"width": 1280, "height": 720},
    ]
    return random.choice(viewports)


def random_timezone() -> str:
    """Get a random timezone."""
    return random.choice([
        "Asia/Bangkok",
        "Asia/Tokyo",
        "America/New_York",
        "Europe/London",
    ])


def generate_fingerprint() -> dict:
    """Generate a random browser fingerprint for Playwright context."""
    return {
        "viewport": random_viewport(),
        "locale": random.choice(["en-US", "en-GB", "th-TH"]),
        "timezone_id": random_timezone(),
        "color_scheme": random.choice(["light", "dark"]),
        "reduced_motion": random.choice(["reduce", "no-preference"]),
    }


def hash_url(url: str) -> str:
    """Generate short hash of URL for dedup."""
    return hashlib.md5(url.encode()).hexdigest()[:12]
