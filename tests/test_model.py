"""Independent tick-by-tick oracle, deliberately unlike the event scheduler."""
from dataclasses import asdict
from fractions import Fraction
import itertools
import math
import random
import statistics
import unittest
from relay_timing_lab.model import Settings, simulate, observe, generate
from relay_timing_lab.metrics import delivery, matching, interval, quantile
from relay_timing_lab.matcher import score_matrix, distance


def reference(trace, policy, s):
    waiting, departures, dropped = [], [], []
    peak = horizon = 0
    for t in range(s.horizon_ms + s.drain_ms + 1):
        for i, (arrival, size) in enumerate(trace):
            if arrival != t:
                continue
            if policy == 'immediate':
                departures.append([t, size, i])
            elif len(waiting) >= s.capacity:
                dropped.append(i)
            else:
                waiting.append(i)
                peak = max(peak, len(waiting))
        if policy == 'batch' and t % s.batch_ms == 0:
            departures.extend([t, trace[i][1], i] for i in waiting)
            waiting = []
        if policy == 'padded' and t % s.tick_ms == 0:
            i = waiting.pop(0) if waiting else None
            departures.append([t, s.cell_bytes, i])
        if t == s.horizon_ms:
            horizon = len(waiting)
    return dict(departures=departures, dropped=dropped, queued=waiting,
                backlog_horizon=horizon, max_backlog=peak)


def independent_metrics(trace, outcome):
    real = [(t, b, i) for t, b, i in outcome['departures'] if i is not None]
    delays = sorted(t - trace[i][0] for t, _, i in real)
    percentiles = {}
    for p in (50, 95, 99):
        index = (len(delays) * p + 99) // 100 - 1
        percentiles[f'delay_p{p}_ms'] = delays[index] if delays else None
    wire = sum(b for _, b, _ in outcome['departures'])
    payload = sum(trace[i][1] for _, _, i in real)
    input_bytes = sum(b for _, b in trace)
    return dict(input_events=len(trace), input_bytes=input_bytes, delivered=len(real),
                dropped=len(outcome['dropped']), queued=len(outcome['queued']),
                undelivered=len(outcome['dropped']) + len(outcome['queued']),
                backlog_horizon=outcome['backlog_horizon'],
                max_backlog_per_flow=outcome['max_backlog'], transmitted_bytes=wire,
                dummy_bytes=sum(b for _, b, i in outcome['departures'] if i is None),
                real_wire_bytes=sum(b for _, b, _ in real), delivered_payload_bytes=payload,
                size_padding_bytes=sum(b for _, b, _ in real)-payload,
                byte_ratio=wire / input_bytes if input_bytes else None,
                delay_max_ms=delays[-1] if delays else None, **percentiles)


