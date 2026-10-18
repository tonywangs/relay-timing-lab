"""Run with python -m relay_timing_lab.clock; no historical CLI changes."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import platform
import resource
import shutil
import signal
import sys
import time
from ..cli import Cancelled, interrupt
from ..protocol import load, write_json, digest
from .protocol import validate, frozen
from .experiment import execute


def run(args):
    c = validate(load(args.config))
    f = frozen(c)
    if load(args.freeze) != f:
        raise ValueError('freeze mismatch')
    out = Path(args.output).absolute()
    start, cpu = time.perf_counter(), time.process_time()
    budget = c['cpu_budget_seconds']
    before = {p: digest(Path(p).read_bytes()) for p in (args.config, args.freeze)}
    def check():
        if time.process_time()-cpu >= budget or time.perf_counter()-start >= budget:
            raise Cancelled('execution budget exceeded')
    handlers = {}
    timers = {}
    out.mkdir()
    try:
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGALRM, signal.SIGVTALRM):
            handlers[sig] = signal.signal(sig, interrupt)
        for timer in (signal.ITIMER_REAL, signal.ITIMER_VIRTUAL):
            timers[timer] = signal.setitimer(timer, budget)
        execute(c, f, out, args.phase, check)
        check()
        if any(digest(Path(p).read_bytes()) != h for p,h in before.items()):
            raise ValueError('input changed during experiment')
        m = load(out/'manifest.json')
        import gzip, json
        times = json.loads(gzip.decompress((out/'measurements.json.gz').read_bytes()))
        aggregates = {name: {'calls': sum(r['matcher']==name for r in times),
            'cpu_seconds': sum(r['cpu_ns'] for r in times if r['matcher']==name)/1e9,
            'elapsed_seconds': sum(r['elapsed_ns'] for r in times if r['matcher']==name)/1e9}
            for name in ('legacy','aligned','random')}
        write_json(out/'runtime.json', dict(python=platform.python_version(), platform=platform.platform(),
            dependencies='Python standard library only', finished_utc=datetime.now(timezone.utc).isoformat(),
            elapsed_seconds=time.perf_counter()-start, process_cpu_seconds=time.process_time()-cpu,
            peak_process_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss//(1024 if sys.platform=='darwin' else 1),
            deterministic_artifact_bytes=m['artifact_bytes'], deterministic_artifact_files=len(m['files']),
            measurements_sha256=digest((out/'measurements.json.gz').read_bytes()), matcher_runtime=aggregates,
            measurement_scope='whole process RSS; execution through manifests; matcher calls exclude evaluation scoring'))
    except BaseException:
        shutil.rmtree(out)
        raise
    finally:
        for timer, previous in timers.items(): signal.setitimer(timer, *previous)
        for sig, handler in handlers.items(): signal.signal(sig, handler)
    print(f'Completed {args.phase}: {out}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    f = sub.add_parser('freeze'); f.add_argument('--config', required=True); f.add_argument('--output', required=True)
    r = sub.add_parser('run')
    for name in ('config','freeze','output'): r.add_argument('--'+name, required=True)
    r.add_argument('--phase', choices=['development','evaluation'], default='evaluation')
    args = parser.parse_args(argv)
    try:
        if args.command == 'freeze': write_json(args.output, frozen(validate(load(args.config))))
        else: run(args)
    except Cancelled as exc:
        print(str(exc), file=sys.stderr); return 130
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        print(str(exc), file=sys.stderr); return 2
    return 0

if __name__ == '__main__': sys.exit(main())
