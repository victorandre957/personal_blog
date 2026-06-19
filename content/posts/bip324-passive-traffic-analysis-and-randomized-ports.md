+++
title = "Finding Bitcoin P2P v2 Traffic After BIP324"
date = 2026-06-10
description = "A Warnet-controlled experiment and b10c mainnet PCAP analysis for studying what a passive observer can still infer from Bitcoin P2P v2 traffic."
[taxonomies]
tags = ["bitcoin", "bip324", "traffic-analysis", "warnet"]
+++

BIP324 encrypts Bitcoin P2P v2 traffic, but encryption does not hide packet sizes, timing, flow direction, or the ports involved in a connection. I wanted to understand what a passive observer can still infer from those metadata signals.

I worked on this from two directions:

1. A controlled **BIP324 traffic lab** built with Warnet.
2. A passive **BIP324 traffic analysis pipeline** that can be applied both to the lab output and to mainnet PCAPs.

This post summarizes what I have found so far, separating controlled Warnet results from exploratory mainnet results, and explains why the findings are relevant to a separate Bitcoin Core feature I have been experimenting with: opt-in randomization of the local P2P listening port.

## Data sources

There are two different kinds of data in this post.

The first source is my **Warnet lab data**. This is controlled data. I know which pods are Bitcoin nodes, which pods are background traffic, when nodes join, when blocks are mined, when transactions are relayed, and which traffic is HTTP, HTTPS/TLS 1.3, Tor, BitTorrent, or UDP streaming. Because I also collect Bitcoin Core logs and an IP map, I can measure true positives, false positives, and false negatives.

The second source is **mainnet PCAP data shared by b10c** from his demo nodes. Those captures are useful because they are longer and come from real mainnet behavior, but I do not have matching Bitcoin Core logs for them. That means I cannot calculate error rates for the b10c data. I can only report passive candidates found by the same heuristics.

The distinction matters: Warnet results are evaluated results; b10c mainnet results are exploratory candidate counts.

## The controlled lab

The lab exists because mainnet captures are hard to validate. If a detector finds a burst of bytes and calls it a block relay, the only way to know whether it was right is to have independent ground truth.

In the Warnet setup I can control and record that ground truth:

- which pods are Bitcoin nodes;
- which pods are background traffic;
- when Bitcoin nodes start;
- when delayed Bitcoin nodes join;
- when blocks are mined;
- when transactions are relayed;
- which traffic belongs to HTTP, HTTPS/TLS 1.3, Tor, BitTorrent, or UDP streaming;
- the seed used to reproduce generated payloads and choices.

The startup order is intentional: the packet sniffer starts first, background traffic starts next, and only then do the Bitcoin nodes start. This gives the passive observer the same kind of view an ISP-like observer would have, while still keeping enough labels to evaluate the analysis later.

The current run has five Bitcoin nodes. Three nodes form the initial network. Two additional nodes join halfway through the simulation and connect to the initial nodes. The analysis sees 13 BIP324 handshake events in this run. That is expected for the observed logs: it is not a full five-node mesh, and the log events represent observed handshake attempts rather than a simple count of unique graph edges.

## What the detector is allowed to see

The passive detector does not decrypt BIP324 traffic and does not inspect Bitcoin messages directly. It only uses metadata:

- packet size;
- timestamp;
- direction inside a TCP flow;
- early flow structure;
- per-second byte bursts;
- whether a flow endpoint uses the expected Bitcoin port in a given scenario.

For Warnet, the analysis can compare predictions against Bitcoin Core logs. That allows precision, recall, false positives, and false negatives to be measured. For the b10c mainnet PCAPs, there are no matching node logs in my dataset, so the analysis can only report candidates. Those mainnet numbers are useful for exploration, but they are not accuracy metrics.

## The three analysis views

I compare each event type in three ways:

1. **All flows**: run the event heuristic on every scoped flow.
2. **Bitcoin port**: run the event heuristic only on flows where one endpoint uses the expected Bitcoin port.
3. **BIP324 handshake filter**: first identify BIP324-like connections, then run the event heuristics only inside those connections.

For Warnet/regtest, the Bitcoin port is `18444`. For mainnet, it is `8333`.

This comparison matters because a default port is a very strong shortcut. If an observer can simply filter for `8333`, the search problem is much smaller before any traffic-analysis heuristic is needed.

## Warnet results

The strongest signal so far is the BIP324 handshake. In the current Warnet run, it is detected correctly across all three views.

![Warnet F1 score by event and analysis view](/images/bip324-traffic-analysis/warnet-f1-by-event.svg)

The handshake detector is looking for early bidirectional encrypted-looking payloads with BIP324-compatible initial sizes and no cleartext protocol hints. It is not using the Bitcoin port as a requirement. That is important: the port makes discovery easier, but the handshake itself also has a visible metadata shape.

