import json, sys
suite = {c['id']: c for c in json.load(open('/home/claude/v087/res/suite.json'))}
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
ra = {r['id']: r for r in a['rows']}; rb = {r['id']: r for r in b['rows']}
ids = [i for i in ra if i in rb]
gain = [i for i in ids if rb[i]['ok'] and not ra[i]['ok']]; lost = [i for i in ids if ra[i]['ok'] and not rb[i]['ok']]
sac = [i for i in ids if suite[i]['sacrifice']]
print(f"{len(ids)}국면: A {sum(ra[i]['ok'] for i in ids)} → B {sum(rb[i]['ok'] for i in ids)} (새로 품 {len(gain)}, 놓침 {len(lost)}) | 희생 {len(sac)}: {sum(ra[i]['ok'] for i in sac)} → {sum(rb[i]['ok'] for i in sac)} | 깊이 {sum(ra[i]['depth'] for i in ids)/len(ids):.2f} → {sum(rb[i]['depth'] for i in ids)/len(ids):.2f}")
if '-v' in sys.argv:
    for i in lost: print('  놓침', i, suite[i]['san'], 'see', suite[i]['see'], 'A깊이', ra[i]['depth'], 'B깊이', rb[i]['depth'], 'B수', rb[i]['move'], suite[i]['fen'])
