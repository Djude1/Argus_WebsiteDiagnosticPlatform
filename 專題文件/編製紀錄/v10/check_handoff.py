from pathlib import Path
import json, re, hashlib
root = Path(__file__).resolve().parents[2] / '本機資料'
md_files = [root/'交接檔案.md', root/'work/v10/artifact.md', root/'work/v10/交接現況.md', root/'work/v10/QA紀錄.md']
missing = []
count = 0
for file in md_files:
    for target in re.findall(r'\]\(([^)]+)\)', file.read_text(encoding='utf-8-sig')):
        count += 1
        path = (file.parent / target.split('#', 1)[0]).resolve()
        if not path.exists():
            missing.append(str(path))
assets = ['final14.pdf','map_render13.json','page_map.json','v4_evidence.json','v4_blocks.json','root_viewed_pages.json','qa-crops/final-page-5-catalog.png','qa-crops/final-page-18-header.png','qa-crops/final-page-22-header.png']
missing += [x for x in assets if not (root/'work/v10'/x).exists()]
for folder, end in [('reference-render',54),('render14',88)]:
    missing += [f'{folder}/page-{n}.png' for n in range(1,end+1) if not (root/'work/v10'/folder/f'page-{n}.png').exists()]
expected = {
 'Argus_系統手冊_v4.docx': '739c11b8d9869bf1955d8590561ede09241fd2206e4d83e0b2ce56897f07b0c6',
 'Argus_系統手冊_v9_新版整合修訂版.docx': '7d22674fe9c099d9db30ee01d9853ea80463371f210f25c465c8b67027719e49',
 'Argus_系統手冊_v10_複審精簡版.docx': 'bb777164cc8e4270a24083a4d136a492f7540a1587de464daf710ee4a9f0749f'}
hashes_match = all(hashlib.sha256((root/name).read_bytes()).hexdigest()==value for name,value in expected.items())
seen = json.loads((root/'work/v10/root_viewed_pages.json').read_text(encoding='utf-8'))
assert seen['pages'] == list(range(1,89))
map_a = json.loads((root/'work/v10/map_render13.json').read_text(encoding='utf-8-sig'))
map_b = json.loads((root/'work/v10/page_map.json').read_text(encoding='utf-8-sig'))
assert map_a == map_b
assert not missing and hashes_match
print(json.dumps({'md_links_checked':count,'missing':missing,'hashes_match':hashes_match,'root_pages_viewed':len(seen['pages']),'map_changes':0},ensure_ascii=False))
