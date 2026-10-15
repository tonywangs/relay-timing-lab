#!/usr/bin/env python3
"""One-command offline reproduction and byte comparison to preserved evidence."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def reproduce(out):
    env={**os.environ,'PYTHONPATH':str(ROOT/'src'),'PYTHONNOUSERSITE':'1'}
    subprocess.run([sys.executable,'-m','relay_timing_lab','run',
                    '--config',str(ROOT/'experiment/protocol.json'),
                    '--freeze',str(ROOT/'experiment/freeze.json'),'--output',str(out)],env=env,check=True)
    reference=ROOT/'results/evaluation'
    expected=json.loads((reference/'manifest.json').read_text())
    actual=json.loads((out/'manifest.json').read_text())
    assert actual==expected,'deterministic artifact manifest differs'
    for name in expected['files']:
        assert (out/name).read_bytes()==(reference/name).read_bytes(),name
    print(f"PASS: {len(expected['files'])} deterministic artifacts reproduced byte-for-byte")
    print((out/'runtime.json').read_text())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,help='new directory to retain; default uses and removes a temporary directory')
    args=parser.parse_args()
    if args.output: reproduce(args.output.absolute())
    else:
        with tempfile.TemporaryDirectory(prefix='relay-reproduce-') as tmp: reproduce(Path(tmp)/'evaluation')

if __name__=='__main__': main()
