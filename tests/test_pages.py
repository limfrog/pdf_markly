"""Page-list integration checks using native browser drag-and-drop and keyboard input."""
import json
from pathlib import Path

import test_browser


class PageTests(test_browser.BrowserHarness):
    def drag_page(self, source, target, *, after=False):
        thumbs = self.page.locator('.page-thumb-item')
        destination = thumbs.nth(target)
        destination.scroll_into_view_if_needed()
        height = destination.bounding_box()['height']
        thumbs.nth(source).drag_to(destination, source_position={'x': 40, 'y': 40},
                                   target_position={'x': 40, 'y': height - 5 if after else 5})

    def load_three_page_pdf(self):
        data = self.page.evaluate('''async () => {
            await loadPdfLib();const doc=await PDFLib.PDFDocument.create();
            for(let i=1;i<=3;i++)doc.addPage([300,400]).drawText('Original page '+i,{x:20,y:300,size:18});
            return Array.from(await doc.save());
        }''')
        self.page.locator('#pdfInput').set_input_files(
            {'name': 'three-pages.pdf', 'mimeType': 'application/pdf', 'buffer': bytes(data)})
        self.page.wait_for_function('() => pages.length === 3 && document.getElementById("loadingModal").classList.contains("hidden")', timeout=45000)

    def test_native_page_reorder_preserves_content_and_export_order(self):
        p = self.page
        self.load_three_page_pdf()
        p.evaluate('addCanvasLayer()')
        self.draw_rectangle()
        p.evaluate('''() => {
            toggleLayerVisible(activeLayer().id);toggleLayerLock(activeLayer().id);
            window.originalPages=[...pages];window.originalSnapshots=pages.map(pg=>JSON.stringify(pg));
            window.originalSources=JSON.stringify(Object.fromEntries(Object.entries(origPdfStore).map(([id,bytes])=>[id,u8ToB64(bytes)])));
        }''')
        self.drag_page(0, 2, after=True)
        self.assertEqual(p.evaluate('pages.map(pg=>pg.srcPdfPage)'), [1, 2, 0])
        self.assertEqual(p.evaluate('curPageIdx'), 2)
        self.assertTrue(p.evaluate('page() === originalPages[0]'))
        self.assertTrue(p.evaluate('originalSnapshots.every((snap,i)=>snap===JSON.stringify(originalPages[i]))'))
        self.assertTrue(p.evaluate('originalSources === JSON.stringify(Object.fromEntries(Object.entries(origPdfStore).map(([id,bytes])=>[id,u8ToB64(bytes)])))'))
        self.assertEqual(p.locator('.page-thumb-label').all_text_contents(), ['1페이지', '2페이지', '3페이지'])
        self.assertTrue(p.evaluate('isDirty'))
        pmf = self.save('curFile="reordered.pmf";savePMF()')
        pmf_path = str(pmf.path())
        project = json.loads(Path(pmf_path).read_text())
        self.assertEqual([pg['srcPdfPage'] for pg in project['pages']], [1, 2, 0])
        self.assertEqual(len(project['pages'][2]['objs']), 1)
        self.assertFalse(project['pages'][2]['layers'][1]['visible'])
        self.assertTrue(project['pages'][2]['layers'][1]['locked'])
        result = self.save('savePDF()')
        labels = p.evaluate('''async data => {
            const lib=await loadPDFjs(),doc=await lib.getDocument({data:new Uint8Array(data)}).promise;
            const labels=[];
            for(let i=1;i<=doc.numPages;i++)labels.push((await (await doc.getPage(i)).getTextContent()).items.map(t=>t.str).join(' '));
            await doc.destroy();return labels;
        }''', list(Path(result.path()).read_bytes()))
        self.assertEqual(labels, ['Original page 2', 'Original page 3', 'Original page 1'])
        # Move upward, then drop into the same gap: no duplicate or dirty change.
        self.drag_page(2, 0)
        self.assertEqual(p.evaluate('pages.map(pg=>pg.srcPdfPage)'), [0, 1, 2])
        self.save('savePMF()')
        self.drag_page(0, 0, after=True)
        self.assertFalse(p.evaluate('isDirty'))
        self.assertEqual(p.evaluate('pages.length'), 3)
        # Reopen the first PMF download and verify that the reordered source links survive.
        p.reload(wait_until='domcontentloaded')
        p.locator('#pmfInput').set_input_files(pmf_path)
        p.wait_for_function('() => pages.length === 3 && document.getElementById("loadingModal").classList.contains("hidden")')
        self.assertEqual(p.evaluate('pages.map(pg=>pg.srcPdfPage)'), [1, 2, 0])
        self.assertTrue(p.evaluate('pages.every(pg=>pg.bgImg.naturalWidth>0 && origPdfStore[pg.srcDocId].length>0)'))

    def test_delete_targets_focused_page_and_preserves_other_contexts(self):
        p = self.page
        for _ in range(2):
            p.locator('button[onclick="addBlankPage()"]').click()
        self.draw_rectangle()
        p.evaluate('window.originalPages=[...pages]')
        p.locator('.page-thumb-item').first.click()
        p.locator('.page-thumb-item').nth(1).focus()  # Keyboard focus may precede selection.
        p.keyboard.press('Delete')  # Cancel by default.
        self.assertEqual(p.evaluate('pages.length'), 3)
        self.assertEqual(self.confirmations, ['2페이지를 삭제할까요?'])
        p.locator('.page-thumb-item').nth(1).click()
        self.accept_confirm = True
        p.keyboard.press('Delete')
        self.assertTrue(p.evaluate('pages.length===2 && pages[0]===originalPages[0] && page()===originalPages[2]'))
        self.assertEqual(p.evaluate('curPageIdx'), 1)
        self.assertEqual(p.locator('#objList .layer-object-name').all_text_contents(), ['사각형'])
        self.assertTrue(p.evaluate('document.activeElement === document.querySelectorAll(".page-thumb-item")[1]'))
        p.evaluate('document.activeElement.dispatchEvent(new KeyboardEvent("keydown",{key:"Delete",repeat:true,bubbles:true,cancelable:true}))')
        self.assertEqual(len(self.confirmations), 2)
        # Canvas focus keeps Delete scoped to objects, even after clicking a thumbnail.
        p.evaluate('setTool("select2")')
        p.locator('#hitCanvas').click(position={'x': 70, 'y': 100})
        p.wait_for_function('() => selIds.length === 1')
        p.keyboard.press('Delete')
        self.assertEqual(p.evaluate('[pages.length,page().objs.length]'), [2, 0])
        self.assertEqual(len(self.confirmations), 2)
        # Text fields and modal dialogs do not delete a page in the background.
        p.get_by_role('button', name='그리기', exact=True).click()
        p.locator('#fontSizeInput').focus()
        p.keyboard.press('Delete')
        p.locator('.page-thumb-item').first.click()
        p.evaluate('openPrintModal()')
        p.keyboard.press('Delete')
        self.assertEqual(p.evaluate('pages.length'), 2)
        self.assertEqual(len(self.confirmations), 2)
        p.evaluate('closePrintModal()')
        p.locator('.page-thumb-item').first.click()
        p.keyboard.press('Delete')
        self.assertEqual(p.evaluate('pages.length'), 1)
        p.keyboard.press('Delete')
        self.assertEqual(p.evaluate('pages.length'), 1)
        self.assertEqual(self.alerts.pop(), '마지막 페이지는 삭제할 수 없습니다.')

    def test_drag_autoscroll_cancel_and_external_file_insertion(self):
        p = self.page
        p.evaluate('''() => {
            for(let i=0;i<11;i++)addBlankPage(false);
            goToPage(0);renderPageIndex();window.originalPages=[...pages];
        }''')
        source = p.locator('.page-thumb-item').first.bounding_box()
        bounds = p.locator('#pageIndexList').bounding_box()
        p.mouse.move(source['x'] + 40, source['y'] + 40)
        p.mouse.down()
        p.mouse.move(source['x'] + 50, source['y'] + 65, steps=4)
        p.mouse.move(bounds['x'] + 70, bounds['y'] + bounds['height'] - 10, steps=10)
        p.wait_for_function('() => document.getElementById("pageIndexList").scrollTop > 250')
        p.mouse.up()
        self.assertGreater(p.evaluate('pages.indexOf(originalPages[0])'), 0)
        self.assertEqual(p.evaluate('new Set(pages).size'), 12)
        self.assertTrue(p.evaluate('page() === originalPages[0]'))
        # Cancel a second native drag outside the list.
        p.evaluate('window.orderBeforeCancel=[...pages]')
        source = p.locator('.page-thumb-item.active')
        source.scroll_into_view_if_needed()
        rect = source.bounding_box()
        p.mouse.move(rect['x'] + 40, rect['y'] + 40)
        p.mouse.down()
        p.mouse.move(rect['x'] + 50, rect['y'] + 65, steps=4)
        p.mouse.move(400, 350, steps=8)
        p.keyboard.press('Escape')
        p.mouse.up()
        self.assertTrue(p.evaluate('orderBeforeCancel.every((pg,i)=>pages[i]===pg)'))
        self.assertTrue(p.evaluate('draggedPage===null && pageDragScrollFrame===0 && pageDropIndicator.style.display==="none"'))
        # Operating-system file drops still insert a new image page at the marked gap.
        p.evaluate('''() => {
            window.orderBeforeFile=[...pages];const list=document.getElementById('pageIndexList');list.scrollTop=0;
            const c=document.createElement('canvas');c.width=32;c.height=16;c.getContext('2d').fillRect(0,0,32,16);
            const data=dataUrlToUint8(c.toDataURL('image/png')),dt=new DataTransfer();
            dt.items.add(new File([data],'insert.png',{type:'image/png'}));
            const rect=list.querySelectorAll('.page-thumb-item')[1].getBoundingClientRect();
            for(const type of ['dragenter','dragover','drop'])list.dispatchEvent(new DragEvent(type,{dataTransfer:dt,clientX:rect.left+40,clientY:rect.top+3,bubbles:true,cancelable:true}));
        }''')
        p.wait_for_function('() => pages.length === 13')
        self.assertEqual(p.evaluate('[pages[1].bgImg.naturalWidth,pages[1].bgImg.naturalHeight]'), [32, 16])
        self.assertTrue(p.evaluate('[pages[0],...pages.slice(2)].every((pg,i)=>pg===orderBeforeFile[i])'))
        self.assertTrue(p.evaluate('pageDragScrollFrame===0 && pageDropIndicator.style.display==="none"'))
