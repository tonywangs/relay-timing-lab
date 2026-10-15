import copy
import json
from pathlib import Path
import random
import statistics
import unittest
from relay_timing_lab.experiment import summarize, derived_seed, METRICS, POLICIES, trial
from relay_timing_lab.protocol import load
from relay_timing_lab.report import render

ROOT=Path(__file__).resolve().parents[1]


class ExperimentTests(unittest.TestCase):
    def test_paired_intervals_resample_run_differences(self):
        c=load(ROOT/'experiment/protocol.json')
        c.update(families=['renewal'],candidate_sizes=[4],bootstrap_samples=100)
        rows=[]
        base=[0.2,0.4,0.8,1.0];other=[0.8,0.6,0.2,0.0]
        for seed in range(4):
            for policy in POLICIES:
                rows.append(dict(seed=seed,family='renewal',candidates=4,policy=policy,
                                 **{k:(base[seed] if policy=='immediate' else other[seed]) for k in METRICS}))
        groups,paired=summarize(rows,c)
        delta=[b-a for a,b in zip(base,other)]
        rng=random.Random(derived_seed(c['bootstrap_seed'],'renewal','4'))
        samples=sorted(statistics.mean(rng.choices(delta,k=4)) for _ in range(100))
        item=next(r for r in paired if r['policy']=='batch')['metrics']['top1']
        self.assertEqual(item,dict(mean=statistics.mean(delta),low=samples[2],high=samples[97],n=4))

    def test_controls_and_policies_share_input_accounting(self):
        c=load(ROOT/'experiment/protocol.json')
        inputs,outcome=trial(c,11,'bursty',4)
        rows=outcome['rows']
        self.assertEqual(len({r['input_bytes'] for r in rows}),1)
        self.assertEqual(len({r['input_events'] for r in rows}),1)
        for r in rows:
            self.assertEqual(r['input_events'],r['delivered']+r['dropped']+r['queued'])
            if r['policy']=='unmodified': self.assertEqual(r['top1'],1)
            if r['policy'] in ('random','padded'):
                self.assertEqual(r['top1'],.25);self.assertEqual(r['rank'],2.5)

    def test_report_escapes_script_delimiters_and_is_deterministic(self):
        label='</script><img src=x onerror="alert(1)"> & <script>'
        data={'rows':[{'family':label}]}
        text=render(data)
        self.assertNotIn(label,text)
        embedded=text.split('<script type="application/json" id="data">')[1].split('</script>')[0]
        self.assertEqual(json.loads(embedded),data)
        self.assertEqual(render(data),text)
