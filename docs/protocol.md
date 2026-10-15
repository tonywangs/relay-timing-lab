# Frozen experiment protocol, version 1

The machine-readable protocol is `experiment/protocol.json`. Before evaluation,
`freeze` records SHA-256 of its canonical JSON and every package `.py` file in
`experiment/freeze.json`. `run` refuses mismatches. The same frozen settings
apply to development and evaluation; development seeds 11–13 are disjoint from
20 evaluation seeds 1000–1019. Tests use separate seeds 0–299. No tuning is
performed on the evaluation outcomes. SHA hashes establish artifact identity,
not a trusted timestamp or preregistration service.

## Traffic and experimental unit

Integer milliseconds and bytes only. For each family and seed, a SHA-256-derived
PRNG seed initializes Python's `random.Random`. Each run has 4 or 12 ingress
streams; the first four of a 12-stream input match the four-stream input.
Candidate settings are therefore related and are **not** pooled as independent
replications. Families use distinct derived seeds. The independent experimental
unit for intervals is the simulation seed within one family/candidate setting,
not an individual stream or packet.

All ingress events satisfy `0 <= t < 6000`. Each event independently chooses a
size uniformly from 128, 256, 512 bytes. These are synthetic wire records, not
application messages or realistic packet-size distributions.

* **renewal:** initial time uniform in integers 0–249, subsequent gaps uniform
  40–220 ms. This is not a Poisson process.
* **bursty:** 3–6 bursts, each with a uniform start in 0–5999, 12–28 events and
  independent offsets 0–99 ms. Events beyond the horizon are discarded at
  generation, before the input event count is defined; overlapping bursts can
  create simultaneous arrivals and overload.
* **periodic:** period uniform 40–110 ms, phase uniform within period, independent
  integer jitter −10 through 10 ms. Negative times clamp to zero; events at or
  beyond the horizon are excluded.

These choices are a compact range of regularity and burstiness, not a model
fitted to measured usage. Exactly the same generated inputs feed every policy.

## Relay semantics

Each candidate has its **own independent FIFO queue**; there is no shared-link
contention, cross-user mixing, network delay, clock noise, retransmission,
congestion feedback, encryption, bidirectional request/response dependency, or
packet fragmentation. Output transmission is instantaneous in this model.

* **immediate:** each input departs at arrival with unchanged size; no queue,
  no drop, no padding, zero relay delay.
* **batch:** release the entire queue at multiples of 200 ms, including zero.
  Preserve input order and original size. No bandwidth cap on a batch. This
  delay-only scheduler is not a shuffled mix network.
* **padded:** emit one 512-byte record at every multiple of 50 ms, including
  zero and all idle slots. Serve the oldest queued event, padding its size to
  512; emit an indistinguishable 512-byte dummy if the queue is empty.

Capacity is 32 events **per flow** for batch and padded. Process all arrivals at
one timestamp in original input order **before** service at that timestamp;
drop new arrivals when the queue is full, even if service is due at that time.
Drops are explicit event IDs. Peak backlog includes the transient pre-service
queue. Horizon backlog is measured after service at 6000 ms.

Continue service through `end = 6000 + 2000 = 8000` **inclusive**, with no new
arrivals during draining. Padded service continues on its fixed schedule even
when empty, producing 161 records per candidate. Batch releases only on its
normal grid. Do not force a final flush if the end is off-grid. Remaining event
IDs are queued/undelivered, not silently discarded. Account for every input
exactly once as delivered, dropped, or queued. Padded rate costs and completion
results depend strongly on this idealized fixed common observation window.

## Observer and matcher

The passive observer has exact synchronized clocks and full timestamp/size
records at both boundaries, partitioned into distinct ingress and egress
streams. It knows the candidate set contains exactly one true egress match for
each ingress. Egress streams are randomly permuted by a separate derived seed.
The matcher receives only `[time_ms, wire_bytes]` pairs, including dummy records.
It receives **no** ground-truth flow labels, event IDs, dummy indicators, queue
states, drop markers, or true permutation. The evaluator retains those in raw
artifacts for audit. This is an API-level experimental separation, not a
sandbox against malicious matcher code. Matching is row-wise ranking; no global
one-to-one assignment optimization is attempted.

