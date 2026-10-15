"""Reproducible experiment runner and independent-run aggregation."""
import gzip
import random
from pathlib import Path
from .matcher import score_matrix
from .metrics import matching, delivery, interval
from .model import Settings, generate, simulate, observe
from .protocol import canonical, digest, write_json
from .report import render

POLICIES = ('immediate', 'batch', 'padded', 'unmodified', 'random')
METRICS = ('top1', 'rank', 'input_events', 'input_bytes', 'delivered', 'dropped',
           'queued', 'undelivered', 'backlog_horizon', 'max_backlog_per_flow',
           'transmitted_bytes', 'dummy_bytes', 'real_wire_bytes',
           'delivered_payload_bytes', 'size_padding_bytes', 'byte_ratio',
           'delay_p50_ms', 'delay_p95_ms', 'delay_p99_ms', 'delay_max_ms')


def derived_seed(seed, family, purpose):
    return int(digest(canonical([seed, family, purpose]))[:16], 16)


def trial(config, seed, family, n):
    settings = Settings(**config['settings'])
    traces = generate(family, derived_seed(seed, family, 'traffic'), n, settings)
    # Candidate sizes share nested traffic within a seed, but are never pooled
    # as independent observations. Permutations contain no visible flow IDs.
    order = list(range(n))
    random.Random(derived_seed(seed, family, f'permutation-{n}')).shuffle(order)
    truth = [order.index(i) for i in range(n)]
    rows, raw = [], {}
    for policy in POLICIES:
        if policy in POLICIES[:3]:
            results = [simulate(tr, policy, settings) for tr in traces]
        else:
            # Unmodified control bypasses the relay scheduler entirely.
            results = [{'departures': [[t, b, i] for i, (t, b) in enumerate(tr)],
                        'dropped': [], 'queued': [], 'backlog_horizon': 0,
                        'max_backlog': 0} for tr in traces]
        public_egress = [observe(results[i]) for i in order]
        scores = score_matrix(traces, public_egress, config['bin_ms'],
                              settings.horizon_ms + settings.drain_ms, config['lags_ms'])
        match = matching(scores, truth)
        if policy == 'random':
            match = {'top1': 1/n, 'rank': (n+1)/2,
                     'per_flow': [{'top1': 1/n, 'rank': (n+1)/2, 'ties': n} for _ in traces]}
        row = {'seed': seed, 'family': family, 'candidates': n, 'policy': policy,
               'top1': match['top1'], 'rank': match['rank'], **delivery(traces, results)}
        rows.append(row)
        if policy in POLICIES[:3]:
            raw[policy] = {'results_in_ingress_order': results,
                           'scores': [[[x.numerator, x.denominator] for x in r] for r in scores],
                           'matching': match}
        else:
            raw[policy] = {'matching': match, 'cost_reference': 'immediate',
                           'note': 'analytical random ranking' if policy == 'random' else 'unmodified ingress traces'}
    return {'seed': seed, 'family': family, 'candidates': n, 'traces': traces}, {
        'egress_order': order, 'truth_indices': truth, 'policies': raw, 'rows': rows}


def summarize(rows, config):
    groups, paired = [], []
    for family in config['families']:
        for n in config['candidate_sizes']:
            base = {r['seed']: r for r in rows if r['family'] == family
                    and r['candidates'] == n and r['policy'] == 'immediate'}
            for policy in POLICIES:
                subset = [r for r in rows if r['family'] == family
                          and r['candidates'] == n and r['policy'] == policy]
                common = {'family': family, 'candidates': n, 'policy': policy}
                # Same bootstrap seed within each group/metric deliberately uses
                # the same resampling indices. Rows are always in seed order.
                seed = derived_seed(config['bootstrap_seed'], family, str(n))
                metrics = {key: interval([r[key] for r in subset if r[key] is not None],
                                         config['bootstrap_samples'], seed) for key in METRICS}
                groups.append({**common, 'metrics': metrics})
                if policy != 'immediate':
                    differences = {key: interval(
                        [r[key] - base[r['seed']][key] for r in subset
                         if r[key] is not None and base[r['seed']][key] is not None],
                        config['bootstrap_samples'], seed)
                        for key in ('top1', 'rank', 'delay_p95_ms', 'byte_ratio', 'undelivered')}
                    paired.append({**common, 'metrics': differences})
    return groups, paired


def execute(config, freeze, out, phase, check_budget):
    out = Path(out)
    (out / 'inputs').mkdir()
    (out / 'raw').mkdir()
    write_json(out / 'protocol.json', config)
    write_json(out / 'freeze.json', freeze)
    rows = []
    seeds = config[f'{phase}_seeds']
    for seed in seeds:
        for family in config['families']:
            for n in config['candidate_sizes']:
                check_budget()
                name = f'{family}-{n}-{seed}'
                inputs, outcome = trial(config, seed, family, n)
                input_data = canonical(inputs)
                (out / 'inputs' / f'{name}.json').write_bytes(input_data)
                outcome['input_sha256'] = digest(input_data)
                outcome['config_sha256'] = freeze['config_sha256']
                # Deterministic gzip shards keep raw evidence within tree limits.
                (out / 'raw' / f'{name}.json.gz').write_bytes(
                    gzip.compress(canonical(outcome), compresslevel=9, mtime=0))
                rows.extend(outcome['rows'])
    check_budget()
    groups, paired = summarize(rows, config)
    summary = {'schema': 1, 'phase': phase, 'config_sha256': freeze['config_sha256'],
               'seeds': seeds, 'rows': rows, 'groups': groups, 'paired': paired}
    write_json(out / 'summary.json', summary)
    (out / 'report.html').write_text(render(summary), encoding='utf-8')
    check_budget()
    # Runtime measurements are deliberately outside this deterministic manifest.
    files = {str(p.relative_to(out)): {'sha256': digest(p.read_bytes()), 'bytes': p.stat().st_size}
             for p in sorted(out.rglob('*')) if p.is_file()}
    write_json(out / 'manifest.json', {'schema': 1, 'files': files,
                                     'artifact_bytes': sum(v['bytes'] for v in files.values())})
    return summary
