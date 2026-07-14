# Security notes — OpenMarket Desktop (alpha)

OpenMarket reads from a **fully untrusted, adversarial network**. Every relay,
every listing, every seller relay-list, and every pubkey is attacker-controllable
and unauthenticated. This file records the threat model, what the client hardens
against, and the **residual risks you should know before alpha testing**.

## Threat model

An attacker can, with no authentication:
- run relays you connect to (including ones you auto-discover),
- publish arbitrary NIP-99 listing events (kind 30402): huge/malformed JSON,
  non-string tags, control characters, terminal escapes, Unicode spoofing,
- publish arbitrary NIP-65 relay lists (kind 10002) and Sybil thousands of keys,
- attribute a listing to **any** pubkey (events are not signature-verified here).

## What the client hardens against (implemented)

| Attack | Mitigation |
|---|---|
| Malformed event crashes the whole fetch (non-list tags, bad `created_at`) | `parse_listing` is type-safe and returns `None`; `_dedupe` drops bad events so one hostile event can't wipe the market (`main.py`) |
| ANSI/OSC **terminal-escape injection** (screen spoof, OSC-8 hyperlink IP-beacon, OSC-52 clipboard hijack) | Central `clean()` strips all C0/C1 controls incl. ESC before anything is printed or shown |
| Unicode **bidi-override / zero-width** title & price spoofing | `clean()` strips those ranges |
| **Newline injection** forging fake rows / `PRICE:`/`SELLER:` lines | newlines are stripped from all fields |
| Multi-MB field freezes the UI (DoS) | every field length-capped; listings capped at `MAX_LISTINGS`; tags capped at `MAX_TAGS_PER_EVENT` |
| Future-dated listing pinned to the top forever | `created_at` clamped to now + 5 min before sorting |
| **IP deanonymization via IPFS** ("compute CID" secretly booting a public Kubo node) | CID is a **pure local sha2-256 hash** (`compute_cid`); no daemon, no DHT, no network, no `basic-ipfs` |
| Auto-discovery pointed at **internal/loopback** endpoints | `_valid_relay` rejects `localhost`, RFC1918, link-local, reserved, `.local` |
| Seed relays crowded out (eclipse) | the 5 hardcoded seeds are **always** queried, so honest listings always come through; discovered relays only *add* |
| nsec echoed to terminal / shell history | read with `getpass` (hidden) |
| Announcing links your IP ↔ npub | explicit warning before every announce (CLI + GUI) |

## Residual risks (NOT fully solved — know these)

1. **Clearnet IP exposure.** Browsing and announcing connect to relays over the
   clearnet, so those relays — including attacker-run ones you auto-discover —
   see your IP. There is **no Tor/proxy support yet.** Mitigations today:
   - Pin a trusted set and disable auto-widening:
     `OPENMARKET_RELAYS="wss://relay.damus.io,wss://nos.lol"`.
   - Run behind a VPN/Tor transparent proxy at the OS/network level.
   - Delete `.relay_cache.json` to forget auto-discovered relays.

2. **Listings are not signature-verified.** The underlying library does not
   verify event signatures, so the displayed **seller pubkey is unauthenticated**
   — an attacker relay can attribute any listing to any npub. Treat seller
   identity and reputation as unproven until per-event Schnorr verification lands.

3. **Sybil influence on discovery.** An attacker with many fake keys/relay-lists
   can fill the ~25 discovered relay slots and inject spam into your view (it
   cannot *remove* honest seed listings, see above). Pinning `OPENMARKET_RELAYS`
   sidesteps this entirely.

4. **Library-level DoS bounds.** `read_products` fetches into memory before we
   cap/render; a malicious relay streaming huge/slow responses can inflate memory
   or stall a fetch. We bound what we keep and render, not what the library reads.

5. **Payments are out-of-band.** OpenMarket never escrows or verifies payment.
   Confirm a seller's payment address through a second channel — a listing field
   is attacker-controllable text.

## Reporting

This is pre-release alpha software. Do not use it for anything you cannot afford
to have go wrong. Found an issue? Open a GitHub issue (no sensitive details) or
contact the maintainer privately.
