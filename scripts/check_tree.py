#!/usr/bin/env python3
"""Check the publishable tracked/unignored tree against artifact size limits."""
import json
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
raw=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=root)
names=sorted(set(x.decode() for x in raw.split(b'\0') if x))
assert len(names)<=1000,f'too many files: {len(names)}'
total=0;largest=(0,'')
for name in names:
    p=root/name
    assert p.is_file() and not p.is_symlink(),f'not a regular file: {name}'
    assert not name.endswith('.log') or name=='results/tests.log',f'unpublishable log: {name}'
    assert not any(part in ('.git','.agents','.codex','__pycache__') for part in p.relative_to(root).parts),name
    size=p.stat().st_size
    assert size<=10*1024*1024,f'file exceeds 10 MiB: {name}'
    total+=size;largest=max(largest,(size,name))
assert total<=32*1024*1024,f'tree exceeds 32 MiB: {total}'
print(json.dumps({'status':'passed','files':len(names),'bytes':total,
                  'largest_file':largest[1],'largest_file_bytes':largest[0]},indent=2))
