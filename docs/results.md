# Frozen evaluation results

Protocol SHA-256: `f01309c062908fce0277d23b438ddb1b01a2624c5dcc5735b944897723e4f269`. Evaluation completed 2026-10-15T11:16:48.048207+00:00.

All 120 trials completed: 20 seeds × three families × two candidate counts. The
600 policy/control rows represent 70,646 synthetic input events across settings.
The smaller candidate sets share prefixes with larger sets; this total is an
artifact count, not a count of independent observations.

## Main finding: batching did not reduce matching

The frozen lag-aware matcher identified every flow under immediate forwarding
and bounded batching in every evaluation setting (top-one 1.0; mean rank 1).
Batching added roughly 188–190 ms to the mean per-run delivered p95 delay
without reducing matching performance. In bursty traffic it also dropped events.
This is a negative result for this batching policy under this model. It is not
a claim that every batching/mixing design is ineffective.

The fixed 200-ms bins and a search containing a 200-ms lag make this deterministic
batching grid particularly easy to match. The matcher does not need truth labels
to try this public delay. This demonstrates why a delay-blind comparison could
overstate protection; it does not exhaust stronger attacks or other defenses.

Padded forwarding matched at expected chance: 0.25 with four candidates and
1/12 (about 0.0833) with twelve, with expected ranks 2.5 and 6.5. Every padded
candidate emits the same 161 cells of 512 bytes at the same timestamps, so this
result is guaranteed by the observation model. Its empirical costs varied
substantially with load. Chance-level matching here is **not demonstrated anonymity**.

## Cost measurements

The following are means over 20 independent seeds in each row. Delay is the
mean of per-run p95 values for delivered events only. Drops are mean event counts
per run, summed across all candidates. Full intervals, p50/p99, dummy bytes,
backlogs, and paired comparisons are in the [HTML report](../results/evaluation/report.html)
and [summary JSON](../results/evaluation/summary.json).

| Family | Candidates | Policy | Top-one | p95 delay (ms) | Wire/input bytes | Dropped events |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| renewal | 4 | batch | 1.0000 | 188.50 | 1.000 | 0.00 |
| renewal | 4 | padded | 0.2500 | 47.40 | 5.891 | 0.00 |
| renewal | 12 | batch | 1.0000 | 188.85 | 1.000 | 0.00 |
| renewal | 12 | padded | 0.0833 | 47.05 | 6.007 | 0.00 |
| bursty | 4 | batch | 1.0000 | 187.95 | 0.982 | 6.40 |
| bursty | 4 | padded | 0.2500 | 1464.35 | 3.193 | 47.80 |
| bursty | 12 | batch | 1.0000 | 188.70 | 0.983 | 19.45 |
| bursty | 12 | padded | 0.0833 | 1483.05 | 3.048 | 139.30 |
| periodic | 4 | batch | 1.0000 | 189.15 | 1.000 | 0.00 |
| periodic | 4 | padded | 0.2500 | 328.85 | 3.324 | 0.00 |
| periodic | 12 | batch | 1.0000 | 189.70 | 1.000 | 0.00 |
| periodic | 12 | padded | 0.0833 | 505.55 | 3.341 | 0.00 |

All evaluation queues drained by the fixed end; undelivered events were drops.
Nonzero end queues are covered by the independent finite-horizon tests. A byte
ratio below one for bursty batching reflects loss, not efficient delivery.
Padded bursty traffic lost an average 47.8 events per four-candidate run and
139.3 per twelve-candidate run; these events do not contribute to reported delay.

For twelve-candidate bursty traffic, the mean padded p95 was 1,483.05 ms
(95% bootstrap interval 1,468.15–1,496.80), and wire/input bytes were 3.048
(2.932–3.171). Twelve-candidate renewal traffic required 6.007× input bytes
(5.915–6.099), despite low delivered p95 delay of 47.05 ms (46.90–47.25).

The analytical random-ranking and unmodified-trace controls behaved as specified.
Their delivery costs refer to unchanged traffic, not a fourth relay mechanism.

## Reproduction and resource measurements

Run `python3 scripts/reproduce.py` from the repository root. It verifies the
freeze, regenerates all evaluation artifacts, and compares deterministic bytes.
Inputs and raw results from the final frozen development phase are also preserved
in `results/development`; these are separate from the held-out evaluation.

The recorded evaluation used **50.417 CPU seconds**,
**59.390 elapsed seconds**, and **23,536 KiB peak process RSS**
on CPython 3.12.3/Linux x86-64. The peak covers the whole CLI process; timings
cover execution through the deterministic manifest. There are no runtime
dependencies beyond the Python standard library. CPU contention and environment
changes affect runtime; this is a single measured run, not a performance study.

The 244 deterministic evaluation artifacts occupy **2,404,794 bytes**
(excluding manifest and runtime metadata). Per-file sizes and SHA-256 values
are in `results/evaluation/manifest.json`. Runtime metadata is intentionally
nondeterministic and excluded from replay comparison. Python/zlib versions and
actual test-tool versions are recorded in `results/verification.json`.

## Interpretation limits

* Exact, synchronized, complete observation; a closed candidate set; independent
  per-flow shaping; and a common fixed observation window are strong assumptions.
* Input is synthetic and open-loop. No congestion feedback, shared bottleneck,
  realistic application dependencies, encryption, clock noise, or active attacks.
* Only one hand-built matcher and six fixed lags are evaluated. There is no
  general anonymity metric, real-network validation, or security proof.
* Bootstrap intervals resample independent seeds, not correlated events. Perfect
  observed matching produces a degenerate [1,1] bootstrap interval; this cannot
  bound the probability of unseen failures. Padded chance intervals are degenerate
  by construction. Intervals are pointwise and use only 20 seeds.
* Real packets queued or dropped are excluded from delivered-delay quantiles.
  Read loss together with latency and bandwidth before comparing policies.

The useful outcome is an auditable demonstration that this deterministic batch
schedule buys delay without defeating lag-aware correlation, while an idealized
fixed padded schedule imposes measurable bandwidth and burst-loss costs. It
cannot support deployment recommendations for Tor or any other anonymity system.
