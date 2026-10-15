"""Integer-time discrete-event simulator. Ground truth stays in this module."""
from collections import deque
from dataclasses import dataclass
import random


@dataclass(frozen=True)
class Settings:
    horizon_ms: int = 6000
    drain_ms: int = 2000
    capacity: int = 32
    batch_ms: int = 200
    tick_ms: int = 50
    cell_bytes: int = 512

    def validate(self):
        limits = {'horizon_ms': (1, 60000), 'drain_ms': (0, 60000),
                  'capacity': (1, 10000), 'batch_ms': (1, 60000),
                  'tick_ms': (1, 60000), 'cell_bytes': (1, 65536)}
        for name, (lo, hi) in limits.items():
            x = getattr(self, name)
            if type(x) is not int or not lo <= x <= hi:
                raise ValueError(f'invalid {name}: expected integer in [{lo}, {hi}]')
        if (self.horizon_ms + self.drain_ms) // self.tick_ms > 100000:
            raise ValueError('too many padded slots')


def generate(family, seed, n, settings):
    """Integer-only PRNG draws; no machine-dependent exponential sampling."""
    rng = random.Random(seed)
    flows = []
    for _ in range(n):
        times = []
        if family == 'renewal':
            t = rng.randrange(250)
            while t < settings.horizon_ms:
                times.append(t)
                t += rng.randint(40, 220)
        elif family == 'bursty':
            for _ in range(rng.randint(3, 6)):
                start = rng.randrange(settings.horizon_ms)
                times.extend(start + rng.randrange(100) for _ in range(rng.randint(12, 28)))
        elif family == 'periodic':
            period = rng.randint(40, 110)
            phase = rng.randrange(period)
            times = [max(0, t + rng.randint(-10, 10))
                     for t in range(phase, settings.horizon_ms, period)]
        else:
            raise ValueError('unknown traffic family')
        flows.append([[t, rng.choice([128, 256, 512])] for t in sorted(times)
                      if t < settings.horizon_ms])
    return flows


def validate_trace(trace, settings):
    if not isinstance(trace, list) or len(trace) > 10000:
        raise ValueError('trace must be a list of at most 10000 events')
    last = -1
    for event in trace:
        if (not isinstance(event, (list, tuple)) or len(event) != 2
                or any(type(v) is not int for v in event)):
            raise ValueError('events must be [integer timestamp_ms, integer bytes]')
        t, size = event
        if not last <= t < settings.horizon_ms or t < 0 or not 1 <= size <= settings.cell_bytes:
            raise ValueError('events must be ordered, within ingress horizon and cell size')
        last = t


def simulate(trace, policy, settings):
    settings.validate()
    validate_trace(trace, settings)
    if policy not in ('immediate', 'batch', 'padded'):
        raise ValueError('unknown forwarding policy')
    end = settings.horizon_ms + settings.drain_ms
    if policy == 'immediate':
        return {'departures': [[t, size, i] for i, (t, size) in enumerate(trace)],
                'dropped': [], 'queued': [], 'backlog_horizon': 0, 'max_backlog': 0}
    interval = settings.batch_ms if policy == 'batch' else settings.tick_ms
    q, departures, dropped = deque(), [], []
    i, slot, maximum, horizon_backlog = 0, 0, 0, None
    # Merge arrivals, periodic service and an explicit horizon marker. At equal
    # timestamps ALL arrivals precede service; snapshot follows service.
    while True:
        arrival = trace[i][0] if i < len(trace) else end + 1
        marker = settings.horizon_ms if horizon_backlog is None else end + 1
        t = min(arrival, slot, marker)
        if t > end:
            break
        while i < len(trace) and trace[i][0] == t:
            if len(q) == settings.capacity:
                dropped.append(i)
            else:
                q.append(i)
                maximum = max(maximum, len(q))
            i += 1
        if t == slot:
            if policy == 'batch':
                while q:
                    j = q.popleft()
                    departures.append([t, trace[j][1], j])
            else:
                j = q.popleft() if q else None
                departures.append([t, settings.cell_bytes, j])
            slot += interval
        if t == settings.horizon_ms:
            horizon_backlog = len(q)
    return {'departures': departures, 'dropped': dropped, 'queued': list(q),
            'backlog_horizon': horizon_backlog, 'max_backlog': maximum}


def observe(result):
    """Only time and wire size cross the observer boundary, including dummies."""
    return [[t, size] for t, size, _ in result['departures']]
