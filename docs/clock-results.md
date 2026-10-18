# Observer clock results

Final evaluation: 20 fresh seeds (3000–3019), three traffic families, candidate
sets of 4 and 12, three forwarding policies, three clock conditions, two measured
matchers and an analytical random-ranking control: **120 trials and 3,240 rows**.
No configuration or implementation change was made after the final freeze.

The bounded alignment baseline recovered most matches lost by the legacy matcher
under clock error. This is evidence of a matcher limitation, **not anonymity**.
For offset plus drift, aligned accuracy was 97.917–100% for immediate/batched
policies, versus 28.750–61.250% for legacy. Both matchers reached 100% in all
synchronized immediate/batched settings. Padding remained at analytical chance
(25% or 8.333%) for every condition, because all padded observations are identical.

The predeclared development comparison selected the cheaper 200 ms grid: a
100 ms grid improved development accuracy by only 0.103 percentage points.
See the [protocol](clock-protocol.md) for source review, observer knowledge,
precision, parameter distributions, selection rule and freeze hashes.

## Accuracy and paired differences

Each row summarizes 20 independent simulation runs. Accuracy is percent; rank
is the mean true-match midrank (one is best). Differences are aligned minus
legacy in percentage points, with 95% paired run-bootstrap intervals. Candidate
sizes and families share seed identifiers and must not be pooled as independent
replicates. No multiple-comparison correction is applied.

| Family | n | Policy | Clock | Legacy % / rank | Aligned % / rank | Difference pp [95% CI] |
|---|---:|---|---|---:|---:|---:|
| renewal | 4 | immediate | offset | 55.000 / 1.806 | 100.000 / 1.000 | 45.000 [30.000, 60.000] |
| renewal | 4 | immediate | offset_drift | 61.250 / 1.750 | 100.000 / 1.000 | 38.750 [22.500, 56.250] |
| renewal | 4 | batch | offset | 53.125 / 1.994 | 100.000 / 1.000 | 46.875 [28.750, 63.750] |
| renewal | 4 | batch | offset_drift | 49.375 / 2.019 | 100.000 / 1.000 | 50.625 [33.750, 67.500] |
| renewal | 12 | immediate | offset | 44.583 / 4.019 | 99.792 / 1.002 | 55.208 [37.083, 72.500] |
| renewal | 12 | immediate | offset_drift | 49.583 / 3.821 | 100.000 / 1.000 | 50.417 [30.833, 69.583] |
| renewal | 12 | batch | offset | 43.125 / 4.783 | 100.000 / 1.000 | 56.875 [37.083, 77.500] |
| renewal | 12 | batch | offset_drift | 39.375 / 4.812 | 100.000 / 1.000 | 60.625 [41.458, 79.375] |
| bursty | 4 | immediate | offset | 50.000 / 1.988 | 100.000 / 1.000 | 50.000 [32.500, 67.500] |
| bursty | 4 | immediate | offset_drift | 55.000 / 1.938 | 100.000 / 1.000 | 45.000 [26.250, 63.750] |
| bursty | 4 | batch | offset | 35.000 / 2.400 | 100.000 / 1.000 | 65.000 [48.750, 78.750] |
| bursty | 4 | batch | offset_drift | 47.500 / 2.138 | 100.000 / 1.000 | 52.500 [36.250, 68.750] |
| bursty | 12 | immediate | offset | 39.375 / 4.835 | 99.583 / 1.004 | 60.208 [42.292, 76.667] |
| bursty | 12 | immediate | offset_drift | 42.431 / 4.629 | 99.167 / 1.008 | 56.736 [38.333, 73.194] |
| bursty | 12 | batch | offset | 24.167 / 5.946 | 100.000 / 1.000 | 75.833 [57.083, 91.250] |
| bursty | 12 | batch | offset_drift | 32.917 / 5.094 | 99.583 / 1.004 | 66.667 [48.333, 83.333] |
| periodic | 4 | immediate | offset | 41.875 / 2.019 | 100.000 / 1.000 | 58.125 [44.375, 71.250] |
| periodic | 4 | immediate | offset_drift | 53.750 / 1.881 | 100.000 / 1.000 | 46.250 [33.750, 58.750] |
| periodic | 4 | batch | offset | 47.500 / 2.138 | 100.000 / 1.000 | 52.500 [36.250, 68.750] |
| periodic | 4 | batch | offset_drift | 43.750 / 2.212 | 100.000 / 1.000 | 56.250 [41.250, 71.250] |
| periodic | 12 | immediate | offset | 27.500 / 4.688 | 100.000 / 1.000 | 72.500 [56.667, 85.833] |
| periodic | 12 | immediate | offset_drift | 31.667 / 4.660 | 97.917 / 1.025 | 66.250 [50.833, 80.833] |
| periodic | 12 | batch | offset | 34.167 / 5.027 | 100.000 / 1.000 | 65.833 [46.667, 84.583] |
| periodic | 12 | batch | offset_drift | 28.750 / 5.200 | 100.000 / 1.000 | 71.250 [52.083, 89.583] |

