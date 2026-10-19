"""Real-process/TCP integration checks; no cryptographic mocks."""
import hashlib
import json
from pathlib import Path
import socket
import ssl
import struct
import tempfile
import threading
import time
import unittest

from relay_timing_lab.messaging.demo import Process, demo, make_keys
from relay_timing_lab.messaging.peer import connect, context, exact, receive, send, transmit


class CorruptingProxy:
    """Forward TLS records; flip one ciphertext byte only after authentication."""
    def __init__(self, port):
        self.target = port
        self.arm = threading.Event()
        self.changed = threading.Event()
        self.errors = []
        self.sockets = []
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(1)
        self.listener.settimeout(5)
        self.port = self.listener.getsockname()[1]
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def copy(self, source, target, corrupt=False):
        try:
            while True:
                header = exact(source, 5)
                body = bytearray(exact(source, struct.unpack('!H', header[3:])[0]))
                if corrupt and self.arm.is_set() and not self.changed.is_set() and header[0] == 23:
                    body[-1] ^= 1
                    self.changed.set()
                target.sendall(header + body)
        except (OSError, ValueError):
            try:
                target.shutdown(socket.SHUT_WR)
            except OSError:
                pass

    def run(self):
        try:
            client, _ = self.listener.accept()
            upstream = socket.create_connection(('127.0.0.1', self.target), 5)
            client.settimeout(5)
            self.sockets.extend([client, upstream])
            reverse = threading.Thread(target=self.copy, args=(upstream, client))
            reverse.start()
            self.copy(client, upstream, True)
            reverse.join(6)
        except OSError as exc:
            self.errors.append(str(exc))

    def close(self):
        for sock in self.sockets:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()
        self.listener.close()
        self.thread.join(7)


class PeerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.keys = Path(cls.temp.name) / 'trusted'
        make_keys(cls.keys, ('alice', 'bob', 'carol', 'outsider'))
        pins = json.loads((cls.keys / 'peers.json').read_text())
        del pins['outsider']
        (cls.keys / 'peers.json').write_text(json.dumps(pins))
        cls.foreign = Path(cls.temp.name) / 'foreign'
        make_keys(cls.foreign, ('alice',))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.bob = Process(self.keys, 'bob')
        self.addCleanup(self.bob.close)

    def events(self):
        return self.bob.command(op='events')['events']

    def await_event(self, kind):
        end = time.monotonic() + 5
        while time.monotonic() < end:
            events = self.events()
            if any(e['event'] == kind for e in events):
                return events
            time.sleep(.01)
        self.fail(f'no {kind} event: {events}')

    def rejected_without_delivery(self):
        events = self.await_event('rejected')
        self.assertFalse(any(e['event'] == 'delivered' for e in events))
        # A rejected connection must not kill the listener.
        ack = send(self.keys, 'alice', 'bob', self.bob.port, 'still alive', 'recovery')
        self.assertEqual(ack['id'], 'recovery')
        return events

    def test_three_process_all_pairs(self):
        result = demo()
        self.assertEqual(len(set(result['peer_pids'].values())), 3)
        self.assertEqual(len(result['deliveries']), 6)

    def test_same_ca_unlisted_client_rejected(self):
        with self.assertRaises((OSError, ValueError)):
            send(self.keys, 'outsider', 'bob', self.bob.port, 'forbidden', 'attack')
        events = self.rejected_without_delivery()
        self.assertTrue(any('not authorized' in e.get('reason', '') for e in events))

    def test_foreign_ca_client_rejected(self):
        ctx = context(self.keys, 'alice')
        ctx.load_cert_chain(str(self.foreign / 'alice.pem'), str(self.foreign / 'alice.key'))
        with self.assertRaises((OSError, ValueError)):
            with socket.create_connection(('127.0.0.1', self.bob.port), 4) as raw:
                with ctx.wrap_socket(raw, server_hostname='bob') as conn:
                    transmit(conn, {'id': 'attack', 'text': 'forbidden'})
                    receive(conn)
        self.rejected_without_delivery()

    def test_missing_client_certificate_rejected(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.load_verify_locations(str(self.keys / 'ca.pem'))
        with self.assertRaises((OSError, ValueError)):
            with socket.create_connection(('127.0.0.1', self.bob.port), 4) as raw:
                with ctx.wrap_socket(raw, server_hostname='bob') as conn:
                    transmit(conn, {'id': 'attack', 'text': 'forbidden'})
                    receive(conn)
        self.rejected_without_delivery()

    def test_wrong_server_identity_rejected(self):
        with self.assertRaises(ssl.SSLCertVerificationError):
            connect(self.keys, 'alice', 'carol', self.bob.port)
        self.rejected_without_delivery()

    def test_wrong_server_pin_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            import shutil
            for filename in ('ca.pem', 'alice.pem', 'alice.key', 'peers.json'):
                shutil.copy(self.keys / filename, Path(directory) / filename)
            pins = json.loads((Path(directory) / 'peers.json').read_text())
            pins['bob'] = '0' * 64
            (Path(directory) / 'peers.json').write_text(json.dumps(pins))
            with self.assertRaisesRegex(ValueError, 'not authorized'):
                connect(directory, 'alice', 'bob', self.bob.port)
        self.rejected_without_delivery()

    def test_modified_encrypted_application_record_rejected(self):
        proxy = CorruptingProxy(self.bob.port)
        self.addCleanup(proxy.close)
        with connect(self.keys, 'alice', 'bob', proxy.port) as conn:
            self.assertEqual(conn.version(), 'TLSv1.3')
            self.await_event('authenticated')
            proxy.arm.set()
            with self.assertRaises((OSError, ValueError)):
                transmit(conn, {'id': 'tampered', 'text': 'must never arrive'})
                receive(conn)
        self.assertTrue(proxy.changed.wait(2), 'proxy did not modify ciphertext')
        events = self.rejected_without_delivery()
        self.assertTrue(any('DECRYPTION_FAILED_OR_BAD_RECORD_MAC' in e.get('reason', '')
                            for e in events), events)
        self.assertEqual(proxy.errors, [])

    def test_oversize_and_malformed_frames_rejected(self):
        for data in (struct.pack('!I', 16385), struct.pack('!I', 1) + b'{'):
            with connect(self.keys, 'alice', 'bob', self.bob.port) as conn:
                conn.sendall(data)
                with self.assertRaises((OSError, ValueError)):
                    receive(conn)
        self.rejected_without_delivery()

    def test_deeply_nested_json_rejected_without_listener_failure(self):
        data = b'{"nested":' + b'[' * 1100 + b'0' + b']' * 1100 + b'}'
        with connect(self.keys, 'alice', 'bob', self.bob.port) as conn:
            conn.sendall(struct.pack('!I', len(data)) + data)
            with self.assertRaises((OSError, ValueError)):
                receive(conn)
        self.rejected_without_delivery()

    def test_invalid_unicode_rejected_before_delivery(self):
        for field in ('id', 'text'):
            message = {'id': 'invalid', 'text': 'invalid'}
            message[field] = chr(0xd800)
            data = json.dumps(message).encode('ascii')
            with connect(self.keys, 'alice', 'bob', self.bob.port) as conn:
                conn.sendall(struct.pack('!I', len(data)) + data)
                with self.assertRaises((OSError, ValueError)):
                    receive(conn)
        self.rejected_without_delivery()

    def test_identity_comes_from_certificate_not_payload(self):
        with connect(self.keys, 'alice', 'bob', self.bob.port) as conn:
            transmit(conn, {'id': 'spoof', 'text': 'hello', 'sender': 'carol'})
            with self.assertRaises((OSError, ValueError)):
                receive(conn)
        self.rejected_without_delivery()

    def test_unicode_and_empty_payloads(self):
        for number, text in enumerate(('', '你好 🌍\nsecond line')):
            ack = send(self.keys, 'alice', 'bob', self.bob.port, text, str(number))
            self.assertEqual(ack['sha256'], hashlib.sha256(text.encode()).hexdigest())
        delivered = [e for e in self.events() if e['event'] == 'delivered']
        self.assertEqual([e['sender'] for e in delivered], ['alice', 'alice'])


if __name__ == '__main__':
    unittest.main()
