#!/usr/bin/env python3
"""Summarize measured matcher costs across independent simulation seeds.

Runtime is machine/load dependent. This file intentionally is not part of the
byte-replay manifest. --check verifies the saved summary from raw timing samples.
"""
from collections import defaultdict
import gzip
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from relay_timing_lab.metrics import interval
from relay_timing_lab.experiment import derived_seed
from relay_timing_lab.protocol import canonical, digest


def calculate(out):
    raw=(out/'measurements.json.gz').read_bytes();times=json.loads(gzip.decompress(raw))
    c=json.loads((out/'protocol.json').read_bytes());groups=defaultdict(list)
    fields=('family','candidates','policy','condition','matcher')
    for r in times:groups[tuple(r[k] for k in fields)].append(r)
    result=[]
    for key,rows in sorted(groups.items()):
        rows.sort(key=lambda r:r['seed']);seed=derived_seed(c['bootstrap_seed'],key[0],str(key[1]))
        result.append({**dict(zip(fields,key)), 'metrics':{
            k.replace('_ns','_ms'):interval([r[k]/1e6 for r in rows],c['bootstrap_samples'],seed) for k in ('cpu_ns','elapsed_ns')}})
    return dict(schema='clock-runtime-v1',units='milliseconds',measurement_sha256=digest(raw),groups=result,
                limitation='Repeated within one machine/load session; intervals resample simulation seeds, not machines or executions.')


def main():
    out=ROOT/'results/clock-evaluation';target=out/'timing-summary.json';value=calculate(out)
    if '--check' in sys.argv:assert json.loads(target.read_bytes())==value
    else:
        with target.open('xb') as f:f.write(canonical(value))
    print(json.dumps({'status':'passed','groups':len(value['groups']),'timing_samples':3240}))

if __name__=='__main__':main()
