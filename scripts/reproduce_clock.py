#!/usr/bin/env python3
"""One-command offline final evaluation replay and byte-for-byte verification."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix='relay-clock-replay-') as tmp:
        work=Path(tmp);out=work/'evaluation';audit=work/'audit';audit.mkdir()
        (audit/'sitecustomize.py').write_text('import sys\ndef deny(event,args):\n if event in ("socket.connect","socket.bind","socket.getaddrinfo"):\n  raise RuntimeError("offline experiment")\nsys.addaudithook(deny)\n')
        env={**os.environ,'PYTHONPATH':os.pathsep.join([str(audit),str(ROOT/'src')]),'PYTHONNOUSERSITE':'1'}
        subprocess.run([sys.executable,'-m','relay_timing_lab.clock','run','--config',str(ROOT/'experiment/clock/protocol.json'),
                        '--freeze',str(ROOT/'experiment/clock/freeze.json'),'--output',str(out)],env=env,check=True)
        reference=ROOT/'results/clock-evaluation'
        manifest=json.loads((reference/'manifest.json').read_text())
        assert json.loads((out/'manifest.json').read_text())==manifest
        for name in manifest['files']:assert (out/name).read_bytes()==(reference/name).read_bytes(),name
        print(json.dumps({'status':'passed','deterministic_artifacts':len(manifest['files']),
                          'network':'socket audit denied','runtime':json.loads((out/'runtime.json').read_text())},indent=2))

if __name__=='__main__':main()
