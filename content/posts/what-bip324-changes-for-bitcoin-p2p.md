+++
title = "BIP324 in Bitcoin Core"
date = 2026-06-19
description = "A technical walkthrough of Bitcoin's encrypted P2P v2 transport in Bitcoin Core."
[taxonomies]
tags = ["bitcoin", "bip324", "p2p", "bitcoin-core"]
+++

For the last few weeks I have been studying Bitcoin's P2P v2 transport implementation in Bitcoin Core. The protocol is specified in [BIP324](https://github.com/bitcoin/bips/blob/master/bip-0324.mediawiki), and the implementation lives mostly in `src/bip324.{h,cpp}` and the `V2Transport` code in `src/net.{h,cpp}`.

This post is a technical breakdown of what BIP324 does, what it deliberately does not do, and how Bitcoin Core wires it into the existing P2P stack.

## The Problem

Bitcoin's original P2P transport, now called v1 transport, sends Bitcoin P2P messages in a self-identifying cleartext format. A connection starts with network magic bytes, and every message carries a cleartext command string such as `version`, `inv`, `tx`, `block`, or `addrv2`.

That creates three problems.

First, a passive observer can read message types and timing directly. The data being relayed by the Bitcoin P2P network is usually public eventually, but the metadata around when a peer first announces something is still sensitive.

Second, the bytestream identifies itself as Bitcoin. Deep packet inspection does not need a subtle classifier when the protocol begins with fixed magic bytes and cleartext command names.

Third, unauthenticated cleartext traffic is cheap to tamper with. An active attacker can modify bytes in flight without having to maintain a full encrypted-session man-in-the-middle.

BIP324 replaces that transport layer. It does not change Bitcoin consensus, peer selection, inventory relay, block validation, or the application-level P2P messages. It changes how those messages are framed and encrypted on the wire.

## The Goal

BIP324 is opportunistic transport encryption for Bitcoin P2P connections. "Opportunistic" matters: peers do not have long-term transport identities and the handshake does not authenticate that the remote peer is a particular node. If both sides support v2 transport, they encrypt the connection. If not, Bitcoin Core can still speak v1.

The core goals are:

- hide P2P message contents from passive observers;
- make the bytestream look pseudorandom instead of self-identifying;
- make cheap byte-level tampering harder by forcing active attackers into a full man-in-the-middle position;
- expose a session ID that peers can compare or bind to a future authentication protocol;
- preserve compatibility with v1 peers;
- keep the cost low enough for ordinary Bitcoin node connections.

That last point is why BIP324 is not "Bitcoin over TLS". The BIP argues for a custom transport because Bitcoin wants encryption decoupled from identity authentication, a pseudorandom bytestream, secp256k1-based key exchange, packet-based framing, and room for traffic shaping.

## The Handshake

A v2 connection begins immediately after the TCP connection is established. There is no v1 `version` message first.

The initiator sends:

1. a 64-byte ElligatorSwift-encoded secp256k1 public key;
2. between 0 and 4095 bytes of random garbage.

The responder starts in a detection state. It reads up to the first 16 bytes and compares them with the beginning of a v1 `version` message: network magic followed by `version` padded with zero bytes. If those bytes match, Bitcoin Core treats the connection as v1. If they do not match, the responder treats the connection as v2 and sends its own 64-byte ElligatorSwift public key plus garbage.

Once each side has the other side's 64-byte public key, both compute an ECDH shared secret. The public keys are ElligatorSwift encodings, not ordinary compressed secp256k1 public keys. The point of ElligatorSwift here is fingerprint resistance: the encoded public key is designed to be indistinguishable from random bytes.

From the shared secret, both sides derive:

- two length-cipher keys, one per direction;
- two packet AEAD keys, one per direction;
- two 16-byte garbage terminators, one per direction;
- one 32-byte session ID.

Then each side sends its garbage terminator. The receiver reads until it sees the expected 16-byte terminator, with a hard limit of 4095 garbage bytes plus the 16-byte terminator. The garbage is not just skipped and forgotten: it becomes associated authenticated data for the first encrypted packet sent in that direction. That binds the apparently random handshake padding into the cryptographic transcript.