For each stream, sum wire bytes in 200-ms bins starting at time zero, through
the inclusive end time (41 bins). Score each ingress–egress pair with L1 distance
between normalized byte histograms, using exact rational arithmetic. Two empty
histograms have distance zero; exactly one empty histogram has distance two.
Search causal ingress delays of 0, 100, 200, 400, 800, and 1600 ms; the pair
score is the minimum distance across these six shifted ingress histograms.
Shifted ingress events beyond the observation end are omitted before
normalization (none exceed it with the frozen 2000-ms drain). No training,
feature selection, or payload inspection is used.
Absolute time, not per-flow start normalization, is used.

For true score `s`, let `b` be the number of candidates with smaller scores and
`e` the number tied with `s`. Top-one credit is `1/e` if `b=0`, otherwise zero;
rank is `b+(e+1)/2`. These are expected values under uniform tie breaking, not
sampled tie choices. Store exact scores as numerator/denominator pairs. Per-run
accuracy and rank average ingress streams equally.

The **random-ranking** control uses exact expected accuracy `1/n` and rank
`(n+1)/2`, without Monte Carlo noise. Its cost columns reference unchanged
traffic. The **unmodified** control bypasses the scheduler and matches the
original traces after the same permutation. Costs also reflect unchanged
traffic. Identical padded schedules necessarily tie for every input: padded
accuracy equals chance by construction, not because the experiment discovered
an effective real-world defense.

## Measurements and uncertainty

Preserve input records, all real/dummy departures, dropped and queued event
IDs, true permutation, exact scores, per-flow matching results, and per-run
metrics. Raw gzip shards use fixed timestamps. Report:

* expected top-one accuracy and mean true-match rank;
* delivered-event nearest-rank p50, p95, p99 and maximum relay delay;
* input/delivered/dropped/queued counts, horizon backlog summed across flows,
  maximum per-flow backlog, and total undelivered (queued plus dropped);
* input bytes, transmitted bytes, dummy bytes, real wire bytes, delivered
  payload bytes, size padding bytes, and transmitted/input byte ratio.

Empty delivered sets have null latency; empty input has null byte ratio.
Delay quantiles exclude undelivered events and may therefore look better when
loss is high. Cost and loss columns must be read alongside latency. Ratios use
all input bytes, including dropped traffic, as the denominator.

Aggregate each metric as the mean of 20 per-run values within its setting.
Latency summaries are means of run quantiles, not pooled packet quantiles.
Use 2,000 bootstrap resamples of independent seeds with replacement and
nearest-rank 2.5/97.5 percentile endpoints. The bootstrap PRNG seed is frozen
(734123, derived by family/candidate setting); use common resampling indices
across metrics and policies. Pair policy-minus-immediate differences by seed
**before** resampling. Null values are omitted with the effective `n` reported.
These are descriptive pointwise intervals, without multiple-comparison
correction, and 20 seeds cannot characterize rare tails precisely.

## Budget, reproducibility and limits

At most 1,800 CPU seconds and also 1,800 elapsed seconds for a CLI evaluation.
Cooperative CPU checks plus POSIX wall/user-CPU timers enforce termination.
No child experiment processes are launched by the evaluator. Config validation
caps trials at 256, estimated event records at 1.5 million, and histogram
comparisons at 12 million; scalar and JSON size bounds apply as well. These are
workload bounds, not a formal memory guarantee. The frozen evaluation has 120
trials and 600 run-policy rows (including both controls).

`runtime.json` records actual elapsed/CPU time, whole-process peak RSS, Python
version, and deterministic artifact sizes. Runtime metadata and its timestamp
are excluded from deterministic comparison. Compression byte identity is
verified on the recorded Python/zlib environment; it is not promised across
all interpreter or zlib versions. Inputs and uncompressed integer/rational
measurements remain inspectable if a different environment changes encoding.

Exclusive creation refuses existing output paths, including symlinks. On
handled failure/SIGINT/SIGTERM/budget expiry, remove the newly created output
tree. SIGKILL or power loss can leave partial outputs: only a completed run
with `manifest.json` **and** `runtime.json` is complete. No automatic overwrite
or resume is performed. Input hashes are checked after execution. The CLI
uses no network. Browser verification is separately run offline.
