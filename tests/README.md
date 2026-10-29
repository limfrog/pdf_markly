# Browser regression checks

With Python Playwright and Chromium installed, run from the repository root:

```sh
python3 -m unittest discover -s tests -v
```

`CHROMIUM_PATH` can select another Chromium binary. Otherwise the runner uses
system Chromium/Chrome or Playwright's installed browser. Each test uses a fresh
browser context and a temporary local HTTP server. No document data is uploaded.

The suite covers Space-drag panning and cleanup, normal text input, zoom bounds,
recent-file persistence, the 10-file limit, duplicate names, PMF/PNG reopening,
unsaved-change confirmation, list deletion, unavailable browser storage, and
PDF import/export using the app's actual CDN libraries and PDF.js worker.
Page-list checks exercise native thumbnail dragging in both directions, no-op
drops, edge autoscroll, cancellation, external image insertion, and focused
Delete handling (confirmation, text/canvas/modal isolation, and last-page
protection). A three-page PDF verifies that page data, layers, source links,
PMF round trips, and exported PDF text retain the new order.

The shared clipboard codec has a separate dependency-free check:

```sh
node tests/clipboard.test.cjs
```

For a managed proxy whose CA is already configured for Node but not Chromium:

```sh
PDF_MARKLY_VERIFIED_FETCH=1 python3 -m unittest discover -s tests -v
```

This mode delivers actual CDN responses fetched by Playwright's API client with
TLS verification enabled and the existing proxy/CA configuration. It does not
change the browser's trust settings. Service Workers are blocked in this mode
so their requests cannot escape the test route; this suite does not test offline
Service Worker behavior. Real iOS sharing and printing still require device tests.
