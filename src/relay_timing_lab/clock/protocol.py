"""Strict schema and independent freeze for the clock study."""
from pathlib import Path
from ..protocol import canonical, digest, sources
from ..model import Settings

RULES = {
    'clock': 'egress-only-affine-floor-ms-origin2000-common-across-flows-v1',
    'alignment': 'pairwise-min-exact-L1-affine-ingress-offset-includes-delay-v1',
    'ties': 'uniform-expected-top1-midrank-first-grid-hypothesis-v1',
    'uncertainty': '2000-percentile-bootstrap-independent-seed-paired-v1',
    'controls': 'synchronized-and-analytical-uniform-ranking-v1',
}


def validate(c):
    required = {'schema', 'settings', 'families', 'candidate_sizes', 'development_seeds',
                'evaluation_seeds', 'bin_ms', 'end_ms', 'lags_ms', 'offsets_ms', 'drifts_ppm',
                'conditions', 'bootstrap_samples', 'bootstrap_seed', 'cpu_budget_seconds',
                'max_comparisons', 'rules'}
    if not isinstance(c, dict) or set(c) != required or c['schema'] != 'clock-v1' or c['rules'] != RULES:
        raise ValueError('unsupported clock protocol')
    if c['settings'] != dict(Settings().__dict__):
        raise ValueError('clock v1 fixes historical traffic settings')
    if c['families'] != ['renewal', 'bursty', 'periodic'] or c['candidate_sizes'] != [4, 12]:
        raise ValueError('clock v1 fixes families and sizes')
    for key, lo, hi in [('bin_ms', 200, 200), ('end_ms', 12000, 12000),
                        ('bootstrap_samples', 2000, 2000), ('bootstrap_seed', 0, 2**32-1),
                        ('cpu_budget_seconds', 1, 1800), ('max_comparisons', 1, 400000)]:
        if type(c[key]) is not int or not lo <= c[key] <= hi:
            raise ValueError('invalid ' + key)
    for key, count in [('development_seeds', 3), ('evaluation_seeds', 20)]:
        values = c[key]
        if (not isinstance(values, list) or len(values) != count
                or any(type(x) is not int or not 2000 <= x < 2**32 for x in values)
                or values != sorted(set(values))):
            raise ValueError('invalid ' + key)
    if set(c['development_seeds']) & set(c['evaluation_seeds']):
        raise ValueError('seed sets overlap')
    if c['lags_ms'] != [0, 100, 200, 400, 800, 1600]:
        raise ValueError('legacy lags must be preserved')
    if c['offsets_ms'] not in [list(range(-800, 2401, 100)), list(range(-800, 2401, 200))]:
        raise ValueError('unsupported development grid')
    if c['drifts_ppm'] != [-20000, 0, 20000]:
        raise ValueError('unsupported drift grid')
    if c['conditions'] != ['synchronized', 'offset', 'offset_drift']:
        raise ValueError('unsupported conditions')
    return c


def frozen(c):
    validate(c)
    files = dict(sources())
    files.update({'clock/' + p.name: digest(p.read_bytes())
                  for p in sorted(Path(__file__).parent.glob('*.py'))})
    return {'schema': 'clock-v1', 'config_sha256': digest(canonical(c)), 'source_sha256': files}
