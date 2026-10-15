# Prior work and scope

Reviewed 2026-10-15. This project makes **no novelty claim**. It is a small,
inspectable experiment about a deliberately limited matcher and three toy
schedulers. We did not run or benchmark the implementations below.

* Dingledine, Mathewson, and Syverson, [Tor: The Second-Generation Onion
  Router](https://svn-archive.torproject.org/svn/projects/design-paper/tor-design.html)
  (2004), particularly sections 2 and 3: low latency leaves timing and volume
  available to an observer at both ends. This motivates our two-boundary
  observer, but the historical design paper is not a description of current
  Tor defenses. Our single relay, fixed clocks, isolated queues and synthetic
  traffic do not model Tor.
* Levine, Reiter, Wang, and Wright, [Timing Attacks in Low-Latency Mix-Based
  Systems](https://freehaven.net/doc/e2e-traffic/e2e-traffic.pdf) (Financial
  Cryptography 2004): studies end-to-end traffic analysis and countermeasures.
  Timing protection has long involved cost and threat-model assumptions;
  batching and constant padding are established ideas.
* Piotrowska et al., [The Loopix Anonymity
  System](https://www.usenix.org/conference/usenixsecurity17/technical-sessions/presentation/piotrowska)
  (USENIX Security 2017): uses cover traffic and independent Poisson delays
  within a multilayer system. Our deterministic, per-flow batch scheduler is
  **not** Loopix mixing; it neither shuffles users together nor models its
  topology, cryptography, active-attack protections, or anonymity analysis.
* Piotrowska, [Studying the anonymity trilemma with a discrete-event mix network
  simulator](https://arxiv.org/abs/2107.12172v2) (2021): demonstrates existing
  simulation work connecting design choices to anonymity, latency, and
  overhead. This project contributes an educational, bounded reproduction
  artifact, not a new anonymity metric or simulator concept.
* [Maybenot simulator](https://github.com/maybenot-io/maybenot/tree/main/crates/maybenot-simulator):
  inspected the README example and
  [event ordering and simulation API](https://raw.githubusercontent.com/maybenot-io/maybenot/main/crates/maybenot-simulator/src/lib.rs).
  Its `SimEvent` ordering explicitly resolves simultaneous events, and its
  advanced API exposes iteration limits. These reinforce the need to specify
  tie ordering and termination here. Its internal event records include
  padding metadata: our observer boundary explicitly strips analogous
  metadata before matching. Maybenot supports much richer defense machinery;
  we did not port its code. The README also warns that replaying traces cannot
  faithfully model application dependencies after blocking. Our open-loop
  generators make that omission explicit.

No real traffic, users, sockets, packet capture, Tor connections, or paid
inference are used. Smaller matching accuracy is evidence only about the
specified matcher on these synthetic streams. In particular, an attacker
could exploit features, clock offsets, long-term behavior, or side information
that we never simulate. This is not a secure messaging protocol.
