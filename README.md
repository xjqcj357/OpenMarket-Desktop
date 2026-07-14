# OpenMarket Desktop

A tiny, runnable desktop client for [OpenMarket](https://github.com/lukeprofits/OpenMarket) —
a decentralized, anonymous marketplace built on Nostr (NIP-99) and IPFS.

The client has three screens:

- **Browse** — reads NIP-99 classified listings (kind 30402) already published across
  public Nostr relays (Shopstr, Plebeian Market, native OpenMarket listings). Starts full,
  not empty.
- **Search** — local keyword filtering over the listings you've pulled.
- **Create** — fills a form, computes the listing's **deterministic IPFS CID locally**
  (you do not upload it), and can announce it as NIP-99 so the rest of the ecosystem sees it.

## Run

**Desktop app (Windows, portable).** Double-click **`OpenMarket.bat`** (or the
`OpenMarket` desktop shortcut). On first run it creates a local `.venv` inside
the folder and installs dependencies, then launches the GUI with no console
window. The folder is self-contained — copy it to another machine with Python 3
installed and it re-bootstraps itself.

**Manual / cross-platform.**

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows (PowerShell: .venv\Scripts\Activate.ps1)
# source .venv/bin/activate       # macOS / Linux
pip install -r requirements.txt
python gui.py                      # tkinter GUI  (or: python main.py for the CLI)
```

The CLI menu offers `1` (browse), `2` (search), `3` (create).

### Notes

- **Browse/Search** and **Create** need only [`basic-nostr`](https://pypi.org/project/basic-nostr/) —
  no heavy setup.
- **Create** computes the listing CID as a pure local sha2-256 hash (no IPFS
  daemon, no network, nothing uploaded). Running a full Kubo node — which would
  join the public IPFS DHT and leak your IP — is deliberately deferred to a
  future, opt-in, Tor-aware seeding mode.
- Override the default relays and disable auto-widening with an env var:
  `OPENMARKET_RELAYS="wss://relay.damus.io,wss://nos.lol"`.

## Security

This client reads from a hostile, unauthenticated network. It's hardened against
malformed-event crashes, terminal-escape/Unicode injection, field-size DoS,
IPFS-daemon IP leakage, and internal-endpoint relay discovery — but it has real
residual risks (clearnet IP exposure / no Tor yet, unverified seller identity).
**Read [`SECURITY.md`](SECURITY.md) before alpha testing.**

## Scope

This POC covers the Nostr (clearnet) leg of the protocol end to end. The full design also
spreads listings over libp2p gossipsub, Bluetooth, and LoRa with probabilistic forwarding —
see the notes at the top of [`main.py`](main.py) and the
[protocol spec](https://github.com/lukeprofits/OpenMarket).

MIT.
