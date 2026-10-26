#!/usr/bin/env python3
"""Copy YYYYMMDD-*.md / *.html docs from repos under ~/source into this repo.

Usage: collect_docs.py [--date YYYYMMDD] [--dry-run]

For each match it prints one line: NEW, UPDATED, SAME or CONFLICT, then the
source path. HTML files get Jekyll front matter (title from <title>, layout
null) so the index lists them with a real title and serves them unchanged.
Files containing Liquid syntax ({{ or {%) are wrapped in {% raw %} so Jekyll
doesn't mangle them. Exits 2 if two repos have a doc with the same name.
"""

import argparse
import datetime
import html
import re
import sys
from pathlib import Path

SOURCE_ROOT = Path.home() / "source"
REPO = Path(__file__).resolve().parents[4]
PRUNE = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    ".next", ".turbo", "Pods", ".gradle", "vendor", "site-packages", "_site",
}
MAX_DEPTH = 6


def find_docs(prefix):
    found = []
    for repo in sorted(SOURCE_ROOT.iterdir()):
        if not repo.is_dir() or repo.resolve() == REPO or repo.name.startswith("."):
            continue
        stack = [(repo, 1)]
        while stack:
            d, depth = stack.pop()
            try:
                entries = list(d.iterdir())
            except (PermissionError, OSError):
                continue
            for p in entries:
                if p.is_dir():
                    # Dot dirs hold worktree copies (.claude/worktrees) and tooling.
                    if (
                        p.name not in PRUNE
                        and not p.name.startswith(".")
                        and not p.is_symlink()
                        and depth < MAX_DEPTH
                    ):
                        stack.append((p, depth + 1))
                elif (
                    p.is_file()
                    and p.name.startswith(prefix + "-")
                    and p.suffix in (".md", ".html")
                ):
                    found.append(p)
    return sorted(found)


def html_title(text, name):
    for pattern in (r"<title[^>]*>(.*?)</title>", r"<h1[^>]*>(.*?)</h1>"):
        m = re.search(pattern, text, re.I | re.S)
        if m:
            title = html.unescape(re.sub(r"<[^>]+>|\s+", " ", m.group(1))).strip()
            if title:
                return title
    return name[9:].rsplit(".", 1)[0].replace("-", " ").replace("_", " ")


def prepare(src):
    text = src.read_text(encoding="utf-8")
    has_front_matter = text.startswith("---\n")
    body = text
    if re.search(r"\{\{|\{%", text) and "{% raw %}" not in text:
        if has_front_matter:
            end = text.index("\n---\n", 4) + 5
            body = text[:end] + "{% raw %}\n" + text[end:] + "\n{% endraw %}\n"
        else:
            body = "{% raw %}\n" + text + "\n{% endraw %}\n"
    if src.suffix == ".html" and not has_front_matter:
        title = html_title(text, src.name).replace("\\", "\\\\").replace('"', '\\"')
        body = f'---\ntitle: "{title}"\nlayout: null\n---\n' + body
    return body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().strftime("%Y%m%d"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not re.fullmatch(r"\d{8}", args.date):
        sys.exit("--date must be YYYYMMDD")

    docs = find_docs(args.date)
    by_name = {}
    for p in docs:
        by_name.setdefault(p.name, []).append(p)

    conflict = False
    for name, paths in sorted(by_name.items()):
        if len(paths) > 1:
            conflict = True
            for p in paths:
                print(f"CONFLICT\t{p}")
            continue
        src = paths[0]
        dest = REPO / name
        content = prepare(src)
        if not dest.exists():
            status = "NEW"
        elif dest.read_text(encoding="utf-8") == content:
            status = "SAME"
        else:
            status = "UPDATED"
        if status != "SAME" and not args.dry_run:
            dest.write_text(content, encoding="utf-8")
        print(f"{status}\t{src}")

    if not docs:
        print(f"NONE\tno {args.date}-*.md or *.html under {SOURCE_ROOT}")
    sys.exit(2 if conflict else 0)


if __name__ == "__main__":
    main()
