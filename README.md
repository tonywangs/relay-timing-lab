# Relay timing lab

An offline, reproducible experiment measuring how three relay schedules affect
synthetic flow matching, delivery delay, and transmitted bytes. It includes a
label-free matcher, full event accounting, paired uncertainty, an interactive
HTML report, and independent scheduling checks.

**This is not a Tor security evaluation or a secure communication protocol.**
Reduced accuracy of this matcher does not establish anonymity. All traffic is
synthetic; no packet capture, personal data, accounts, services, or GPUs are
needed. See [model and protocol](docs/protocol.md) and
[prior work](docs/prior-work.md).

## Run and reproduce

Requires Python 3.11+ on Linux or macOS (POSIX signals and resource accounting).
The application has **no third-party runtime dependencies**. Python 3.12.3 was
used for the preserved evaluation. From the repository root, one command
reruns the frozen evaluation and compares every deterministic artifact against
the preserved evidence:

```sh
python3 scripts/reproduce.py
```

It uses a temporary directory, prints measured runtime, and cleans up. To keep
the reproduced report, supply a **new, nonexistent** output path:

```sh
python3 scripts/reproduce.py --output /tmp/my-relay-evaluation
```

Open [the preserved report](results/evaluation/report.html) directly in a browser
(download it first if your repository browser displays HTML as source). There
is no server or external asset dependency. Select family, candidate count and
policy to compare results; use native keyboard controls and paginated numeric
tables. Tables provide matching estimates, paired changes, cost, loss, and
latency. Raw results are linked by filenames in the artifact manifest.

The underlying CLI is also available without installation:

```sh
PYTHONPATH=src python3 -m relay_timing_lab run \
  --config experiment/protocol.json --freeze experiment/freeze.json \
  --phase development --output /tmp/relay-development
```

An optional normal installation uses `python3 -m pip install .` (requires build
tools setuptools and wheel); then replace `PYTHONPATH=src python3 -m
relay_timing_lab` with `relay-timing-lab`. Runtime still stays offline. On systems
without pip/venv support, the source command and reproduction command work
without them. Windows is not currently supported.

## What is measured

Twenty independent evaluation seeds for each of three traffic families
(renewal, bursty, periodic) and two candidate counts (4, 12): 120 paired trials,
600 run-policy rows including random-ranking and unmodified-trace controls.
The observer sees times and sizes, but no event IDs, dummy labels, or true
correspondence. It ranks normalized byte histograms using exact L1 distances
and a frozen causal lag search. The evaluation uses expected tie-breaking
credit and paired bootstrap intervals over simulation seeds.

The relay policies use independent per-flow queues:

| Policy | Service | Queue and size behavior |
| --- | --- | --- |
| Immediate | At arrival | No queue; unchanged sizes |
| Bounded batch | All queued events every 200 ms | FIFO, 32-event capacity, drop-tail |
| Constant-rate padded | One 512-byte cell every 50 ms | FIFO, 32-event capacity, dummy on idle |

Ingress ends at 6 seconds; scheduled draining ends at 8 seconds. Padded service
runs throughout this fixed window. This deliberately produces identical
observable padded streams: chance matching is guaranteed in this model,
while costs and losses are empirical. Batching and lag-aware matching provide
a useful contrast. The [results discussion](docs/results.md) records actual
measurements and limitations, including negative results.

## Evidence layout

* `experiment/protocol.json`, `experiment/freeze.json`: fixed seeds, settings,
  rules, limits, and hashes of the exact implementation.
* `results/evaluation/inputs/*.json`: generated timestamp/size records.
* `results/evaluation/raw/*.json.gz`: deterministic compressed per-trial raw
  departures, drops, queued IDs, scores, truth, and metrics.
* `results/evaluation/summary.json`: deterministic run rows and aggregate/paired
  intervals; `report.html`: self-contained visualization.
* `results/evaluation/manifest.json`: SHA-256 and byte count for each
  deterministic artifact; `runtime.json`: actual runtime and peak RSS.
* `results/verification.json`, `results/tests.log`: actual verification evidence.

The raw truth data intentionally exists for auditing; the matching function
accepts only timestamp/size arrays. This API separation is not an adversarial
code sandbox. Gzip uses a fixed header timestamp. Runtime metadata is excluded
from deterministic comparisons. Different Python/zlib versions can change
compressed encodings; use the recorded environment for byte identity.

## Verify

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 scripts/check_evidence.py
python3 scripts/reproduce.py
```

The tests compare an event scheduler with an independent tick-by-tick oracle
and independently calculated metrics on 300 seeded small cases across all
three policies. A further 300 cases enumerate tie-breaking orders. They also
exercise overload, simultaneous arrivals, idle intervals, finite draining,
empty traces, malformed input, workload limits, input immutability, output
collisions, failure cleanup, signal cancellation and deterministic replay.

Browser verification requires Node and Playwright 1.56.1 with its Chromium
build. Install these optional test tools once (network needed only for setup),
then run the check with networking blocked by the browser harness:

```sh
npm install --prefix /tmp/relay-browser playwright@1.56.1
PLAYWRIGHT_BROWSERS_PATH=/tmp/relay-browsers /tmp/relay-browser/node_modules/.bin/playwright install chromium
NODE_PATH=/tmp/relay-browser/node_modules PLAYWRIGHT_BROWSERS_PATH=/tmp/relay-browsers \
  node scripts/check_browser.cjs results/evaluation/report.html
```

This checks filters, numeric values, keyboard controls, pagination, hostile
labels through the real Python renderer, and bounded rendering for 12,000
rows. Chromium runs offline, permits local files, and aborts all network routes.

The isolated installation check builds a wheel, installs it in a clean venv,
and runs the installed CLI outside the source tree with socket operations
blocked. Prepare an offline wheelhouse (setup needs network) and then verify:

```sh
python3 -m pip download --only-binary=:all: --no-deps --dest /tmp/relay-wheelhouse \
  pip==25.3 setuptools==80.9.0 wheel==0.45.1
python3 scripts/verify_install.py --wheelhouse /tmp/relay-wheelhouse
```

The check itself needs no network and uses `pip --no-index` throughout.

## New experiments

Copy the protocol to a new file, change settings within documented limits,
then create a **new** freeze and use a new output directory. Never overwrite
frozen results to hide a changed protocol:

```sh
PYTHONPATH=src python3 -m relay_timing_lab freeze --config my-protocol.json --output my-freeze.json
PYTHONPATH=src python3 -m relay_timing_lab run --config my-protocol.json --freeze my-freeze.json --output /tmp/new-relay-run
```

The CLI refuses altered implementation/configuration hashes and existing
output paths. SIGINT/SIGTERM and handled failures remove only the output tree
created by that invocation. SIGKILL/power loss can leave incomplete outputs;
check for both manifest and runtime metadata. The 30-minute budget and explicit
workload caps prevent unbounded experiments. No scheduling or publication is
performed by this project.
