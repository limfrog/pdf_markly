# Horizon object clipboard v1

Easy Paint Pad 2.1.20 and PDF Markly 0.9.12 share `object-clipboard.js` (keep the files identical in both repositories). Select objects, copy, focus the other app's canvas, and paste. HTTPS or localhost and browser clipboard permission are required for cross-app keyboard/menu operations. Internal copying remains available if permission is denied. Native paste events also accept the format. Text editing uses normal text/rich-text clipboard behavior.

The system clipboard contains `text/plain` JSON:

```json
{"format":"horizon.objects","version":1,"source":"easy-paint-pad","units":"canvas-px","copiedAt":123456789,"objects":[]}
```

`objects` must be nonempty, ordered back to front. Types: `shape` (`line`, `rect`, `ellipse`, `arrow`, `staff`), `stroke`, `text`, `image`. Coordinates and font sizes use canvas pixels, independent of zoom. A group translates as a unit; the receiving app uses its active layer/page and generates new IDs. Layer IDs, original object IDs, and background-selection flags are not transferred. Imported images are ordinary selectable objects, including after project save/reopen.

- Shapes use `strokeColor`, `strokeWidth`, `alpha`, `fillColor`, absolute `fillAlpha`, `measureBars`, and `geometry.origin` to retain source arrow/staff conventions.
- Text uses `richLines` with per-run font family, size, color, bold, italic, underline, plus object line height and EPP-style box fields. Installed/loaded fonts and canvas font metrics can affect exact layout.
- Images use self-contained PNG/JPEG/WebP/GIF base64 `src`; remote URLs and executable image formats are rejected. All images load before a group is inserted; failure inserts no partial group.
- Strokes retain points, width, color, alpha, eraser/highlight flags. Highlight multiply rendering is supported by both apps. Eraser results depend on content beneath the stroke.

Unknown format versions/types and invalid coordinates are rejected. EPP continues reading its legacy `_eppClip` payload. PDF source-page content is not an object in this protocol; copy an image of that content if needed. EPP and PMF project formats remain app-specific. Standard annotated PDF export retains its existing approximation rules.

Verify the codec with `node tests/clipboard.test.cjs`. Browser verification should cover actual keyboard copy/paste in both directions, multiple mixed objects, order/relative positions, rich text, image loading failure, undo/redo, project save/reopen, and offline loading. Changes to the shared module require bumping each app's service-worker cache.
