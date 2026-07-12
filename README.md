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

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows (PowerShell: .venv\Scripts\Activate.ps1)
# source .venv/bin/activate       # macOS / Linux
pip install -r requirements.txt
python main.py
```

Then pick `1` (browse), `2` (search), or `3` (create) from the menu.

### Notes

- **Browse/Search** need only network access to relays — no heavy setup.
- **Create** computes the CID via [`basic-ipfs`](https://pypi.org/project/basic-ipfs/), which
  downloads a real Kubo node (~115 MB) on first use. Everything else uses
  [`basic-nostr`](https://pypi.org/project/basic-nostr/).
- Override the default relays with an env var:
  `OPENMARKET_RELAYS="wss://relay.damus.io,wss://nos.lol"`.

## Scope

This POC covers the Nostr (clearnet) leg of the protocol end to end. The full design also
spreads listings over libp2p gossipsub, Bluetooth, and LoRa with probabilistic forwarding —
see the notes at the top of [`main.py`](main.py) and the
[protocol spec](https://github.com/lukeprofits/OpenMarket).

MIT.
