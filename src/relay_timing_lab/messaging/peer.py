"""Bounded loopback messaging over mutually authenticated TLS 1.3."""
import argparse
import hashlib
import json
import socket
import ssl
import struct
import threading
from pathlib import Path

LIMIT = 16384
TIMEOUT = 4


def context(directory, name, server=False):
    directory = Path(directory)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER if server else ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_verify_locations(str(directory / 'ca.pem'))
    ctx.load_cert_chain(str(directory / f'{name}.pem'), str(directory / f'{name}.key'))
    return ctx


def identify(connection, directory, expected=None):
    pins = json.loads((Path(directory) / 'peers.json').read_text())
    digest = hashlib.sha256(connection.getpeercert(binary_form=True)).hexdigest()
    matches = [name for name, pin in pins.items() if pin == digest]
    if len(matches) != 1 or (expected is not None and matches[0] != expected):
        raise ValueError('peer certificate is not authorized for this identity')
    return matches[0]


def exact(connection, count):
    data = bytearray()
    while len(data) < count:
        block = connection.recv(count - len(data))
        if not block:
            raise ValueError('truncated frame')
        data.extend(block)
    return bytes(data)


def receive(connection):
    size = struct.unpack('!I', exact(connection, 4))[0]
    if not 0 < size <= LIMIT:
        raise ValueError('invalid frame length')
    try:
        value = json.loads(exact(connection, size))
    except RecursionError as exc:
        raise ValueError('JSON nesting exceeds parser limit') from exc
    if not isinstance(value, dict):
        raise ValueError('frame must be an object')
    return value


def transmit(connection, value):
    data = json.dumps(value, ensure_ascii=False).encode()
    if not 0 < len(data) <= LIMIT:
        raise ValueError('message exceeds frame limit')
    connection.sendall(struct.pack('!I', len(data)) + data)


def connect(directory, name, target, port):
    raw = socket.create_connection(('127.0.0.1', port), TIMEOUT)
    conn = None
    try:
        conn = context(directory, name).wrap_socket(raw, server_hostname=target)
        identify(conn, directory, target)
        return conn
    except BaseException:
        if conn is not None:
            conn.close()
        raw.close()
        raise


def send(directory, name, target, port, text, message_id):
    with connect(directory, name, target, port) as conn:
        transmit(conn, {'id': message_id, 'text': text})
        reply = receive(conn)
        wanted = {'id': message_id, 'sha256': hashlib.sha256(text.encode()).hexdigest(), 'receiver': target}
        if reply != wanted:
            raise ValueError('delivery acknowledgment mismatch')
        return reply


class Peer:
    def __init__(self, directory, name):
        self.directory, self.name = directory, name
        self.context = context(directory, name, server=True)
        self.events = []
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(8)
        self.listener.settimeout(.2)
        self.port = self.listener.getsockname()[1]
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def record(self, event):
        with self.lock:
            # A bounded demo inbox, not a durable message store.
            self.events.append(event)
            self.events[:] = self.events[-256:]

    def serve(self):
        while not self.stopped.is_set():
            try:
                raw, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                with raw:
                    raw.settimeout(TIMEOUT)
                    with self.context.wrap_socket(raw, server_side=True) as conn:
                        sender = identify(conn, self.directory)
                        self.record({'event': 'authenticated', 'sender': sender})
                        message = receive(conn)
                        if (set(message) != {'id', 'text'} or
                            not isinstance(message['id'], str) or not 1 <= len(message['id']) <= 128 or
                            not isinstance(message['text'], str)):
                            raise ValueError('invalid message')
                        message['id'].encode('utf-8')
                        digest = hashlib.sha256(message['text'].encode()).hexdigest()
                        self.record({'event': 'delivered', 'sender': sender, **message})
                        transmit(conn, {'id': message['id'], 'receiver': self.name,
                                        'sha256': digest})
            except (OSError, ValueError, UnicodeError) as exc:
                self.record({'event': 'rejected', 'reason': str(exc)})

    def close(self):
        self.stopped.set()
        self.listener.close()
        self.thread.join(TIMEOUT + 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--keys', required=True)
    parser.add_argument('--name', choices=['alice', 'bob', 'carol'], required=True)
    args = parser.parse_args()
    peer = Peer(args.keys, args.name)
    def output(value):
        print(json.dumps(value), flush=True)
    output({'ready': args.name, 'port': peer.port})
    try:
        import sys
        for line in sys.stdin:
            try:
                command = json.loads(line)
                if command['op'] == 'stop':
                    break
                if command['op'] == 'events':
                    with peer.lock:
                        output({'events': list(peer.events)})
                elif command['op'] == 'send':
                    output({'ack': send(args.keys, args.name, command['target'], command['port'],
                                        command['text'], command['id'])})
                else:
                    raise ValueError('unknown operation')
            except (OSError, ValueError, KeyError, TypeError) as exc:
                output({'error': str(exc)})
    finally:
        peer.close()


if __name__ == '__main__':
    main()
