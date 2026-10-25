---
name: publish-docs
description: Publish today's docs to the afung-docs GitHub Pages site. Finds YYYYMMDD-*.md and *.html files with today's date (or a given date) in other repos under ~/source, copies them into this repo, prepares HTML for Jekyll, commits, pushes, and checks that the live index lists them. Use whenever the user asks to publish, sync, copy or pull in today's docs, reports or write-ups to the docs site / GitHub page / afung-docs, update the page or TOC with new docs, or says "/publish-docs" (optionally with a date).
---

# Publish docs to the GitHub Pages site

The site (https://arthur-fung.github.io/afung-docs/) is built by GitHub Pages' Jekyll. `index.md` generates the table of contents from every `YYYYMMDD-*` page, so the TOC needs no manual edit. Getting a doc onto the index only takes the file sitting at the repo root with a title. Docs are written in other repos (e.g. `~/source/scribe-mobile/docs/`, `~/source/normandy/docs/`) and this skill brings them over.

Run everything from the repo root, `/Users/arthur/source/afung-docs`.

## 1. Sync and preview

```bash
git pull --ff-only origin main
python3 .claude/skills/publish-docs/scripts/collect_docs.py --dry-run          # today
python3 .claude/skills/publish-docs/scripts/collect_docs.py --date 20261024 --dry-run   # another day
```

Each output line is `STATUS<TAB>source path`:
- `NEW`: not in this repo yet.
- `UPDATED`: already here, and the source has changed since. Copying overwrites this repo's version. If the repo copy has edits made here (check `git log -- <file>`), tell the user before overwriting.
- `SAME`: already published, nothing to do.
- `CONFLICT`: two repos have a doc with the same name. Stop and ask which one to publish.
- `NONE`: nothing dated that day. Tell the user and stop; don't guess another date.

## 2. Check before publishing

The repo and site are **public**, but these docs are usually internal. For each `NEW` / `UPDATED` file, skim it and grep for things that shouldn't be public: credentials (`token`, `secret`, `password`, `api_key`, `Bearer ey…`), patient data (names with DOB/MRN, clinical note text), personal emails other than the user's own, or customer data dumps. If anything turns up, show the user the matching lines and ask before going on. If it's clean, don't ask; the user asked to publish.

## 3. Copy

```bash
python3 .claude/skills/publish-docs/scripts/collect_docs.py [--date YYYYMMDD]
```

The script prepares the files for Jekyll:
- **HTML** gets a header with `title:` (taken from `<title>`, else the first `<h1>`, else the filename) and `layout: null`. The title is what the index shows, and `layout: null` serves the page exactly as written.
- **Markdown** needs nothing. Jekyll uses the first `# heading` as its title.
- Any file containing `{{` or `{%` is wrapped in `{% raw %}` so Jekyll's Liquid templating leaves it alone.

## 4. Commit and push

Stage only the doc files the script copied. Don't use `git add -A`: the working tree can hold unrelated files.

```bash
git add <file>...
git commit -m "Add docs for YYYY-MM-DD: <short names>" -m "Co-Authored-By: ..."   # use the attribution line from the system prompt
git push origin main
```

For a single file, a message like `Add LLM-20508 admin appointment rules API comparison` reads better. If the push is blocked or rejected, say so, leave the commit in place, and tell the user to run `! git push origin main`.

## 5. Verify the live page

```bash
bash .claude/skills/publish-docs/scripts/wait_for_pages.sh <file>...
```

This waits for the Pages build of `HEAD` (up to 8 minutes), then checks that the live index links each file and the page returns 200. If the build errors, show the message.

## 6. Report

For each published doc, give its title and live URL (`https://arthur-fung.github.io/afung-docs/<name>.html`, using `.html` for Markdown too), plus whether it was new or updated. Mention anything skipped (`SAME`, conflicts) and anything in the check that made you pause. Browsers can cache pages for up to 10 minutes, so a hard refresh may be needed.
