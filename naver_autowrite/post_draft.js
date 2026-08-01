const { chromium } = require('playwright-core');
const path = require('path');
const fs = require('fs');

const BLOG_ID = process.argv[2] || 'mnt202606';
const CONTENT_FILE = process.argv[3];

if (!CONTENT_FILE) {
  console.error('Usage: node post_draft.js <blogId> <content.json>');
  process.exit(1);
}

const content = JSON.parse(fs.readFileSync(CONTENT_FILE, 'utf-8'));
// content = { title: "...", blocks: [ {type:"text", text:"..."}, {type:"image", path:"..."} ] }

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function typeHuman(page, text) {
  await page.keyboard.type(text, { delay: 45 + Math.random() * 35 });
}

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  });
  const context = await browser.newContext({
    storageState: path.join(__dirname, 'secrets', 'storage_state.json'),
    viewport: { width: 1400, height: 1000 },
  });
  const page = await context.newPage();

  await page.goto(`https://blog.naver.com/${BLOG_ID}/postwrite`, { waitUntil: 'networkidle' });
  await sleep(3000);

  // Defensive: handle "작성 중인 글이 있습니다" recovery popup if present.
  // Scope strictly to the confirm-popup container, and match EXACT text 취소
  // (never a substring match like 취소선, the toolbar strikethrough button).
  const popup = page.locator('.se-popup-alert-confirm');
  if (await popup.count() > 0 && await popup.first().isVisible().catch(() => false)) {
    console.log('recovery popup detected, clicking exact 취소 inside it');
    const cancelInPopup = popup.first().getByText('취소', { exact: true });
    await cancelInPopup.first().click({ timeout: 10000 });
    await sleep(1000);
  }

  // close help panel if present (top-right X, coordinate-based, harmless if absent)
  await page.mouse.click(1358, 42).catch(() => {});
  await sleep(500);

  // click title field and type
  await page.mouse.click(400, 249);
  await sleep(300);
  await typeHuman(page, content.title);
  await sleep(500);

  // click body field to start
  await page.mouse.click(400, 362);
  await sleep(300);

  for (const block of content.blocks) {
    if (block.type === 'text') {
      await typeHuman(page, block.text);
      await page.keyboard.press('Enter');
      await page.keyboard.press('Enter');
      await sleep(300);
    } else if (block.type === 'image') {
      const fileChooserPromise = page.waitForEvent('filechooser', { timeout: 8000 }).catch(() => null);
      await page.click('text=사진');
      const chooser = await fileChooserPromise;
      if (chooser) {
        await chooser.setFiles(path.resolve(block.path));
        await sleep(3500);
      } else {
        console.log('WARNING: file chooser did not appear for image', block.path);
      }
    }
  }

  await sleep(1000);
  await page.screenshot({ path: path.join(__dirname, 'out', 'before_save.png'), fullPage: true });

  // click 저장 (save draft) - NOT 발행 (publish)
  await page.getByText('저장', { exact: true }).first().click();
  await sleep(2500);

  await page.screenshot({ path: path.join(__dirname, 'out', 'after_save.png'), fullPage: true });

  console.log('DONE - saved as draft, did not publish. Review out/after_save.png and the recorded video.');

  await context.close();
  await browser.close();
})();
