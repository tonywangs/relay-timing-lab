import contextlib
import copy
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
from relay_timing_lab import cli
from relay_timing_lab.protocol import load, validate, frozen, write_json, canonical, digest

ROOT = Path(__file__).resolve().parents[1]


def small_config():
    c = load(ROOT / 'experiment/protocol.json')
    c.update(families=['bursty'], candidate_sizes=[2], development_seeds=[1], evaluation_seeds=[100], bootstrap_samples=100)
    c['settings'].update(horizon_ms=100,drain_ms=10,tick_ms=10,batch_ms=20)
    return c


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root/'config.json'
        self.freeze = self.root/'freeze.json'
        write_json(self.config,small_config())
        write_json(self.freeze,frozen(small_config()))

    def args(self,out):
        return ['run','--config',str(self.config),'--freeze',str(self.freeze),'--output',str(out)]

    def call(self,args):
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            return cli.main(args)

    def test_deterministic_replay_inputs_unchanged_manifest(self):
        before = [self.config.read_bytes(),self.freeze.read_bytes()]
        a,b = self.root/'a',self.root/'b'
        self.assertEqual(self.call(self.args(a)),0)
        self.assertEqual(self.call(self.args(b)),0)
        self.assertEqual(load(a/'manifest.json'), load(b/'manifest.json'))
        for name, item in load(a/'manifest.json')['files'].items():
            self.assertEqual((a/name).read_bytes(),(b/name).read_bytes())
            self.assertEqual(digest((a/name).read_bytes()),item['sha256'])
        self.assertEqual(before,[self.config.read_bytes(),self.freeze.read_bytes()])

    def test_collision_directory_file_and_symlink(self):
        for kind in ('dir','file','symlink'):
            out = self.root/kind
            if kind=='dir': out.mkdir()
            elif kind=='file': out.write_text('keep')
            else: out.symlink_to(self.config)
            self.assertEqual(self.call(self.args(out)),2)
            self.assertTrue(out.exists())
        self.assertEqual((self.root/'file').read_text(),'keep')
        self.assertTrue((self.root/'symlink').is_symlink())

    def test_failure_cleanup(self):
        out = self.root/'out'
        def fail(*args):
            (out/'partial').write_text('temporary')
            raise OSError('injected disk error')
        with patch.object(cli,'execute',fail):
            self.assertEqual(self.call(self.args(out)),2)
        self.assertFalse(out.exists())

    def test_signal_cleanup_real_subprocess(self):
        c=load(ROOT/'experiment/protocol.json')
        self.config.write_bytes(canonical(c));self.freeze.write_bytes(canonical(frozen(c)))
        for sig in (signal.SIGINT,signal.SIGTERM):
            out=self.root/f'signal-{sig}'
            p=subprocess.Popen([sys.executable,'-m','relay_timing_lab',*self.args(out)],
                               stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                deadline=time.monotonic()+10
                while not (out/'raw').exists() and p.poll() is None and time.monotonic()<deadline:
                    time.sleep(.01)
                self.assertTrue((out/'raw').exists(),'subprocess did not start')
                p.send_signal(sig)
                stdout,stderr=p.communicate(timeout=10)
                self.assertEqual(p.returncode,130,stderr.decode())
                self.assertIn(b'cancelled',stderr)
                self.assertFalse(out.exists())
            finally:
                if p.poll() is None: p.kill();p.wait()

    def test_budget_cleanup(self):
        out=self.root/'budget'
        c=small_config();c['cpu_budget_seconds']=1
        self.config.write_bytes(canonical(c));self.freeze.write_bytes(canonical(frozen(c)))
        with patch.object(cli,'execute',lambda *args:time.sleep(2)):
            self.assertEqual(self.call(self.args(out)),130)
        self.assertFalse(out.exists())

    def test_freeze_mismatch(self):
        c=small_config();c['bin_ms']=100
        self.config.write_bytes(canonical(c))
        self.assertEqual(self.call(self.args(self.root/'bad')),2)
        self.assertFalse((self.root/'bad').exists())
        self.assertEqual(self.call(['freeze','--config',str(self.config),'--output',str(self.freeze)]),2)

    def test_malformed_and_limits(self):
        for data in ('{','{"schema":1,"schema":2}', '{"x":NaN}', '[]', '{}', 'x'*(2*1024*1024+1)):
            self.config.write_text(data)
            self.assertEqual(self.call(self.args(self.root/'bad')),2)
            self.assertFalse((self.root/'bad').exists())
        for field,value in [('candidate_sizes',[100]),('evaluation_seeds',[1]),
                            ('bin_ms',0),('cpu_budget_seconds',1801),('families',['bad']),
                            ('bootstrap_samples',100000),('schema',True)]:
            c=small_config();c[field]=value
            with self.assertRaises(ValueError):validate(c)
        c=load(ROOT/'experiment/protocol.json');c['settings']['tick_ms']=1
        with self.assertRaises(ValueError):validate(c)
        c=load(ROOT/'experiment/protocol.json');c['bin_ms']=1
        with self.assertRaises(ValueError):validate(c)
        c=load(ROOT/'experiment/protocol.json');c['evaluation_seeds']=list(range(1000,1040));c['candidate_sizes']=[4,8,12,16]
        with self.assertRaises(ValueError):validate(c)

    def test_input_mutation_detected(self):
        out=self.root/'out'
        def change(*args): self.config.write_text('{}')
        with patch.object(cli,'execute',change):
            self.assertEqual(self.call(self.args(out)),2)
        self.assertFalse(out.exists())
