# 完整性核对：每个语料文件应有 7 个工具形态的评测 JSON；另有 exact 参考若干。
import collections
import glob
import json

expect = {}
for p in glob.glob('benchmarks/corpus/*/*.cld'):
    base = p.replace('\\', '/').split('/')[-1][:-4]
    expect[base] = ['stdraw-ortho', 'stdraw-auto', 'stdraw-auto-exact',
                    'graphviz-dot', 'graphviz-neato', 'graphviz-sfdp', 'elk-layered']
have = collections.defaultdict(set)
for p in glob.glob('benchmarks/raw/*.json'):
    if p.endswith('.in.json') or p.endswith('.layout.json') or p.endswith('.exact.json'):
        continue
    d = json.load(open(p, encoding='utf-8'))
    have[d['graph']].add(d['tool'])
missing = []
for b, tools in expect.items():
    for t in tools:
        if t not in have[b]:
            missing.append((b, t))
print('graphs:', len(expect), 'missing records:', len(missing))
for m in missing[:10]:
    print('  ', m)
ex = glob.glob('benchmarks/raw/*.exact.json')
ok = sum(1 for p in ex if json.load(open(p, encoding='utf-8')).get('status') == 'ok')
print('exact refs:', len(ex), 'ok:', ok)
