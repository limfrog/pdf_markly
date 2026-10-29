"""Browser regressions: python3 -m unittest discover -s tests -v.

Requires Python Playwright and Chromium (CHROMIUM_PATH overrides discovery).
PDF integration checks use the application's actual CDN libraries and worker.
"""
import functools
import http.server
import json
import os
from pathlib import Path
import shutil
import threading
import unittest

from playwright.sync_api import sync_playwright


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = functools.partial(QuietHandler, directory=str(Path(__file__).resolve().parents[1]))
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/'
        cls.pw = sync_playwright().start()
        options = {'headless': True, 'args': ['--no-sandbox']}
        binary = os.environ.get('CHROMIUM_PATH') or shutil.which('chromium') or shutil.which('google-chrome')
        if binary:
            options['executable_path'] = binary
        if os.environ.get('HTTPS_PROXY'):
            options['proxy'] = {'server': os.environ['HTTPS_PROXY'], 'bypass': 'localhost,127.0.0.1'}
        cls.browser = cls.pw.chromium.launch(**options)
        cls.verified_fetch = os.environ.get('PDF_MARKLY_VERIFIED_FETCH') == '1'
        # Some managed machines configure the proxy CA for Node, but not Chromium.
        # Opt in to fetching real CDN responses via Playwright's TLS-verifying
        # API client. Never change browser trust or ignore certificate errors.
        cls.api = cls.pw.request.new_context(proxy=options.get('proxy'), ignore_https_errors=False)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.api.dispose()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width': 1440, 'height': 1000}, accept_downloads=True,
                                              service_workers='block' if self.verified_fetch else 'allow')
        self.addCleanup(self.context.close)
        if self.verified_fetch:
            self.context.route('https://cdnjs.cloudflare.com/**',
                               lambda route: route.fulfill(response=self.api.get(route.request.url)))
        self.page = self.context.new_page()
        self.errors = []
        self.alerts = []
        self.accept_confirm = False
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        def handle_dialog(dialog):
            if dialog.type == 'alert':
                self.alerts.append(dialog.message)
            if dialog.type == 'confirm' and self.accept_confirm:
                dialog.accept()
            else:
                dialog.dismiss()
        self.page.on('dialog', handle_dialog)
        self.page.goto(self.url, wait_until='domcontentloaded')
        self.page.wait_for_function('() => pages.length === 1')

    def tearDown(self):
        self.assertEqual(self.errors, [], 'Uncaught application errors')
        self.assertEqual(self.alerts, [], 'Unexpected application alerts')

    def draw_rectangle(self):
        p = self.page
        p.get_by_role('button', name='그리기', exact=True).click()
        p.locator('#tool-rect').click()
        box = p.locator('#hitCanvas').bounding_box()
        p.mouse.move(box['x'] + 70, box['y'] + 70)
        p.mouse.down()
        p.mouse.move(box['x'] + 170, box['y'] + 140, steps=5)
        p.mouse.up()
        p.wait_for_function('() => page().objs.length === 1')
        p.get_by_role('button', name='파일', exact=True).click()

    def save(self, expression):
        with self.page.expect_download(timeout=45000) as event:
            call = expression.rsplit(';', 1)[-1]
            if call in ('savePMF()', 'savePNG()'):
                setup = expression[:-len(call)]
                if setup:
                    self.page.evaluate(setup)
                self.page.locator(f'button[onclick="{call}"]').click()
            else:
                self.page.evaluate(expression)
        download = event.value
        self.assertIsNone(download.failure())
        self.page.evaluate('() => recentFilesWrites')
        return download

    def recent_names(self):
        self.page.evaluate('openRecentFiles()')
        self.page.wait_for_function('() => !document.getElementById("recentFilesStatus").textContent.includes("불러오는 중")')
        return self.page.locator('.recent-file-name').all_text_contents()

    def test_space_pan_and_keyboard_cleanup(self):
        p = self.page
        self.draw_rectangle()
        p.evaluate('setZoom(2); canvasArea.scrollLeft=200; canvasArea.scrollTop=200')
        before = p.evaluate('({left:canvasArea.scrollLeft,top:canvasArea.scrollTop,objs:JSON.stringify(page().objs),history:page().undoSt.length,tool})')
        # A toolbar button retains focus: Space must not click it or scroll.
        p.locator('button[onclick="addBlankPage()"]').focus()
        p.keyboard.down('Space')
        p.keyboard.down('Space')  # repeated keydown
        self.assertEqual(p.evaluate('[canvasArea.scrollLeft,canvasArea.scrollTop]'), [200, 200])
        self.assertEqual(p.evaluate('getComputedStyle(HC).cursor'), 'grab')
        p.mouse.move(650, 420)
        p.mouse.down()
        self.assertEqual(p.evaluate('getComputedStyle(HC).cursor'), 'grabbing')
        p.mouse.move(540, 330, steps=6)
        self.assertEqual(p.evaluate('[canvasArea.scrollLeft,canvasArea.scrollTop]'), [310, 290])
        p.mouse.up()
        p.keyboard.up('Space')
        self.assertEqual(p.evaluate('pages.length'), 1)
        self.assertFalse(p.evaluate('canvasArea.classList.contains("space-pan")'))
        self.assertEqual(p.evaluate('JSON.stringify(page().objs)'), before['objs'])
        self.assertEqual(p.evaluate('page().undoSt.length'), before['history'])
        self.assertEqual(p.evaluate('tool'), before['tool'])
        p.keyboard.down('Space')
        p.mouse.move(650, 420)
        p.mouse.down()
        p.keyboard.up('Space')  # release the modifier before the mouse
        p.mouse.up()
        self.assertFalse(p.evaluate('canvasArea.classList.contains("panning")'))
        p.keyboard.down('Space')
        p.evaluate('window.dispatchEvent(new Event("blur"))')
        self.assertFalse(p.evaluate('canvasArea.classList.contains("space-pan")'))
        p.keyboard.up('Space')
        # Native space remains available inside text editing.
        p.evaluate('setZoom(1); canvasArea.scrollLeft=0;canvasArea.scrollTop=0;openTed(60,60)')
        p.wait_for_function('() => document.activeElement === actTed')
        p.keyboard.type('a b')
        self.assertEqual(p.locator('[contenteditable="true"]').inner_text(), 'a b')
        self.assertFalse(p.evaluate('canvasArea.classList.contains("space-pan")'))
        p.keyboard.press('Escape')
        p.get_by_role('button', name='보기', exact=True).click()
        p.locator('#pdfContentScaleInput').evaluate('(el) => { el.disabled=false;el.focus(); }')
        p.keyboard.press('Space')
        self.assertFalse(p.evaluate('canvasArea.classList.contains("space-pan")'))
        # The entire scaled page remains reachable at both extremes.
        for zoom in (0.5, 1, 2, 4):
            metrics = p.evaluate('z => {setZoom(z);canvasArea.scrollLeft=0;canvasArea.scrollTop=0; const a=canvasArea.getBoundingClientRect(),c=HC.getBoundingClientRect();canvasArea.scrollLeft=1e6;canvasArea.scrollTop=1e6;const end=HC.getBoundingClientRect();return {left:c.left-a.left,top:c.top-a.top,right:end.right-a.right,bottom:end.bottom-a.bottom,width:c.width};}', zoom)
            self.assertGreaterEqual(metrics['left'], 0)
            self.assertGreaterEqual(metrics['top'], 0)
            self.assertLessEqual(metrics['right'], 0)
            self.assertLessEqual(metrics['bottom'], 0)
            self.assertEqual(metrics['width'], 794 * zoom)

    def test_recent_limit_deduplication_and_pmf_reopen_after_reload(self):
        self.assertEqual(self.recent_names(), [])
        self.page.keyboard.press('Escape')
        self.draw_rectangle()
        for i in range(11):
            if i == 6:
                # A second tab also verifies that history is shared by this
                # browser, without triggering Chromium's rapid-download limit.
                self.page = self.context.new_page()
                self.page.on('pageerror', lambda error: self.errors.append(str(error)))
                self.page.goto(self.url, wait_until='domcontentloaded')
                self.page.wait_for_function('() => pages.length === 1')
                self.draw_rectangle()
            saved = self.save(f'curFile="score-{i:02}.pmf";page().objs[0].x1={i+20};savePMF()')
            self.assertEqual(json.loads(Path(saved.path()).read_text())['pages'][0]['objs'][0]['x1'], i+20)
        self.assertEqual(self.recent_names(), [f'score-{i:02}.pmf' for i in range(10, 0, -1)])
        self.page.keyboard.press('Delete')
        self.assertEqual(self.page.evaluate('page().objs.length'), 1, 'Recent-file dialog must shield canvas shortcuts')
        self.page.keyboard.press('Escape')
        self.save('curFile="score-05.pmf";page().objs[0].x1=125;savePMF()')
        self.page.reload(wait_until='domcontentloaded')
        names = self.recent_names()
        self.assertEqual(len(names), 10)
        self.assertEqual(names[0], 'score-05.pmf')
        self.assertEqual(names.count('score-05.pmf'), 1)
        self.page.locator('.recent-file-open').first.click()
        self.page.wait_for_function('() => page().objs.length === 1 && page().objs[0].x1 === 125')
        self.assertFalse(self.page.evaluate('isDirty'))

    def test_png_reopen_unsaved_confirmation_and_clear(self):
        p = self.page
        self.draw_rectangle()
        image = self.save('curFile="drawing.pmf";savePNG()')
        self.assertEqual(Path(image.path()).read_bytes()[:8], b'\x89PNG\r\n\x1a\n')
        p.evaluate('addBlankPage()')
        self.assertEqual(self.recent_names(), ['drawing_1.png'])
        p.locator('.recent-file-open').click()
        p.locator('#saveConfirmOverlay button[onclick="hideSaveConfirm()"]' ).click()
        self.assertEqual(p.evaluate('pages.length'), 2)
        self.recent_names()
        p.locator('.recent-file-open').click()
        p.locator('#scNoSaveBtn').click()
        p.wait_for_function('() => pages.length === 1 && page().bgImg !== null')
        self.assertEqual(p.evaluate('[page().bgImg.naturalWidth,page().bgImg.naturalHeight]'), [794, 1123])
        self.assertEqual(p.evaluate('page().objs.length'), 0)
        self.recent_names()
        self.accept_confirm = True
        p.locator('#clearRecentFilesBtn').click()
        p.wait_for_function('() => document.getElementById("recentFilesStatus").textContent.includes("아직 저장한")')
        p.reload(wait_until='domcontentloaded')
        self.assertEqual(self.recent_names(), [])

    def test_storage_denial_does_not_break_download(self):
        p = self.page
        p.add_init_script("Object.defineProperty(window,'indexedDB',{get(){throw new DOMException('Storage denied','SecurityError');}})")
        p.reload(wait_until='domcontentloaded')
        self.save('savePMF()')
        self.assertEqual(self.recent_names(), [])
        self.assertIn('사용할 수 없습니다', p.locator('#recentFilesStatus').inner_text())

    def test_recent_open_waits_for_pdf_save(self):
        p = self.page
        self.save('curFile="saved.pmf";savePMF()')
        p.evaluate('addBlankPage()')
        self.recent_names()
        p.locator('.recent-file-open').click()
        pending = []
        p.route('**/jspdf.umd.min.js', lambda route: pending.append(route))
        with p.expect_request('**/jspdf.umd.min.js'):
            p.locator('button[onclick="scSaveImg()"]').click()
        # Hold the real CDN request beyond the old 100 ms navigation timer.
        p.wait_for_timeout(250)
        self.assertEqual(p.evaluate('pages.length'), 2)
        self.assertTrue(p.evaluate('isDirty'))
        self.assertEqual(len(pending), 1)
        with p.expect_download(timeout=45000) as event:
            pending[0].fallback()
        data = Path(event.value.path()).read_bytes()
        p.wait_for_function('() => pages.length === 1 && !isDirty && document.getElementById("loadingModal").classList.contains("hidden")')
        count = p.evaluate('async bytes => {await loadPdfLib();return (await PDFLib.PDFDocument.load(new Uint8Array(bytes))).getPageCount();}', list(data))
        self.assertEqual(count, 2, 'Save must finish with the outgoing document before reopening the recent file')

    def test_pdf_exports_are_recorded_and_can_be_reopened(self):
        p = self.page
        self.draw_rectangle()
        # Exercise the real jsPDF fallback used for documents without a source PDF.
        raster = self.save('curFile="raster.pmf";savePDF()')
        self.assertTrue(Path(raster.path()).read_bytes().startswith(b'%PDF-'))
        # Reopen the saved result through the menu (including the PDF.js worker).
        self.assertEqual(self.recent_names(), ['raster.pdf'])
        p.locator('.recent-file-open').click()
        p.wait_for_function('() => page()?.srcPdfPage === 0 && document.getElementById("loadingModal").classList.contains("hidden")', timeout=45000)
        self.assertEqual(p.evaluate('pages.length'), 1)
        self.assertEqual(p.evaluate('[page().bgImg.width>0,Object.keys(origPdfStore).length]'), [True, 1])
        p.evaluate('curFile="source.pdf"')
        for expression, name in [('savePDF()', 'source.pdf'), ('savePDFCompressed(0.5,0.7)', 'source_compressed.pdf'), ('saveStandardAnnotatedPDF()', 'source_annotated.pdf')]:
            saved = self.save(expression)
            content = Path(saved.path()).read_bytes()
            self.assertTrue(content.startswith(b'%PDF-'), name)
            # Parse the actual downloaded bytes using a second PDF implementation.
            count = p.evaluate('async bytes => {await loadPdfLib();return (await PDFLib.PDFDocument.load(new Uint8Array(bytes))).getPageCount();}', list(content))
            self.assertEqual(count, 1, name)
        self.assertEqual(self.recent_names(), ['source_annotated.pdf', 'source_compressed.pdf', 'source.pdf', 'raster.pdf'])


if __name__ == '__main__':
    unittest.main()
