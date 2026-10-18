#!/usr/bin/env python3
"""Run the predeclared two-grid development comparison, then freeze selection.

Writes new directories only. Run once before final evaluation. Does not read
any final evaluation artifact. Selection procedure: docs/clock-protocol.md.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from relay_timing_lab.protocol import load, write_json, digest
from relay_timing_lab.clock.protocol import frozen


def main():
    base=load(ROOT/'experiment/clock/protocol.json')
    env={**os.environ,'PYTHONPATH':str(ROOT/'src')}
    candidates=[]
    for step in (200,100):
        c={**base,'offsets_ms':list(range(-800,2401,step))}
        config=ROOT/f'experiment/clock/development-{step}.json'
        freeze=ROOT/f'experiment/clock/development-{step}-freeze.json'
        write_json(config,c);write_json(freeze,frozen(c))
        out=ROOT/f'results/clock-development-{step}'
        subprocess.run([sys.executable,'-m','relay_timing_lab.clock','run','--config',str(config),
                        '--freeze',str(freeze),'--phase','development','--output',str(out)],env=env,check=True)
        summary=json.loads((out/'summary.json').read_text())
        rows=[r for r in summary['rows'] if r['matcher']=='aligned']
        candidates.append(dict(step_ms=step,mean_top1=sum(r['top1'] for r in rows)/len(rows),
                               rows=len(rows),manifest_sha256=digest((out/'manifest.json').read_bytes())))
    fine=candidates[1]['mean_top1']-candidates[0]['mean_top1']>=.01
    selected=100 if fine else 200
    c={**base,'offsets_ms':list(range(-800,2401,selected))}
    # The draft input is replaced only after development; final freeze is exclusive.
    from relay_timing_lab.protocol import canonical
    (ROOT/'experiment/clock/protocol.json').write_bytes(canonical(c))
    write_json(ROOT/'experiment/clock/selection.json',dict(rule='fine minus coarse >= 0.01 selects fine; else coarse',
        candidates=candidates,selected_step_ms=selected,development_seeds=c['development_seeds']))
    write_json(ROOT/'experiment/clock/freeze.json',frozen(c))
    print(json.dumps(candidates,indent=2));print('Selected step:',selected)

if __name__=='__main__':main()
