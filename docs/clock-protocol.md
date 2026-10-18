# Observer clock experiment (v1)

This study is separate from the historical synchronized experiment. Its source,
protocol, inputs and results remain unchanged. No novelty is claimed.

## Sources and scope

Reviewed 2026-10-18:

* Sun et al., [RAPTOR: Routing Attacks on Privacy in Tor](https://arxiv.org/abs/1503.03940v1)
  (2015), abstract: observing both ends can enable correlation, with routing
  determining that visibility. Here visibility is assumed, not simulated. We
  do not implement RAPTOR, model routing, collect traffic, or evaluate Tor.
* Wireshark's [Time Shifting Packets](https://www.wireshark.org/docs/wsug_html_chunked/ChWorkShiftTimePacketSection)
  describes fixed shifts and linear drift correction using two known packet
  timestamps. Its [`ui/time_shift.c`](https://raw.githubusercontent.com/wireshark/wireshark/master/ui/time_shift.c)
  implementation was inspected: `calcNT3` implements affine interpolation
  between anchors; `time_shift_adjtime` applies the correction across frames.
  No code was copied or executed. Our observer lacks known packet pairs and
  searches hypotheses instead. This is a limited matching baseline, not a
  replacement for clock synchronization or a new clock-estimation algorithm.
* Levine et al., [Timing Attacks in Low-Latency Mix Systems](https://users.ece.cmu.edu/~reiter/papers/2004/FC.pdf)
  (FC 2004), sections 4.1, 5 and 7.1–7.2: the paper explains why inter-arrival
  comparisons are sensitive to packet loss, then cross-correlates packet counts
  in adjacent windows. Its reported test uses 10-second windows and zero lag;
  ours uses normalized byte mass, 200 ms bins and a bounded affine search.
  The paper also discusses candidate populations and prior probabilities. Our
  closed-set top-one score is not its pairwise equal-error rate, and no numerical
  comparison to its results is justified. This deeper methodological review did
  not change the already frozen protocol or implementation.
* The [historical prior-work review](prior-work.md) documents the simulator's
  relationship to low-latency traffic analysis and existing defense simulators.

## Observer and clock model

The passive observer receives only lists of `[integer timestamp_ms, wire_bytes]`.
Ingress flow order and independently permuted egress candidate order are public;
flow identities, event indices, padding flags, relay state and true clock
parameters are passed only to evaluation code. The callable matchers accept no
truth object. This is an API separation, not process isolation against malicious
Python code. All candidate streams share one egress clock, but the baseline
fits each pair separately; it does not exploit shared-clock consistency.

Relay generation, queueing, delivery and byte accounting occur in physical
integer milliseconds using the unchanged historical settings. Observer ingress
adds a numeric origin of 2000 ms. Egress applies

`observed = 2000 + offset_ms + floor(physical_ms * (1000000 + drift_ppm) / 1000000)`.

Rounding is mathematical floor, including for negative intermediate values;
collisions retain separate events. No events are removed by the observation
step. Ingress is the reference clock. Conditions are synchronized (0,0),
offset-only, and offset-plus-drift. Each seed/family deterministically draws an
offset with independent sign and magnitude uniform over integer 250..750 ms,
and a signed drift magnitude uniform over integer 5000..18000 ppm. The same
draw is reused across candidate sizes and policies. Drift is deliberately large
(0.5–1.8%) to stress a six-second trace and 200 ms histogram, **not** a measured
oscillator distribution. This experiment cannot resolve ordinary hardware
clock stability or long-duration behavior.

Both observers have full traces, a closed candidate set, known time units and
nominal recording origin. The 2000 ms guard and 12000 ms end keep every frozen
observation and search hypothesis in bounds. These guards are protocol constants,
not inferred from true parameters. Adding a whole-bin origin and trailing zero
bins leaves synchronized legacy distances equal to historical distances.

## Scoring and development selection

Legacy calls the unchanged normalized wire-byte histogram L1 matcher with
200 ms bins and causal lags `[0,100,200,400,800,1600]`. Alignment forward-transforms
ingress using each candidate affine hypothesis, then minimizes exact rational
normalized histogram L1 for each ingress/egress pair. The displacement search
covers -800..2400 ms, combining possible clock offset and relay delay; it is
not an identifiable clock parameter estimate. Drift hypotheses are
`[-20000,0,20000]` ppm. It can overfit unrelated candidates. Empty/empty distance
is zero, empty/nonempty is two. Histograms explicitly clip outside 0..12000;
no frozen run should clip. Tied hypotheses retain the first offset-major,
drift-minor grid element; tied candidate ranks receive uniform expected top-one
credit and midrank. There is no global one-to-one assignment.

Before evaluation, compare 200 ms and 100 ms displacement steps on development
seeds 2000..2002, all families, sizes, policies and clock conditions. Select
100 ms only if its mean top-one accuracy across development rows exceeds the
200 ms grid by at least 0.01; otherwise choose the cheaper 200 ms grid. Runtime
is recorded but not a selection criterion. Evaluation seeds 3000..3019 are
fresh, disjoint from development and the historical 11..13/1000..1019 sets.
Freeze the selected protocol and all implementation hashes before evaluating.
Development results are not confirmatory evidence.

## Evaluation and resource limits

120 independent-seed/setting trials: 20 seeds × three traffic families × two
candidate sizes. Within each trial identical traffic is reused across three
policies, three conditions and two measured matchers plus analytical uniform
ranking (27 rows). Nested candidate sets and reused seeds are never pooled as
independent replicates. Synchronized trials are controls. The random control
has exact expected accuracy 1/n and rank (n+1)/2, not Monte Carlo estimates.
Delivery metrics are computed on physical time, then reused across conditions.

Report per-run accuracy and rank, delivery quantiles, losses, backlog and all
byte accounting. Paired differences compare aligned minus legacy, each clock
condition minus synchronized, and each policy minus immediate. Each setting
uses 2000 percentile bootstrap resamples of independent run means/differences,
with nearest-rank 2.5/97.5 percentiles; ties use expected credit, not random draws.
Intervals are descriptive, not multiplicity-adjusted. No packet-level bootstrap.

Each execution is limited to 1800 process CPU seconds and 1800 wall seconds.
A conservative comparison budget counts every flow pair/grid hypothesis before
histogram deduplication; exhaustion aborts with no partial result. Configuration
bounds fix the workload; signal cancellation and exclusive output reservation
ensure failed executions remove only their own output. Match runtime measures
real wall and process CPU nanoseconds around each matcher call, including its
input validation and feature construction but excluding truth scoring. These
measurements and whole-process peak RSS are kept outside deterministic manifests.

All evidence uses synthetic data, standard-library Python, and local compute.
Low accuracy is a failure of these particular matchers, not anonymity. Constant
padding remains indistinguishable in this feature model by construction.

## Freeze and development outcome

Development completed before final evaluation. The 200 ms grid achieved mean
top-one 0.7211934156378601 across 162 aligned development rows; the 100 ms grid
achieved 0.7222222222222222. The improvement of 0.0010288065843621 is below the
predeclared 0.01 threshold, so the 200 ms grid was selected. This is a development
null result for a finer grid, not evidence that finer searches never help.

The selected configuration SHA-256 is
`d9f96bc83185a4f0ba556462773311e2eb5d40c7e88f5dc7530ac396049866da`.
`experiment/clock/freeze.json` records every implementation hash, including the
unchanged historical modules. Each development candidate also retains its own
protocol, freeze, inputs, raw evidence, summaries and real runtime samples.
The historical freeze deliberately enumerates only its original source module
directory; the clock freeze includes that directory and the new clock package.
