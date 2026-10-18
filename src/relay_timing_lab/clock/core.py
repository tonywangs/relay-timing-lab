"""Pure observer transformation and label-free, bounded alignment search."""
from fractions import Fraction
from ..matcher import score_matrix

ORIGIN = 2000
PPM = 1000000


def transform(trace, offset_ms=0, drift_ppm=0):
    """Floor affine time to milliseconds. Input uses the shared numeric origin.

    Return fresh records, retaining collisions and sizes. No relay state enters.
    """
    if type(offset_ms) is not int or not -800 <= offset_ms <= 2400:
        raise ValueError('offset outside supported bounds')
    if type(drift_ppm) is not int or not -20000 <= drift_ppm <= 20000:
        raise ValueError('drift outside supported bounds')
    return [[ORIGIN + offset_ms + (t - ORIGIN) * (PPM + drift_ppm) // PPM, size]
            for t, size in trace]


def validate_observations(flows):
    if not isinstance(flows, list) or not 1 <= len(flows) <= 32:
        raise ValueError('expected 1..32 traces')
    for trace in flows:
        if not isinstance(trace, list) or len(trace) > 10000:
            raise ValueError('too many events')
        last = -1
        for event in trace:
            if (not isinstance(event, (list, tuple)) or len(event) != 2
                    or any(type(v) is not int for v in event)):
                raise ValueError('observer records must contain only integer time and size')
            t, size = event
            if not 0 <= t <= 12000 or t < last or not 1 <= size <= 65536:
                raise ValueError('invalid observer event')
            last = t


def histogram(trace, bin_ms, end_ms):
    # Explicit clipping on both ends; guards prevent clipping in frozen runs.
    bins = [0] * (end_ms // bin_ms + 1)
    for t, size in trace:
        if 0 <= t <= end_ms:
            bins[t // bin_ms] += size
    return tuple(bins)


def aligned(ingress, egress, bin_ms, end_ms, offsets, drifts, max_comparisons,
            check=lambda: None):
    """Minimum exact normalized L1 per pair over affine ingress hypotheses.

    Offsets represent combined clock displacement and relay delay, not a clock
    estimator. Tied hypotheses use offset-major, drift-minor traversal order.
    Exceeding the deterministic work limit fails, never returns partial scores.
    """
    validate_observations(ingress)
    validate_observations(egress)
    if (type(bin_ms) is not int or not 1 <= bin_ms <= 1000
            or type(end_ms) is not int or not 1 <= end_ms <= 12000):
        raise ValueError('invalid histogram bounds')
    if (not offsets or not drifts or len(offsets) > 65 or len(drifts) > 5
            or offsets != sorted(set(offsets)) or drifts != sorted(set(drifts))):
        raise ValueError('invalid alignment grid')
    for off in offsets:
        for drift in drifts:
            transform([], off, drift)
    work = len(ingress) * len(egress) * len(offsets) * len(drifts)
    if type(max_comparisons) is not int or not 1 <= max_comparisons <= 400000:
        raise ValueError('invalid comparison budget')
    if work > max_comparisons:
        raise ValueError('alignment comparison budget exhausted')
    targets = [histogram(tr, bin_ms, end_ms) for tr in egress]
    scores, winners = [], []
    # Deduplicate identical public histograms (not identities). This matters for
    # fixed padding; declared work remains the conservative pre-dedup count.
    for trace in ingress:
        check()
        variants = []
        seen = set()
        for off in offsets:
            for drift in drifts:
                h = histogram(transform(trace, off, drift), bin_ms, end_ms)
                if h not in seen:
                    variants.append((h, sum(h), [off, drift]))
                    seen.add(h)
        cache = {}
        row, wr = [], []
        for target in targets:
            check()
            if target not in cache:
                total = sum(target)
                best = None
                winner = None
                for h, mass, hypothesis in variants:
                    if not mass or not total:
                        score = Fraction(0 if mass == total else 2)
                    else:
                        score = Fraction(sum(abs(x * total - y * mass)
                                             for x, y in zip(h, target)), mass * total)
                    if best is None or score < best:
                        best, winner = score, hypothesis
                cache[target] = (best, winner)
            score, winner = cache[target]
            row.append(score)
            wr.append(winner)
        scores.append(row)
        winners.append(wr)
    return scores, winners, work


def legacy(ingress, egress, bin_ms, end_ms, lags):
    validate_observations(ingress)
    validate_observations(egress)
    return score_matrix(ingress, egress, bin_ms, end_ms, lags)
