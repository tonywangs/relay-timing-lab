"""Offline command line with strict limits, exclusive outputs and cleanup."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import resource
import shutil
import signal
import sys
import time
from . import __version__
from .experiment import execute
from .protocol import load, validate, frozen, write_json, digest


class Cancelled(Exception):
    pass


def interrupt(signum, frame):
    raise Cancelled(f'cancelled by signal {signum}')


def run(args):
    config = validate(load(args.config))
    expected = frozen(config)
    if load(args.freeze) != expected:
        raise ValueError('freeze mismatch: config or implementation changed; create a new freeze')
    out = Path(args.output).absolute()
    if not out.parent.is_dir():
        raise ValueError('output parent must exist')
    started, cpu = time.perf_counter(), time.process_time()
    handlers = {}
    old_timer = None
    budget = config['cpu_budget_seconds']
    input_before = {str(Path(p).absolute()): digest(Path(p).read_bytes()) for p in (args.config, args.freeze)}
    def check():
        if time.process_time() - cpu >= budget or time.perf_counter() - started >= budget:
            raise Cancelled('execution budget exceeded')
    # mkdir is an exclusive reservation: existing paths (including symlinks) are
    # never overwritten. Only this invocation's newly created tree is removed.
    out.mkdir()
    try:
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGALRM, signal.SIGVTALRM):
            handlers[sig] = signal.signal(sig, interrupt)
        old_timer = signal.setitimer(signal.ITIMER_REAL, budget)
        signal.setitimer(signal.ITIMER_VIRTUAL, budget)
        execute(config, expected, out, args.phase, check)
        check()
        for p, before in input_before.items():
            if digest(Path(p).read_bytes()) != before:
                raise ValueError('input hash changed during experiment')
        manifest = load(out / 'manifest.json')
        write_json(out / 'runtime.json', {
            'version': __version__, 'python': platform.python_version(),
            'implementation': platform.python_implementation(), 'platform': platform.platform(),
            'dependencies': 'Python standard library only',
            'finished_utc': datetime.now(timezone.utc).isoformat(),
            'elapsed_seconds': time.perf_counter() - started,
            'process_cpu_seconds': time.process_time() - cpu,
            'peak_process_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                // (1024 if sys.platform == 'darwin' else 1),
            'deterministic_artifact_bytes': manifest['artifact_bytes'],
            'deterministic_artifact_files': len(manifest['files']),
            'measurement_scope': 'whole CLI process peak RSS; execution elapsed/CPU through deterministic artifact manifest; runtime and manifest bytes excluded from artifact total'})
    except BaseException:
        shutil.rmtree(out)
        raise
    finally:
        if old_timer is not None:
            signal.setitimer(signal.ITIMER_REAL, *old_timer)
            signal.setitimer(signal.ITIMER_VIRTUAL, 0)
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
    print(f'Completed {args.phase}: {out / "report.html"}')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline synthetic relay experiment (not a security protocol)')
    sub = parser.add_subparsers(dest='command', required=True)
    freeze = sub.add_parser('freeze', help='hash protocol and exact implementation before evaluation')
    freeze.add_argument('--config', required=True)
    freeze.add_argument('--output', required=True)
    experiment = sub.add_parser('run', help='run a frozen experiment into a new output directory')
    experiment.add_argument('--config', required=True)
    experiment.add_argument('--freeze', required=True)
    experiment.add_argument('--output', required=True)
    experiment.add_argument('--phase', choices=['development', 'evaluation'], default='evaluation')
    args = parser.parse_args(argv)
    try:
        if args.command == 'freeze':
            write_json(args.output, frozen(validate(load(args.config))))
            print(f'Frozen: {args.output}')
        else:
            run(args)
    except Cancelled as exc:
        print(str(exc), file=sys.stderr)
        return 130
    except (ValueError, OSError, TypeError, KeyError, RecursionError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    return 0
