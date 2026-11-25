# byulbyul_yeonye/*.md -> naver_autowrite/byulbyul_content/*.json (post_draft.js 입력 형식)
import glob, json, os, re
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = os.path.join(root, 'naver_autowrite', 'byulbyul_content')
os.makedirs(out, exist_ok=True)
for f in sorted(glob.glob(os.path.join(root, 'byulbyul_yeonye', '*.md'))):
    lines = open(f, encoding='utf-8').read().split('\n')
    title = lines[0].lstrip('# ').strip().replace('[별별연예] ', '')
    body, cur = [], []
    def flush():
        global cur
        if cur: body.append('\n'.join(cur).strip()); cur = []
    for l in lines[1:]:
        if l.startswith('## '):
            flush(); cur.append(l[3:].strip())
        elif l.startswith('#') and ' #' in l:
            flush(); body.append(l.strip())
        else:
            t = re.sub(r'\*\*', '', l.rstrip())
            cur.append(t[2:].strip() if t.startswith('- ') else t)
    flush()
    blocks = [{"type": "text", "text": re.sub(r'\n{3,}', '\n\n', b)} for b in body if b.strip()]
    name = os.path.splitext(os.path.basename(f))[0] + '.json'
    json.dump({"title": "[별별연예] " + title, "blocks": blocks}, open(os.path.join(out, name), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('done')
