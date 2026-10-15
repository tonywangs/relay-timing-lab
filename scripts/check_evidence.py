#!/usr/bin/env python3
"""Audit preserved inputs, event accounting, exact matching and summary rows."""
import gzip
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from relay_timing_lab.experiment import derived_seed
from relay_timing_lab.matcher import score_matrix
from relay_timing_lab.metrics import matching, delivery
from relay_timing_lab.model import Settings, generate, observe
from relay_timing_lab.protocol import load, canonical, digest, frozen

root=Path(__file__).resolve().parents[1]
out=root/'results/evaluation'
config=load(root/'experiment/protocol.json')
assert load(root/'experiment/freeze.json')==frozen(config)
manifest=load(out/'manifest.json')
for name,item in manifest['files'].items():
    data=(out/name).read_bytes()
    assert digest(data)==item['sha256'] and len(data)==item['bytes'],name
assert manifest['artifact_bytes']==sum(v['bytes'] for v in manifest['files'].values())
summary=load(out/'summary.json')
assert len(summary['seeds'])>=20 and len(config['families'])>=3
all_rows=[];events=0;trials=0
for p in sorted((out/'inputs').glob('*.json')):
    inputs=load(p);traces=inputs['traces'];n=inputs['candidates'];family=inputs['family'];seed=inputs['seed']
    assert traces==generate(family,derived_seed(seed,family,'traffic'),n,Settings(**config['settings']))
    raw=json.loads(gzip.decompress((out/'raw'/(p.stem+'.json.gz')).read_bytes()))
    assert raw['input_sha256']==digest(p.read_bytes())
    assert raw['config_sha256']==summary['config_sha256']
    assert sorted(raw['egress_order'])==list(range(n))
    assert raw['truth_indices']==[raw['egress_order'].index(i) for i in range(n)]
    for policy in ('immediate','batch','padded'):
        record=raw['policies'][policy];results=record['results_in_ingress_order']
        costs=delivery(traces,results)
        public=[observe(results[i]) for i in raw['egress_order']]
        scores=score_matrix(traces,public,config['bin_ms'],config['settings']['horizon_ms']+config['settings']['drain_ms'],config['lags_ms'])
        assert record['scores']==[[[v.numerator,v.denominator] for v in row] for row in scores]
        match=matching(scores,raw['truth_indices'])
        assert record['matching']==match
        row=next(r for r in raw['rows'] if r['policy']==policy)
        assert all(row[k]==v for k,v in costs.items())
        assert row['top1']==match['top1'] and row['rank']==match['rank']
        if policy=='padded': assert all(v==public[0] for v in public)
    all_rows.extend(raw['rows']);events+=sum(map(len,traces));trials+=1
key=lambda r:(r['seed'],r['family'],r['candidates'],r['policy'])
assert sorted(all_rows,key=key)==sorted(summary['rows'],key=key)
assert len({(r['seed'],r['family'],r['candidates'],r['policy']) for r in all_rows})==len(all_rows)
for r in all_rows:
    if r['policy'] in ('immediate','unmodified'): assert r['top1']==1
    if r['policy'] in ('random','padded'):
        assert r['top1']==1/r['candidates'] and r['rank']==(r['candidates']+1)/2
print(json.dumps({'status':'passed','trials':trials,'run_policy_rows':len(all_rows),
                  'input_events':events,'hashed_artifacts':len(manifest['files']),
                  'artifact_bytes':manifest['artifact_bytes']},indent=2))
