"""Strict, bounded protocol IO and source/configuration freeze hashes."""
from dataclasses import fields
import hashlib
import json
from pathlib import Path
from .model import Settings

MAX_JSON = 2 * 1024 * 1024
RULES = {
    'generator': 'integer-renewal-bursty-periodic-v1',
    'scheduler': 'arrivals-before-service-fifo-drop-tail-fixed-drain-v1',
    'matcher': 'lag-search-normalized-byte-histogram-exact-L1-empty-distance-2-v1',
    'ties': 'expected-uniform-top1-midrank-v1',
    'uncertainty': 'paired-independent-seed-percentile-bootstrap-nearest-rank-v1',
    'controls': 'analytic-uniform-rank-and-unmodified-traces-v1',
}


def canonical(obj):
    return (json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def no_duplicates(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError(f'duplicate JSON key: {k}')
        result[k] = v
    return result


def load(path):
    with Path(path).open('rb') as f:
        raw = f.read(MAX_JSON + 1)
    if len(raw) > MAX_JSON:
        raise ValueError('JSON exceeds 2 MiB input limit')
    return json.loads(raw, object_pairs_hook=no_duplicates,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f'invalid JSON number {x}')))


def validate(config):
    if not isinstance(config, dict) or set(config) != {
        'schema', 'settings', 'families', 'candidate_sizes', 'development_seeds',
        'evaluation_seeds', 'bin_ms', 'lags_ms', 'bootstrap_samples', 'bootstrap_seed',
        'cpu_budget_seconds', 'rules'}:
        raise ValueError('protocol fields do not match schema')
    if config['schema'] != 1 or type(config['schema']) is not int or config['rules'] != RULES:
        raise ValueError('unsupported protocol version/rules')
    s = config['settings']
    if not isinstance(s, dict) or set(s) != {f.name for f in fields(Settings)}:
        raise ValueError('settings fields do not match schema')
    Settings(**s).validate()
    for key, lo, hi in [('bin_ms', 1, 60000), ('bootstrap_samples', 100, 5000),
                        ('bootstrap_seed', 0, 2**32-1), ('cpu_budget_seconds', 1, 1800)]:
        x = config[key]
        if type(x) is not int or not lo <= x <= hi:
            raise ValueError(f'invalid {key}')
    lags = config['lags_ms']
    if (not isinstance(lags, list) or not 1 <= len(lags) <= 8
            or any(type(x) is not int or not 0 <= x <= 2000 for x in lags)
            or lags != sorted(set(lags)) or lags[0] != 0):
        raise ValueError('invalid lags_ms')
    for key, lo, hi, count in [('candidate_sizes', 2, 32, 4),
                              ('development_seeds', 0, 2**32-1, 20),
                              ('evaluation_seeds', 0, 2**32-1, 40)]:
        x = config[key]
        if (not isinstance(x, list) or not 1 <= len(x) <= count
                or any(type(v) is not int or not lo <= v <= hi for v in x)
                or len(set(x)) != len(x)):
            raise ValueError(f'invalid {key}')
    if set(config['development_seeds']) & set(config['evaluation_seeds']):
        raise ValueError('development and evaluation seeds overlap')
    families = config['families']
    if (not isinstance(families, list) or not 1 <= len(families) <= 3
            or any(x not in ('renewal', 'bursty', 'periodic') for x in families)
            or len(set(families)) != len(families)):
        raise ValueError('invalid families')
    trials = len(families) * len(config['candidate_sizes']) * max(
        len(config['development_seeds']), len(config['evaluation_seeds']))
    if trials > 256:
        raise ValueError('workload exceeds 256 trials')
    end = s['horizon_ms'] + s['drain_ms']
    # Conservative estimates cap event generation, raw storage, and matching work.
    max_events = max(s['horizon_ms'] // 40 + 2, 168)
    max_n = max(config['candidate_sizes'])
    if trials * max_n * (end // s['tick_ms'] + 1 + 3 * max_events) > 1500000:
        raise ValueError('workload exceeds 1.5 million estimated event records')
    if trials * max_n**2 * (end // config['bin_ms'] + 1) * len(lags) > 12000000:
        raise ValueError('workload exceeds 12 million matching bin comparisons')
    return config


def sources():
    return {p.name: digest(p.read_bytes()) for p in sorted(Path(__file__).parent.glob('*.py'))}


def frozen(config):
    validate(config)
    return {'schema': 1, 'config_sha256': digest(canonical(config)), 'source_sha256': sources()}


def write_json(path, obj):
    with Path(path).open('xb') as f:
        f.write(canonical(obj))
