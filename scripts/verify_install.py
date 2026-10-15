#!/usr/bin/env python3
"""Build and exercise the installed CLI in a clean venv, with sockets denied.

Supply an offline wheelhouse containing pip, setuptools and wheel (see README).
No third-party packages are needed by the resulting application.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheelhouse',type=Path,required=True)
    args=parser.parse_args()
    wheels=[next(args.wheelhouse.absolute().glob(name+'-*.whl'),None) for name in ('pip','setuptools','wheel')]
    if any(x is None for x in wheels): parser.error('wheelhouse needs pip, setuptools and wheel')
    with tempfile.TemporaryDirectory(prefix='relay-installed-') as tmp:
        work=Path(tmp);source=work/'source';source.mkdir()
        shutil.copytree(ROOT/'src',source/'src',ignore=shutil.ignore_patterns('__pycache__','*.egg-info'))
        shutil.copy(ROOT/'pyproject.toml',source/'pyproject.toml')
        audit=work/'audit';audit.mkdir()
        (audit/'sitecustomize.py').write_text('import sys\ndef deny(event, args):\n    if event in ("socket.connect", "socket.getaddrinfo", "socket.bind"):\n        raise RuntimeError("network disabled during installed verification")\nsys.addaudithook(deny)\n')
        build_tools=work/'build-tools';build_tools.mkdir()
        for wheel in wheels:
            with zipfile.ZipFile(wheel) as archive: archive.extractall(build_tools)
        env={**os.environ,'PYTHONPATH':os.pathsep.join([str(audit),str(build_tools)]),
             'PIP_NO_INDEX':'1','PIP_CACHE_DIR':str(work/'cache'),'PIP_DISABLE_PIP_VERSION_CHECK':'1','PYTHONNOUSERSITE':'1'}
        def run(command,environment=env):
            result=subprocess.run(list(map(str,command)),cwd=work,env=environment,
                                  capture_output=True,text=True)
            if result.returncode:
                raise RuntimeError(f'{command!r} failed:\n{result.stdout}\n{result.stderr}')
            return result
        run([sys.executable,'-m','venv','--without-pip',work/'venv'])
        python=work/'venv/bin/python';wheelout=work/'wheels'
        run([python,'-m','pip','wheel','--no-index','--no-deps','--no-build-isolation','--wheel-dir',wheelout,source])
        wheel=next(wheelout.glob('relay_timing_lab-*.whl'))
        run([python,'-m','pip','install','--no-index','--no-deps',wheel])
        runtime_env={**env,'PYTHONPATH':str(audit)}
        location=run([python,'-c','import relay_timing_lab; print(relay_timing_lab.__file__)'],runtime_env).stdout.strip()
        assert str(work/'venv') in location, location
        # Prove that the runtime network guard is active in this environment.
        probe=run([python,'-c','import socket\ntry: socket.create_connection(("127.0.0.1",1))\nexcept RuntimeError: print("blocked")'],runtime_env)
        assert probe.stdout.strip()=='blocked'
        cli=work/'venv/bin/relay-timing-lab'
        run([cli,'run','--config',ROOT/'experiment/protocol.json','--freeze',ROOT/'experiment/freeze.json',
             '--phase','development','--output',work/'experiment'],runtime_env)
        summary=json.loads((work/'experiment/summary.json').read_text())
        assert len(summary['rows'])==90
        assert all(r['top1']==1 for r in summary['rows'] if r['policy']=='unmodified')
        assert all(r['top1']==1/r['candidates'] for r in summary['rows'] if r['policy']=='padded')
        print(json.dumps({'status':'passed','build_wheels':[p.name for p in wheels],
              'isolated_import':True,'network':'socket audit denied; pip --no-index',
              'phase':'development','rows':len(summary['rows']),
              'runtime':json.loads((work/'experiment/runtime.json').read_text())},indent=2))

if __name__=='__main__': main()
