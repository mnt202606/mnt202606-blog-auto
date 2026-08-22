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

const HISTORY_FILE = path.join(__dirname, 'rank_history.json');
const KEYWORDS_FILE = path.join(__dirname, 'keywords.json');
const PUBLISHED_FILE = path.join(__dirname, 'published_posts.json');
const MOBILE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1';

// Given a Playwright page already open, look up where logNo appears among
// blog-post results for `keyword`. Returns 1-based rank, or null if it
// isn't in the top 30 results returned by this search page.
async function lookupRank(page, keyword, logNo) {
  await page.goto(
    `https://m.search.naver.com/search.naver?ssc=tab.m_blog.all&query=${encodeURIComponent(keyword)}`,
    { waitUntil: 'domcontentloaded', timeout: 30000 }
  );
  await page.waitForTimeout(1500);

  const hrefs = await page.$$eval('a[href]', (as) => as.map((a) => a.href || ''));
  const logNos = [];
  for (const href of hrefs) {
    const m = href.match(/blog\.naver\.com\/[^/]+\/(\d{6,})/);
    if (m && !logNos.includes(m[1])) logNos.push(m[1]);
  }
  const idx = logNos.indexOf(String(logNo));
  return idx === -1 ? null : idx + 1;
}

async function checkAllRanks() {
  if (!fs.existsSync(KEYWORDS_FILE) || !fs.existsSync(PUBLISHED_FILE)) {
    throw new Error('keywords.json or published_posts.json missing - run scan_published.js and extract_keywords.js first');
  }
  const keywords = JSON.parse(fs.readFileSync(KEYWORDS_FILE, 'utf-8'));
  const published = JSON.parse(fs.readFileSync(PUBLISHED_FILE, 'utf-8'));
  const history = fs.existsSync(HISTORY_FILE) ? JSON.parse(fs.readFileSync(HISTORY_FILE, 'utf-8')) : {};

  const browser = await chromium.launch({
    headless: true,
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  });
  const context = await browser.newContext({ viewport: { width: 420, height: 900 }, userAgent: MOBILE_UA });
  const page = await context.newPage();

  const today = todayKST();
  history[today] = history[today] || {};

  for (const [keyword, info] of Object.entries(keywords)) {
    const post = published[info.topic];
    if (!post) continue; // topic no longer matched to a live post
    try {
      const rank = await lookupRank(page, keyword, post.logNo);
      history[today][keyword] = { rank };
      console.log(`${keyword}: ${rank === null ? '권외' : rank + '위'}`);
    } catch (e) {
      console.log(`${keyword}: FAIL (${e.message.slice(0, 60)})`);
    }
    await page.waitForTimeout(1200); // be polite to Naver between queries
  }

  await browser.close();
  fs.writeFileSync(HISTORY_FILE, JSON.stringify(history, null, 2), 'utf-8');

  // Drop detection: compare today vs the most recent earlier date that has
  // a recorded rank for that keyword. Only a move between two *ranked*
  // positions (better number -> worse number) counts as a drop worth
  // diagnosing - per spec, a drop to 권외 (today's rank is null) is recorded
  // in history for tracking but excluded here, since there is no current
  // rank of ours to diagnose against (nothing to compare our content to).
  const priorDates = Object.keys(history).filter((d) => d !== today).sort();
  const drops = [];
  for (const [keyword, todayEntry] of Object.entries(history[today])) {
    let priorRank = null;
    for (let i = priorDates.length - 1; i >= 0; i -= 1) {
      const entry = history[priorDates[i]][keyword];
      if (entry) { priorRank = entry.rank; break; }
    }
    if (priorRank === null) continue; // no prior data, nothing to compare
    if (!keywords[keyword]) continue; // keyword pruned from keywords.json since being recorded
    const todayRank = todayEntry.rank;
    const gotWorse = todayRank !== null && todayRank > priorRank;
    if (gotWorse) {
      drops.push({ keyword, topic: keywords[keyword].topic, from: priorRank, to: todayRank });
    }
  }
  return drops;
}

module.exports = { lookupRank, checkAllRanks };

if (require.main === module) {
  checkAllRanks()
    .then((drops) => {
      console.log(`\nDONE: ${drops.length} drop(s) detected`);
      console.log(JSON.stringify(drops, null, 2));
    })
    .catch((e) => { console.error('FAIL:', e.message); process.exit(1); });
}
