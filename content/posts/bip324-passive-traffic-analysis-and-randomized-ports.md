+++
title = "Passive Traffic Analysis of Bitcoin P2P v2"
date = 2026-06-23
description = "A Warnet-controlled experiment and b10c mainnet PCAP analysis for studying passive metadata signals in Bitcoin P2P v2 traffic."
[taxonomies]
tags = ["bitcoin", "bip324", "traffic-analysis", "warnet"]
+++

<style>
table {
  background: color-mix(in srgb, currentColor 3%, transparent);
  border: 1px solid color-mix(in srgb, currentColor 14%, transparent);
  border-collapse: collapse;
}

thead {
  background: color-mix(in srgb, currentColor 6%, transparent);
}

th,
td {
  border: 1px solid color-mix(in srgb, currentColor 12%, transparent);
  padding: 0.45rem 0.6rem;
}
</style>

BIP324 encrypts Bitcoin P2P v2 traffic and hides the protocol's internal packet length field, but a network observer can still see TCP/IP packet sizes, timing, flow direction, connection endpoints, and the ports involved in a connection. I wanted to understand what a passive observer can still infer from those metadata signals.

I worked on this from two directions:

1. A controlled **BIP324 traffic lab** built with Warnet: [`victorandre957/bip324-traffic-lab`](https://github.com/victorandre957/bip324-traffic-lab).
2. A passive **BIP324 traffic analysis pipeline** that can be applied both to the lab output and to mainnet PCAPs: [`victorandre957/bip324-traffic-analysis`](https://github.com/victorandre957/bip324-traffic-analysis).

This post summarizes the current test results, separating controlled Warnet data from exploratory mainnet candidates, and connects them to an experiment with opt-in randomization of the local P2P listening port.

## Data sources

I use the Warnet lab for evaluated results and the b10c mainnet PCAPs only as candidate data.

The Warnet run has Bitcoin Core logs, an IP map, packet capture, node roles, and the simulation seed. That lets me compare passive detections against a separate log-derived reference. The detector itself only reads the PCAP; logs are used after detection for validation.

The mainnet PCAPs do not have matching logs in this dataset. I do not use them for precision, recall, or confusion matrices.

These are test results from a small controlled setup. They are useful for checking whether the passive features are plausible, not for making broad claims about the public Bitcoin network.

## What the detector sees

The detector does not decrypt BIP324 and does not read Bitcoin message types. It builds a passive timeline per TCP flow from packet size, timestamp, direction, burst shape, early handshake structure, and the position of later bursts inside the connection.

The current version also exports notebook evidence tables: per-flow timeline buckets, event evidence, false-positive rows, and validation rows. That made the analysis easier to inspect than the earlier size-threshold-only version.

## Evaluation rules

The Warnet evaluation is event matching, not packet decryption. The rules below describe what the passive detector looks for in the PCAP; the logs are only the evaluation reference.

These heuristics are still being improved, so the numbers below should be read as the current state of the experiment, not as final classifier performance. The detector is strictly passive: it only uses packet-capture metadata. It does not run another Bitcoin node to observe the network, decrypt BIP324, read message types, or use Warnet profiles/logs to decide detections.

| Label | Meaning |
| --- | --- |
| `TP` | predicted event matched a log event |
| `FP` | predicted event had no matching log event |
| `FN` | log event had no matching prediction |
| `TN` | not computed; the current evaluator does not enumerate every negative window or negative flow |

The percentages in the charts use `TP + FP + FN` as the denominator. `TN` is shown as unavailable instead of being inferred.

| Data | Passive rule used in this test |
| --- | --- |
| BIP324 handshake | early encrypted-looking TCP flow, BIP324-sized initial flight, no cleartext hint, high entropy, bidirectional payload |
| Block arrival | large encrypted burst with timing support from nearby block-like activity |
| Compact block arrival | compact-block-sized burst in a post-handshake flow |
| Block propagation wave | block-like activity appearing close together across multiple BIP324-looking flows |
| Large transaction | post-handshake burst above the calibrated large-transaction threshold |
| INV announcement | small post-handshake burst shaped like inventory metadata |
| Request-like burst | small opposite-direction burst after inventory-like activity |
| TX-like burst | transaction-sized burst in the transaction-relay window |
| Transaction relay exchange | inventory-like burst, request-like burst, then tx-like burst in the same flow |

## The three filters

I compare each event type with three filters:

1. **No filter**: run the event heuristic on every scoped flow.
2. **filter by bitcoin port**: run the event heuristic only on flows where one endpoint uses the expected Bitcoin port.
3. **filter by handshake**: first identify BIP324-like connections, then run the event heuristics only inside those connections.

For Warnet/regtest, the Bitcoin port is `18444`. For mainnet, it is `8333`.

This comparison matters because a default port is a cheap shortcut. If an observer can filter for `8333`, the search problem becomes smaller before any traffic-analysis heuristic is applied.

## Warnet results

The tables below use `TP + FP + FN` as the measured option count. They include the three filters: no filter, filter by bitcoin port, and filter by handshake.

### Handshake

| Event | Filter | Options | Correct | TP | FP | FN |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| BIP324 handshake | No filter | 13 | 12 (92.3%) | 12 (92.3%) | 1 (7.7%) | 0 (0.0%) |
| BIP324 handshake | filter by bitcoin port | 12 | 12 (100.0%) | 12 (100.0%) | 0 (0.0%) | 0 (0.0%) |
| BIP324 handshake | filter by handshake | 13 | 12 (92.3%) | 12 (92.3%) | 1 (7.7%) | 0 (0.0%) |

The single handshake error is the same case shown in the notebook: a Tor/noise flow matched enough early-flow BIP324 checks to be counted as a false positive. The port filter avoids it because the flow is not on the Bitcoin port.

### Blocks

| Event | Filter | Options | Correct | TP | FP | FN |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Block arrival | No filter | 7295 | 264 (3.6%) | 264 (3.6%) | 5383 (73.8%) | 1648 (22.6%) |
| Block arrival | filter by bitcoin port | 1982 | 264 (13.3%) | 264 (13.3%) | 70 (3.5%) | 1648 (83.1%) |
| Block arrival | filter by handshake | 1982 | 264 (13.3%) | 264 (13.3%) | 70 (3.5%) | 1648 (83.1%) |
| Compact block arrival | No filter | 3629 | 302 (8.3%) | 302 (8.3%) | 2629 (72.4%) | 698 (19.2%) |
| Compact block arrival | filter by bitcoin port | 2431 | 302 (12.4%) | 302 (12.4%) | 1431 (58.9%) | 698 (28.7%) |
| Compact block arrival | filter by handshake | 2432 | 302 (12.4%) | 302 (12.4%) | 1432 (58.9%) | 698 (28.7%) |
| Block propagation wave | No filter | 2201 | 1 (0.0%) | 1 (0.0%) | 289 (13.1%) | 1911 (86.8%) |
| Block propagation wave | filter by bitcoin port | 2022 | 121 (6.0%) | 121 (6.0%) | 110 (5.4%) | 1791 (88.6%) |
| Block propagation wave | filter by handshake | 2023 | 120 (5.9%) | 120 (5.9%) | 111 (5.5%) | 1792 (88.6%) |

### Transactions

| Event | Filter | Options | Correct | TP | FP | FN |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Large transaction | No filter | 3118 | 189 (6.1%) | 189 (6.1%) | 2876 (92.2%) | 53 (1.7%) |
| Large transaction | filter by bitcoin port | 791 | 189 (23.9%) | 189 (23.9%) | 549 (69.4%) | 53 (6.7%) |
| Large transaction | filter by handshake | 791 | 189 (23.9%) | 189 (23.9%) | 549 (69.4%) | 53 (6.7%) |
| INV announcement | No filter | 3679 | 207 (5.6%) | 207 (5.6%) | 27 (0.7%) | 3445 (93.6%) |
| INV announcement | filter by bitcoin port | 3652 | 207 (5.7%) | 207 (5.7%) | 0 (0.0%) | 3445 (94.3%) |
| INV announcement | filter by handshake | 3653 | 207 (5.7%) | 207 (5.7%) | 1 (0.0%) | 3445 (94.3%) |
| Request-like burst | No filter | 2692 | 54 (2.0%) | 54 (2.0%) | 0 (0.0%) | 2638 (98.0%) |
| Request-like burst | filter by bitcoin port | 2692 | 54 (2.0%) | 54 (2.0%) | 0 (0.0%) | 2638 (98.0%) |
| Request-like burst | filter by handshake | 2692 | 54 (2.0%) | 54 (2.0%) | 0 (0.0%) | 2638 (98.0%) |
| TX-like burst | No filter | 1646 | 54 (3.3%) | 54 (3.3%) | 0 (0.0%) | 1592 (96.7%) |
| TX-like burst | filter by bitcoin port | 1646 | 54 (3.3%) | 54 (3.3%) | 0 (0.0%) | 1592 (96.7%) |
| TX-like burst | filter by handshake | 1646 | 54 (3.3%) | 54 (3.3%) | 0 (0.0%) | 1592 (96.7%) |
| Transaction relay exchange | No filter | 2172 | 54 (2.5%) | 54 (2.5%) | 0 (0.0%) | 2118 (97.5%) |
| Transaction relay exchange | filter by bitcoin port | 2172 | 54 (2.5%) | 54 (2.5%) | 0 (0.0%) | 2118 (97.5%) |
| Transaction relay exchange | filter by handshake | 2172 | 54 (2.5%) | 54 (2.5%) | 0 (0.0%) | 2118 (97.5%) |

I tested an address-response heuristic too, but it is not included here as a usable result. In this Warnet run it had zero matching `addr`/`addrv2` log events and only produced false positives, so I treat it as a discarded rule rather than a detector.

The matrices below show the filter by handshake view as a 2x2 layout. The evaluator does not enumerate true-negative windows, so the `TN` cell is shown as `0`.

![Warnet BIP324 handshake matrix](../../images/bip324-traffic-analysis/warnet-confusion-handshake.svg)

![Warnet block arrival matrix](../../images/bip324-traffic-analysis/warnet-confusion-block-arrival.svg)

![Warnet compact block arrival matrix](../../images/bip324-traffic-analysis/warnet-confusion-compact-block-arrival.svg)

![Warnet block propagation wave matrix](../../images/bip324-traffic-analysis/warnet-confusion-block-propagation-wave.svg)

![Warnet large transaction matrix](../../images/bip324-traffic-analysis/warnet-confusion-large-transaction.svg)

![Warnet INV announcement matrix](../../images/bip324-traffic-analysis/warnet-confusion-inv-announcement.svg)

![Warnet request-like burst matrix](../../images/bip324-traffic-analysis/warnet-confusion-request-like-burst.svg)

![Warnet TX-like burst matrix](../../images/bip324-traffic-analysis/warnet-confusion-tx-like-burst.svg)

![Warnet transaction relay exchange matrix](../../images/bip324-traffic-analysis/warnet-confusion-transaction-relay-exchange.svg)

The handshake case is still the easiest signal to inspect in this run, but it is not perfect: one encrypted noise flow matched enough early-flow checks to become a false positive. The notebook shows that case directly.

## Search-space reduction

Filtering by port or by detected BIP324 handshakes changes how many flows the later event rules inspect. The chart uses absolute flow counts on a log scale because the all-flow case is much larger than the filtered cases.

![Warnet flow scope comparison](../../images/bip324-traffic-analysis/warnet-flow-scope.svg)

This is why the default port matters in the experiment. Even when message contents are encrypted, a stable listening port gives a passive observer a cheap first filter. Randomizing the listening port would remove that shortcut for inbound discovery, but it would not remove the metadata signals themselves.

## b10c mainnet PCAPs

I also applied the same passive methodology to mainnet captures shared by b10c. These rows are candidate counts only. There are no matching Bitcoin Core logs in this dataset, so the table does not say whether a candidate is right or wrong.

| Capture | Filter | TCP flows | Handshake candidates | Passive candidates | Handshake | Block | Compact block | Large tx |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| bnoc-111-hal | No filter | 215433 | 456 | 159293 | 456 | 51 | 1043 | 19635 |
| bnoc-111-hal | filter by bitcoin port | 215433 | 456 | 159293 | 456 | 51 | 1043 | 19635 |
| bnoc-111-hal | filter by handshake | 215433 | 456 | 117789 | 456 | 2 | 860 | 14208 |
| bnoc-111-len | No filter | 168389 | 400 | 146651 | 400 | 64 | 1083 | 19384 |
| bnoc-111-len | filter by bitcoin port | 168389 | 400 | 146651 | 400 | 64 | 1083 | 19384 |
| bnoc-111-len | filter by handshake | 168389 | 400 | 107245 | 400 | 19 | 685 | 12109 |

The `No filter` and `filter by bitcoin port` rows are identical here because these captures are already scoped around Bitcoin-port traffic. The handshake filter reduces later candidate volume, but without logs I treat that only as a candidate reduction, not as better accuracy.

## Why randomized P2P ports matter here

The randomized-port feature I have been experimenting with is opt-in. I currently have two alternative implementations in my own Bitcoin Core fork, not upstream Bitcoin Core:

- [victorandre957/bitcoin#3](https://github.com/victorandre957/bitcoin/pull/3): dynamic randomization, where the node changes the listening port for each new connection and advertises the current port.
- [victorandre957/bitcoin#2](https://github.com/victorandre957/bitcoin/pull/2): startup randomization, where the node chooses a randomized port and persists it across restarts.

The final design would likely be one of these approaches, not both. The startup-randomization version is the simpler model:

- if the user passes `-port`, Bitcoin Core keeps using that explicit port;
- if `-randomizep2pport=1` is enabled and no port was provided, the node chooses a port in `49152-65534`;
- the chosen port is persisted and reused on restart;
- the port is only saved after the node successfully binds;
- remote peers using default ports remain valid.

Using a non-default listening port can make passive discovery harder because it removes the simplest first-stage filter: "look for traffic involving port `8333`." That does not make BIP324 traffic disappear from metadata. In this test setup, the handshake heuristic can still find candidates without relying on the port.

The dynamic version is more complex because the reachable address changes across connections and has to be advertised correctly. The startup version is simpler because it behaves like a stable non-default listening port after first bind. Both versions share an important trade-off: today, peers cannot directly connect to that node only from a DNS seed result, because DNS seeds do not currently carry the randomized per-node port in the way this experiment would need.

Both options remove a cheap classifier for inbound traffic and listening-node discovery. They do not hide outbound connections to peers that still listen on `8333`, and they do not remove timing or packet-size metadata. In practice, that gives a passive observer two broad choices: use the default-port shortcut when it exists, or rely more heavily on passive flow metadata when it does not.

In other words, randomized ports do not replace BIP324. They may complement it by removing one simple side channel while BIP324 removes cleartext protocol contents.

## Current takeaways

My current read is modest:

- the handshake heuristic is the easiest result to inspect;
- block and transaction rules are still experimental metadata rules;
- the newer temporal sequence tables make misses and false positives easier to debug;
- randomized listening ports would not solve traffic analysis, but they can remove one simple first-stage filter.

The next useful test is a capture where Bitcoin nodes listen on randomized ports and the sniffer captures all ports, not only `8333` or `18444`.
