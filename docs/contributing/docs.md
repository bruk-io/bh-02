# Building these docs

This site is built with [MkDocs](https://www.mkdocs.org/) from the repository itself. Most pages
include a README, the glossary or the contracts as they are, so those files stay the one source.

## Preview and build

From the repository's root, after `uv sync --all-packages`:

```sh
uv run mkdocs serve             # preview at http://127.0.0.1:8000, rebuilt as you edit
uv run mkdocs build --strict    # build into site/, failing on any warning
```

`site/` is git-ignored. `scripts/check` runs the strict build as its `docs` step, so a broken link
or a missing page fails the check.

## Where the pages come from

`mkdocs.yml` holds the navigation. The pages are under `docs/`, in three kinds:

- **Included.** A page that is one line, such as
  <code>&#123;% include-markdown "../../libs/cordis/README.md" %&#125;</code>, shows that file. Edit
  the file itself, not the page. Links in an included file are fixed up when the site is built: one
  to a file another page includes goes to that page, and one to any other file in the repository
  goes to the file on GitHub.
- **Generated.** The cordis API reference is built from the docstrings of `cordis`,
  `cordis.loader`, `cordis.composition` and `cordis.testing` by mkdocstrings. Edit the docstrings.
- **Written for the site.** Get started, Using it, How it works, Extending it, the command line
  reference and these Contributing pages. Each fact in them comes from the code, a README or a
  command's output; when one of those changes, change the page with it.

The `CLAUDE.md` files (instructions for coding agents) and `backlog/` are not part of the site.

To add a page, write it under `docs/` and add it to `nav` in `mkdocs.yml`.

## The look

The site is a bh-01 app, built from bh-01's own components: `<bh-app-shell>`, the activity bar of
sections, a sidebar panel with each section's pages as a tree, the status bar, and the command
palette for search (`Ctrl+K`). The theme is in `docs/theme/`:

| Path | What it is |
|---|---|
| `main.html` | the page template: the frame around each page |
| `assets/bh-docs.css` | the page's own styles, reading bh-01's semantic tokens only |
| `assets/bh-docs.js` | the frame's behaviour: sections, search, the theme toggle, copy buttons |
| `vendor/bh-01/` | a pinned build of bh-01 and its token CSS, vendored so the site builds and runs offline; `VENDOR.md` there says which build and how it was made |

`docs/hooks/bh_docs.py` is a MkDocs hook: it puts the branch and commit the site was built from in
the status bar, and fixes up the links in included files.

The site follows bh-01's rules: one mandarin mark in a view (the page you are on, in the sidebar),
status as a word and a colour, uppercase only for instrument labels such as the sidebar's header,
and no colour or size written by hand. It follows your system's light or dark setting until you
pick one with the status bar's toggle, which the browser remembers when it can.
