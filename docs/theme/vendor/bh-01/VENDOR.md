# bh-01, vendored

The documentation site's theme is built from bh-01's own web components. This directory is a
pinned build of the library, so the site builds and runs offline and the same way every time.
Nothing here is edited by hand.

| | |
|---|---|
| Package | `@bruk-io/bh-01` 0.0.1 (not published to npm) |
| Source | https://github.com/bruk-io/bh-01 |
| Commit | `73304968d1bdb9e04fad3b7881611cef2792832e` (`main`, 2026-02-26; the commit bh-01's spec, `tokens.json`, records as its ref) |
| Licence | MIT, as declared in the package's `package.json` (the repository has no LICENSE file) |
| Bundled in | `lit` 3.3.2, `lit-html` 3.3.2, `lit-element` 4.2.2, `@lit/reactive-element` 2.1.2 and `@lit/context` 1.1.6, all BSD-3-Clause (Google LLC); their licence notices are kept at the end of `bh-01.js` |

## Files

| File | What it is | sha256 |
|---|---|---|
| `bh-01.js` | the library's `dist/index.js` (every component) with lit, bundled into one ES module | `e75f053339919042d35acf528d7ad7c310c99a4ff0a5b5b661d277ce62eb90b4` |
| `tokens/*.css` | the package's `./tokens` export (`dist/tokens/`), unchanged | |
| `themes/default.css` | the package's `./theme` export (`dist/themes/default.css`), unchanged | `e51ccf0b9339437cd28d9815a6fa5244f8682f72b50bfd5a44ae1ce15fabf4e5` |

`tokens/typography.css` declares the DSEG14 segment font by a jsDelivr URL. A browser fetches it
only for text set in `--bh-font-seg`, which the site never uses, so it is not vendored.

## How it was built

Outside this repository, with Node 22:

```sh
git clone https://github.com/bruk-io/bh-01 && cd bh-01
git checkout 73304968d1bdb9e04fad3b7881611cef2792832e
npm ci --ignore-scripts
npm run build                        # vite build && tsc: dist/
node_modules/.bin/esbuild dist/index.js --bundle --format=esm --target=es2021 \
  --legal-comments=eof --banner:js="/* ...the provenance line at the top of bh-01.js... */" \
  --outfile=bh-01.js                 # esbuild 0.27.3, from the package's own lockfile
cp dist/tokens/*.css tokens/ && cp dist/themes/default.css themes/
```

The build is reproducible: the same commit and lockfile give the same `bh-01.js`, byte for byte.

To move to a newer bh-01, repeat this at the new commit, update this file, and look at the site in
both themes: the theme reads only bh-01's semantic tokens and components, so a change there shows
up here.

## Where this build differs from bh-01's spec

bh-01's spec (its `tokens.json` and component specs) has moved on since this commit, and lists the
library's known gaps itself. One difference shows on the site: the spec maps `color-link` and
`color-accent-secondary` to pine, while this build still maps them to sky, so links on the site
are sky blue. The site reads `--bh-color-link` and picks up pine with a build that has it.
