#!/usr/bin/env python3
"""Verify predeclared development selection and the separate evaluation freeze."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from relay_timing_lab.protocol import canonical,digest
from relay_timing_lab.clock.protocol import frozen


def read(p):return json.loads(p.read_bytes())


def main():
    selected=read(ROOT/'experiment/clock/selection.json');candidates=[];configs={}
    for step in (200,100):
        out=ROOT/f'results/clock-development-{step}'
        c=read(out/'protocol.json');configs[step]=c
        assert read(out/'freeze.json')==frozen(c)
        assert c['offsets_ms']==list(range(-800,2401,step))
        summary=read(out/'summary.json');assert summary['seeds']==c['development_seeds']
        rows=[r for r in summary['rows'] if r['matcher']=='aligned'];assert len(rows)==162
        candidates.append(dict(step_ms=step,mean_top1=sum(r['top1'] for r in rows)/len(rows),
                               rows=len(rows),manifest_sha256=digest((out/'manifest.json').read_bytes())))
    assert candidates==selected['candidates']
    assert {k:v for k,v in configs[100].items() if k!='offsets_ms'}=={k:v for k,v in configs[200].items() if k!='offsets_ms'}
    chosen=100 if candidates[1]['mean_top1']-candidates[0]['mean_top1']>=.01 else 200
    assert selected['selected_step_ms']==chosen
    c=read(ROOT/'experiment/clock/protocol.json');assert c==configs[chosen]
    assert selected['development_seeds']==c['development_seeds']
    assert read(ROOT/'experiment/clock/freeze.json')==frozen(c)
    historic=read(ROOT/'experiment/protocol.json')
    assert not set(c['evaluation_seeds']) & set(c['development_seeds']+historic['evaluation_seeds']+historic['development_seeds'])
    assert len(c['evaluation_seeds'])>=20
    print(json.dumps(dict(status='passed',selected_step_ms=chosen,config_sha256=digest(canonical(c)),fresh_evaluation_seeds=len(c['evaluation_seeds'])),indent=2))

if __name__=='__main__':main()
