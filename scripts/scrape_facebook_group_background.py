#!/usr/bin/env python3
"""Capture authorised Facebook Group posts in a dedicated Playwright profile.

This is an opt-in background alternative to the Chrome extension.  It opens
only operator-supplied Group URLs, reads rendered ``[role=article]`` nodes,
and writes the same bounded CSV shape consumed by
``scripts/import_facebook_group_posts.py``.  It never exports cookies, calls a
Facebook API, follows a post link, submits a form, or sends outreach.

The profile directory must be a dedicated directory outside this repository.
Run ``--login-only --headed`` once so the operator can sign in manually when
needed; later runs may use the same profile headlessly.  Do not use a personal
Chrome profile or copy its files into the repository.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.import_facebook_group_posts import (  # noqa: E402
    MAX_INPUT_BYTES,
    canonical_group_url,
    canonical_post_url,
)


MAX_GROUPS = 20
MAX_ROUNDS = 10
MAX_POSTS = 500
DEFAULT_ROUNDS = 3
DEFAULT_PAUSE_MS = 1500
MIN_PAUSE_MS = 500
MAX_PAUSE_MS = 10_000
VISIBILITY_CHOICES = {"auto", "public", "private", "unknown"}

_PUBLIC_MARKERS = re.compile(r"\bpublic\s+group\b|กลุ่มสาธารณะ|สาธารณะ", re.IGNORECASE)
_PRIVATE_MARKERS = re.compile(
    r"\bprivate\s+group\b|กลุ่มส่วนตัว|สมาชิกเท่านั้น|ส่วนตัว", re.IGNORECASE
)
_INCOMPLETE_MARKERS = re.compile(
    r"see\s+more|ดูเพิ่มเติม|อ่านเพิ่มเติม|แสดงเพิ่มเติม", re.IGNORECASE
)


@dataclass(frozen=True)
class CaptureTarget:
    url: str


class BackgroundCaptureError(RuntimeError):
    """A redacted, user-actionable capture error."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _bounded(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _playwright_start_error(exc: BaseException) -> str:
    """Map browser launch failures to safe, actionable reason codes."""

    message = str(exc).casefold()
    if "error while loading shared libraries" in message:
        return "playwright_system_dependencies_missing"
    if "executable doesn't exist" in message or "please run the following command" in message:
        return "playwright_browser_not_installed"
    if "missing x server" in message or "no display" in message:
        return "playwright_headed_requires_display"
    return "playwright_profile_could_not_start"


def visibility_from_text(value: Any) -> str:
    """Classify only explicit rendered visibility wording."""

    text = _bounded(value, 4000)
    if _PRIVATE_MARKERS.search(text):
        return "private"
    if _PUBLIC_MARKERS.search(text):
        return "public"
    return "unknown"


def resolve_visibility(
    detected_visibility: Any,
    visibility_override: str = "auto",
    *,
    allow_unknown: bool,
    allow_private: bool,
) -> str:
    """Apply the visibility gate without allowing a private page to be relabelled.

    The operator may confirm an ambiguous page as public, but an explicit
    private marker always remains private and requires the private gate.  This
    keeps the override useful for localized/partially-rendered public pages
    without turning a detected private page into public source evidence.
    """

    detected = str(detected_visibility or "unknown").casefold()
    if detected not in {"public", "private", "unknown"}:
        detected = "unknown"
    override = str(visibility_override or "auto").casefold()
    if override not in VISIBILITY_CHOICES:
        override = "auto"
    if detected == "private" and not allow_private:
        raise BackgroundCaptureError("private_group_requires_explicit_allow_private")
    if detected == "private" and override == "public":
        raise BackgroundCaptureError("private_group_cannot_be_labelled_public")
    visibility = override if override != "auto" else detected
    if visibility == "private" and not allow_private:
        raise BackgroundCaptureError("private_group_requires_explicit_allow_private")
    if visibility == "unknown" and not allow_unknown:
        raise BackgroundCaptureError("unknown_visibility_requires_explicit_allow_unknown")
    return visibility


