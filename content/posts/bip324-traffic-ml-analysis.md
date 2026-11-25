+++
title = "Identifying BIP324 Traffic: Final Analysis of a Controlled ML Experiment"
date = 2026-10-14
updated = 2026-11-25
aliases = ["/posts/bip324-traffic-ml-v2-preliminary-results/"]
description = "XGBoost and CNN identify Bitcoin traffic without IPs or ports. Final lab results compare activity classification, false alarms, feature dependence and recognition without the connection opening."
[taxonomies]
tags = ["bitcoin", "bip324", "traffic-analysis", "machine-learning", "warnet"]
+++

BIP324 encrypts P2P messages, while packet sizes, timing and direction remain observable. Building on my [earlier passive analysis](@/posts/bip324-passive-traffic-analysis-and-randomized-ports.md), this experiment asks whether those measurements can identify **Bitcoin connections and their activities in a full-network PCAP**.

**Throughout this article, “Bitcoin traffic” means traffic using BIP324. Legacy v1 is outside the positive target and grouped under `other`.**

I compare **XGBoost** and a **temporal CNN**. Both identify all Bitcoin connections in the combined test, with some false alarms. Useful activity classification also survives removing the observed opening. This is the final analysis of the current lab campaign.

## Collection and ground truth

The [Warnet lab](https://github.com/victorandre957/bip324-traffic-lab) runs Bitcoin Core beside HTTP, HTTPS, Tor, obfs4-shaped, BitTorrent and UDP traffic. A bridge sniffer records the mixed network. The dataset combines accelerated and mainnet-like block timing, initial synchronization, and activity on established connections. Every profile uses **regtest**.

The combined dataset covers three node scenarios:

- **Miners:** generate new regtest blocks on the configured schedule and propagate them to peers.
- **New nodes:** join with an empty chain and perform initial block download (IBD). Observing this synchronization includes the concentrated block traffic needed to catch up.
- **Already synchronized nodes:** represent established nodes using a chain preloaded before P2P communication. They exchange transactions, `inv` and `getdata`, and relay new blocks without an initial burst from downloading the existing chain.

These scenarios describe the collection design, not classes supplied to the model. A miner can also be a preloaded node. Their traffic is combined with the background applications above; **node roles, chain state and IBD status never enter the feature vector**.

The established-connection workload includes nodes with a preloaded chain, transactions throughout the measurement, and deliberate historical full-block transfers after the opening. Its new-block intervals are 120–180 seconds. Historical transfers ensure late full-block examples; their frequency is a controlled workload, rather than an estimate of mainnet relay rates. Keeping the older IBD cases covers another behavior that occurs in real networks.

The [ML pipeline](https://github.com/victorandre957/bip324-traffic-ml) separates PCAP extraction, labeling and training. It groups supported TCP/UDP traffic into bidirectional flows, then extracts nonempty **250 ms payload windows**, without a Bitcoin-port filter or a preliminary Bitcoin detector. Payload-free flows do not produce activity targets.

Core logs and lab metadata supply ground truth **only**. The multiclass targets are:

- **`other`:** background applications and traffic outside the scope of this analysis.
- **`handshake`:** the opening Bitcoin transport exchange.
- **`inv`:** announcement of transaction or block identifiers.
- **`getdata`:** a request for an object, such as a transaction or block.
- **`tx`:** transaction transfer, including matched `inv` → `getdata` → `tx` sequences.
- **`block`:** full block transfer.
- **`cmpctblock`:** compact block transfer for reconstruction using transactions already available to the receiver.
- **Unclassified Bitcoin (`bitcoin_v2_other`):** logs/connection metadata establish that the flow carries Bitcoin traffic, but the pipeline assigns none of the specific activity labels to this window. This is a dataset category, not a Bitcoin message type.

Labels are approximate endpoint/time matches to logs, not decrypted packet-level truth. Ambiguous activities are excluded as activity targets, but can provide context and enter Bitcoin-versus-other evaluation when their transport is known. A message can span several windows; a window can contain several messages. These are activity classifications, not message decoding.

The unclassified Bitcoin category can contain commands outside the selected activities, such as `ping`, `pong` or `headers`, and windows not matched to a specific logged event. An event is associated with a nearby window; this does not label every window spanned by its message. **Unclassified Bitcoin is still known Bitcoin traffic; its activity label does not establish the presence or absence of `getdata`.** Conflicting specific labels normally produce `ambiguous`, a separate category. These labels train the activity classifier; they are never inputs.

## Exactly what enters the models

The [feature builder](https://github.com/victorandre957/bip324-traffic-ml/blob/main/src/bip324_traffic_ml/features.py) selects **34 numeric inputs**:

- **Window sizes and counts (7):** payload bytes and packet counts in each direction, their totals, and byte-direction imbalance.
- **Burst timing (6):** duration, byte rate and gap since the preceding payload activity, measured separately in each direction.
- **Neighboring windows (8):** payload bytes 1, 2 and 4 observed nonempty windows before and after the target; bytes and packets in the previous four.
- **Observed connection age (4):** seconds since the first observed packet, plus flags for age below 1 second, 1–5 seconds and at least 5 seconds. Their code names include `phase_handshake`, but they are time bins, not known handshake labels.
- **Opening exchange (5):** first payload size and initial sending-turn size in each direction, plus entropy of early captured bytes.
- **Whole-flow statistics (3):** completed duration, total packet count and payload-carrying packet count.
- **Transport (1):** TCP versus UDP.

These seven groups cover all 34 inputs used by both models. Direction A → B or B → A distinguishes the two endpoints within a flow; it does not identify a particular node or its role. The activity names listed above are prediction targets, not additional inputs.

**IPs and ports never enter either model.** They group packets into flows and help associate ground truth. Flow IDs, node identities/roles, Core logs, IP maps and noise-family labels are also excluded as inputs, avoiding direct endpoint or lab-identity shortcuts. Raw payload bytes and heuristic detector outputs are excluded; only the early entropy summary is retained.

My [port-randomization PR](https://github.com/victorandre957/bitcoin/pull/2), discussed in the [earlier analysis](@/posts/bip324-passive-traffic-analysis-and-randomized-ports.md), removes a useful shortcut for observers: selecting likely Bitcoin connections by a known default port, even without ML. In a separate model-input test, randomizing port metadata left every prediction unchanged for both XGBoost and CNN. IPs and ports still separate packets into flows, but their values are excluded from the models. **This check is separate from the results presented below and is not pooled into their metrics.** It tests port-value invariance, rather than a new capture of the PR running on the network. Changing ports alone therefore does not remove the size, timing and direction patterns used here.

**Absolute timestamps do not enter the models.** PCAP timestamps are used to derive relative age, intervals, durations, rates and ordering. This distinction matters: the models see how traffic evolves, not the calendar date or time of day. The dependence on elapsed time is measured below.

[XGBoost](https://github.com/victorandre957/bip324-traffic-ml/blob/main/src/bip324_traffic_ml/training/xgboost.py) classifies each feature row using 400 boosting rounds (3,200 trees across eight classes), with maximum depth 5. The [CNN](https://github.com/victorandre957/bip324-traffic-ml/blob/main/src/bip324_traffic_ml/training/temporal.py) processes the target plus up to four adjacent 250 ms buckets on each side within the same flow; it trains for 32 epochs with batches of 1,024. Both use the opening features. Neither requires a previous handshake prediction, and the CNN does not retain hidden state between predictions.

Future-window features and completed-flow statistics make this an **offline PCAP analysis**, rather than a demonstrated real-time detector. Class weights and CNN normalization use training data only.

## Final mixed-data results

Whole lab runs are held out, so windows from a test run never enter training. The test includes both older profiles and the established-connection workload. Hyperparameters and epoch counts are fixed before evaluating this update.

| Partition | Activity-labeled windows | Flows contributing targets |
| --- | ---: | ---: |
| Training | 2,415,768 | 451,044 |
| Test | 602,004 | 114,511 |

Together, **565,555 flows** contribute activity targets. The tables below report the combined held-out test, not training performance.

### Reading the scores

I use **identification score (F1)** for each activity. Precision measures how often a predicted activity is correct; recall measures how much of the true activity is found. F1 is their harmonic mean, from 0 to 1. **A score of 0.8 does not mean 80% of examples were classified correctly.** The **mean class score (macro F1)** gives every class equal weight, preventing abundant `other` windows from dominating the summary.

| Metric | XGBoost | CNN |
| --- | ---: | ---: |
| Activity-window accuracy | 98.52% | 98.88% |
| Mean class score (macro F1) | 0.787 | 0.811 |
| Mean class recall (balanced accuracy) | 0.848 | 0.878 |

`other` accounts for 92.8% of these windows, so overall accuracy alone would hide important errors:

| Activity | Test windows | XGBoost identification score | CNN identification score |
| --- | ---: | ---: | ---: |
| `handshake` | 239 | 0.891 | 0.887 |
| `inv` | 27,280 | 0.892 | 0.933 |
| `cmpctblock` | 1,343 | 0.805 | 0.774 |
| `tx` | 1,105 | 0.818 | 0.850 |
| `block` | 317 | 0.845 | 0.850 |
| `getdata` | 1,295 | 0.434 | 0.460 |
| Unclassified Bitcoin | 11,945 | 0.611 | 0.735 |
| `other` | 558,480 | 0.99990 | 0.99983 |

### Why is `getdata` harder to distinguish?

The main confusion is **inside Bitcoin traffic**, especially with the unclassified Bitcoin category. XGBoost correctly calls 866 of the 1,295 labeled `getdata` windows; the CNN calls 953. However, they also predict `getdata` for 1,603 and 1,827 windows labeled unclassified Bitcoin. These count as errors against the dataset labels, but do not prove that every such window lacked a request. The measured precision is low; the contribution of incomplete labeling has not been quantified.

`getdata` is a request: a successful response carries the requested transaction or block, rather than another `getdata`. [Core processes queued transaction requests in batches, but at most one block item per processing call](https://github.com/bitcoin/bitcoin/blob/master/src/net_processing.cpp). This is a per-peer queue, not a single outstanding request for the whole node. Transaction requests can be ignored when that peer has no transaction-relay state, including block-relay-only connections. These rules make response patterns conditional, but we have not established missing responses as the cause of the low score. Our `getdata` label comes from its own logged event and does not require a successful response.

Several factors plausibly contribute:

- **Similar wire lengths:** [`inv` and `getdata` use the same inventory-list payload format](https://developer.bitcoin.org/reference/p2p_networking.html#getdata). Equal-sized lists can have equal lengths; the message-type distinction is encrypted by BIP324.
- **Request/response aggregation:** a short request can share a 250 ms window with a much larger response. Packet segmentation and coalescing also prevent treating a window as an isolated request.
- **Approximate labels:** matching logs to windows can leave specific activities unpaired. Windows containing multiple labeled activities can become ambiguous, while a full-block transfer takes priority over its co-occurring request.

These explanations fit the representation and confusion matrix; the experiment does not isolate how much each contributes. In particular, the scores do not show that `getdata` is usually mistaken for background traffic.

The mixture also preserves coverage across workloads. On the older test, training only on the new workload gives zero full-block identification score for both models; mixed training gives 0.719/0.778. On the new test, the mixed models score 0.883/0.879 for full blocks. Data quantity, traffic profiles and pipeline revisions change together, so this comparison does not isolate IBD as the sole cause.

### Bitcoin versus background traffic

The same multiclass predictions can be mapped to Bitcoin versus `other`, without a second binary model. Including 33,779 ambiguous-activity windows with known transport gives **635,783 test windows across 114,511 flows**. Connection results use a majority vote across their scored windows; ties count as Bitcoin.

| Detection result, complete test | XGBoost | CNN |
| --- | ---: | ---: |
| Bitcoin connections found | 331 / 331 | 331 / 331 |
| Background connections incorrectly called Bitcoin | 2 / 114,180 | 15 / 114,180 |
| Bitcoin windows incorrectly called `other` | 18 / 77,303 | 16 / 77,303 |
| Background windows incorrectly called Bitcoin | 95 / 558,480 | 177 / 558,480 |
| Precision of Bitcoin connection predictions | 0.994 | 0.957 |

Thus both have **100% Bitcoin-connection recall in this test**, while neither perfectly separates Bitcoin from background connections. Individual windows still produce errors. Most false-positive windows are obfs4-shaped, HTTPS and Tor for XGBoost, and Tor and obfs4-shaped for the CNN. These rates describe this lab population.

### Identification after successive round trips

In a separate sequential test, both models were refitted with **23 causal inputs**, excluding future windows and completed-flow statistics. The table shows precision after 1, 2 and 3 observed payload round trips, using the same **Bitcoin score threshold of 0.9** for both models. Scores accumulate only over windows already observed; results use the six evaluation runs, separate from calibration.

| Model | Payload round trips | Precision of Bitcoin predictions | Bitcoin connections found | Bitcoin connections missed | Background connections called Bitcoin |
| --- | ---: | ---: | ---: | ---: | ---: |
| XGBoost | 1 | 90.20% | 221 / 237 | 16 / 237 | 24 / 59,278 |
| XGBoost | 2 | 99.13% | 228 / 237 | 9 / 237 | 2 / 1,806 |
| XGBoost | 3 | 99.55% | 219 / 226 | 7 / 226 | 1 / 1,707 |
| CNN | 1 | 47.22% | 229 / 237 | 8 / 237 | 256 / 59,278 |
| CNN | 2 | 69.94% | 228 / 237 | 9 / 237 | 98 / 1,806 |
| CNN | 3 | 95.63% | 219 / 226 | 7 / 226 | 10 / 1,707 |

Precision is the fraction of connections called Bitcoin that actually were Bitcoin. The counts show correct Bitcoin detections, missed Bitcoin connections and background connections incorrectly called Bitcoin, with eligible connections in each category as denominator. A round trip means payload in one direction followed by reverse-direction payload, excluding ACK-only packets, rather than a matched Bitcoin request/response. Each snapshot uses the first available 250 ms window after reaching at least that number of exchanges; a window can contain additional exchanges.

For example, after one round trip the CNN has **47.22% precision**, not 47.22% confidence. It labels 256 of 59,278 background connections as Bitcoin: a **0.43% false-positive rate**. Because Bitcoin connections are much rarer in this population, those 256 false positives still outnumber the 229 correct Bitcoin predictions. A small false-positive rate can therefore coexist with many incorrect alerts.

Only connections reaching each stage within 60 seconds enter that row. All 237 Bitcoin connections reached stages 1 and 2; 226 reached stage 3. The background population also shrinks at later stages, so higher precision does not mean every connection becomes identifiable. These causal results are separate from the offline-model tables above.

## Classification with and without the observed handshake

This comparison tests whether later activity remains recognizable **without access to the connection opening**. Neither model receives a flag saying “this flow was already identified as Bitcoin”, nor a previous handshake prediction. A detector that first marks a flow as Bitcoin and then classifies its messages would be a separate experiment.

Both XGBoost and CNN are evaluated in two configurations:

- **With opening context (34 inputs):** opening measurements, observed connection age and original whole-flow statistics remain available when classifying a later window.
- **Without opening/history (22 inputs):** refit after discarding the first 30 seconds of every flow, including noise, and removing opening measurements, age/phase flags and original whole-flow totals. Lags, leads, rolling counts and the first retained gap per direction are rebuilt; CNN context contains retained windows only.

Both configurations classify **exactly the same later targets** from the combined test. Seven classes remain; handshake is absent as a target. This tests more than removing the handshake alone: other original-history features are also excluded. Short flows can disappear, so the scores are not directly comparable with the eight-class, complete-network scores above.

| Model | Available context | Mean class score | Activity-window accuracy |
| --- | --- | ---: | ---: |
| XGBoost | With opening context | 0.774 | 97.87% |
| XGBoost | Without opening/history | 0.742 | 97.66% |
| CNN | With opening context | 0.801 | 98.40% |
| CNN | Without opening/history | 0.765 | 98.04% |

| Later activity | Test windows | XGBoost with opening | XGBoost without opening/history | CNN with opening | CNN without opening/history |
| --- | ---: | ---: | ---: | ---: | ---: |
| `block` | 229 | 0.883 | 0.739 | 0.864 | 0.749 |
| `cmpctblock` | 1,294 | 0.808 | 0.788 | 0.781 | 0.729 |
| `inv` | 26,340 | 0.893 | 0.887 | 0.933 | 0.930 |
| `tx` | 1,036 | 0.817 | 0.802 | 0.852 | 0.826 |
| `getdata` | 1,225 | 0.430 | 0.415 | 0.455 | 0.442 |
| Unclassified Bitcoin | 10,787 | 0.589 | 0.566 | 0.723 | 0.681 |
| `other` | 354,741 | 0.99994 | 0.99969 | 0.99986 | 0.99858 |

Full blocks remain in the later targets after removing the opening and history. XGBoost identifies them with precision 0.856 and recall 0.651; the CNN has precision 0.859 and recall 0.664. About one third of labeled block windows are not classified as `block`. This is an error about the **activity type**, not necessarily a failure to recognize the connection as Bitcoin.

For **Bitcoin detection versus background traffic**, using those same later windows:

| Model and inputs | Bitcoin connections found | Background connections called Bitcoin | Bitcoin windows missed | Background windows called Bitcoin |
| --- | ---: | ---: | ---: | ---: |
| XGBoost, with opening context | 206 / 207 | 1 / 4,409 | 6 / 73,599 | 40 / 354,741 |
| XGBoost, without opening/history | 207 / 207 | 2 / 4,409 | 78 / 73,599 | 200 / 354,741 |
| CNN, with opening context | 207 / 207 | 4 / 4,409 | 11 / 73,599 | 94 / 354,741 |
| CNN, without opening/history | 207 / 207 | 31 / 4,409 | 82 / 73,599 | 970 / 354,741 |

Removing opening/history reduces the mean class score from 0.774 to 0.742 for XGBoost and from 0.801 to 0.765 for the CNN. The opening helps, but later activity still provides useful signal. Both models trained without opening/history find every Bitcoin connection in this subset, but introduce false alarms, especially the CNN. More window errors and better majority-vote recall can coexist: the errors occur in different flows. This is not evidence that removing context improves detection.

## Which inputs matter?

Grouped permutation freezes the mixed models and shuffles related inputs, jointly across the CNN context. It uses **all 218,668 unambiguous activity windows in the new held-out workload**, including late full blocks. Values are decreases in mean class score on the same 0–1 scale; ± is the standard deviation over three shuffles. Larger decreases indicate greater dependence on the perturbed inputs.

| Shuffled input group | XGBoost | CNN |
| --- | ---: | ---: |
| Window sizes and counts | 0.462 ± 0.007 | 0.561 ± 0.003 |
| Whole-flow statistics | 0.318 ± 0.006 | 0.480 ± 0.005 |
| Burst timing | 0.201 ± 0.013 | 0.476 ± 0.006 |
| Neighboring-window features | 0.268 ± 0.009 | 0.170 ± 0.009 |
| Opening exchange | 0.134 ± 0.006 | 0.259 ± 0.004 |
| Elapsed time and phase flags | 0.067 ± 0.016 | 0.088 ± 0.005 |
| TCP / UDP | 0.058 ± 0.003 | 0.150 ± 0.002 |

Both depend strongly on sizes/counts and whole-flow statistics. The CNN also depends strongly on burst timing; XGBoost is more sensitive to the explicitly engineered neighboring-window features. Disrupting opening inputs affects both, rather than being an XGBoost-only effect.

To distinguish the elapsed-time measurement from its phase flags, I also shuffled them separately:

| Time input shuffled alone | XGBoost decrease | CNN decrease |
| --- | ---: | ---: |
| Seconds since first observed packet | 0.046 ± 0.009 | 0.077 ± 0.008 |
| Three age-phase flags | 0.004 ± 0.002 | 0.093 ± 0.007 |

**Relative time contributes to both models; absolute timestamps are unused.** The inputs are correlated, and these decreases are neither additive nor causal. Jointly shuffling time and phases can affect a model differently from breaking their consistency individually.

![Feature dependence of both mixed models, including separate elapsed-time and phase-flag tests](../../images/bip324-ml-v2-20261124/feature-dependence.png)

[TreeSHAP](https://github.com/victorandre957/bip324-traffic-ml/tree/main/src/bip324_traffic_ml/explanation) provides an individual-input view for XGBoost. These global averages use 2,876 population-weighted examples from that same test:

| XGBoost input | Mean absolute SHAP contribution |
| --- | ---: |
| Current-window payload bytes | 0.773 |
| Complete-flow payload packet count | 0.609 |
| Seconds since first observed packet | 0.510 |
| Complete-flow duration | 0.459 |
| Previous observed window payload bytes | 0.358 |

SHAP contributions use raw class-score units, whereas permutation measures changes in identification score. They cannot be compared numerically. Shuffling can also create unrealistic combinations; strong dependence does not prove that the feature is indispensable after retraining or that changing it on the wire will hide traffic.

## What this means for traffic hiding

The results support two separate findings: **Bitcoin connections are highly detectable in this lab**, and **several later activity classes remain recognizable without observing the opening**. Encryption hides contents while recurring sizes, directional exchanges and timing still provide statistical evidence. SSeparating getdata from traffic windows without a specific activity label remains substantially less reliable than identifying inv, full blocks or transactions.

Consequently, **handshake-only defenses should not be assumed sufficient**. The retained representation lets both models recognize established Bitcoin connections and later activities. Countermeasure research should also test the sizes, timing and directional patterns of ongoing traffic, with realistic background connections and explicit false-alarm measurements.

This experiment removes observations/features; it does not modify the protocol on the wire. A real protocol change can affect subsequent traffic too. Establishing whether a particular defense works requires new captures and retraining/evaluation against that defense.

## Limits of this analysis

These conclusions apply to the controlled workloads measured here. Shared implementations, generated background traffic, correlated windows and one training seed per condition remain limitations of this campaign. Activity labels approximate log events in time windows; the unclassified Bitcoin category does not identify a specific message type.
