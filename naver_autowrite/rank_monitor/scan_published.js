const { chromium } = require('playwright-core');
const path = require('path');
const fs = require('fs');

const BLOG_ID = 'mnt202606';
const AUTOWRITE_DIR = __dirname + '/..';
const OUT_FILE = path.join(__dirname, 'published_posts.json');

// Strip particles/hooking punctuation, split on whitespace, drop 1-char tokens.
// e.g. "지금 안 바꾸면 늦어요, 청약통장 갈아타면 국민·민영주택 둘 다 가능"
//   -> ["지금","바꾸면","늦어요","청약통장","갈아타면","국민","민영주택","가능"]
function tokenize(title) {
  return title
    .replace(/[,.!?()·⏰📈✅⚠️]/g, ' ')
    .split(/\s+/)
    .map((t) => t.trim())
    .filter((t) => t.length >= 2);
}

function overlapRatio(draftTokens, liveTokens) {
  const liveSet = new Set(liveTokens);
  const hits = draftTokens.filter((t) => liveSet.has(t)).length;
  return draftTokens.length === 0 ? 0 : hits / draftTokens.length;
}

async function fetchLivePosts() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  });
  const context = await browser.newContext({
    viewport: { width: 420, height: 900 },
    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
  });
  const page = await context.newPage();
  await page.goto(`https://m.blog.naver.com/${BLOG_ID}`, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(1500);

  const posts = await page.evaluate(() => {
    const out = [];
    // Tighten selector: only target post links with /PostView (specific to Naver posts)
    // Skip the overly broad 'a[href*="/"]' from original
    document.querySelectorAll('a[href*="/PostView"]').forEach((a) => {
      const href = a.getAttribute('href') || '';
      const m = href.match(/logNo=(\d+)/);
      if (!m) return;

      // Extract title from text_area child element, not from entire anchor
      let title = '';
      const textArea = a.querySelector('[class*="text_area"]');
      if (textArea) {
        title = (textArea.innerText || '').trim();
      }
      // Fallback to anchor text if text_area not found
      if (!title) {
        title = (a.innerText || '').trim();
      }

      // If title is implausibly long (over 120 chars), likely contains body text
      // Split on newline and take first line only (title is always first line on Naver)
      if (title.length > 120) {
        title = title.split('\n')[0].trim();
      }

      if (!title || title.length < 4) return;
      out.push({ title, logNo: m[1] });
    });
    return out;
  });

  await browser.close();
  // de-dupe by logNo, first title wins
  const seen = new Map();
  for (const p of posts) if (!seen.has(p.logNo)) seen.set(p.logNo, p);
  return [...seen.values()];
}

function loadDraftTitles() {
  const drafts = {};
  for (const file of fs.readdirSync(AUTOWRITE_DIR)) {
    if (!file.startsWith('content_') || !file.endsWith('.json')) continue;
    const topic = file.slice('content_'.length, -'.json'.length);
    try {
      const data = JSON.parse(fs.readFileSync(path.join(AUTOWRITE_DIR, file), 'utf-8'));
      if (data.title) drafts[topic] = data.title;
    } catch (e) {
      console.log(`skip ${file}: ${e.message}`);
    }
  }
  return drafts;
}

async function main() {
  const drafts = loadDraftTitles();
  const live = await fetchLivePosts();
  const existing = fs.existsSync(OUT_FILE) ? JSON.parse(fs.readFileSync(OUT_FILE, 'utf-8')) : {};

  for (const [topic, draftTitle] of Object.entries(drafts)) {
    if (existing[topic]) continue; // already matched previously, don't re-match
    const draftTokens = tokenize(draftTitle);
    let best = null;
    for (const p of live) {
      const ratio = overlapRatio(draftTokens, tokenize(p.title));
      if (ratio >= 0.6 && (!best || ratio > best.ratio)) best = { ...p, ratio };
    }
    if (best) {
      existing[topic] = {
        title: best.title,
        url: `https://blog.naver.com/${BLOG_ID}/${best.logNo}`,
        logNo: best.logNo,
      };
      console.log(`matched: ${topic} -> ${best.title} (${(best.ratio * 100).toFixed(0)}%)`);
    }
  }

  fs.writeFileSync(OUT_FILE, JSON.stringify(existing, null, 2), 'utf-8');
  console.log(`DONE: ${Object.keys(existing).length} published posts tracked`);
}

if (require.main === module) {
  main().catch((e) => { console.error('FAIL:', e.message); process.exit(1); });
}

module.exports = { tokenize, overlapRatio };
