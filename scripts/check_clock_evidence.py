#!/usr/bin/env python3
"""Independent audit of clock observations, score witnesses, costs and summaries.

No production clock, alignment, matching, delivery or summary function is used.
Global minimum correctness is additionally tested by the 300-case exhaustive
oracle and full deterministic replay; here every saved winning witness is checked.
"""
from collections import defaultdict
from fractions import Fraction
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from relay_timing_lab.clock.protocol import frozen
from relay_timing_lab.protocol import canonical


def read(p):return json.loads(p.read_bytes())
def sha(data):return hashlib.sha256(data).hexdigest()
def q(a,p):return sorted(a)[max(0,math.ceil(len(a)*p)-1)] if a else None


def hist(trace,width,end):
    result=defaultdict(int)
    for t,b in trace:
        if 0<=t<=end:result[t//width]+=b
    return result


def dist(a,b):
    sa,sb=sum(a.values()),sum(b.values())
    if not sa or not sb:return Fraction(0 if sa==sb else 2)
    return Fraction(sum(abs(a[k]*sb-b[k]*sa) for k in a.keys()|b.keys()),sa*sb)


def clock(trace,offset,drift):
    result=[]
    for t,b in trace:
        exact=Fraction(t-2000)*(1+Fraction(drift,1000000))+2000+offset
        result.append([math.floor(exact),b])
    return result


def costs(traces,results):
    sent=dummy=real=payload=delivered=dropped=queued=horizon=maximum=0;delays=[]
    for trace,r in zip(traces,results):
        ids=[]
        for t,b,i in r['departures']:
            sent+=b
            if i is None:dummy+=b
            else:
                ids.append(i);delivered+=1;real+=b;payload+=trace[i][1];delays.append(t-trace[i][0])
        ids+=r['dropped']+r['queued'];assert sorted(ids)==list(range(len(trace)))
        dropped+=len(r['dropped']);queued+=len(r['queued']);horizon+=r['backlog_horizon']
        maximum=max(maximum,r['max_backlog'])
    input_bytes=sum(b for tr in traces for t,b in tr)
    return dict(input_events=sum(map(len,traces)),input_bytes=input_bytes,delivered=delivered,
        dropped=dropped,queued=queued,undelivered=dropped+queued,backlog_horizon=horizon,
        max_backlog_per_flow=maximum,transmitted_bytes=sent,dummy_bytes=dummy,real_wire_bytes=real,
        delivered_payload_bytes=payload,size_padding_bytes=real-payload,
        byte_ratio=sent/input_bytes if input_bytes else None,
        delay_p50_ms=q(delays,.5),delay_p95_ms=q(delays,.95),delay_p99_ms=q(delays,.99),
        delay_max_ms=max(delays,default=None))


def audit(out):
    c=read(out/'protocol.json');f=read(out/'freeze.json');assert f==frozen(c)
    m=read(out/'manifest.json')
    for name,item in m['files'].items():
        b=(out/name).read_bytes();assert sha(b)==item['sha256'] and len(b)==item['bytes'],name
    assert m['artifact_bytes']==sum(v['bytes'] for v in m['files'].values())
    summary=read(out/'summary.json');rows=[];pairs=0;paired_inputs={};paired_clocks={}
    assert summary['seeds']==c[summary['phase']+'_seeds']
    assert len(summary['groups'])==162 and len(summary['paired'])==270
    for p in sorted((out/'inputs').glob('*.json')):
        inp=read(p);traces=inp['traces'];n=inp['candidates']
        pairkey=(inp['seed'],inp['family'])
        if pairkey in paired_inputs:
            previous=paired_inputs[pairkey];assert previous[:min(n,len(previous))]==traces[:min(n,len(previous))]
        paired_inputs[pairkey]=traces
        raw=json.loads(gzip.decompress((out/'raw'/(p.stem+'.json.gz')).read_bytes()))
        assert raw['input_sha256']==sha(p.read_bytes()) and raw['config_sha256']==f['config_sha256']
        assert raw['ingress_observed']==[[[t+2000,b] for t,b in tr] for tr in traces]
        order=raw['egress_order'];truth=raw['truth_indices']
        assert sorted(order)==list(range(n)) and truth==[order.index(i) for i in range(n)]
        for policy,record in raw['policies'].items():
            results=record['results_in_ingress_order'];expected_cost=costs(traces,results)
            original=[[[t+2000,b] for t,b,_ in results[i]['departures']] for i in order]
            for condition,record_c in record['conditions'].items():
                off,drift=record_c['true_offset_ms'],record_c['true_drift_ppm']
                ck=(*pairkey,condition)
                assert paired_clocks.setdefault(ck,(off,drift))==(off,drift)
                if condition=='synchronized':assert (off,drift)==(0,0)
                else:assert 250<=abs(off)<=750
                if condition=='offset_drift':assert 5000<=abs(drift)<=18000
                else:assert drift==0
                public=record_c['egress_observed'];assert public==[clock(tr,off,drift) for tr in original]
                assert all(0<=t<=c['end_ms'] for tr in public for t,b in tr)
                if policy=='padded':assert all(tr==public[0] for tr in public)
                for matcher,record_m in record_c['matchers'].items():
                    matching=record_m['matching'];scores=record_m['scores']
                    if matcher=='random':
                        assert scores is None
                        assert matching['top1']==1/n and matching['rank']==(n+1)/2
                    else:
                        for i,score_row in enumerate(scores):
                            fractions=[Fraction(*x) for x in score_row]
                            for j,value in enumerate(fractions):
                                if matcher=='legacy':
                                    variants=[[[t+lag,b] for t,b in raw['ingress_observed'][i]] for lag in c['lags_ms']]
                                else:
                                    o,d=record_m['winning_hypotheses'][i][j]
                                    assert o in c['offsets_ms'] and d in c['drifts_ppm']
                                    variants=[clock(raw['ingress_observed'][i],o,d)]
                                assert all(0<=t<=c['end_ms'] for tr in variants for t,b in tr)
                                assert value==min(dist(hist(tr,c['bin_ms'],c['end_ms']),hist(public[j],c['bin_ms'],c['end_ms'])) for tr in variants)
                                pairs+=1
                            target=fractions[truth[i]];lower=sum(v<target for v in fractions);equal=fractions.count(target)
                            expected={'top1':1/equal if lower==0 else 0.,'rank':lower+(equal+1)/2,'ties':equal}
                            assert matching['per_flow'][i]==expected
                        for key in ('top1','rank'):
                            assert matching[key]==statistics.mean(r[key] for r in matching['per_flow'])
                    row=next(r for r in raw['rows'] if (r['policy'],r['condition'],r['matcher'])==(policy,condition,matcher))
                    assert all(row[k]==v for k,v in expected_cost.items())
                    assert row['top1']==matching['top1'] and row['rank']==matching['rank']
                    if policy=='padded':assert row['top1']==1/n and row['rank']==(n+1)/2
        rows.extend(raw['rows'])
    keys=('seed','family','candidates','policy','condition','matcher')
    key=lambda r:tuple(r[k] for k in keys)
    assert sorted(rows,key=key)==sorted(summary['rows'],key=key)
    assert len(set(map(key,rows)))==len(rows)
    assert len(rows)==len(summary['seeds'])*6*27
    # Independently recompute all aggregate and paired bootstrap intervals.
    cache={}
    def interval(values,family,n):
        seed=int(sha(canonical([c['bootstrap_seed'],family,str(n)]))[:16],16)
        cache_key=(tuple(values),seed)
        if cache_key not in cache:
            if not values:result=dict(mean=None,low=None,high=None,n=0)
            else:
                rng=random.Random(seed)
                means=sorted(statistics.mean(rng.choices(values,k=len(values))) for _ in range(c['bootstrap_samples']))
                result=dict(mean=statistics.mean(values),low=means[math.ceil(.025*len(means))-1],
                            high=means[math.ceil(.975*len(means))-1],n=len(values))
            cache[cache_key]=result
        return cache[cache_key]
    fields=keys[1:]
    for section in ('groups','paired'):
        for g in summary[section]:
            selected=sorted([r for r in rows if all(r[k]==g[k] for k in fields)],key=lambda r:r['seed'])
            if section=='paired':
                overrides={'aligned_minus_legacy':{'matcher':'legacy'},'clock_minus_synchronized':{'condition':'synchronized'},
                           'policy_minus_immediate':{'policy':'immediate'}}[g['comparison']]
                ref={**g,**overrides};base={r['seed']:r for r in rows if all(r[k]==ref[k] for k in fields)}
            for metric,expected in g['metrics'].items():
                if section=='groups':values=[r[metric] for r in selected if r[metric] is not None]
                else:values=[r[metric]-base[r['seed']][metric] for r in selected
                             if r[metric] is not None and base[r['seed']][metric] is not None]
                assert interval(values,g['family'],g['candidates'])==expected,(section,metric,g)
    runtime=read(out/'runtime.json');measurement_bytes=(out/'measurements.json.gz').read_bytes()
    assert sha(measurement_bytes)==runtime['measurements_sha256']
    times=json.loads(gzip.decompress(measurement_bytes))
    assert sorted(map(key,times))==sorted(map(key,rows))
    assert all(r['cpu_ns']>=0 and r['elapsed_ns']>=0 for r in times)
    assert runtime['process_cpu_seconds']<c['cpu_budget_seconds']
    print(json.dumps(dict(status='passed',rows=len(rows),score_witnesses=pairs,artifacts=len(m['files']),
                         independent_intervals=len(cache),artifact_bytes=m['artifact_bytes']),indent=2))

if __name__=='__main__':audit(Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'results/clock-evaluation')
