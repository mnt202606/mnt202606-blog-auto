# Naver Blog Rank-Drop Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect when a published mnt202606 Naver blog post's search rank drops for a tracked keyword, diagnose why against the current top-ranking competitors, and produce a paste-ready fix — without ever touching the live post automatically.

**Architecture:** Four small Node/Playwright scripts under `naver_autowrite/rank_monitor/`, each reading/writing plain JSON or Markdown files so they compose via the filesystem rather than direct calls. Three scripts (`scan_published.js`, `extract_keywords.js`, `check_ranks.js`) are pure data-gathering and need no Naver login — they only read public pages. The fourth (`prepare_fix_input.js`) gathers the raw material for a drop; turning that material into the actual 3-line diagnosis + patch paragraph is an LLM reasoning step performed directly by whichever Claude session runs the daily routine, not a script.

**Tech Stack:** Node.js, `playwright-core` + local Chrome (matches `naver_autowrite/post_draft.js`'s existing convention), plain JSON files for state.

## Global Constraints

- Never insert into or publish an already-live post automatically — Naver's edit-existing-post screen has no draft-save state, only publish, so any automated "helpfulness" here would force a live change. (spec: 핵심 제약)
- No login/session file needed anywhere in this feature — every page read is public. Do not add `storageState` to any context created in this feature's scripts.
- Prefer accuracy over recall when matching draft titles to live posts: skip ambiguous matches (40–60% token overlap) rather than mismatching. (spec: 발행글 자동 파악)
- Stay silent in the daily report when there are no rank drops — do not produce a "no drops today" message every morning. (spec: 보고)

---

### Task 1: `scan_published.js` — find which drafts are actually live

**Files:**
- Create: `naver_autowrite/rank_monitor/scan_published.js`
- Create (on first run): `naver_autowrite/rank_monitor/published_posts.json`

**Interfaces:**
- Produces: `published_posts.json` shaped as `{ "<topic>": { "title": string, "url": string, "logNo": string } }`, where `<topic>` is the `content_<topic>.json` filename stem (e.g. `"청약통장전환마감"`). Later tasks read this file.

- [ ] **Step 1: Write the tokenizer helper used for title matching**

Create the file with this content:

```javascript
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

module.exports = { tokenize, overlapRatio };
```

- [ ] **Step 2: Verify the tokenizer in isolation**

Run: `node -e "const {tokenize,overlapRatio}=require('./naver_autowrite/rank_monitor/scan_published.js'); const d=tokenize('지금 안 바꾸면 늦어요, 청약통장 갈아타면 국민·민영주택 둘 다 가능'); const l=tokenize('지금 안바꾸면 늦어요 청약통장 갈아타기 총정리'); console.log(d); console.log(overlapRatio(d,l));"`

Expected: prints the draft token array, then a ratio ≥ 0.6 (both titles share 청약통장/갈아타/늦어요-family tokens). This confirms the matching threshold from the spec is reachable for realistically-reworded titles before wiring up the scraping half.

- [ ] **Step 3: Add the scraping + matching main routine to the same file**

Append to `naver_autowrite/rank_monitor/scan_published.js` (replace the trailing `module.exports` line with this, keeping the exports for the step-2 check):

```javascript
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
    document.querySelectorAll('a[href*="/PostView"], a[href*="/" ]').forEach((a) => {
      const href = a.getAttribute('href') || '';
      const m = href.match(/logNo=(\d+)/) || href.match(/\/(\d{6,})(?:$|[/?])/);
      if (!m) return;
      const title = (a.innerText || '').trim();
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
```

- [ ] **Step 4: Run it against the real blog**

Run: `cd naver_autowrite/rank_monitor && node scan_published.js`

Expected: prints one `matched:` line per live post it can pair to a draft, then `DONE: N published posts tracked`. Open `published_posts.json` and confirm at least the topics you know are actually published (e.g. `ISA계좌개편`, `청약통장전환마감` if already posted) appear with a real `blog.naver.com/mnt202606/<logNo>` URL — spot-check one URL in a browser to confirm it's the right post.

- [ ] **Step 5: Commit**

```bash
git add naver_autowrite/rank_monitor/scan_published.js naver_autowrite/rank_monitor/published_posts.json
git commit -m "Add scan_published.js to auto-detect which blog drafts are live

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: `extract_keywords.js` — build the tracked-keyword list

**Files:**
- Create: `naver_autowrite/rank_monitor/extract_keywords.js`
- Create (on first run): `naver_autowrite/rank_monitor/keywords.json`

**Interfaces:**
- Consumes: `published_posts.json` from Task 1, shape `{ topic: { title, url, logNo } }`.
- Produces: `keywords.json` shaped as `{ "<keyword>": { "topic": string, "addedDate": "YYYY-MM-DD" } }`. Task 3 reads the keys of this file.

- [ ] **Step 1: Write the stopword list and phrase extractor**

Create the file:

```javascript
const path = require('path');
const fs = require('fs');

const PUBLISHED_FILE = path.join(__dirname, 'published_posts.json');
const OUT_FILE = path.join(__dirname, 'keywords.json');

// Words too generic to be worth tracking on their own - drop them before
// picking phrases, but keep them if they're glued inside a longer phrase
// (e.g. "생활정보" alone is dropped, but doesn't block "생활정보센터").
const STOPWORDS = new Set([
  '생활정보', '총정리', '방법', '얼마나', '얼마', '가능', '확인', '지금',
  '오늘', '이번', '진짜', '정말', '완전', '2026년', '8월', '9월',
]);

function extractKeywords(title, max = 4) {
  const cleaned = title.replace(/[,.!?()·⏰📈✅⚠️]/g, ' ').trim();
  // Split on whitespace first, then re-group into 1-2 word phrases so
  // multi-word terms like "청약통장 갈아타기" survive as one keyword
  // instead of being torn into "청약통장" and "갈아타기" separately.
  const words = cleaned.split(/\s+/).filter((w) => w.length >= 2 && !STOPWORDS.has(w));
  const phrases = [];
  for (let i = 0; i < words.length; i += 2) {
    const phrase = words.slice(i, i + 2).join(' ');
    if (phrase) phrases.push(phrase);
  }
  return phrases.slice(0, max);
}

module.exports = { extractKeywords, STOPWORDS };
```

- [ ] **Step 2: Verify extraction on a known title**

Run: `node -e "const {extractKeywords}=require('./naver_autowrite/rank_monitor/extract_keywords.js'); console.log(extractKeywords('지금 안 바꾸면 늦어요, 청약통장 갈아타면 국민·민영주택 둘 다 가능'));"`

Expected: an array of up to 4 two-word phrases built from non-stopword tokens, e.g. `['지금 안', '바꾸면 늦어요', '청약통장 갈아타면', '국민 민영주택']` (exact grouping depends on tokenization, but no stopword-only phrase and no more than 4 entries).

- [ ] **Step 3: Add the file-updating main routine**

Append (replacing the trailing `module.exports` line):

```javascript
function main() {
  if (!fs.existsSync(PUBLISHED_FILE)) {
    console.error('published_posts.json not found - run scan_published.js first');
    process.exit(1);
  }
  const published = JSON.parse(fs.readFileSync(PUBLISHED_FILE, 'utf-8'));
  const keywords = fs.existsSync(OUT_FILE) ? JSON.parse(fs.readFileSync(OUT_FILE, 'utf-8')) : {};
  const today = new Date().toISOString().slice(0, 10);
  let added = 0;

  for (const [topic, post] of Object.entries(published)) {
    for (const kw of extractKeywords(post.title)) {
      if (keywords[kw]) continue; // already tracked, don't reset its addedDate
      keywords[kw] = { topic, addedDate: today };
      added += 1;
    }
  }

  fs.writeFileSync(OUT_FILE, JSON.stringify(keywords, null, 2), 'utf-8');
  console.log(`DONE: ${added} new keywords added, ${Object.keys(keywords).length} tracked total`);
}

if (require.main === module) {
  main();
}

module.exports = { extractKeywords, STOPWORDS };
```

- [ ] **Step 4: Run it**

Run: `cd naver_autowrite/rank_monitor && node extract_keywords.js`

Expected: `DONE: N new keywords added, M tracked total` where N matches roughly 2-4 per entry in `published_posts.json`. Open `keywords.json` and confirm no stopword-only entries and each keyword has a plausible `topic` pointing back to a real key in `published_posts.json`.

- [ ] **Step 5: Commit**

```bash
git add naver_autowrite/rank_monitor/extract_keywords.js naver_autowrite/rank_monitor/keywords.json
git commit -m "Add extract_keywords.js to build the tracked-keyword list

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: `check_ranks.js` — daily rank check + drop detection

**Files:**
- Create: `naver_autowrite/rank_monitor/check_ranks.js`
- Create (on first run): `naver_autowrite/rank_monitor/rank_history.json`

**Interfaces:**
- Consumes: `keywords.json` from Task 2 (its keys), `published_posts.json` from Task 1 (to know each keyword's `topic`'s `logNo` so it recognizes "our" result in the search page).
- Produces: `rank_history.json` shaped as `{ "<YYYY-MM-DD>": { "<keyword>": { "rank": number|null } } }` (`null` rank means "not found in top 30"). Exports `checkAllRanks()` returning an array of drop objects `{ keyword, topic, from, to }`, consumed by Task 4.

- [ ] **Step 1: Write the single-keyword rank lookup**

Create the file:

```javascript
const { chromium } = require('playwright-core');
const path = require('path');
const fs = require('fs');

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

module.exports = { lookupRank };
```

- [ ] **Step 2: Verify the lookup against a known-live post**

Pick one topic from `published_posts.json` you know is actually live (has a real URL you can open), and its logNo. Then run:

Run: `node -e "const {chromium}=require('playwright-core'); const {lookupRank}=require('./naver_autowrite/rank_monitor/check_ranks.js'); (async()=>{const b=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'}); const c=await b.newContext({viewport:{width:420,height:900},userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'}); const p=await c.newPage(); console.log(await lookupRank(p,'<한 키워드>','<그 글의 logNo>')); await b.close();})();"`

Expected: prints a number (its current rank) or `null`. A `null` result is plausible for a very fresh post — that's not a failure, it just means the keyword isn't ranking in the top 30 yet.

- [ ] **Step 3: Add the multi-keyword driver + drop detection**

Append (replacing the trailing `module.exports` line):

```javascript
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

  const today = new Date().toISOString().slice(0, 10);
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
```

- [ ] **Step 4: Run it end-to-end**

Run: `cd naver_autowrite/rank_monitor && node check_ranks.js`

Expected: one `<keyword>: N위` or `<keyword>: 권외` line per tracked keyword, then `DONE: 0 drop(s) detected` (0 is correct on a first run — there's no prior day to compare against yet). Run it a second time the next day (or manually edit `rank_history.json` to insert a fake worse-ranked yesterday entry for one keyword) to confirm the drop list actually populates when a real regression exists.

- [ ] **Step 5: Commit**

```bash
git add naver_autowrite/rank_monitor/check_ranks.js naver_autowrite/rank_monitor/rank_history.json
git commit -m "Add check_ranks.js for daily rank checking and drop detection

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: `prepare_fix_input.js` — gather diagnosis material for each drop

**Files:**
- Create: `naver_autowrite/rank_monitor/prepare_fix_input.js`
- Create: `naver_autowrite/rank_monitor/fixes/` (output directory, created by the script)

**Interfaces:**
- Consumes: a `drops` array shaped like Task 3's `checkAllRanks()` output (`{ keyword, topic, from, to }`), and `published_posts.json` for each drop's post URL.
- Produces: for each drop, `fixes/input_<keyword>_<date>.md` containing our full post text plus the top 3 competing posts' title + intro. This is the file a Claude session reads to write the actual `fixes/fix_<keyword>_<date>.md` diagnosis (that writing step is manual/LLM, not code — see Task 5).

- [ ] **Step 1: Write the public-page content reader**

Create the file:

```javascript
const { chromium } = require('playwright-core');
const path = require('path');
const fs = require('fs');

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

module.exports = { readPost, topResultUrls };
```

- [ ] **Step 2: Verify against a real keyword**

Run: `node -e "const {chromium}=require('playwright-core'); const {topResultUrls}=require('./naver_autowrite/rank_monitor/prepare_fix_input.js'); (async()=>{const b=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'}); const c=await b.newContext({viewport:{width:420,height:900},userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'}); const p=await c.newPage(); console.log(await topResultUrls(p,'청약통장 갈아타기',3)); await b.close();})();"`

Expected: an array of up to 3 real `blog.naver.com/.../<logNo>` URLs.

- [ ] **Step 3: Add the per-drop brief-writing main routine**

Append (replacing the trailing `module.exports` line):

```javascript
async function prepareFixInputs(drops) {
  if (drops.length === 0) return [];
  fs.mkdirSync(FIXES_DIR, { recursive: true });
  const published = JSON.parse(fs.readFileSync(PUBLISHED_FILE, 'utf-8'));
  const today = new Date().toISOString().slice(0, 10);

  const browser = await chromium.launch({
    headless: true,
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  });
  const context = await browser.newContext({ viewport: { width: 420, height: 900 }, userAgent: MOBILE_UA });
  const page = await context.newPage();

  const writtenFiles = [];
  for (const drop of drops) {
    const post = published[drop.topic];
    if (!post) continue;
    const mine = await readPost(page, post.url, true);
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
  }

  await browser.close();
  return writtenFiles;
}

module.exports = { readPost, topResultUrls, prepareFixInputs };
```

- [ ] **Step 4: Run it against a manufactured drop**

Run: `node -e "const {prepareFixInputs}=require('./naver_autowrite/rank_monitor/prepare_fix_input.js'); prepareFixInputs([{keyword:'청약통장 갈아타기', topic:'청약통장전환마감', from:3, to:7}]).then(f=>console.log(f));"` (swap in a topic/keyword that's actually in your `published_posts.json`).

Expected: prints the path to one `fixes/input_..._<date>.md` file. Open it and confirm it has our full post text under `## 내 글 전문` and up to 3 real competitor title+intro blocks under `## 현재 상위 경쟁글`.

- [ ] **Step 5: Commit**

```bash
git add naver_autowrite/rank_monitor/prepare_fix_input.js
git commit -m "Add prepare_fix_input.js to gather diagnosis material for rank drops

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Diagnosis-writing procedure + daily routine wiring

This task has no new script — it documents the LLM-reasoning step (per the spec, done directly by whichever Claude session runs the routine, not a separate API call) and wires everything above into the existing 8am cloud routine.

**Files:**
- Create: `naver_autowrite/rank_monitor/README.md` (the documented procedure below)
- Modify: the `daily_naver_blog_draft_routine` cloud trigger's prompt, via `RemoteTrigger action:update` on trigger id `trig_01GsFsw7kLrs331Ypsrw3CYM` (see memory `daily_naver_blog_draft_routine.md`)

**Interfaces:**
- Consumes: `fixes/input_<keyword>_<date>.md` files from Task 4.
- Produces: `fixes/fix_<keyword>_<date>.md`, each containing a `## 진단` section (≤3 lines) and a `## 보강 문구` section (a ready-to-paste Korean paragraph, plus the exact existing sentence from our post to insert it after).

- [ ] **Step 1: Write the procedure doc**

Create `naver_autowrite/rank_monitor/README.md`:

```markdown
# rank_monitor 사용법

## 매일 아침 순서 (사람 또는 클라우드 루틴이 실행)

1. `node scan_published.js` — 어떤 초안이 실제로 발행됐는지 갱신
2. `node extract_keywords.js` — 새로 발행된 글의 키워드 추가
3. `node check_ranks.js` — 오늘 순위 기록 + 하락 목록 출력 (JSON, stdout)
4. 하락이 있으면: `prepare_fix_input.js`의 `prepareFixInputs(drops)`를 호출해
   `fixes/input_<keyword>_<date>.md`를 만든다.
5. 각 `input_*.md`를 읽고, 아래 규칙으로 `fix_<keyword>_<date>.md`를 직접 작성한다
   (별도 API 호출 없이, 이 절차를 실행 중인 Claude가 직접 작성):

   - `## 진단` — 3줄 이내. `input` 파일에 있는 내 글과 경쟁글의 **실제 차이만** 쓴다.
     추측하거나 없는 내용을 지어내지 않는다.
   - `## 보강 문구` — 기존 글의 톤을 유지하면서, 진단에서 짚은 부족한 부분만 채우는
     한두 문단. 문단 앞에 반드시 `삽입 위치: "<내 글에 실제로 있는 문장>" 뒤`
     형식으로 앵커 문장을 명시한다 (대표님이 어디에 붙여넣을지 바로 알 수 있게).

6. 하락이 없으면 아무 파일도 만들지 않고 조용히 넘어간다.

## 다음 세션 보고 형식

`fixes/fix_*.md` 중 오늘 날짜 파일이 있으면, 다음 세션 시작 시 채팅에 키워드별로
진단과 보강 문구를 그대로 보여준다(파일 경로만 던지지 않는다). 없으면 언급하지 않는다.

## 안전 규칙

- 이 폴더의 어떤 스크립트도 로그인 세션을 쓰지 않는다 (전부 공개 페이지).
- 어떤 스크립트도 발행된 글을 직접 수정하지 않는다. 삽입·발행은 항상 사람이 한다.
```

- [ ] **Step 2: Confirm the trigger id and current prompt before editing it**

Call `RemoteTrigger action:get` with id `trig_01GsFsw7kLrs331Ypsrw3CYM` and read back the current prompt text in full before changing anything — the existing keyword-research routine must keep working, this only adds a step to it.

- [ ] **Step 3: Update the cloud routine's prompt**

Call `RemoteTrigger action:update` on `trig_01GsFsw7kLrs331Ypsrw3CYM`, appending a new step to the existing prompt (keep every existing step exactly as-is, add this as a new final step):

```
6. 순위 점검: naver_autowrite/rank_monitor/README.md의 절차대로 scan_published.js,
   extract_keywords.js, check_ranks.js를 순서대로 실행하고, 하락이 감지되면
   prepare_fix_input.js로 자료를 모은 뒤 README의 규칙대로 fix_<키워드>_<날짜>.md를
   직접 작성해서 fixes/ 에 저장해라. 하락이 없으면 이 단계에 대해 아무것도 보고하지 마라.
```

Note: if this cloud sandbox turns out not to have Chrome/`playwright-core` available (unlike this local machine), this step will fail loudly the first time it runs — check the routine's next-run log and, if that happens, fall back to running `check_ranks.js` from this local session each morning instead of from the cloud trigger, reporting the same way. Do not silently assume cloud parity with the local environment.

- [ ] **Step 4: Verify by hand-running the whole chain locally once**

Run in order from `naver_autowrite/rank_monitor/`: `node scan_published.js && node extract_keywords.js && node check_ranks.js`. Take the printed drops array (if any) and manually write one real `fix_<keyword>_<date>.md` following the README's rules, using an `input_*.md` produced by `prepare_fix_input.js`. Read it back and confirm it has both required sections and a real anchor sentence quoted from the actual post.

- [ ] **Step 5: Commit**

```bash
git add naver_autowrite/rank_monitor/README.md
git commit -m "Document rank-monitor daily procedure and wire into cloud routine

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