Block arrival remains visible, but it is much noisier than the handshake detector. The current detector uses the average incoming block size seen in the logs as a run-specific size reference and then checks whether candidate bursts align with the observed block cadence. In this run, filtering by Bitcoin port or by the BIP324 handshake improves the block-arrival F1 score because it removes many false positives while keeping the same number of true positives.

Compact blocks, large transactions, and address responses are weaker. They produce signals, but they are noisier and less reliable than the handshake detector.

## False positives

The false-positive pattern is as important as the raw score.

![Warnet false positives by event and analysis view](/images/bip324-traffic-analysis/warnet-false-positives.svg)

For block arrival, filtering by Bitcoin port cuts false positives from 1710 to 831 in this run. The BIP324-handshake filter gives the same result. That is still noisy, but it is better than evaluating all flows.

For address responses, the result is identical in all three views. This was surprising at first, but it makes sense after looking at the heuristic. The address-response detector is trying to infer `addr` or `addrv2` responses from small early-session byte bursts. In this run, those candidates were already inside Bitcoin/BIP324 flows. The confusion is not mainly coming from HTTP, HTTPS, Tor, BitTorrent, or UDP noise. It is coming from other encrypted Bitcoin traffic that has a similar small-burst shape.

That is a useful negative result: address-response detection is currently exploratory, not reliable.

## Search-space reduction

Filtering by port or by detected BIP324 handshakes greatly reduces the number of flows that later heuristics need to inspect.

![Warnet flow scope comparison](/images/bip324-traffic-analysis/warnet-flow-scope.svg)

In this Warnet run, the all-flow view contains 767 flows. The Bitcoin-port view contains 25 flows. The BIP324-handshake-filtered view also contains 25 candidate flows. In other words, in this controlled capture, filtering by the known Bitcoin port and filtering by the detected BIP324 handshake produce practically the same flow set.

This is exactly why the default port matters. Even if encryption hides message contents, a stable and well-known listening port gives a passive observer a cheap first filter that reaches almost the same place as a more protocol-specific handshake detector. If the port is randomized, an observer loses that cheap first step and has to rely more directly on metadata heuristics such as the BIP324 handshake shape.

## b10c mainnet PCAPs

I also applied the same passive methodology to two longer mainnet captures shared by b10c. These captures do not include Bitcoin Core logs in my analysis dataset, so there is no ground truth for true positives or false positives. The chart below should be read as candidate volume, not accuracy.

![Mainnet passive candidate counts](/images/bip324-traffic-analysis/mainnet-candidate-counts.svg)

In these captures, the Bitcoin-port-filtered view is identical to the all-flow view. I interpret this as a sign that the exported PCAPs are already heavily scoped around Bitcoin-port traffic. In that setup, filtering on `8333` cannot improve the result because the capture itself has already removed most of the unrelated traffic.

Even with that limitation, the same pattern appears: handshake candidates are much more interpretable than the other event types. Block candidates are rare, while address-response and large-transaction candidates are very frequent and need stronger validation before they can support firm claims about mainnet behavior.

## How this relates to randomized P2P ports

The randomized-port feature I have been experimenting with is opt-in. The idea is:

- if the user passes `-port`, Bitcoin Core keeps using that explicit port;
- if `-randomizep2pport=1` is enabled and no port was provided, the node chooses a port in `49152-65534`;
- the chosen port is persisted and reused on restart;
- the port is only saved after the node successfully binds;
- remote peers using default ports remain valid.

This does not make BIP324 traffic impossible to detect. The Warnet results show that the handshake can still be detected from metadata without relying on the port.

But it does remove the easiest classifier: "look for connections involving the default Bitcoin port." That matters because passive traffic analysis is often a pipeline. In the Warnet data, the port filter and the BIP324-handshake filter reduce the dataset to almost the same flow set. The difference is that the port filter is trivial, while the handshake filter requires actual traffic-analysis logic.

In other words, randomized ports do not replace BIP324. They complement it by removing one obvious side channel while BIP324 removes cleartext protocol contents.

## Current takeaways

My current conclusions are:

- BIP324 handshakes are the clearest passive signal in these experiments.
- Block arrivals are visible, but still noisy; filtering by Bitcoin port or by detected BIP324 handshakes improves the result in the current Warnet run.
- Compact blocks, large transactions, and address responses need more careful heuristics before they are useful as reliable detectors.
- In the Warnet data, filtering by Bitcoin port and filtering by detected BIP324 handshakes produce practically the same flow scope.
- Default Bitcoin ports make passive classification much easier because they provide that scope almost for free.
- Randomizing the listening port would not defeat traffic analysis by itself, but it would remove a cheap and highly effective first filter.

The next useful step is to test the same analysis against captures where Bitcoin nodes listen on randomized ports while the sniffer captures all ports, not only `8333` or `18444`. That would measure how much harder the first-stage discovery problem becomes when the port shortcut is removed.
