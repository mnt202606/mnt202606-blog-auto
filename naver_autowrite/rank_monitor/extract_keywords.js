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
  // Protect digit-comma-digit and digit-period-digit patterns before cleanup
  // to preserve formatted numbers like 6,480 and 3.3%
  const protectedPatterns = [];
  let protected_title = title;
  protected_title = protected_title.replace(/\d[,.]\d/g, (match) => {
    const placeholder = `__PROTECTED_${protectedPatterns.length}__`;
    protectedPatterns.push(match);
    return placeholder;
  });

  const cleaned = protected_title.replace(/[,.!?()·⏰📈✅⚠️]/g, ' ').trim();

  // Restore protected patterns
  let restored = cleaned;
  protectedPatterns.forEach((pattern, index) => {
    restored = restored.replace(`__PROTECTED_${index}__`, pattern);
  });

  // Split on whitespace first, then re-group into 1-2 word phrases so
  // multi-word terms like "청약통장 갈아타기" survive as one keyword
  // instead of being torn into "청약통장" and "갈아타기" separately.
  const words = restored.split(/\s+/).filter((w) => w.length >= 2 && !STOPWORDS.has(w));
  const phrases = [];
  for (let i = 0; i < words.length; i += 2) {
    const phrase = words.slice(i, i + 2).join(' ');
    if (phrase) phrases.push(phrase);
  }
  return phrases.slice(0, max);
}

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
      if (keywords[kw]) {
        // Log collision only if this keyword is tracked under a different topic
        if (keywords[kw].topic !== topic) {
          console.log(`collision: "${kw}" already tracked for topic "${keywords[kw].topic}", skipping for "${topic}"`);
        }
        continue; // already tracked, don't reset its addedDate
      }
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