After that, both peers exchange an encrypted version packet. Today Bitcoin Core sends an empty version packet, which means "plain BIP324 v2 transport, no extra transport extensions." The field exists so future versions can negotiate more without changing the outer connection setup.

Only after the encrypted version packet succeeds does the connection enter the application phase.

## Garbage Bytes

The garbage bytes are one of the easiest parts of BIP324 to underestimate. They are not application data and they are not decrypted into a Bitcoin P2P message. Their job is to make the beginning of a v2 connection harder to fingerprint.

In Bitcoin Core, `GenerateRandomGarbage()` chooses a random length from 0 to `V2Transport::MAX_GARBAGE_LEN`, currently 4095, and fills that buffer with random bytes. `StartSendingHandshake()` then writes:

```text
our_ellswift_pubkey || random_garbage
```

to the send buffer.

The tricky part is that the receiver cannot know where the garbage ends until the ciphers have been initialized. Once the peer's ElligatorSwift key is received, `BIP324Cipher::Initialize()` derives the expected receive-side garbage terminator. `V2Transport::ProcessReceivedGarbageBytes()` then reads one byte at a time and keeps checking whether the last 16 bytes equal that terminator.

If the terminator appears, the receiver stores everything before it in `m_recv_aad`. That value becomes associated authenticated data for the next encrypted packet. If the terminator never appears after `4095 + 16` bytes, the connection is dropped with `V2 transport error: missing garbage terminator`.

That AAD detail matters. Without it, an active attacker could tamper with the unencrypted garbage region and the encrypted packet layer would not notice. With AAD, the first packet authenticates the garbage transcript too.

## Packet Encryption

BIP324 packets separate length encryption from content encryption.

The packet content is:

```text
message_type || payload
```

For known Bitcoin P2P messages, `message_type` can be a compact 1-byte ID. If no compact ID is used, the content starts with `0x00`, followed by the old 12-byte command-name encoding. This is why v2 can be slightly smaller than v1 for common messages: it does not need to send a 12-byte command string every time.

The packet length is encoded as three little-endian bytes and encrypted with an FSChaCha20 stream cipher. The content is encrypted with FSChaCha20Poly1305, an AEAD construction that also authenticates the packet.

Bitcoin Core passes `BIP324Cipher::REKEY_INTERVAL` to both forward-secure cipher wrappers. In this checkout that constant is `224`, and the wrappers rekey after that many length-cipher calls or packet AEAD operations. That gives the transport forward secrecy for old packet keys within a long-lived connection: compromising current packet state should not automatically decrypt all past traffic.

## Decoy Packets

BIP324 also defines decoy packets. A decoy is a real encrypted packet with the `ignore` bit set in the encrypted packet header. The receiver still decrypts and authenticates it, updates cipher state, clears any expected AAD if the packet is valid, and then discards the content instead of passing a `CNetMessage` upward.

Bitcoin Core implements the mechanism in `BIP324Cipher`:

- `BIP324Cipher::Encrypt()` receives a `bool ignore`;
- if `ignore` is true, it sets `IGNORE_BIT` in the encrypted packet header;
- `BIP324Cipher::Decrypt()` returns the decoded `ignore` value after AEAD verification.

`V2Transport::ProcessReceivedPacketBytes()` understands that bit. After decrypting a packet, it only advances the version/application message state when `ignore` is false. If `ignore` is true, the packet is simply treated as a valid decoy and ignored.

So receiving decoys is implemented.

Sending decoys is not active in the normal Bitcoin Core message path. The variable exists, but the production calls are effectively locked to `false`:

```cpp
m_cipher.Encrypt(
    /*contents=*/VERSION_CONTENTS,
    /*aad=*/MakeByteSpan(m_send_garbage),
    /*ignore=*/false,
    ...
);
```

and later, for normal application messages:

```cpp
m_cipher.Encrypt(MakeByteSpan(contents), {}, false, MakeWritableByteSpan(m_send_buffer));
```

