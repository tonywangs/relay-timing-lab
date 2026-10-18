import contextlib
import io
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from relay_timing_lab.clock import __main__ as cli
from relay_timing_lab.clock.protocol import validate, frozen
from relay_timing_lab.protocol import load, canonical

ROOT=Path(__file__).resolve().parents[1]


class ClockCLITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.config=self.root/'config.json';self.freeze=self.root/'freeze.json'
        self.c=load(ROOT/'experiment/clock/protocol.json');self.save()

    def save(self):
        self.config.write_bytes(canonical(self.c));self.freeze.write_bytes(canonical(frozen(self.c)))

    def args(self,out):
        return ['run','--config',str(self.config),'--freeze',str(self.freeze),'--output',str(out),'--phase','development']

    def call(self,args):
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):return cli.main(args)

    def test_collision_and_freeze_mismatch(self):
        for kind in ('dir','file','symlink','dangling'):
            out=self.root/kind
            if kind=='dir':out.mkdir()
            elif kind=='file':out.write_text('keep')
            else:out.symlink_to(self.config if kind=='symlink' else self.root/'absent')
            self.assertEqual(self.call(self.args(out)),2)
            self.assertTrue(os.path.lexists(out))
        self.assertEqual((self.root/'file').read_text(),'keep')
        self.c['bootstrap_seed']+=1;self.config.write_bytes(canonical(self.c))
        self.assertEqual(self.call(self.args(self.root/'bad')),2)
        self.assertFalse((self.root/'bad').exists())

    def test_limits_malformed(self):
        for key,value in [('max_comparisons',0),('cpu_budget_seconds',1801),('bin_ms',1),
                          ('end_ms',100000),('candidate_sizes',[32]),('drifts_ppm',[1000000]),
                          ('evaluation_seeds',list(range(2000,2020)))]:
            c={**self.c,key:value}
            with self.assertRaises(ValueError):validate(c)
        for value in ('{','[]','{}','{"x":NaN}','{"x":1,"x":2}','x'*(2*1024*1024+1)):
            self.config.write_text(value)
            self.assertEqual(self.call(self.args(self.root/'bad')),2)
            self.assertFalse((self.root/'bad').exists())

    def test_failures_cleanup_and_inputs(self):
        out=self.root/'out'
        def fail(*args):
            (out/'partial').write_text('x');raise OSError('injected disk error')
        with patch.object(cli,'execute',fail):self.assertEqual(self.call(self.args(out)),2)
        self.assertFalse(out.exists())
        def mutate(*args):self.config.write_text('{}')
        with patch.object(cli,'execute',mutate):self.assertEqual(self.call(self.args(out)),2)
        self.assertFalse(out.exists())

    def test_wall_and_cpu_budget_cleanup(self):
        self.c['cpu_budget_seconds']=1;self.save()
        out=self.root/'out'
        with patch.object(cli,'execute',lambda *args:time.sleep(2)):
            self.assertEqual(self.call(self.args(out)),130)
        self.assertFalse(out.exists())
        def busy(*args):
            while True:sum(range(1000))
        with patch.object(cli,'execute',busy):self.assertEqual(self.call(self.args(out)),130)
        self.assertFalse(out.exists())

    def test_alignment_budget_cleanup(self):
        self.c['max_comparisons']=1;self.save()
        out=self.root/'out'
        self.assertEqual(self.call(self.args(out)),2)
        self.assertFalse(out.exists())

    def test_signal_cleanup_subprocess(self):
        for sig in (signal.SIGINT,signal.SIGTERM):
            out=self.root/str(sig)
            p=subprocess.Popen([sys.executable,'-m','relay_timing_lab.clock',*self.args(out)],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                deadline=time.monotonic()+10
                while not (out/'raw').exists() and p.poll() is None and time.monotonic()<deadline:time.sleep(.01)
                self.assertTrue((out/'raw').exists())
                p.send_signal(sig);stdout,stderr=p.communicate(timeout=10)
                self.assertEqual(p.returncode,130,stderr.decode());self.assertFalse(out.exists())
            finally:
                if p.poll() is None:p.kill();p.wait()