class OracleTests(unittest.TestCase):
    def test_300_seeded_cases_all_policies_and_metrics(self):
        coverage = set()
        for seed in range(300):
            rng = random.Random(seed)
            s = Settings(horizon_ms=rng.randint(1, 40), drain_ms=rng.randint(0, 15),
                         capacity=rng.randint(1, 5), batch_ms=rng.randint(1, 12),
                         tick_ms=rng.randint(1, 12), cell_bytes=512)
            trace = sorted([[rng.randrange(s.horizon_ms), rng.choice([128, 256, 512])]
                            for _ in range(rng.randrange(35))], key=lambda x:x[0])
            for policy in ('immediate', 'batch', 'padded'):
                with self.subTest(seed=seed, policy=policy):
                    actual, expected = simulate(trace, policy, s), reference(trace, policy, s)
                    self.assertEqual(actual, expected)
                    self.assertEqual(delivery([trace], [actual]), independent_metrics(trace, expected))
                    ids = [i for _, _, i in actual['departures'] if i is not None]
                    self.assertEqual(sorted(ids + actual['queued'] + actual['dropped']), list(range(len(trace))))
                    self.assertEqual(ids, sorted(ids))
                    if not trace: coverage.add('empty')
                    if actual['queued']: coverage.add('queued')
                    if actual['dropped']: coverage.add('overload')
                    if any(i is None for _, _, i in actual['departures']): coverage.add('idle')
                    if len(set(t for t, _ in trace)) < len(trace): coverage.add('simultaneous')
        self.assertEqual(coverage, {'empty', 'queued', 'overload', 'idle', 'simultaneous'})

    def test_exact_boundary_and_drop_before_service(self):
        s = Settings(horizon_ms=10, drain_ms=0, capacity=1, batch_ms=5, tick_ms=5)
        trace = [[0, 128], [0, 256], [4, 512], [5, 128], [9, 256]]
        r = simulate(trace, 'padded', s)
        self.assertEqual(r['departures'], [[0, 512, 0], [5, 512, 2], [10, 512, 4]])
        self.assertEqual(r['dropped'], [1, 3])
        self.assertEqual(r['backlog_horizon'], 0)

    def test_fixed_padding_independent_of_trace(self):
        s = Settings(horizon_ms=30, drain_ms=7, tick_ms=5)
        self.assertEqual(observe(simulate([], 'padded', s)),
                         observe(simulate([[0, 128], [2, 512], [29, 256]], 'padded', s)))

    def test_300_seeded_matching_and_ties_by_enumeration(self):
        for seed in range(300):
            rng = random.Random(seed)
            n = rng.randint(2, 5)
            scores = [Fraction(rng.randrange(3)) for _ in range(n)]
            truth = rng.randrange(n)
            ranks = []
            # Average all possible independent tie-breaking orders, with no use
            # of the production better/equal-count formula.
            for order in itertools.permutations(range(n)):
                ranked = sorted(order, key=lambda i: scores[i])
                ranks.append(ranked.index(truth)+1)
            result = matching([scores], [truth])
            self.assertAlmostEqual(result['top1'], ranks.count(1)/len(ranks))
            self.assertEqual(result['rank'], statistics.mean(ranks))

    def test_scores_exact_and_label_free(self):
        self.assertEqual(distance([1, 1], [2, 2]), 0)
        self.assertEqual(distance([1, 0], [0, 1]), 2)
        self.assertEqual(distance([0, 0], [0, 0]), 0)
        self.assertEqual(distance([0, 0], [0, 1]), 2)
        # Third fields (event IDs or dummy indicators) cannot enter the matcher.
        with self.assertRaises(ValueError):
            score_matrix([[[0, 128, 'secret']]], [[[0, 128]]], 1, 2)
        self.assertEqual(score_matrix([[[0, 128]]], [[[1, 128]], [[0, 128]]], 1, 2), [[2, 0]])

    def test_causal_lag_search_recovers_shift(self):
        a=[[[0,128],[10,256]]]
        b=[[[5,128],[15,256]]]
        self.assertEqual(score_matrix(a,b,1,20,[0,5])[0][0],0)
        self.assertEqual(score_matrix(a,b,1,20,[0])[0][0],2)
        # Late shifts are clipped before normalization.
        self.assertEqual(score_matrix([[[19,128]]],[[]],1,20,[0,5])[0][0],0)

    def test_bootstrap_independent_calculation(self):
        values = [1, 2, 4, -2]
        rng = random.Random(123)
        means = sorted(sum(rng.choices(values, k=4))/4 for _ in range(200))
        self.assertEqual(interval(values, 200, 123),
                         {'mean': 1.25, 'low': means[4], 'high': means[194], 'n': 4})
        self.assertEqual(interval([], 100, 1)['mean'], None)
        self.assertEqual(quantile([], .95), None)
        self.assertEqual(quantile([5], .95), 5)

    def test_accounting_rejects_duplicates(self):
        result = simulate([[0,128]], 'immediate', Settings())
        result['queued'] = [0]
        with self.assertRaises(ValueError): delivery([[[0,128]]], [result])

    def test_generator_replay_and_nested_candidates(self):
        for family in ('renewal','bursty','periodic'):
            self.assertEqual(generate(family,42,4,Settings()),generate(family,42,12,Settings())[:4])

    def test_invalid_trace_and_settings(self):
        for trace in ([[1,128],[0,128]], [[6000,128]], [[0,513]], [[0,True]], [[float('nan'),128]], 'bad'):
            with self.assertRaises(ValueError): simulate(trace, 'batch', Settings())
        for s in (Settings(tick_ms=0),Settings(capacity=True),Settings(drain_ms=-1)):
            with self.assertRaises(ValueError): simulate([], 'padded', s)