Residual alignment failures are retained. The lowest aligned setting was
periodic / 12 candidates / immediate / offset-plus-drift (97.917%). Coarse
alignment does not guarantee recovery, and the selected grid is not a strict
superset of the legacy lag set. The synchronized control showed no accuracy
regression here; that does not establish universal dominance.

Adding drift did not monotonically reduce legacy accuracy: some offset-only
settings improved when drift was added. Histogram boundaries and the asymmetric
causal lag search can make such changes non-monotonic. This experiment does not
estimate a causal dose-response curve for drift magnitude.

## Delivery and overhead

Clock transformations affect observations only. Every condition and matcher has
identical physical delivery/accounting for a given seed and policy. Immediate
forwarding has zero delay, no loss and byte ratio one. Below are run-mean
delivery metrics; undelivered includes drops plus remaining queued events.
Padded losses are not counted as fast deliveries. Full quantiles, counts, byte
breakdowns and intervals are in `summary.json` and the offline report.

| Family | n | Policy | p95 delay ms | Wire/input bytes | Undelivered events/run |
|---|---:|---|---:|---:|---:|
| renewal | 4 | batch | 189.200 | 1.000 | 0.000 |
| renewal | 4 | padded | 47.400 | 5.914 | 0.000 |
| renewal | 12 | batch | 189.050 | 1.000 | 0.000 |
| renewal | 12 | padded | 47.150 | 6.033 | 0.000 |
| bursty | 4 | batch | 187.450 | 0.986 | 5.100 |
| bursty | 4 | padded | 1443.900 | 3.162 | 40.000 |
| bursty | 12 | batch | 189.200 | 0.985 | 16.550 |
| bursty | 12 | padded | 1473.100 | 3.132 | 126.150 |
| periodic | 4 | batch | 189.500 | 1.000 | 0.000 |
| periodic | 4 | padded | 457.400 | 3.257 | 0.000 |
| periodic | 12 | batch | 189.900 | 1.000 | 0.000 |
| periodic | 12 | padded | 615.850 | 3.257 | 0.000 |

## Runtime and artifacts

Recorded final evaluation: **170.128 process CPU seconds**,
407.090 elapsed seconds, **38,840 KiB peak process RSS**.
It completed within the frozen 1,800-second CPU and wall limits on 3.12.3
CPython / Linux x86-64, using only the Python standard library. Other verification
processes shared this host during measurement; elapsed times are not an isolated
benchmark and should not be compared directly to another machine.

| Matcher | Calls | CPU seconds | Elapsed seconds |
|---|---:|---:|---:|
| aligned | 1080 | 107.580362 | 277.242672 |
| legacy | 1080 | 17.325341 | 46.651416 |
| random | 1080 | 0.008522 | 0.013956 |

The aligned calls consumed 6.21× the legacy calls' aggregate CPU time.
Timing covers feature construction and alignment/scoring but excludes truth
evaluation. Raw call measurements are in `measurements.json.gz`; its SHA-256 is
`c0e759710e20adee307dbda4fc14c7316e87a6ce98e700fde1165d64c3588552`. `timing-summary.json` gives per-setting means and
bootstrap intervals over simulation seeds in milliseconds. These intervals
describe variation across traffic instances in this execution, not repeated
benchmark runs, machines or host loads. Sub-clock-resolution measurements can
be zero; none are replaced with invented positive values.

The deterministic evaluation manifest contains 244 files totaling
**7,663,296 bytes** (manifest, runtime and timing files excluded).
Inputs and raw observer/relay evidence are sharded per trial; no project file
exceeds 10 MiB. Both development candidates are retained alongside the final
evaluation. The tree-size checker enforces the total publication budget.

## Reproduction and limits

```sh
python3 scripts/reproduce_clock.py
```

This runs the final frozen protocol offline in a temporary directory and compares
all deterministic artifact bytes, then removes the temporary outputs. Runtime
samples are intentionally excluded from byte equality. The installed CLI is
`python3 -m relay_timing_lab.clock`; setup and optional browser/install checks are
in the [README](../README.md). Byte equality is environment-specific: this run
uses Python 3.12.3 and zlib 1.3 (build 1.3). POSIX timers/signals are
required. Source hashes reject accidental changes before an experiment starts.

An independent 300-seed small-case oracle covers transforms, exact grid scoring,
winning hypotheses, candidate ties, empty traces, collisions, overload and
accounting. The evidence auditor independently reconstructs every observation,
checks every saved score witness, recomputes accounting and bootstrap summaries.
Full deterministic replay checks global matching results; the small-case oracle
independently checks the global minimum search itself.

The observer has full traces, known recording units and a bounded search range.
Drift is an intentionally large 0.5–1.8% stress condition, not hardware data.
There is no packet-capture loss, shared-link contention, application feedback,
network jitter, routing, bidirectional traffic, open-world candidates, learned
matcher, or shared-clock joint estimator. Offset and relay delay are confounded.
The 20-seed intervals cannot bound unseen failure modes. These are synthetic
matching experiments, not a Tor evaluation or a demonstrated anonymity defense.
