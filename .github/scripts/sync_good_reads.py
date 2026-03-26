#!/usr/bin/env python3
"""
Rebuild README from queue/done and process ADD_HERE / MARK_DONE paste buffers.
Optional env: GOOD_READS_ADD, GOOD_READS_MARK (multiline) for workflow_dispatch.
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADD = ROOT / "ADD_HERE.md"
MARK = ROOT / "MARK_DONE.md"
QUEUE = ROOT / ".good-reads" / "queue.txt"
DONE = ROOT / ".good-reads" / "done.txt"
README = ROOT / "README.md"

ADD_TEMPLATE = """# Add good reads

Paste **one URL per line** below. Optional title after a pipe:

`https://example.com | Why this is worth it`

Commit this file on GitHub (web or desktop). A workflow appends lines to the queue and clears everything below the rule.

---

"""

MARK_TEMPLATE = """# Mark as read

Paste **full URLs** to remove from the queue (one per line). They must match a URL in the queue exactly.

Commit this file. A workflow moves each match to **Done** and clears everything below the rule.

---

"""


def parse_line(line: str) -> tuple[str, str | None] | None:
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    if "|" in s:
        url, title = s.split("|", 1)
        url, title = url.strip(), title.strip()
        return (url, title or None) if url else None
    return (s, None)


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
    lines = []
    for url, title in items:
        lines.append(f"{url} | {title}" if title else url)
    QUEUE.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def read_done(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def write_done(lines: list[str]) -> None:
    DONE.parent.mkdir(parents=True, exist_ok=True)
    DONE.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def parse_paste_file(path: Path, after_rule: bool) -> list[tuple[str, str | None]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if after_rule and "---" in text:
        _, rest = text.split("---", 1)
        text = rest
    found: list[tuple[str, str | None]] = []
    for line in text.splitlines():
        p = parse_line(line)
        if p:
            found.append(p)
    return found


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
    today = date.today().isoformat()
    keys_remove = {queue_key(u) for u in urls_to_done if u.strip()}
    if not keys_remove:
        return queue, done_lines, 0

    new_queue: list[tuple[str, str | None]] = []
    moved = 0
    for url, title in queue:
        if queue_key(url) in keys_remove:
            label = title or url
            done_lines.append(f"{today} | {url} | {label}")
            moved += 1
        else:
            new_queue.append((url, title))
    return new_queue, done_lines, moved


def render_readme(queue: list[tuple[str, str | None]], done_lines: list[str]) -> str:
    to_read = []
    for url, title in queue:
        display = title or url
        to_read.append(f"- [{display}]({url})")

    done_section = []
    for ln in reversed(done_lines[-50:]):
        done_section.append(f"- {ln}")
    done_section.reverse()

    body = [
        "# personal-good-reads",
        "",
        "Queue and done list are driven by GitHub Actions — no PR workflow required.",
        "",
        "## How to add",
        "",
        "1. Open [`ADD_HERE.md`](ADD_HERE.md) on GitHub.",
        "2. Paste URLs (one per line). Optional: `https://… | Title`.",
        "3. Commit. The workflow appends to the queue and clears the paste area.",
        "",
        "Or: **Actions → Good reads → Run workflow → add-read** and fill the form.",
        "",
        "## How to mark done",
        "",
        "1. Open [`MARK_DONE.md`](MARK_DONE.md).",
        "2. Paste the **exact** URL(s) you finished (one per line).",
        "3. Commit. Items move to **Done** below.",
        "",
        "Or: **Actions → Good reads → Run workflow → mark-done**.",
        "",
        "## To read",
        "",
    ]
    if to_read:
        body.extend(to_read)
    else:
        body.append("_Nothing queued. Add via ADD_HERE or the workflow._")
    body.extend(
        [
            "",
            "## Done (recent)",
            "",
        ]
    )
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

    additions = parse_paste_file(ADD, after_rule=True)
    additions.extend(lines_from_env("GOOD_READS_ADD"))
    if additions:
        queue = merge_into_queue(queue, additions)
    ADD.write_text(ADD_TEMPLATE, encoding="utf-8")

    mark_urls = [u for u, _ in parse_paste_file(MARK, after_rule=True)]
    mark_urls.extend(u for u, _ in lines_from_env("GOOD_READS_MARK"))
    if mark_urls:
        queue, done_lines, _ = move_urls_from_queue(queue, mark_urls, done_lines)
    MARK.write_text(MARK_TEMPLATE, encoding="utf-8")

    write_queue(queue)
    write_done(done_lines)
    README.write_text(render_readme(queue, done_lines), encoding="utf-8")


if __name__ == "__main__":
    main()
