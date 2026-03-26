#!/usr/bin/env python3
"""
Rebuild README from .good-reads/queue.txt and done.txt.

Triggers (via env):
- GOOD_READS_ADD / GOOD_READS_MARK: multiline (workflow_dispatch).
- issues: title/body read from GITHUB_EVENT_PATH (avoids broken multiline step env).
- Optional: GOOD_READS_FROM_ISSUE + GOOD_READS_ISSUE_* for local testing.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUEUE = ROOT / ".good-reads" / "queue.txt"
DONE = ROOT / ".good-reads" / "done.txt"
README = ROOT / "README.md"

# Loose scan for URLs embedded in title/body (stops at whitespace).
URL_TOKEN_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def parse_line(line: str) -> tuple[str, str | None] | None:
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    if "|" in s:
        url, title = s.split("|", 1)
        url, title = url.strip(), title.strip()
        return (url, title or None) if url else None
    return (s, None)


def extract_urls_loose(text: str) -> list[str]:
    if not text:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for u in URL_TOKEN_RE.findall(text):
        u = u.rstrip(".,;:!?")
        k = queue_key(u)
        if k not in seen:
            seen.add(k)
            out.append(u)
    return out


def parse_issue_body_line(line: str) -> tuple[str, str | None] | None:
    """One pasted line: plain URL, optional ``url | title``, or a single markdown link."""
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    md = re.fullmatch(r"\[([^\]]*)\]\((https?://[^)]+)\)\s*", s, re.IGNORECASE)
    if md:
        url = md.group(2).strip()
        label = (md.group(1) or "").strip()
        return (url, label or None)
    if "|" in s:
        left, right = s.split("|", 1)
        left, right = left.strip(), right.strip()
        if re.match(r"^https?://", left, re.IGNORECASE):
            return (left, right or None) if left else None
        return None
    if re.match(r"^https?://", s, re.IGNORECASE):
        return (s, None)
    return None


def issue_intent(title: str) -> str | None:
    t = (title or "").strip().lower()
    if t.startswith("[read]"):
        return "add"
    if t.startswith("[r]") and not t.startswith("[read]"):
        return "add"
    if t.startswith("[done]"):
        return "done"
    if t.startswith("[d]") and not t.startswith("[done]"):
        return "done"
    return None


def issue_body_to_additions(title: str, body: str) -> list[tuple[str, str | None]]:
    items: list[tuple[str, str | None]] = []
    text = body or ""
    for line in text.splitlines():
        p = parse_issue_body_line(line)
        if p:
            items.append(p)
    blob = f"{title or ''}\n{text}"
    seen = {queue_key(u) for u, _ in items}
    for u in extract_urls_loose(blob):
        k = queue_key(u)
        if k not in seen:
            items.append((u, None))
            seen.add(k)
    return items


def issue_urls_for_done(title: str, body: str) -> list[str]:
    return [u for u, _ in issue_body_to_additions(title, body)]


def read_queue(path: Path) -> list[tuple[str, str | None]]:
    if not path.exists():
        return []
    out: list[tuple[str, str | None]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        p = parse_line(line)
        if p:
            out.append(p)
    return out


def write_queue(items: list[tuple[str, str | None]]) -> None:
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{url} | {title}" if title else url for url, title in items]
    QUEUE.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def read_done(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def write_done(lines: list[str]) -> None:
    DONE.parent.mkdir(parents=True, exist_ok=True)
    DONE.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def normalize_url(url: str) -> str:
    return url.strip().rstrip("/")


def queue_key(url: str) -> str:
    return normalize_url(url).lower()


def merge_into_queue(
    existing: list[tuple[str, str | None]],
    additions: list[tuple[str, str | None]],
) -> list[tuple[str, str | None]]:
    by_key: dict[str, tuple[str, str | None]] = {}
    for url, title in existing:
        by_key[queue_key(url)] = (normalize_url(url), title)
    for url, title in additions:
        k = queue_key(url)
        nu = normalize_url(url)
        if k in by_key:
            old_u, old_t = by_key[k]
            by_key[k] = (old_u, title or old_t)
        else:
            by_key[k] = (nu, title)
    return list(by_key.values())


def move_urls_from_queue(
    queue: list[tuple[str, str | None]],
    urls_to_done: list[str],
    done_lines: list[str],
) -> tuple[list[tuple[str, str | None]], list[str], int]:
    keys_remove = {queue_key(u) for u in urls_to_done if u.strip()}
    if not keys_remove:
        return queue, done_lines, 0

    new_queue: list[tuple[str, str | None]] = []
    moved = 0
    for url, title in queue:
        if queue_key(url) in keys_remove:
            label = title or url
            done_lines.append(f"{date.today().isoformat()} | {url} | {label}")
            moved += 1
        else:
            new_queue.append((url, title))
    return new_queue, done_lines, moved


def render_readme(queue: list[tuple[str, str | None]], done_lines: list[str]) -> str:
    to_read = [f"- [{title or url}]({url})" for url, title in queue]

    done_section: list[str] = []
    for ln in reversed(done_lines[-50:]):
        done_section.append(f"- {ln}")
    done_section.reverse()

    body = [
        "# personal-good-reads",
        "",
        "Use **Issues** (no edits to this repo). Shorthand: `[r]` = add, `[d]` = done.",
        "",
        "<details>",
        "<summary><strong>How to use</strong></summary>",
        "",
        "## Add",
        "",
        "1. New issue → title starts with **`[read]`**",
        "2. Paste links in the description (one per line; optional `url | title`)",
        "3. Submit — list updates here; issue auto-closes",
        "",
        "## Mark done",
        "",
        "1. New issue → title starts with **`[done]`**",
        "2. Paste the same URL(s) as in **To read**",
        "3. Submit — they go under **Done (recent)**; issue auto-closes",
        "",
        "<details>",
        "<summary><strong>Example walkthrough</strong></summary>",
        "",
        "**Add two links**",
        "",
        "1. Repo → **Issues** → **New issue**.",
        "2. **Title:** `[read] Weekend` (must start with `[read]`).",
        "3. **Description:** paste one URL per line, for example:",
        "",
        "```",
        "https://example.com/article-one | Great post",
        "https://example.org/guide",
        "```",
        "",
        "4. **Submit** (Create). GitHub Actions runs; this README’s **To read** gains those links; the issue closes with a bot comment.",
        "",
        "**Mark one as read**",
        "",
        "1. **Issues** → **New issue** again.",
        "2. **Title:** `[done] Read article-one` (must start with `[done]`).",
        "3. **Description:** paste the **exact** URL you finished, e.g. `https://example.com/article-one` (copy from **To read** above).",
        "4. **Submit**. Actions removes it from **To read** and appends a line under **Done (recent)**; the issue closes.",
        "",
        "</details>",
        "",
        "<details>",
        "<summary><strong>If nothing updates</strong></summary>",
        "",
        "- Open **Actions** → **Good reads** and check the latest run (errors show there).",
        "- This workflow file must be on your **default branch** (`main` / `master`) and **Actions** must be enabled.",
        "- On **GitHub**, open the repo root on the default branch and refresh; **locally**, run `git pull` — the bot commits there, not on your machine.",
        "- After fixing the workflow, open a **new** `[read]` issue (or re-run the failed workflow if GitHub offers it).",
        "",
        "</details>",
        "",
        "</details>",
        "",
        "## To read",
        "",
    ]
    if to_read:
        body.extend(to_read)
    else:
        body.append("_Empty — add with a `[read]` issue._")
    body.extend(["", "## Done (recent)", ""])
    if done_section:
        body.extend(done_section)
    else:
        body.append("_No completed items yet._")
    body.append("")
    return "\n".join(body)


def read_issue_from_github_event() -> tuple[str, str] | None:
    """Use the webhook JSON on the runner (always multiline-safe)."""
    if os.environ.get("GITHUB_EVENT_NAME") != "issues":
        return None
    path = os.environ.get("GITHUB_EVENT_PATH")
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as e:
        print(f"Could not read GITHUB_EVENT_PATH: {e}", file=sys.stderr)
        return None
    issue = payload.get("issue")
    if not isinstance(issue, dict):
        return None
    title = issue.get("title")
    body = issue.get("body")
    if title is None:
        title = ""
    if body is None:
        body = ""
    if not isinstance(title, str):
        title = str(title)
    if not isinstance(body, str):
        body = str(body)
    return (title, body)


def lines_from_env(name: str) -> list[tuple[str, str | None]]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return []
    found: list[tuple[str, str | None]] = []
    for line in raw.splitlines():
        p = parse_line(line)
        if p:
            found.append(p)
    return found


def main() -> None:
    queue = read_queue(QUEUE)
    done_lines = read_done(DONE)

    issue_from_event = read_issue_from_github_event()
    if issue_from_event is not None:
        from_issue = True
        title, body = issue_from_event
    elif os.environ.get("GOOD_READS_FROM_ISSUE", "").lower() in ("1", "true", "yes"):
        from_issue = True
        title = os.environ.get("GOOD_READS_ISSUE_TITLE") or ""
        body = os.environ.get("GOOD_READS_ISSUE_BODY") or ""
    else:
        from_issue = False
        title = ""
        body = ""

    additions: list[tuple[str, str | None]] = []
    mark_urls: list[str] = []
    intent: str | None = None

    if from_issue:
        intent = issue_intent(title)
        if intent is None:
            print("Issue title does not start with [read]/[r] or [done]/[d]; skipping.", file=sys.stderr)
            sys.exit(0)
        if intent == "add":
            additions.extend(issue_body_to_additions(title, body))
            if not additions:
                print("No URLs found in issue. Add http(s) links in the body or title.", file=sys.stderr)
                sys.exit(2)
        else:
            mark_urls.extend(issue_urls_for_done(title, body))
            if not mark_urls:
                print("No URLs found to mark done.", file=sys.stderr)
                sys.exit(2)
    else:
        additions.extend(lines_from_env("GOOD_READS_ADD"))
        mark_urls.extend(u for u, _ in lines_from_env("GOOD_READS_MARK"))

    if additions:
        queue = merge_into_queue(queue, additions)
    if mark_urls:
        queue, done_lines, moved = move_urls_from_queue(queue, mark_urls, done_lines)
        if moved == 0 and from_issue and intent == "done":
            print("None of those URLs were in the queue.", file=sys.stderr)
            sys.exit(2)

    write_queue(queue)
    write_done(done_lines)
    README.write_text(render_readme(queue, done_lines), encoding="utf-8")


if __name__ == "__main__":
    main()
