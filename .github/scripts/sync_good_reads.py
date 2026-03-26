#!/usr/bin/env python3
"""
Rebuild README from .good-reads/queue.txt and done.txt.

Triggers (via env):
- GOOD_READS_ADD / GOOD_READS_MARK: multiline (workflow_dispatch).
- GOOD_READS_ISSUE_MODE=add|done + GOOD_READS_ISSUE_TITLE + GOOD_READS_ISSUE_BODY: issue opened.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUEUE = ROOT / ".good-reads" / "queue.txt"
DONE = ROOT / ".good-reads" / "done.txt"
README = ROOT / "README.md"

URL_RE = re.compile(r"https?://[^\s\)\]<>\"']+", re.IGNORECASE)


def parse_line(line: str) -> tuple[str, str | None] | None:
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    if "|" in s:
        url, title = s.split("|", 1)
        url, title = url.strip(), title.strip()
        return (url, title or None) if url else None
    return (s, None)


def extract_urls(text: str) -> list[str]:
    if not text:
        return []
    raw = URL_RE.findall(text)
    out: list[str] = []
    seen: set[str] = set()
    for u in raw:
        u = u.rstrip(".,);]")
        k = u.lower()
        if k not in seen:
            seen.add(k)
            out.append(u)
    return out


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
        p = parse_line(line)
        if p:
            items.append(p)
    blob = f"{title or ''}\n{text}"
    seen = {queue_key(u) for u, _ in items}
    for u in extract_urls(blob):
        k = queue_key(u)
        if k not in seen:
            items.append((u, None))
            seen.add(k)
    return items


def issue_urls_for_done(title: str, body: str) -> list[str]:
    return extract_urls(f"{title or ''}\n{body or ''}")


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
    issue_mode = (os.environ.get("GOOD_READS_ISSUE_MODE") or "").strip().lower()

    additions: list[tuple[str, str | None]] = []
    mark_urls: list[str] = []

    if issue_mode in ("add", "done"):
        title = os.environ.get("GOOD_READS_ISSUE_TITLE") or ""
        body = os.environ.get("GOOD_READS_ISSUE_BODY") or ""
        intent = issue_intent(title)
        if intent is None:
            print("Issue title does not start with [read]/[r] or [done]/[d]; skipping.", file=sys.stderr)
            sys.exit(0)
        if intent != issue_mode:
            print("Issue intent does not match GOOD_READS_ISSUE_MODE; skipping.", file=sys.stderr)
            sys.exit(0)
        if issue_mode == "add":
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
        if moved == 0 and issue_mode == "done":
            print("None of those URLs were in the queue.", file=sys.stderr)
            sys.exit(2)

    write_queue(queue)
    write_done(done_lines)
    README.write_text(render_readme(queue, done_lines), encoding="utf-8")


if __name__ == "__main__":
    main()