The tests can manually send packets with `ignore=true`, and they verify that `V2Transport` skips them correctly. But the live sending path does not currently schedule random decoy packets as a traffic-shaping policy.

The version packet has a similar "implemented but fixed" shape. `V2Transport` defines:

```cpp
static constexpr std::array<std::byte, 0> VERSION_CONTENTS = {};
```

The protocol has a version packet slot for future transport extensions, and receivers ignore its contents today. Bitcoin Core currently sends it empty every time.

## Core Implementation

Bitcoin Core splits the implementation into two layers.

`BIP324Cipher` is the cryptographic packet layer. It owns the ephemeral key, the ElligatorSwift public key, the derived session ID, the garbage terminators, the length ciphers, and the packet AEADs.

Its initialization path follows the BIP closely:

```text
ephemeral key -> ElligatorSwift pubkey
their ElligatorSwift pubkey -> ECDH shared secret
shared secret + network-specific salt -> HKDF outputs
HKDF outputs -> length keys, packet keys, garbage terminators, session ID
```

The salt is not just a fixed string. Bitcoin Core uses:

```text
"bitcoin_v2_shared_secret" || message_start
```

where `message_start` is the network magic for the active chain. That keeps mainnet, testnet, signet, and regtest v2 sessions domain-separated at the key-derivation level.

The HKDF labels in the code are the protocol roles: `initiator_L`, `initiator_P`, `responder_L`, `responder_P`, `garbage_terminators`, and `session_id`. The `L` keys are used for length encryption. The `P` keys are used for packet encryption.

`BIP324Cipher::Encrypt()` writes the encrypted 3-byte length first, then encrypts the packet header and contents. `BIP324Cipher::DecryptLength()` decrypts only the length prefix so the transport knows how many more bytes to read. `BIP324Cipher::Decrypt()` verifies and decrypts the AEAD-protected packet body and returns whether the ignore bit was set.

After key derivation, Bitcoin Core wipes the shared secret, the temporary HKDF output, the HKDF object, and the private key stored in the cipher object. That is a small but important implementation detail: the transport keeps the active ciphers, not the raw material needed to derive them again.

## V2Transport

The higher-level implementation is `V2Transport`, a `Transport` subclass next to the old `V1Transport`.

The receive side moves through these states:

```text
KEY_MAYBE_V1 -> KEY -> GARB_GARBTERM -> VERSION -> APP -> APP_READY
       |
       +-> V1
```

For inbound connections, Bitcoin Core starts in `KEY_MAYBE_V1` because it does not know yet whether the remote peer is speaking v1 or v2. If the first bytes match the v1 `version` prefix, it switches to the embedded `V1Transport`. If they do not match, it switches to v2 and starts processing the remote ElligatorSwift key.

For outbound v2 connections, Bitcoin Core already knows it is initiating v2, so it starts in `KEY` on the receive side and immediately starts sending its own handshake bytes on the send side.

The send side has a smaller state machine:

```text
MAYBE_V1 -> AWAITING_KEY -> READY
     |
     +-> V1
```

When `V2Transport` enters `READY`, Bitcoin Core appends the garbage terminator and the encrypted empty version packet to the send buffer. From that point onward, application messages can be encrypted and sent.

This design lets the rest of the networking stack keep using the abstract `Transport` interface. `CNode` owns a `std::unique_ptr<Transport>`, and `MakeTransport()` chooses either `V1Transport` or `V2Transport` when the node object is constructed.

## Message Encoding

The application layer still deals in ordinary Bitcoin P2P messages. The transport is responsible for turning a `CSerializedNetMsg` into v2 packet contents.

When Bitcoin Core sends a message through `V2Transport::SetMessageToSend()`:

1. it looks up the message type in the v2 short-ID map;
2. if a short ID exists, it writes one byte plus the payload;
3. otherwise, it writes `0x00`, the 12-byte command-name field, and the payload;
4. it encrypts the resulting contents with `BIP324Cipher`.

