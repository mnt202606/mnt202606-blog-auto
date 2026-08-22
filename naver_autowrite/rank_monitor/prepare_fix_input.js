const { chromium } = require('playwright-core');
const path = require('path');
const fs = require('fs');

// Returns today's date as YYYY-MM-DD in KST (UTC+9), not the system/UTC date -
// this project's daily routine runs around 8am KST, which is still "yesterday"
// in UTC, so a plain toISOString() would silently misdate every morning run.
function todayKST() {
  const kst = new Date(Date.now() + 9 * 60 * 60 * 1000);
  return kst.toISOString().slice(0, 10);
}

const PUBLISHED_FILE = path.join(__dirname, 'published_posts.json');
const FIXES_DIR = path.join(__dirname, 'fixes');
const MOBILE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1';

// Reads a public Naver mobile blog post page. `full=true` returns the whole
// body text; `full=false` returns just the first ~500 chars (enough to see
// how a competitor frames their intro without spending time on their whole post).
async function readPost(page, url, full) {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(1500);
  return page.evaluate((full) => {
    const titleEl = document.querySelector('.se-title-text, .pcol1, h3.tit_h3');
    const title = (titleEl ? titleEl.innerText : document.title).trim();
    const bodyEl = document.querySelector('.se-main-container, #viewTypeSelector, .post_ct');
    let body = bodyEl ? bodyEl.innerText : '';
    body = body.replace(/\n{3,}/g, '\n\n').trim();
    return { title, body: full ? body : body.slice(0, 500) };
  }, full);
}

// Given a mobile search results page already loaded for `keyword`, return
// the URLs of the top `n` blog-post results, in rank order.
async function topResultUrls(page, keyword, n) {
  await page.goto(
    `https://m.search.naver.com/search.naver?ssc=tab.m_blog.all&query=${encodeURIComponent(keyword)}`,
    { waitUntil: 'domcontentloaded', timeout: 30000 }
  );
  await page.waitForTimeout(1500);
  const hrefs = await page.$$eval('a[href]', (as) => as.map((a) => a.href || ''));
  const urls = [];
  for (const href of hrefs) {
    const m = href.match(/^https?:\/\/(?:m\.)?blog\.naver\.com\/[^/]+\/\d{6,}/);
    if (m && !urls.includes(m[0])) urls.push(m[0]);
    if (urls.length >= n) break;
  }
  return urls;
}

async function prepareFixInputs(drops) {
  if (drops.length === 0) return [];
  fs.mkdirSync(FIXES_DIR, { recursive: true });
  const published = JSON.parse(fs.readFileSync(PUBLISHED_FILE, 'utf-8'));
  const today = todayKST();

  const browser = await chromium.launch({
    headless: true,
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  });
  const context = await browser.newContext({ viewport: { width: 420, height: 900 }, userAgent: MOBILE_UA });
  const page = await context.newPage();

  const writtenFiles = [];
  try {
    for (const drop of drops) {
      try {
        const post = published[drop.topic];
        if (!post) continue;

        let mine;
        try {
          mine = await readPost(page, post.url, true);
        } catch (e) {
          console.log(`skipping ${drop.keyword}: failed to read own post (${e.message.slice(0, 60)})`);
          continue;
        }

        const rivalUrls = (await topResultUrls(page, drop.keyword, 4)).filter((u) => !u.includes(`/${post.logNo}`)).slice(0, 3);
        const rivals = [];
        for (const url of rivalUrls) {
          await page.waitForTimeout(1200);
          try {
            rivals.push({ url, ...(await readPost(page, url, false)) });
          } catch (e) {
            console.log(`  rival read failed (${url}): ${e.message.slice(0, 60)}`);
          }
        }

        const lines = [
          `# 순위 하락 진단 자료`,
          `키워드: "${drop.keyword}" (${drop.from}위 -> ${drop.to === null ? '권외' : drop.to + '위'})`,
          `내 글: ${post.url}`,
          ``,
          `## 내 글 전문`,
          `제목: ${mine.title}`,
          ``,
          mine.body,
          ``,
          `## 현재 상위 경쟁글`,
          ...rivals.map((r, i) => `\n### ${i + 1}위 후보: ${r.title}\n${r.url}\n${r.body}`),
        ];
        const outPath = path.join(FIXES_DIR, `input_${drop.keyword.replace(/\s+/g, '_')}_${today}.md`);
        fs.writeFileSync(outPath, lines.join('\n'), 'utf-8');
        console.log(`wrote ${outPath}`);
        writtenFiles.push(outPath);
      } catch (e) {
        console.log(`skipping ${drop.keyword}: unexpected error (${e.message.slice(0, 60)})`);
        continue;
      }
    }
  } finally {
    await browser.close();
  }
  return writtenFiles;
}

module.exports = { readPost, topResultUrls, prepareFixInputs };
