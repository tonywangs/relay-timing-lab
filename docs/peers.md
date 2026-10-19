# Local authenticated messaging

## Launch

From a checkout with Python 3.11+ and an OpenSSL executable supporting TLS 1.3:

```sh
python3 scripts/demo_peers.py
```

This launches Alice, Bob, and Carol as three separate operating-system processes.
Each listens on an OS-assigned IPv4 loopback port and sends a Unicode greeting
to each other peer. The terminal prints the six messages, independent process
IDs, and verification results. Exit status is nonzero on failure. The sender
checks a TLS-protected acknowledgment containing the message ID, receiver name,
and SHA-256 of the UTF-8 text; the controller additionally checks the receiver's
in-memory inbox for the exact text and certificate-derived sender. These are
real TCP/TLS connections, not the timing simulator or mocked cryptography.
The demonstration takes several seconds, primarily generating fresh keys.

No public dataset is needed for a messaging transport. Actual local network
traffic is exercised from the first demo; the example greeting is not evidence
of deployment, anonymity, or performance on an external network.

## Keys and protocol

The implementation uses Python's `ssl` bindings to OpenSSL. TLS 1.3 is required.
Both endpoints must present valid certificates signed by the temporary local
CA. Clients additionally verify the destination DNS SAN (`alice`, `bob`, or
`carol`); both sides check the SHA-256 fingerprint of the full leaf certificate
against an explicit identity allowlist. A CA-signed certificate alone does not
authorize a new identity. The sender identity comes from the certificate,
never from a claimed name in the message body. System public CA roots are not
loaded. No custom cipher or key-exchange algorithm is implemented.

`make_keys` in `relay_timing_lab.messaging.demo` invokes OpenSSL to create a one-day
RSA-2048 CA and one-day peer certificates with server/client authentication
usages. The CA private key is removed after signing. Keys are unencrypted files
with mode 0600 inside a mode-0700 temporary directory. No static private keys
are shipped. The demo deletes that directory on normal completion or handled
exceptions; force-killing the controller can leave it in the OS temp directory.
Each run establishes a new trust domain. The shared key directory and controller
are trusted: this is not process isolation against a malicious local user.
For separately administered endpoints, each must receive only its own private
key, the CA certificate and a verified `peers.json` allowlist over an authenticated
out-of-band channel. That provisioning/rotation workflow is not implemented.
Do not reuse demo keys for production.

Each connection carries one length-prefixed UTF-8 JSON message and one reply.
Frames are capped at 16,384 bytes; IDs at 128 characters. Socket operations have
four-second timeouts. The listener handles one connection at a time and keeps
only the most recent 256 events in memory. An acknowledgment means the receiver
accepted the message into its volatile inbox, not that a human read it or that
it survived a crash. No durable delivery, retry, deduplication, offline mailbox,
or application-level replay protection is promised. An authorized sender may
resubmit a message ID. TLS record integrity is distinct from those semantics.

For local experimentation, start a peer using:

```sh
PYTHONPATH=src python3 -m relay_timing_lab.messaging.peer --keys /path/to/disposable-keys --name alice
```

It prints a readiness object with its listening port. Its trusted local stdin
accepts JSON commands: `{"op":"events"}` reads inbox/rejection events;
`{"op":"send","target":"bob","port":12345,"id":"example","text":"hello"}`
sends a message; `{"op":"stop"}` shuts down. Replace 12345 with Bob's reported
port. The Python helper `make_keys(Path(...))` creates keys in a private directory;
the one-command demo performs all provisioning and cleanup automatically.
The local command interface is not a network API or security boundary.

## Threat model and limits

The intended network adversary may observe, connect, forward, or modify bytes,
but does not possess an authorized peer key, control trust provisioning, or
compromise the host/OpenSSL. Authentication rejects untrusted and unlisted
certificates. TLS detects changes to encrypted application records. Tests
establish those specific behaviors, not a formal security proof or audit.

An observer still sees IP addresses, ports, connection direction, timing,
duration, and record sizes. There is no onion routing, mixing, cover traffic,
metadata hiding, peer discovery, NAT traversal, or Tor integration. No anonymity
or Tor-equivalent security is demonstrated. The offline timing experiment's
results do not confer security on this separate messaging prototype.

Endpoint compromise exposes plaintext, the inbox, private keys, and future
impersonation capability. The demo controller has access to every identity.
Terminal output intentionally displays messages. There is no secure deletion,
key revocation service, user authentication, encrypted storage, or recovery
protocol. Sequential handling and bounded socket waits do not prevent denial
of service; a slow client can consume resources across multiple reads. The
listener is deliberately loopback-only, unsuitable for internet deployment.

## Reproducible checks

```sh
env PYTHONPATH=src python3 -W error::ResourceWarning -m unittest discover -s tests -p test_peers.py -v
```

Tests create fresh local identities and launch real peer processes. They check
all six directed deliveries, Unicode/empty text, unlisted same-CA clients,
foreign-CA clients, missing client certificates, wrong destination names and
pins, payload identity spoofing, and malformed/oversized frames. After rejection,
a valid delivery verifies the listener remains usable.

The tamper test runs a TCP proxy that forwards TLS records. It waits until the
server reports authentication, then flips one byte in the next client encrypted
application record. It requires evidence that the mutation happened, OpenSSL's
bad-record-MAC/decryption rejection, and absence of delivered plaintext. This
isolates ciphertext tampering from merely failing a handshake. Certificates,
ports, PIDs, and TLS randomness vary; assertions, not byte-identical output,
are reproducible. Linux/OpenSSL 3.0.13 was exercised; other platform/error-string
combinations have not been verified.

## Existing work and sources

This is an application of established mutual TLS, not a novel security protocol.
The [Python ssl documentation](https://docs.python.org/3/library/ssl.html)
describes the OpenSSL binding, certificate verification and socket APIs used
here. [TLS 1.3 (RFC 8446)](https://www.rfc-editor.org/rfc/rfc8446.html) specifies
the underlying protocol, including authenticated encryption and client
certificate authentication. These sources explain the primitive; neither
constitutes validation of this application's trust provisioning or threat model.