On receive, `V2Transport::GetReceivedMessage()` reverses that process. It decrypts the packet, parses either the 1-byte compact message ID or the 13-byte long form, and returns a normal `CNetMessage` to the message-processing layer.

This is the nice engineering boundary: `net_processing` still receives message types like `tx`, `inv`, `headers`, and `block`. It does not need to know whether the peer used v1 cleartext framing or v2 encrypted framing.

## Service Bit

BIP324 support is advertised with the service bit:

```text
NODE_P2P_V2 = 1 << 11
```

In this checkout, `DEFAULT_V2_TRANSPORT` is `true`. The `-v2transport` option controls whether the node supports v2 transport, and initialization adds `NODE_P2P_V2` to local services when that option is enabled.

For automatic outbound connections, Bitcoin Core uses v2 only when both sides advertise `NODE_P2P_V2`. The connection code checks:

```text
addrConnect.nServices & GetLocalServices() & NODE_P2P_V2
```

Manual connections can also request v2 through RPC. `addnode` has a `v2transport` argument, defaulting to the node's `-v2transport` setting. If the caller asks for v2 while the local node has v2 disabled, the RPC returns an error instead of silently doing something else.

Inbound handling is different. If the local node advertises `NODE_P2P_V2`, Bitcoin Core constructs a `V2Transport` for inbound peers because that transport can detect and fall back to v1. This avoids partitioning the network: a v2-capable listening node can still accept old v1 peers.

## Session ID

BIP324's session ID is a 32-byte value derived from the ECDH secret. Bitcoin Core exposes it in peer information only after the encrypted version packet has been received and verified. Until then, the transport reports `detecting` rather than claiming a completed v2 session.

The session ID does not authenticate the peer by itself. It is channel binding material. If two operators manually compare session IDs over an authenticated side channel, or if a future authentication extension signs over the session ID, then a man-in-the-middle can be detected because each side would derive a different session.

That distinction is subtle but important: BIP324 gives confidentiality against passive observers and makes active attacks more expensive and more observable. It does not give every Bitcoin node a cryptographic identity.

## Compatibility

Bitcoin Core's implementation takes compatibility seriously.

Inbound v1 fallback happens inside `V2Transport` by checking the v1 prefix and delegating to `V1Transport`.

Outbound fallback is handled separately. If Bitcoin Core tries v2 because the peer was advertised as supporting it, but the peer disconnects immediately without sending anything back, `V2Transport::ShouldReconnectV1()` can tell the connection manager to retry using v1. The functional test covers this case by falsely advertising a v1 node as v2 and checking that the node retries with v1 transport.

The tests also cover:

- `NODE_P2P_V2` appearing in local service flags when v2 is enabled;
- v2 peers syncing blocks over a v2 connection;
- shared 64-character hex session IDs on both sides of a v2 peer connection;
- v1 peers syncing with v1 peers;
- v1 and v2 peers remaining mutually compatible;
- detection of the v1 prefix during inbound connection setup;
- wrong-network v1 prefix detection;
- disconnecting when the garbage terminator is missing after the maximum allowed handshake garbage.

## Limits

BIP324 encrypts the Bitcoin P2P transport, but it is not a complete network privacy solution.

It does not hide peer IP addresses. It does not hide TCP connection timing. It does not hide packet sizes from the network. It does not hide whether a node listens on a recognizable port. It does not stop an attacker from running their own Bitcoin nodes and observing what peers send to them.

What it does is remove the self-identifying cleartext Bitcoin protocol from the wire and replace it with an encrypted, pseudorandom, upgradeable transport. That is a large improvement because it changes the attacker's job from "read or edit obvious Bitcoin messages" to "perform active interception or infer behavior from metadata."

In Bitcoin Core, that improvement is implemented without rewriting the rest of the P2P message layer. The transport abstraction absorbs the difference: v1 and v2 both deliver `CNetMessage` objects upward, while `V2Transport` and `BIP324Cipher` handle the new handshake, key derivation, encrypted packet framing, message-type compression, session ID reporting, fallback behavior, and compatibility rules underneath.
