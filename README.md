# afung docs

Published at https://arthur-fung.github.io/afung-docs/ via GitHub Pages (built-in Jekyll, no build step).

## Adding a doc

- Name it `YYYYMMDD-slug.html` or `YYYYMMDD-slug.md` at the repo root. The index picks it up automatically, newest first.
- Markdown: no front matter needed; the first `# heading` becomes the title.
- HTML: prepend this so the index shows a real title and the page is served as-is:

  ```
  ---
  title: "Page title"
  layout: null
  ---
  ```

  HTML without it still appears in the index, titled from the filename.
