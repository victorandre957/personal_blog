+++
title = "Classifying BIP324 Traffic in a Full Network Capture: Preliminary ML Results"
date = 2026-10-14
description = "XGBoost and a temporal CNN classify Bitcoin v2 activity in full-network Warnet PCAPs, with an explicit comparison of errors and limits."
[taxonomies]
tags = ["bitcoin", "bip324", "traffic-analysis", "machine-learning", "warnet"]
+++

BIP324 encrypts P2P messages, but packet sizes, timing, and direction remain visible. Building on my [earlier passive analysis](@/posts/bip324-passive-traffic-analysis-and-randomized-ports.md), I test whether a multiclass classifier can identify Bitcoin v2 activity in a **full-network PCAP**, without filtering by port or applying a hand-written BIP324 detector first.

## Collection and labels

The [Warnet lab](https://github.com/victorandre957/bip324-traffic-lab) runs Bitcoin Core beside HTTP, HTTPS, Tor, obfs4-shaped, BitTorrent, and UDP traffic. A bridge sniffer records every flow. The captures vary Bitcoin activity and block load, with accelerated timing and heavy background noise. This is a controlled simulation, not mainnet traffic.

The [preparation pipeline](https://github.com/victorandre957/bip324-traffic-ml) divides every observed TCP/UDP flow into 250 ms windows. Core connection records and message logs label those windows for training and evaluation; they never enter the classifier. I report eight outcomes, using P2P message names where applicable:

- **`other`:** non-v2 traffic, including Bitcoin v1 and all background applications.
- **`handshake`:** the initial v2 connection exchange.
- **`inv`:** announcement of transaction or block identifiers, without the objects.
- **`getdata`:** request for an announced transaction or block.
- **`tx`:** transaction transfer, including matched `inv` → `getdata` → `tx` relay sequences.
- **`block`:** full block transfer.
- **`cmpctblock`:** compact block transfer, reconstructed partly from transactions the receiver already has.
- **`bitcoin_v2_other`:** v2 window without a matched specific event; it may still contain a Bitcoin message.

Ambiguous windows are excluded from scoring; a full block transfer sharing a window with its `getdata` request remains labeled `block`. Labels rely on log-to-flow/time matching, rather than decrypted packet-level ground truth.

## What the model sees

The [feature builder](https://github.com/victorandre957/bip324-traffic-ml/blob/main/src/bip324_traffic_ml/consolidate.py) gives both models **34 numeric PCAP-derived inputs** per window:

- **Current window (7):** payload bytes and packet counts in each direction, totals, and byte-direction imbalance.
- **Burst timing (6):** duration, byte rate, and gap since the previous burst, per direction.
- **Neighboring windows (8):** byte totals 1, 2, and 4 observed windows before/after; bytes and packets in the previous 4.
- **Connection age (4):** elapsed seconds and time-based phase flags for the first second, next four seconds, and later traffic. The “handshake” flag is just a time range, not a Core label.
- **Opening payloads (5):** first payload size and initial sending-turn size per direction, plus entropy of early captured bytes. Raw bytes do not enter the model.
- **Whole flow (3):** completed duration, all packets, and payload-carrying packets.
- **Transport (1):** whether the observed flow uses TCP or UDP.

Excluded inputs:

- **IPs and ports:** visible in the PCAP but prone to memorizing lab endpoints or the Bitcoin port; omitting them tests whether detection survives port randomization. They still help pair flows to logs for labeling.
- **Run/flow IDs, absolute time, and node roles:** used to group or audit captures, but would identify a particular run or node.
- **Core logs, IP maps, and noise-family labels:** ground truth and error analysis only; unavailable to an outside observer.
- **Raw payload and heuristic BIP324/cleartext flags:** would shift the experiment toward content signatures or reproduce an existing detector. Only an early-byte entropy summary is retained.

Future windows and whole-flow totals make this an **offline classifier of completed captures**. Each architecture fits one multiclass model; Bitcoin connection detection is derived afterward by voting across its window predictions.

Alongside [XGBoost](https://github.com/victorandre957/bip324-traffic-ml/blob/main/src/bip324_traffic_ml/train.py), I tested a [temporal CNN](https://github.com/victorandre957/bip324-traffic-ml/tree/main/experiments/temporal_cnn): an exchange can span several windows, so the CNN reads the target plus up to four adjacent windows on each side **within the same flow**. Ambiguous windows can supply context but not training targets. XGBoost classifies one feature row at a time.

## Results so far

Both models used the same **262,654 flows** and 34 inputs. Splitting by capture kept all eight classes on each side:

| Split | Labeled windows | Distinct flows | Bitcoin v2 flows |
| --- | ---: | ---: | ---: |
| Training | 1,325,246 | 244,618 | 1,753 |
| Test | 97,803 | 18,036 | 138 |

Another 73,130 ambiguous windows were excluded as targets. The CNN could still use them as neighboring context. A **window** is one 250 ms slice; a **flow** is the entire bidirectional exchange. To classify a flow, each model first maps its window predictions to Bitcoin v2 or `other`, then takes the majority vote. A mistaken window therefore does not necessarily make the whole flow a false positive.

| Test result per 250 ms window | XGBoost | Temporal CNN |
| --- | ---: | ---: |
| Window accuracy | 98.58% | 98.83% |
| Macro F1 across eight classes | 0.764 | 0.791 |
| Balanced accuracy | 0.819 | 0.843 |
| V2 windows predicted as `other` | 20 / 6,882 | 10 / 6,882 |
| `other` windows predicted as v2 | 55 / 90,921 | 73 / 90,921 |

| Test result per complete flow (majority vote) | XGBoost | Temporal CNN |
| --- | ---: | ---: |
| Bitcoin v2 flows found | 138 / 138 | 138 / 138 |
| Non-v2 flows incorrectly called Bitcoin v2 | 2 / 17,898 | 2 / 17,898 |

Because `other` makes up **93%** of test windows, per-class F1 matters more than overall accuracy:

| Activity | Test windows | XGBoost F1 | CNN F1 |
| --- | ---: | ---: | ---: |
| V2 handshake | 112 | 0.909 | 0.906 |
| `inv` | 3,746 | 0.898 | 0.927 |
| `cmpctblock` | 578 | 0.838 | 0.837 |
| `tx` | 100 | 0.739 | 0.736 |
| `block` | 69 | 0.667 | 0.730 |
| `getdata` | 167 | 0.397 | 0.444 |
| V2 without a matched specific activity | 2,110 | 0.664 | 0.746 |

The CNN improves macro F1 and cuts missed Bitcoin windows from 20 to 10, but raises false positives from 55 to 73; **60 of its 73** are obfs4-shaped noise. Just 69 block windows appear in the test, so the block F1 gain remains uncertain.

The CNN ran for 32 GPU epochs with batches of 1,024. These are **exploratory lab results**: the same test flows have guided model comparisons, and all runs share a Core build, topology, and generators. New untouched data, randomized ports, different noise, and removal of future/whole-flow inputs are needed before making claims about mainnet or an ISP.