def _post_quality(post: dict[str, Any]) -> tuple[int, int, int, int]:
    complete = post.get("text_complete") is True or str(
        post.get("text_complete") or ""
    ).strip().casefold() in {"1", "true", "yes", "complete"}
    return (
        int(complete),
        len(str(post.get("text") or "").strip()),
        int(bool(str(post.get("author_name") or "").strip())),
        int(bool(str(post.get("posted_at") or "").strip())),
    )


def deduplicate_posts(posts: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one strongest rendered copy per canonical post permalink."""

    chosen: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for post in posts:
        url = str(post.get("post_url") or "").strip()
        if not url:
            continue
        try:
            canonical, _ = canonical_post_url(url)
        except ValueError:
            continue
        candidate = dict(post)
        candidate["post_url"] = canonical
        if canonical not in chosen:
            order.append(canonical)
            chosen[canonical] = candidate
        elif _post_quality(candidate) > _post_quality(chosen[canonical]):
            chosen[canonical] = candidate
    return [chosen[url] for url in order]


def _profile_path(value: str) -> Path:
    if not str(value or "").strip():
        raise BackgroundCaptureError("profile_dir_required")
    path = Path(value).expanduser().resolve()
    try:
        path.relative_to(ROOT)
    except ValueError:
        return path
    raise BackgroundCaptureError("profile_dir_must_be_outside_repository")


def load_fixture_html(path: Path | None) -> str | None:
    """Read a bounded local HTML fixture for an offline browser smoke run."""

    if path is None:
        return None
    try:
        raw = path.expanduser().read_bytes()
    except OSError as exc:
        raise BackgroundCaptureError("fixture_unreadable") from exc
    if len(raw) > MAX_INPUT_BYTES:
        raise BackgroundCaptureError("fixture_too_large")
    try:
        html = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BackgroundCaptureError("fixture_must_be_utf8") from exc
    if not html.strip():
        raise BackgroundCaptureError("fixture_must_not_be_empty")
    return html


def load_group_targets(
    group_urls: Iterable[str] = (),
    groups_file: Path | None = None,
) -> list[CaptureTarget]:
    """Load and canonicalise a bounded, local list of Group URLs."""

    raw_values = [str(value).strip() for value in group_urls if str(value).strip()]
    if groups_file:
        try:
            raw = groups_file.read_bytes()
        except OSError as exc:
            raise BackgroundCaptureError("groups_file_unreadable") from exc
        if len(raw) > MAX_INPUT_BYTES:
            raise BackgroundCaptureError("groups_file_too_large")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise BackgroundCaptureError("groups_file_must_be_utf8") from exc
        if groups_file.suffix.casefold() == ".json" or text.lstrip().startswith("["):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise BackgroundCaptureError("groups_file_invalid_json") from exc
            if not isinstance(payload, list):
                raise BackgroundCaptureError("groups_json_must_be_a_list")
            raw_values.extend(str(item).strip() for item in payload if str(item).strip())
        else:
            raw_values.extend(
                line.split("#", 1)[0].strip()
                for line in text.splitlines()
                if line.split("#", 1)[0].strip()
            )
    if not raw_values:
        raise BackgroundCaptureError("at_least_one_group_url_required")
    targets: list[CaptureTarget] = []
    seen: set[str] = set()
    for value in raw_values:
        try:
            url = canonical_group_url(value)
        except ValueError as exc:
            raise BackgroundCaptureError("group_url_must_be_https_facebook_group") from exc
        if url in seen:
            continue
        seen.add(url)
        targets.append(CaptureTarget(url))
        if len(targets) > MAX_GROUPS:
            raise BackgroundCaptureError(f"maximum_{MAX_GROUPS}_groups_per_run")
    return targets


def _normalise_dom_post(
    raw: dict[str, Any],
    *,
    group_url: str,
    captured_at: str,
) -> dict[str, Any] | None:
    try:
        post_url, post_id = canonical_post_url(raw.get("post_url"))
        canonical_group = canonical_group_url(group_url)
    except ValueError:
        return None
    group_slug = re.search(r"/groups/([^/]+)", canonical_group, re.IGNORECASE)
    post_group = re.search(r"/groups/([^/]+)/", post_url, re.IGNORECASE)
    if group_slug and post_group and group_slug.group(1).casefold() != post_group.group(1).casefold():
        return None
    text = _bounded(raw.get("text"), 10_000)
    if not text:
        return None
    text_complete = raw.get("text_complete") is True
    return {
        "captured_at": _bounded(raw.get("captured_at"), 80) or captured_at,
        "group_url": canonical_group,
        "post_url": post_url,
        "post_id": _bounded(raw.get("post_id"), 100) or post_id,
        "group_name": _bounded(raw.get("group_name"), 240),
        "author_name": _bounded(raw.get("author_name"), 160),
        "posted_at": _bounded(raw.get("posted_at"), 80),
        "text": text,
        "visibility": str(raw.get("visibility") or "unknown").casefold()
        if str(raw.get("visibility") or "unknown").casefold() in {"public", "private", "unknown"}
        else "unknown",
        "text_complete": text_complete,
        "capture_method": "playwright_visible_tab",
        "source_channel": "facebook_group",
        "source_platform": "facebook",
    }


DOM_CAPTURE_SCRIPT = r"""
() => {
  const current = new URL(window.location.href);
  const host = current.hostname.toLowerCase().replace(/^www\./, '');
  const groupMatch = current.pathname.match(/^\/groups\/([^/]+)/i);
  const result = {
    group_url: host === 'facebook.com' || host.endsWith('.facebook.com')
      ? (groupMatch ? `https://facebook.com/groups/${groupMatch[1]}` : '') : '',
    group_name: '',
    visibility: 'unknown',
    captured_at: new Date().toISOString(),
    posts: [],
  };
  if (!result.group_url) return result;
  const heading = document.querySelector('h1, [role="heading"]');
  const ogTitle = document.querySelector('meta[property="og:title"]');
  result.group_name = ((heading && heading.textContent) || (ogTitle && ogTitle.content) || document.title || '')
    .replace(/\s+/g, ' ').trim().slice(0, 240);
  const bodyText = ((document.body && document.body.innerText) || '').slice(0, 4000);
  if (/\bpublic\s+group\b|กลุ่มสาธารณะ|สาธารณะ/iu.test(bodyText)) result.visibility = 'public';
  else if (/\bprivate\s+group\b|กลุ่มส่วนตัว|สมาชิกเท่านั้น|ส่วนตัว/iu.test(bodyText)) result.visibility = 'private';
  const clean = (href) => {
    try {
      const parsed = new URL(href, window.location.href);
      const parsedHost = parsed.hostname.toLowerCase().replace(/^www\./, '');
      if (parsed.protocol !== 'https:' || (parsedHost !== 'facebook.com' && !parsedHost.endsWith('.facebook.com')) || parsed.username || parsed.password || parsed.port) return '';
      const params = new URLSearchParams(parsed.search);
      [...params.keys()].forEach((key) => {
        if (/^(utm_|fbclid$|gclid$|dclid$|ref$|referrer$|source$|src$)/i.test(key)) params.delete(key);
      });
      params.sort();
      parsed.hostname = 'facebook.com';
      parsed.search = params.toString();
      parsed.hash = '';
      parsed.pathname = parsed.pathname.replace(/\/+$/, '') || '/';
      return parsed.toString();
    } catch (error) { return ''; }
  };
  const postId = (href) => {
    try {
      const parsed = new URL(href);
      const pathMatch = parsed.pathname.match(/\/groups\/[^/]+\/(?:posts|permalink)\/([^/]+)/i) || parsed.pathname.match(/\/(?:posts|permalink)\/([^/]+)/i);
      if (pathMatch) return pathMatch[1].slice(0, 100);
      return (parsed.searchParams.get('story_fbid') || parsed.searchParams.get('fbid') || parsed.searchParams.get('post_id') || parsed.searchParams.get('id') || '').slice(0, 100);
    } catch (error) { return ''; }
  };
  const seen = new Set();
  document.querySelectorAll('[role="article"]').forEach((article) => {
    const links = [...article.querySelectorAll('a[href]')].map((anchor) => ({
      url: clean(anchor.href),
      label: (anchor.textContent || '').replace(/\s+/g, ' ').trim(),
    }));
    const postUrl = links.map((item) => item.url).find((url) => {
      if (!url) return false;
      try {
        const path = new URL(url).pathname;
        return /\/groups\/[^/]+\/(?:posts|permalink)\/[^/]+/i.test(path) || /\/(?:story|posts|permalink)\.php$/i.test(path) || /\/(?:posts|permalink)\/[^/]+/i.test(path);
      } catch (error) { return false; }
    });
    if (!postUrl || seen.has(postUrl)) return;
    seen.add(postUrl);
    const text = (article.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 10000);
    if (!text) return;
    const author = links.find((item) => item.url && /facebook\.com\/(?:profile\.php\?id=|[A-Za-z0-9.]+$)/i.test(item.url));
    const time = article.querySelector('abbr, time');
    result.posts.push({
      post_url: postUrl,
      post_id: postId(postUrl),
      group_name: result.group_name,
      author_name: author ? author.label.slice(0, 160) : '',
      posted_at: ((time && (time.getAttribute('title') || time.textContent)) || '').replace(/\s+/g, ' ').trim().slice(0, 80),
      text,
      visibility: result.visibility,
      text_complete: !/see\s+more|ดูเพิ่มเติม|อ่านเพิ่มเติม|แสดงเพิ่มเติม/iu.test(article.innerText || ''),
      captured_at: result.captured_at,
    });
  });
  return result;
}
"""


async def _capture_group_page(
    page: Any,
    target: CaptureTarget,
    *,
    rounds: int,
    pause_ms: int,
    max_posts: int,
    allow_unknown: bool,
    allow_private: bool,
    visibility_override: str,
) -> tuple[list[dict[str, Any]], str]:
    try:
        await page.goto(target.url, wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(2500)
    except Exception as exc:  # pragma: no cover - requires a live browser
        raise BackgroundCaptureError("facebook_group_navigation_failed") from exc
    captured: list[dict[str, Any]] = []
    visibility = "unknown"
    for round_number in range(rounds):
        try:
            payload = await page.evaluate(DOM_CAPTURE_SCRIPT)
        except Exception as exc:  # pragma: no cover - requires a live browser
            raise BackgroundCaptureError("facebook_group_dom_read_failed") from exc
        if not isinstance(payload, dict) or not payload.get("group_url"):
            raise BackgroundCaptureError("facebook_group_requires_an_authorised_group_page")
        try:
            rendered_group = canonical_group_url(payload.get("group_url"))
        except ValueError as exc:
            raise BackgroundCaptureError("facebook_group_identity_unavailable") from exc
        if rendered_group != target.url:
            raise BackgroundCaptureError("facebook_group_redirected_to_a_different_group")
        visibility = resolve_visibility(
            payload.get("visibility"),
            visibility_override,
            allow_unknown=allow_unknown,
            allow_private=allow_private,
        )
        captured.extend(
            item
            for item in (
                _normalise_dom_post(
                    raw,
                    group_url=target.url,
                    captured_at=str(payload.get("captured_at") or _utc_now()),
                )
                for raw in (payload.get("posts") or [])
                if isinstance(raw, dict)
            )
            if item is not None
        )
        captured = deduplicate_posts(captured)[:max_posts]
        if round_number + 1 >= rounds or len(captured) >= max_posts:
            break
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(pause_ms)
        except Exception as exc:  # pragma: no cover - requires a live browser
            raise BackgroundCaptureError("facebook_group_scroll_failed") from exc
    for row in captured:
        row["visibility"] = visibility if visibility in {"public", "private", "unknown"} else "unknown"
    return captured, visibility


async def capture_groups(
    targets: list[CaptureTarget],
    *,
    profile_dir: Path,
    headed: bool,
    rounds: int,
    pause_ms: int,
    max_posts: int,
    allow_unknown: bool,
    allow_private: bool,
    visibility_override: str = "auto",
    login_only: bool = False,
    fixture_html: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover - dependency environment
        raise BackgroundCaptureError("playwright_is_not_installed") from exc
    try:
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=not headed,
                viewport={"width": 1440, "height": 1000},
                locale="th-TH",
                service_workers="block",
            )
            try:
                if fixture_html is not None:
                    async def fulfill_fixture(route: Any) -> None:
                        if route.request.resource_type == "document":
                            await route.fulfill(
                                status=200,
                                content_type="text/html; charset=utf-8",
                                body=fixture_html,
                            )
                        else:
                            await route.abort()

                    await context.route("**/*", fulfill_fixture)
                if login_only:
                    page = await context.new_page()
                    await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=45_000)
                    print("เปิด browser profile แล้ว ล็อกอินด้วยตัวเองถ้าจำเป็น จากนั้นกด Enter เพื่อปิด")
                    await asyncio.to_thread(input)
                    await page.close()
                    return [], {"groups": 0, "posts": 0, "skipped": 0}
                all_posts: list[dict[str, Any]] = []
                stats: dict[str, Any] = {
                    "groups": 0,
                    "posts": 0,
                    "skipped": 0,
                    "skip_reasons": {},
                }
                for target in targets:
                    page = await context.new_page()
                    try:
                        posts, _visibility = await _capture_group_page(
                            page,
                            target,
                            rounds=rounds,
                            pause_ms=pause_ms,
                            max_posts=max_posts,
                            allow_unknown=allow_unknown,
                            allow_private=allow_private,
                            visibility_override=visibility_override,
                        )
                        all_posts.extend(posts)
                        stats["groups"] += 1
                        stats["posts"] += len(posts)
                    except BackgroundCaptureError as exc:
                        stats["skipped"] += 1
                        reasons = stats["skip_reasons"]
                        reasons[str(exc)] = int(reasons.get(str(exc), 0)) + 1
                    finally:
                        await page.close()
                return deduplicate_posts(all_posts)[:max_posts], stats
            finally:
                await context.close()
    except BackgroundCaptureError:
        raise
    except Exception as exc:  # pragma: no cover - requires a live browser
        raise BackgroundCaptureError(_playwright_start_error(exc)) from exc


def write_capture(path: Path, rows: Iterable[dict[str, Any]]) -> Path:
    materialised = list(rows)
    if not materialised:
        raise BackgroundCaptureError("capture_has_no_posts")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
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
        ])
        writer.writeheader()
        for row in materialised:
            writer.writerow({field: row.get(field, "") for field in writer.fieldnames})
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group-url", action="append", default=[], help="Authorised Facebook Group URL; repeat up to 20 times")
    parser.add_argument("--groups-file", type=Path, help="Local newline-delimited or JSON list of Group URLs")
    parser.add_argument("--profile-dir", required=True, help="Dedicated Playwright profile directory outside this repository")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "exported" / "facebook_group_background.csv")
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS, help="Bounded scroll/capture rounds per Group (1-10)")
    parser.add_argument("--pause-ms", type=int, default=DEFAULT_PAUSE_MS, help="Pause after each bounded scroll (500-10000 ms)")
    parser.add_argument("--max-posts", type=int, default=MAX_POSTS, help="Maximum posts in one output (1-500)")
    parser.add_argument("--headed", action="store_true", help="Show the dedicated browser window; useful for first login/checkpoint")
    parser.add_argument("--login-only", action="store_true", help="Open the dedicated profile for manual login, then exit without capture")
    parser.add_argument("--fixture", type=Path, help="Offline local HTML fixture; intercepts all browser requests and never contacts Facebook")
    parser.add_argument("--dry-run", action="store_true", help="Validate profile/Group inputs without opening a browser or writing output")
    parser.add_argument("--allow-unknown", action="store_true", help="Capture when rendered visibility wording is not explicit; importer will quarantine it by default")
    parser.add_argument("--allow-private", action="store_true", help="Capture an explicitly private Group only with retention and terms references")
    parser.add_argument("--visibility", choices=sorted(VISIBILITY_CHOICES), default="auto", help="Use rendered visibility (auto) or an operator-confirmed label for every Group in this run")
    parser.add_argument("--retention-until", default="", help="Required with --allow-private; pass the same value to the importer")
    parser.add_argument("--terms-basis-ref", default="", help="Required with --allow-private; pass the same value to the importer")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        profile_dir = _profile_path(args.profile_dir)
        if args.rounds < 1 or args.rounds > MAX_ROUNDS:
            raise BackgroundCaptureError(f"rounds_must_be_between_1_and_{MAX_ROUNDS}")
        if args.pause_ms < MIN_PAUSE_MS or args.pause_ms > MAX_PAUSE_MS:
            raise BackgroundCaptureError(f"pause_ms_must_be_between_{MIN_PAUSE_MS}_and_{MAX_PAUSE_MS}")
        if args.max_posts < 1 or args.max_posts > MAX_POSTS:
            raise BackgroundCaptureError(f"max_posts_must_be_between_1_and_{MAX_POSTS}")
        if args.visibility == "private" and not args.allow_private:
            raise BackgroundCaptureError("visibility_private_requires_explicit_allow_private")
        if args.visibility == "unknown" and not args.allow_unknown:
            raise BackgroundCaptureError("visibility_unknown_requires_explicit_allow_unknown")
        if args.allow_private and (not str(args.retention_until).strip() or not str(args.terms_basis_ref).strip()):
            raise BackgroundCaptureError("allow_private_requires_retention_until_and_terms_basis_ref")
        fixture_html = load_fixture_html(args.fixture)
        if fixture_html is not None and args.login_only:
            raise BackgroundCaptureError("fixture_cannot_be_used_with_login_only")
        targets = [] if args.login_only else load_group_targets(args.group_url, args.groups_file)
        if args.dry_run:
            print(
                "facebook_group_background: dry-run "
                f"groups={len(targets)} profile={profile_dir} rounds={args.rounds} max_posts={args.max_posts}"
            )
            return 0
        rows, stats = asyncio.run(
            capture_groups(
                targets,
                profile_dir=profile_dir,
                headed=bool(args.headed or args.login_only),
                rounds=args.rounds,
                pause_ms=args.pause_ms,
                max_posts=args.max_posts,
                allow_unknown=args.allow_unknown,
                allow_private=args.allow_private,
                visibility_override=args.visibility,
                login_only=args.login_only,
                fixture_html=fixture_html,
            )
        )
        if args.login_only:
            print("facebook_group_background: login profile ready; no posts captured")
            return 0
        if not rows:
            reasons = ",".join(
                f"{key}={value}" for key, value in sorted(stats.get("skip_reasons", {}).items())
            ) or "no_posts_found"
            raise BackgroundCaptureError(f"no_posts_captured:{reasons}")
        write_capture(args.output, rows)
        print(
            "facebook_group_background: "
            f"groups={stats['groups']} posts={len(rows)} skipped={stats['skipped']} "
            f"output={args.output}"
        )
        return 0
    except (BackgroundCaptureError, OSError) as exc:
        print(f"facebook_group_background: ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
