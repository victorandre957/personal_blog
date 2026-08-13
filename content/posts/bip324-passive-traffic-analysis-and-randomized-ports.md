+++
title = "Passive Traffic Analysis of Bitcoin P2P v2"
date = 2026-06-23
updated = 2026-08-12
description = "A controlled Warnet experiment and mainnet PCAP study of the metadata that remains visible in Bitcoin P2P v2 traffic."
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

BIP324 encrypts Bitcoin P2P v2 messages and their internal length field. A passive observer cannot read the message type, but can still measure TCP/IP headers, payload sizes, timing, direction, endpoints, and connection behavior. This experiment asks how much those signals reveal without decrypting traffic or operating another Bitcoin node as an observer.

I use two separate projects:

1. A controlled [BIP324 Warnet lab](https://github.com/victorandre957/bip324-traffic-lab), which produces PCAPs, Bitcoin Core logs, and reproducibility metadata.
2. A [passive analysis pipeline](https://github.com/victorandre957/bip324-traffic-analysis), which detects candidates from PCAPs and uses logs only afterward to evaluate them.

This is an updated account of an ongoing experiment. In the same-capture comparison, some transaction metrics increased, while the block metrics remained similar or decreased. The numbers below describe one controlled run and should not be generalized to the public network.

## Experimental boundary

Event classification uses only features derived from the PCAP. For Warnet captures, the pipeline first uses `ip-map.txt` to define the controlled lab scope and exclude the sniffer and unmapped infrastructure flows. The map is not used to tell the classifier whether a retained flow is Bitcoin or noise. Bitcoin Core logs and `metadata.json` are loaded only after candidate generation for validation, labeling, and reproducibility.

The b10c mainnet captures do not have matching logs in this dataset. They can show candidate volume, but not whether a candidate is correct.

The current Warnet run contains 632 lab-scoped flows, including five Bitcoin-port flows and one additional handshake-like candidate. That sixth candidate is the obfs4 noise flow. It started `3.71` seconds before the common PCAP/log validation window, so it is visible in the captured-flow audit but excluded from the temporal confusion counts. The seed is recorded as `9c221b3ee1d50c69b6cb6dc55919a958`.

## What changed in the lab

The first lab version used a dense topology and relatively uniform traffic, which provided limited variation for evaluating temporal heuristics. The current lab includes:

- sparse directed connections instead of a full mesh;
- miner, heavy sender, light sender, delayed burst sender, and quiet peer roles;
- seeded jitter in transaction and block intervals;
- small, medium, and mainnet-like block-load profiles;
- delayed joins and an outbound-only node;
- deterministic latency, jitter, and optional loss with `tc netem`;
- Tor, obfs4-shaped, UDP, BitTorrent, and other background flows;
- bridge-interface capture, graceful `tcpdump` shutdown, nanosecond timestamps, and capture statistics.

The capture also keeps enough TCP/IP header information for complementary fingerprinting. Generated roles and network settings are saved in `metadata.json`, but they are never inputs to passive classification.

## What changed in the analysis

The old detector relied heavily on byte thresholds inside one-second buckets. The new pipeline preserves those simple features, but adds connection and temporal context.

| Evidence | How it is used |
| --- | --- |
| TCP sessions | a new SYN separates reused endpoint pairs into distinct connections |
| Sequence numbers | retransmitted or duplicated payload overlap is excluded from burst totals |
| Multi-scale timeline | each flow is summarized in 100 ms, 250 ms, and 1 s buckets |
| Burst context | bytes, packets, direction, gap, duration, density, and time since handshake are retained |
| Segment-size evidence | TCP payload lengths are checked as candidates, with explicit warnings about segmentation and aggregation |
| Transaction sequence | inventory-like, reverse request-like, and TX-like evidence can form a tolerant relay sequence |
| Block episode | forward timing, independent flows, size coherence, precursors, and burst strength produce a propagation score |
| TCP/IP fingerprint | TTL, window, MSS, window scale, SACK, timestamps, and option order are exported as supporting context |

The fingerprint is not treated as OS ground truth. Containers in this lab share similar Linux network stacks, and NAT or middleboxes may alter observed fields. I retain it as complementary context rather than as a hard label.

The pipeline exports the evidence associated with each decision, including `notebook_flow_timeline.csv`, `notebook_event_evidence.csv`, segment-size evidence, fingerprints, false positives, and validation matches. These tables are intended to support inspection of individual cases alongside aggregate metrics.

## Related research

These changes draw on four pieces of prior work, while keeping this experiment strictly passive.

| Work | Contribution | Use in this experiment |
| --- | --- | --- |
| [Ndolo and Tschorsch, *Security Analysis of Bitcoin's V2 Transport Protocol* (2026)](https://arxiv.org/abs/2605.19715) | studies BIP324 message classification from visible TCP payload lengths and discusses active eclipse and downgrade attacks | motivates explicit payload-size candidates and their validation; the active attacks are outside this lab |
| [Lastovicka et al., *Passive operating system fingerprinting revisited* (2023)](https://doi.org/10.1016/j.comnet.2023.109782) | evaluates TCP/IP features used for passive OS fingerprinting and the limits of aging, fixed signatures | motivates exporting transport fingerprints as complementary, uncertain evidence |
| [Neudecker, Andelfinger, and Hartenstein, *Timing Analysis for Inferring the Topology of the Bitcoin Peer-to-Peer Network* (2016)](https://publikationen.bibliothek.kit.edu/1000067310) | relates Bitcoin relay timing across observations to propagation and topology | motivates causal forward windows, multiple independent flows, and varied link latency; this detector does not infer topology |
| [Grundmann et al., *Estimating the Peer Degree of Reachable Peers in the Bitcoin P2P Network* (2021)](https://arxiv.org/abs/2108.00815) | estimates reachable-peer degree and shows why observations must be grouped carefully before counting peers | motivates varied node degree and avoiding independent-peer evidence from mirrored NAT capture legs |

The 2026 BIP324 paper is directly relevant to the size analysis, while also describing an important limitation. A fixed-size application message may leave a useful payload-size trace, whereas variable messages such as blocks are harder to identify. TCP can split one encrypted packet or combine several packets into one segment. For that reason, I treat an exact payload length as supporting evidence, not as a decoded message type.

## Evaluation

Warnet logs provide an operational reference only after passive detection finishes. A prediction is matched to a compatible log event inside a chosen time window. This reference is not equivalent to packet-level ground truth: one application event may produce observations in several node logs, and matching results depend on event definitions and window sizes.

| Label | Meaning |
| --- | --- |
| `TP` | predicted event matched a reference event |
| `FP` | prediction had no matching reference event |
| `FN` | reference event had no matching prediction |
| `TN` | not measured because the evaluator does not enumerate all negative windows |

The same PCAP is evaluated with three filters:

| Filter | Scope |
| --- | --- |
| No filter | inspect all flows |
| filter by bitcoin port | inspect flows involving Warnet port `18444` |
| filter by handshake | detect BIP324-like handshakes first, then inspect those flows |

Here, precision is the fraction of predictions matched to the reference, recall is the fraction of reference events matched by predictions, and F1 is their harmonic mean. These metrics therefore inherit the limitations of the reference and matching procedure.

### Current run

The table compares F1 across all three filters inside the common PCAP/log validation window. The last three columns expose the temporal confusion counts for the handshake-filtered result.

| Event | No filter F1 | Bitcoin-port F1 | Handshake-filter F1 | Temporal TP | Temporal FP | Temporal FN |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BIP324 handshake | 100.00% | 100.00% | 100.00% | 5 | 0 | 0 |
| Block arrival | 6.96% | 15.89% | 13.79% | 164 | 481 | 1,569 |
| Compact block arrival | 8.35% | 20.47% | 18.10% | 79 | 220 | 495 |
| Block propagation wave | 0.74% | 4.75% | 4.98% | 46 | 68 | 1,687 |
| Large transaction | 3.91% | 47.84% | 14.42% | 83 | 858 | 127 |
| INV announcement | 61.06% | 69.32% | 61.06% | 374 | 249 | 228 |
| Request-like burst | 34.32% | 36.89% | 34.32% | 360 | 263 | 1,115 |
| TX-like burst | 56.79% | 65.13% | 56.79% | 324 | 299 | 194 |
| Transaction relay sequence | 61.07% | 70.58% | 61.07% | 331 | 292 | 130 |

Inside the validation window, the handshake detector found all five reference handshakes and produced no measured false positive. The wider captured-flow scope still contains the earlier obfs4 candidate described above. The `100%` temporal score therefore describes only the five validated connections, not perfect separation from encrypted noise.

For handshake noise testing, I use a second evaluation over all 632 retained lab flows, including traffic outside the PCAP/log overlap. It treats flows involving the controlled Bitcoin nodes as positives and lab-generated noise flows as negatives. The IP map supplies these labels after candidate generation. This assumes that the mapped tank connections are BIP324 flows and should be understood as lab-level flow labeling, not packet-level message ground truth.

| Scope | Bitcoin flows | Noise flows | TP | FP | FN | TN | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Captured lab flows | 5 | 627 | 5 | 1 | 0 | 626 | 83.33% | 100.00% | 90.91% |

| Noise type | Flows | Handshake candidates |
| --- | ---: | ---: |
| BitTorrent | 1 | 0 |
| HTTP | 258 | 0 |
| HTTPS | 249 | 0 |
| Tor | 117 | 0 |
| obfs4 | 1 | 1 |
| UDP streaming | 1 | 0 |

In this capture, the single obfs4 flow matched the current early-flight rules and was counted as a false positive. The overall false-positive rate across labeled noise flows is `0.16%`; however, the obfs4 subset contains only one flow. This observation identifies a case that the current heuristic does not separate, but it does not estimate an obfs4 false-positive rate.

Future lab runs hold the obfs4 client until the initial Bitcoin setup is complete, with the intention of placing its connection inside the Core-log interval as well. The captured-flow audit remains separate as a complementary test when event logs start later than the capture.

In this run, the transaction-sequence detector produced non-zero matches and measured `71.80%` recall, compared with `62.13%` for INV, `24.41%` for request-like, and `62.55%` for TX-like evidence. This comparison is internal to the current reference mapping and does not establish message decoding. The measured block results remain limited: block arrival produced 481 false positives and `9.46%` recall, while block propagation produced `2.65%` recall.

The current passive thresholds are independent from logs. An older implementation derived Warnet thresholds from Bitcoin Core events, introducing validation information into detection and producing higher metrics for some block cases. The current implementation removes that dependency, while the resulting block measurements indicate that the fixed threshold still requires calibration.

### Historical comparison on the same capture

To separate code changes from different Warnet runs, I executed the old and current analysis against the same PCAP and logs. The old values below are retained from that archived comparison; the current column was checked again against the present CSV output.

| Event | Old handshake-filter F1 | Current handshake-filter F1 | Observation |
| --- | ---: | ---: | --- |
| BIP324 handshake | 100.00% | 100.00% | unchanged |
| Block arrival | 14.21% | 13.79% | slightly lower |
| Compact block arrival | 18.12% | 18.10% | effectively unchanged |
| Block propagation wave | 6.84% | 4.98% | lower |
| INV announcement | 68.49% | 61.06% | lower |
| Request-like burst | 15.02% | 34.32% | higher |
| TX-like burst | 36.39% | 56.79% | higher |
| Transaction relay sequence | 40.87% | 61.07% | higher |

Large-transaction results are omitted from this comparison because its reference definition changed. On this capture, F1 increased for the request-like, TX-like, and transaction-sequence rules, while it decreased or remained approximately unchanged for block, propagation, compact-block, and INV rules. This comparison does not establish behavior on other captures.

### Confusion matrices

The handshake matrix uses labels for all retained lab flows and therefore includes the measured `TN=626` and the obfs4 false positive. Its cell percentages use all labeled flows as the denominator. The remaining matrices use temporal event matching inside the PCAP/log overlap. Their percentages use `TP + FP + FN`, and their `TN=0` cells are placeholders because negative event windows are not enumerated.

The high FN counts are present in the current evaluation: five of the eight post-handshake rules miss more than half of their corresponding log references. The highest miss rates are block propagation (`97.35%`), block arrival (`90.54%`), compact-block arrival (`86.24%`), request-like bursts (`75.59%`), and large transactions (`60.48%`). These are `FN / (TP + FN)` rates, not the displayed share of all measured outcomes. They indicate low measured recall, but may also reflect the difference between per-node or per-peer log records and aggregated passive bursts. The results therefore show a limitation of the present detector and reference mapping rather than a packet-level count of every missed message.

![Warnet BIP324 handshake confusion matrix](../../images/bip324-traffic-analysis/warnet-confusion-handshake.svg)

![Warnet block arrival confusion matrix](../../images/bip324-traffic-analysis/warnet-confusion-block-arrival.svg)

![Warnet compact block arrival confusion matrix](../../images/bip324-traffic-analysis/warnet-confusion-compact-block-arrival.svg)

![Warnet block propagation wave confusion matrix](../../images/bip324-traffic-analysis/warnet-confusion-block-propagation-wave.svg)

![Warnet large transaction confusion matrix](../../images/bip324-traffic-analysis/warnet-confusion-large-transaction.svg)

![Warnet INV announcement confusion matrix](../../images/bip324-traffic-analysis/warnet-confusion-inv-announcement.svg)

![Warnet request-like burst confusion matrix](../../images/bip324-traffic-analysis/warnet-confusion-request-like-burst.svg)

![Warnet TX-like burst confusion matrix](../../images/bip324-traffic-analysis/warnet-confusion-tx-like-burst.svg)

![Warnet transaction relay sequence confusion matrix](../../images/bip324-traffic-analysis/warnet-confusion-transaction-relay-exchange.svg)

## Search-space reduction

In this run, the port and handshake filters reduced how many retained lab flows reached later heuristics. A logarithmic scale keeps the 632-flow unfiltered case readable beside the smaller filtered sets.

![Warnet flow scope comparison](../../images/bip324-traffic-analysis/warnet-flow-scope.svg)

This is a reduction in work, not an accuracy result. The Bitcoin-port filter inspected five flows. The handshake stage selected six candidates without using the port: five labeled Bitcoin flows and the pre-window obfs4 flow.

## Mainnet captures

I also applied the passive pipeline to two mainnet PCAPs shared by b10c. In the generated outputs, every retained flow also appears in the `8333`-port view, so the no-filter and port-filter counts are identical and only one of those duplicate rows is shown below. There are no matching logs, and the values are candidate counts rather than TP, FP, or FN.

| Capture | Filter | TCP flows | Handshake candidates | Block candidates | Compact-block candidates | Large-tx candidates |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| bnoc-111-hal | No filter | 215,433 | 456 | 51 | 1,043 | 19,635 |
| bnoc-111-hal | filter by handshake | 215,433 | 456 | 2 | 860 | 14,208 |
| bnoc-111-len | No filter | 168,389 | 400 | 64 | 1,083 | 19,384 |
| bnoc-111-len | filter by handshake | 168,389 | 400 | 19 | 685 | 12,109 |

The table only shows that filtering changes candidate volume. Without independent labels, it cannot establish accuracy.

## Randomized P2P ports

A stable default listening port can provide an observer with a simple first-stage filter: inspect flows involving `8333`. A non-default port may make that filter less useful, while packet-size and timing metadata remain observable.

The implementation retained in my Bitcoin Core fork is an opt-in random port selected at startup. It is not part of upstream Bitcoin Core, and the current tests establish local behavior rather than a deployment-ready privacy result.

### Random port selected at startup

In the [startup-randomization experiment](https://github.com/victorandre957/bitcoin/pull/2), `-port=0` requests a port from `49152` through `65534`. The implementation excludes the known Bitcoin network ports and ports that Bitcoin Core already considers unsuitable, checks whether the candidate can be bound, and makes at most 512 attempts. This applies to the clearnet listener; the default Tor target is deliberately left unchanged.

The selected port is written to `settings.json` only after the connection manager starts successfully. Later starts reuse that value. If the saved port is no longer available, startup fails instead of silently choosing another one. This makes the advertised endpoint stable across restarts, although it also requires operator intervention after a port conflict. Explicit `-bind`, `-whitebind`, and `-externalip` ports are validated separately.

The experiment uses Bitcoin Core's existing local-address path. `GetListenPort()` returns the selected port, `AddLocal()` associates it with discovered or configured local addresses, and the node can advertise the resulting IP-and-port endpoint in `addr` or `addrv2` messages. Randomization therefore changes the endpoint advertised through P2P address relay; it does not add a new discovery protocol.

### Why dynamic rotation was discarded

I also prototyped rotating the listening port after accepted inbound connections, but did not retain that design. Keeping it reachable would require the surrounding network infrastructure to follow every rotation, including firewall rules, router port forwarding or NAT mappings, and address announcements. That adds operational state whose correctness is difficult to preserve across different environments.

The prototype also did not indicate a clear additional benefit for hiding the node. Rotation changes the destination port, but a passive observer can still see the IP address, TCP connection timing, packet sizes, direction, and BIP324 handshake-like behavior. Given that limited expected benefit and the additional reachability complexity, the current work focuses only on choosing and persisting a non-default port at startup. This is an engineering decision based on the present implementation and experiments, not a general proof that dynamic rotation cannot be useful under another threat model.

### Discovery and passive observation

Bitcoin Core's current DNS-seed path converts returned IP addresses into endpoints using the network's default port. A DNS response alone therefore cannot tell a new node which random port was selected at startup. A randomized listener may still become discoverable through `addr` or `addrv2`, because those records include the port, but that requires the endpoint to reach address relay through some other peer. This is a reachability trade-off, not evidence that randomized nodes cannot be reached at all.

For a passive observer, plausible approaches include using the default-port filter where it exists or searching a wider set of flows using handshake and temporal metadata. The 2026 BIP324 security analysis similarly treats the default port as useful prior knowledge because v2 traffic is not self-identifying on the wire.

Port randomization has not been included in the accuracy measurements presented above. At most, the implementation suggests that a non-default listening port can remove one convenient signal from inbound-flow selection. It does not hide IP addresses, TCP behavior, packet sizes, timing, or outbound connections to peers that still listen on `8333`. It should therefore not be treated as a replacement for BIP324 or as a demonstrated privacy improvement without broader testing.

## Current limits and next steps

The handshake heuristic has the highest measured scores in this run, but the positive sample contains only five flows and the obfs4 case remains a false positive. The transaction-sequence F1 is higher than in the earlier implementation on this capture, while its false-positive count remains substantial. The current block measurements do not support broad claims about block identification.

A more defensible next evaluation would freeze event definitions, calibrate thresholds on separate training captures, and test them on held-out Warnet seeds. More varied operating systems and network paths would also be needed to evaluate whether TCP/IP fingerprints contribute useful information. Estimating mainnet accuracy would require an independent reference; candidate counts alone are insufficient.
