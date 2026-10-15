"""Evaluation side: ground truth is available here, never to the matcher."""
import math
import random
import statistics


def quantile(values, p):
    """Nearest-rank empirical quantile; empty delivered sets have null latency."""
    return sorted(values)[max(0, math.ceil(p * len(values)) - 1)] if values else None


def matching(scores, truth):
    rows = []
    for i, row in enumerate(scores):
        true_score = row[truth[i]]
        better = sum(x < true_score for x in row)
        equal = sum(x == true_score for x in row)
        rows.append({'top1': 1 / equal if better == 0 else 0.0,
                     'rank': better + (equal + 1) / 2, 'ties': equal})
    return {'top1': statistics.mean(x['top1'] for x in rows),
            'rank': statistics.mean(x['rank'] for x in rows), 'per_flow': rows}


def delivery(traces, results):
    delays, sent, dummy, real_wire, payload = [], 0, 0, 0, 0
    delivered = dropped = queued = horizon = maximum = 0
    for trace, result in zip(traces, results):
        seen = []
        for t, size, j in result['departures']:
            sent += size
            if j is None:
                dummy += size
            else:
                seen.append(j)
                delivered += 1
                real_wire += size
                payload += trace[j][1]
                delays.append(t - trace[j][0])
        seen += result['queued'] + result['dropped']
        if sorted(seen) != list(range(len(trace))):
            raise ValueError('event accounting violated')
        dropped += len(result['dropped'])
        queued += len(result['queued'])
        horizon += result['backlog_horizon']
        maximum = max(maximum, result['max_backlog'])
    input_bytes = sum(size for tr in traces for _, size in tr)
    return {'input_events': sum(map(len, traces)), 'input_bytes': input_bytes,
            'delivered': delivered, 'dropped': dropped, 'queued': queued,
            'undelivered': dropped + queued, 'backlog_horizon': horizon,
            'max_backlog_per_flow': maximum, 'transmitted_bytes': sent,
            'dummy_bytes': dummy, 'real_wire_bytes': real_wire,
            'delivered_payload_bytes': payload, 'size_padding_bytes': real_wire - payload,
            'byte_ratio': sent / input_bytes if input_bytes else None,
            'delay_p50_ms': quantile(delays, .5), 'delay_p95_ms': quantile(delays, .95),
            'delay_p99_ms': quantile(delays, .99), 'delay_max_ms': max(delays, default=None)}


def interval(values, samples, seed):
    """Percentile bootstrap over independent runs, NOT packets or flows."""
    if not values:
        return {'mean': None, 'low': None, 'high': None, 'n': 0}
    rng = random.Random(seed)
    means = [statistics.mean(rng.choices(values, k=len(values))) for _ in range(samples)]
    return {'mean': statistics.mean(values), 'low': quantile(means, .025),
            'high': quantile(means, .975), 'n': len(values)}
