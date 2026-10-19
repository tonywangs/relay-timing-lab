"""Launch three independent peers with disposable, locally generated identities."""
import hashlib
import json
from pathlib import Path
import selectors
import ssl
import subprocess
import sys
import tempfile
from contextlib import ExitStack

NAMES = ('alice', 'bob', 'carol')


def make_keys(directory, names=NAMES):
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    def run(*args):
        subprocess.run(['openssl', *args], cwd=directory, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=20)
    run('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', 'ca.key',
        '-out', 'ca.pem', '-days', '1', '-subj', '/CN=Disposable relay demo CA',
        '-addext', 'basicConstraints=critical,CA:TRUE', '-addext', 'keyUsage=critical,keyCertSign,cRLSign')
    pins = {}
    for index, name in enumerate(names, 1):
        run('req', '-new', '-newkey', 'rsa:2048', '-nodes', '-keyout', f'{name}.key',
            '-out', f'{name}.csr', '-subj', f'/CN={name}')
        (directory / 'extensions.cnf').write_text(
            f'subjectAltName=DNS:{name}\nbasicConstraints=critical,CA:FALSE\n'
            'keyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth,clientAuth\n')
        run('x509', '-req', '-in', f'{name}.csr', '-CA', 'ca.pem', '-CAkey', 'ca.key',
            '-set_serial', str(index), '-out', f'{name}.pem', '-days', '1', '-extfile', 'extensions.cnf')
        der = ssl.PEM_cert_to_DER_cert((directory / f'{name}.pem').read_text())
        pins[name] = hashlib.sha256(der).hexdigest()
        (directory / f'{name}.key').chmod(0o600)
    (directory / 'ca.key').unlink()
    (directory / 'peers.json').write_text(json.dumps(pins))


class Process:
    def __init__(self, directory, name):
        self.name = name
        self.proc = subprocess.Popen([sys.executable, '-m', 'relay_timing_lab.messaging.peer',
                                      '--keys', str(directory), '--name', name],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True)
        try:
            self.port = self.read()['port']
        except BaseException:
            self.close()
            raise

    def read(self):
        with selectors.DefaultSelector() as selector:
            selector.register(self.proc.stdout, selectors.EVENT_READ)
            if not selector.select(10):
                raise TimeoutError(f'{self.name} did not respond')
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError(f'{self.name} exited: {self.proc.stderr.read()}')
        return json.loads(line)

    def command(self, **value):
        self.proc.stdin.write(json.dumps(value) + '\n')
        self.proc.stdin.flush()
        return self.read()

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=6)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            stream.close()


def demo():
    with tempfile.TemporaryDirectory(prefix='relay-peers-') as directory, ExitStack() as stack:
        make_keys(directory)
        peers = {}
        for name in NAMES:
            peers[name] = Process(directory, name)
            stack.callback(peers[name].close)
        deliveries = []
        for sender in NAMES:
            for target in NAMES:
                if sender == target:
                    continue
                message_id = f'{sender}-to-{target}'
                text = f'Hello {target}, from {sender}! — encrypted loopback message'
                result = peers[sender].command(op='send', target=target, port=peers[target].port,
                                               id=message_id, text=text)
                expected = {'id': message_id, 'receiver': target,
                            'sha256': hashlib.sha256(text.encode()).hexdigest()}
                if result != {'ack': expected}:
                    raise RuntimeError(result)
                events = peers[target].command(op='events')['events']
                if {'event': 'delivered', 'sender': sender, 'id': message_id, 'text': text} not in events:
                    raise RuntimeError('receiver inbox did not match')
                deliveries.append({'from': sender, 'to': target, 'text': text, 'verified': True})
        result = {'status': 'passed', 'transport': 'mutual TLS 1.3 over loopback TCP',
                  'peer_pids': {name: p.proc.pid for name, p in peers.items()}, 'deliveries': deliveries}
        print(json.dumps(result, indent=2))
        return result


if __name__ == '__main__':
    demo()
