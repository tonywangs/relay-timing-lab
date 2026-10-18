"""Paired clock trials, preserved observer evidence and run-level uncertainty."""
import gzip
import random
import time
from pathlib import Path
from ..experiment import derived_seed, METRICS
from ..metrics import matching, delivery, interval
from ..model import Settings, generate, simulate, observe
from ..protocol import canonical, digest, write_json
from .core import ORIGIN, transform, aligned, legacy
from .report import render

POLICIES = ('immediate', 'batch', 'padded')
MATCHERS = ('legacy', 'aligned', 'random')


def clock_parameters(seed, family, condition):
    rng = random.Random(derived_seed(seed, family, 'clock-v1'))
    offset = rng.choice([-1, 1]) * rng.randint(250, 750)
    drift = rng.choice([-1, 1]) * rng.randint(5000, 18000)
    return (0 if condition == 'synchronized' else offset,
            drift if condition == 'offset_drift' else 0)


def trial(c, seed, family, n, check=lambda: None):
    s = Settings(**c['settings'])
    traces = generate(family, derived_seed(seed, family, 'clock-traffic-v1'), n, s)
    ingress = [[[t + ORIGIN, b] for t, b in tr] for tr in traces]
    order = list(range(n))
    random.Random(derived_seed(seed, family, f'clock-order-{n}')).shuffle(order)
    truth = [order.index(i) for i in range(n)]
    raw = {'seed': seed, 'family': family, 'candidates': n, 'truth_indices': truth,
           'egress_order': order, 'ingress_observed': ingress, 'policies': {}, 'rows': []}
    measurements = []
    for policy in POLICIES:
        results = [simulate(tr, policy, s) for tr in traces]
        costs = delivery(traces, results)
        original = [[[t + ORIGIN, b] for t, b in observe(results[i])] for i in order]
        record = {'results_in_ingress_order': results, 'conditions': {}}
        raw['policies'][policy] = record
        for condition in c['conditions']:
            check()
            offset, drift = clock_parameters(seed, family, condition)
            public = [transform(tr, offset, drift) for tr in original]
            cr = {'true_offset_ms': offset, 'true_drift_ppm': drift,
                  'egress_observed': public, 'matchers': {}}
            record['conditions'][condition] = cr
            for matcher in MATCHERS:
                common = dict(seed=seed, family=family, candidates=n, policy=policy,
                              condition=condition, matcher=matcher)
                start, cpu = time.perf_counter_ns(), time.process_time_ns()
                if matcher == 'legacy':
                    scores = legacy(ingress, public, c['bin_ms'], c['end_ms'], c['lags_ms'])
                    winners, work = None, n*n*len(c['lags_ms'])
                elif matcher == 'aligned':
                    scores, winners, work = aligned(ingress, public, c['bin_ms'], c['end_ms'],
                        c['offsets_ms'], c['drifts_ppm'], c['max_comparisons'], check)
                else:
                    scores, winners, work = None, None, 0
                measurements.append({**common, 'elapsed_ns': time.perf_counter_ns()-start,
                                     'cpu_ns': time.process_time_ns()-cpu})
                if scores is None:
                    match = {'top1': 1/n, 'rank': (n+1)/2,
                             'per_flow': [{'top1': 1/n, 'rank': (n+1)/2, 'ties': n} for _ in traces]}
                else:
                    match = matching(scores, truth)
                cr['matchers'][matcher] = {'scores': None if scores is None else
                    [[[x.numerator, x.denominator] for x in r] for r in scores],
                    'winning_hypotheses': winners, 'matching': match, 'comparisons': work}
                raw['rows'].append({**common, 'top1': match['top1'], 'rank': match['rank'],
                                    'comparisons': work, **costs})
    return {'seed': seed, 'family': family, 'candidates': n, 'traces': traces}, raw, measurements


def summarize(rows, c):
    groups, paired = [], []
    cache = {}
    def ci(values, family, n):
        seed = derived_seed(c['bootstrap_seed'], family, str(n))
        key = (tuple(values), seed)
        if key not in cache:
            cache[key] = interval(values, c['bootstrap_samples'], seed)
        return cache[key]
    for family in c['families']:
        for n in c['candidate_sizes']:
            for policy in POLICIES:
                for condition in c['conditions']:
                    for matcher in MATCHERS:
                        common = dict(family=family, candidates=n, policy=policy,
                                      condition=condition, matcher=matcher)
                        subset = sorted([r for r in rows if all(r[k] == v for k,v in common.items())],
                                        key=lambda r: r['seed'])
                        groups.append({**common, 'metrics': {
                            key: ci([r[key] for r in subset if r[key] is not None], family, n)
                            for key in (*METRICS, 'comparisons')}})
                        references = []
                        if matcher == 'aligned': references.append(('aligned_minus_legacy', {'matcher': 'legacy'}))
                        if condition != 'synchronized': references.append(('clock_minus_synchronized', {'condition': 'synchronized'}))
                        if policy != 'immediate': references.append(('policy_minus_immediate', {'policy': 'immediate'}))
                        for comparison, override in references:
                            ref = {**common, **override}
                            base = {r['seed']: r for r in rows if all(r[k] == v for k,v in ref.items())}
                            paired.append({**common, 'comparison': comparison, 'metrics': {
                                key: ci([r[key]-base[r['seed']][key] for r in subset
                                         if r[key] is not None and base[r['seed']][key] is not None], family, n)
                                for key in ('top1', 'rank', 'delay_p95_ms', 'byte_ratio', 'undelivered')}})
    return groups, paired


def execute(c, freeze, out, phase, check):
    out = Path(out)
    (out/'inputs').mkdir()
    (out/'raw').mkdir()
    write_json(out/'protocol.json', c)
    write_json(out/'freeze.json', freeze)
    rows, measurements = [], []
    for seed in c[phase+'_seeds']:
        for family in c['families']:
            for n in c['candidate_sizes']:
                check()
                name = f'{family}-{n}-{seed}'
                inputs, raw, times = trial(c, seed, family, n, check)
                payload = canonical(inputs)
                (out/'inputs'/f'{name}.json').write_bytes(payload)
                raw['input_sha256'] = digest(payload)
                raw['config_sha256'] = freeze['config_sha256']
                (out/'raw'/f'{name}.json.gz').write_bytes(gzip.compress(canonical(raw), mtime=0))
                rows.extend(raw['rows'])
                measurements.extend(times)
    check()
    groups, paired = summarize(rows, c)
    summary = dict(schema='clock-v1', phase=phase, config_sha256=freeze['config_sha256'],
                   seeds=c[phase+'_seeds'], rows=rows, groups=groups, paired=paired)
    write_json(out/'summary.json', summary)
    (out/'report.html').write_text(render(summary))
    check()
    files = {str(p.relative_to(out)): {'sha256': digest(p.read_bytes()), 'bytes': p.stat().st_size}
             for p in sorted(out.rglob('*')) if p.is_file()}
    write_json(out/'manifest.json', {'schema': 'clock-v1', 'files': files,
                                    'artifact_bytes': sum(v['bytes'] for v in files.values())})
    # Real timing samples cannot be byte-reproducible. Preserve them separately.
    (out/'measurements.json.gz').write_bytes(gzip.compress(canonical(measurements), mtime=0))
    return summary
