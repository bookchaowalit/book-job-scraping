from __future__ import annotations

import asyncio
import csv
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from scripts.scrape_facebook_group_background import (
    DOM_CAPTURE_SCRIPT,
    BackgroundCaptureError,
    CaptureTarget,
    _normalise_dom_post,
    _playwright_start_error,
    _profile_path,
    capture_groups,
    deduplicate_posts,
    load_fixture_html,
    load_group_targets,
    main,
    resolve_visibility,
    visibility_from_text,
    write_capture,
)


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "scrape_facebook_group_background.py"
FIXTURE = ROOT / "tests" / "fixtures" / "facebook_group_background.html"


class FacebookGroupBackgroundTests(unittest.TestCase):
    def test_visibility_requires_explicit_rendered_wording(self):
        self.assertEqual(visibility_from_text("This is a public group"), "public")
        self.assertEqual(visibility_from_text("กลุ่มส่วนตัว สมาชิกเท่านั้น"), "private")
        self.assertEqual(visibility_from_text("โพสต์จากกลุ่ม"), "unknown")

    def test_visibility_override_can_confirm_unknown_as_public(self):
        self.assertEqual(
            resolve_visibility(
                "unknown",
                "public",
                allow_unknown=False,
                allow_private=False,
            ),
            "public",
        )

    def test_visibility_override_cannot_relabel_private_as_public(self):
        with self.assertRaisesRegex(
            BackgroundCaptureError, "private_group_cannot_be_labelled_public"
        ):
            resolve_visibility(
                "private",
                "public",
                allow_unknown=False,
                allow_private=True,
            )

    def test_playwright_launch_errors_are_redacted_to_actionable_codes(self):
        self.assertEqual(
            _playwright_start_error(RuntimeError("error while loading shared libraries: libnspr4.so")),
            "playwright_system_dependencies_missing",
        )
        self.assertEqual(
            _playwright_start_error(RuntimeError("Executable doesn't exist at /tmp/browser")),
            "playwright_browser_not_installed",
        )

    def test_fixture_is_bounded_and_dry_run_validates_it(self):
        self.assertGreater(len(load_fixture_html(FIXTURE) or ""), 100)
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with redirect_stdout(output):
                result = main(
                    [
                        "--group-url",
                        "https://facebook.com/groups/demo",
                        "--profile-dir",
                        directory,
                        "--visibility",
                        "public",
                        "--fixture",
                        str(FIXTURE),
                        "--dry-run",
                    ]
                )
        self.assertEqual(result, 0)
        self.assertIn("dry-run groups=1", output.getvalue())

    def test_group_targets_are_canonicalised_and_deduplicated(self):
        targets = load_group_targets(
            [
                "https://www.facebook.com/groups/demo/?ref=book",
                "https://facebook.com/groups/demo",
            ]
        )
        self.assertEqual([target.url for target in targets], ["https://facebook.com/groups/demo"])

    def test_group_target_file_is_bounded_and_supports_comments(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "groups.txt"
            path.write_text(
                "# approved group list\nhttps://facebook.com/groups/one\nhttps://facebook.com/groups/two # second\n",
                encoding="utf-8",
            )
            self.assertEqual(
                [target.url for target in load_group_targets(groups_file=path)],
                ["https://facebook.com/groups/one", "https://facebook.com/groups/two"],
            )

    def test_group_targets_fail_closed_for_non_facebook_urls(self):
        with self.assertRaises(BackgroundCaptureError):
            load_group_targets(["https://example.com/groups/demo"])

    def test_dry_run_validates_without_opening_browser(self):
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with redirect_stdout(output):
                result = main(
                    [
                        "--group-url",
                        "https://facebook.com/groups/demo",
                        "--profile-dir",
                        directory,
                        "--visibility",
                        "public",
                        "--dry-run",
                    ]
                )
        self.assertEqual(result, 0)
        self.assertIn("dry-run groups=1", output.getvalue())

    def test_profile_directory_cannot_live_inside_repository(self):
        with self.assertRaises(BackgroundCaptureError):
            _profile_path(str(ROOT / "data" / "browser-profile"))

    def test_deduplicate_keeps_the_more_complete_rendered_copy(self):
        posts = deduplicate_posts(
            [
                {
                    "post_url": "https://facebook.com/groups/demo/posts/1?utm_source=one",
                    "text": "short",
                    "text_complete": False,
                },
                {
                    "post_url": "https://www.facebook.com/groups/demo/posts/1?fbclid=synthetic",
                    "text": "a longer complete post",
                    "text_complete": True,
                    "author_name": "Owner",
                },
            ]
        )
        self.assertEqual(len(posts), 1)
        self.assertTrue(posts[0]["text_complete"])
        self.assertEqual(posts[0]["author_name"], "Owner")

    def test_dom_post_rejects_a_different_group(self):
        row = _normalise_dom_post(
            {
                "post_url": "https://facebook.com/groups/other/posts/1",
                "text": "Owner post",
                "text_complete": True,
            },
            group_url="https://facebook.com/groups/demo",
            captured_at="2026-09-15T00:00:00Z",
        )
        self.assertIsNone(row)

    def test_write_capture_uses_extension_compatible_headers(self):
        with tempfile.TemporaryDirectory() as directory:
            output = write_capture(
                Path(directory) / "capture.csv",
                [
                    {
                        "captured_at": "2026-09-15T00:00:00Z",
                        "group_url": "https://facebook.com/groups/demo",
                        "post_url": "https://facebook.com/groups/demo/posts/1",
                        "post_id": "1",
                        "group_name": "Demo",
                        "author_name": "Owner",
                        "posted_at": "today",
                        "text": "Owner post",
                        "visibility": "public",
                        "text_complete": True,
                        "capture_method": "playwright_visible_tab",
                        "source_channel": "facebook_group",
                        "source_platform": "facebook",
                    }
                ],
            )
            with output.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(
                    reader.fieldnames,
                    [
                        "captured_at",
                        "group_url",
                        "post_url",
                        "post_id",
                        "group_name",
                        "author_name",
                        "posted_at",
                        "text",
                        "visibility",
                        "text_complete",
                        "capture_method",
                        "source_channel",
                        "source_platform",
                    ],
                )
                self.assertEqual(next(reader)["capture_method"], "playwright_visible_tab")

    def test_browser_script_has_no_cookie_or_network_api_path(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("context.cookies", source)
        self.assertNotIn("storage_state", source)
        self.assertNotIn("fetch(", DOM_CAPTURE_SCRIPT)
        self.assertIn("[role=\"article\"]", DOM_CAPTURE_SCRIPT)
        self.assertIn("window.scrollTo", source)
        self.assertIn('service_workers="block"', source)

    def test_browser_fixture_capture_when_playwright_is_available(self):
        try:
            import playwright  # noqa: F401
        except ImportError:
            self.skipTest("playwright is not installed in this test environment")
        with tempfile.TemporaryDirectory() as directory:
            try:
                rows, stats = asyncio.run(
                    capture_groups(
                        [CaptureTarget("https://facebook.com/groups/demo")],
                        profile_dir=Path(directory) / "profile",
                        headed=False,
                        rounds=1,
                        pause_ms=500,
                        max_posts=10,
                        allow_unknown=False,
                        allow_private=False,
                        visibility_override="public",
                        fixture_html=load_fixture_html(FIXTURE),
                    )
                )
            except BackgroundCaptureError as exc:
                if str(exc) in {
                    "playwright_profile_could_not_start",
                    "playwright_system_dependencies_missing",
                    "playwright_browser_not_installed",
                    "playwright_headed_requires_display",
                }:
                    self.skipTest("Playwright Chromium cannot start in this environment")
                raise
        self.assertEqual(stats["groups"], 1)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["visibility"], "public")
        self.assertEqual(rows[0]["author_name"], "Demo Owner")
        self.assertTrue(rows[0]["text_complete"])
        self.assertFalse(rows[1]["text_complete"])


if __name__ == "__main__":
    unittest.main()
