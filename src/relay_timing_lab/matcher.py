"""Label-free matching: accepts only timestamp/size records, never simulation state."""
from fractions import Fraction


def features(trace, bin_ms, end_ms, lag_ms=0):
    bins = [0] * (end_ms // bin_ms + 1)
    for t, size in trace:
        if t + lag_ms <= end_ms:
            bins[(t + lag_ms) // bin_ms] += size
    return bins


def distance(a, b):
    """Exact L1 distance between normalized wire-byte histograms (0..2)."""
    sa, sb = sum(a), sum(b)
    if not sa or not sb:
        return Fraction(0 if sa == sb else 2)
    return Fraction(sum(abs(x * sb - y * sa) for x, y in zip(a, b)), sa * sb)


def score_matrix(ingress, egress, bin_ms, end_ms, lags_ms=(0,)):
    a = [[features(x, bin_ms, end_ms, lag) for lag in lags_ms] for x in ingress]
    b = [features(x, bin_ms, end_ms) for x in egress]
    return [[min(distance(shifted, y) for shifted in variants) for y in b] for variants in a]
