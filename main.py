"""
OpenMarket Desktop: the free market.

A fully decentralized, anonymous marketplace client. There is no "platform" to
shut down and no servers -- only the code you run, which interoperates with
copies of itself and with the wider Nostr marketplace ecosystem (NIP-99).

This desktop client is intentionally tiny -- three screens:

  1. Browse  -- read NIP-99 classified listings (kind 30402) already published
                across Nostr relays (shopstr, Plebeian Market, and native
                OpenMarket listings). "Starts full, not empty."
  2. Search  -- local keyword/structured filtering over what you've pulled.
  3. Create  -- fill a form, compute the listing's deterministic IPFS CID
                *locally* (you do not upload it), and announce it as NIP-99 so
                the rest of the ecosystem sees it too.

Built on:
  - basic-nostr  -> NIP-99 read/write (kind 30402)
  - basic-ipfs   -> deterministic content-addressing (CID computed locally)

------------------------------------------------------------------------------
Protocol notes (from the original design sketch -- not yet wired into this POC)
------------------------------------------------------------------------------
The full protocol also spreads a listing over libp2p gossipsub, Bluetooth, and
LoRa, with *probabilistic forwarding*: when a node receives gossiped listing
JSON it usually forwards it to one of its most-trusted nodes and only
occasionally posts it to IPFS itself. Because a post travels several hops before
anyone pins it, the origin IP is "lost in the crowd" before a logging node ever
sees the CID. Offline, the deterministic CID keeps propagating over Bluetooth /
LoRa so discovery survives a blackout; content resolves from IPFS once back
online. Those transports are out of scope for this first runnable client, which
covers the Nostr (clearnet) leg end to end.
"""

import json
import sys
import textwrap

# Listings come from all over the world; force UTF-8 so non-Latin titles and
# symbols don't crash on a cp1252 Windows console.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# Public relays to read/announce from. Override with OPENMARKET_RELAYS
# (comma-separated wss:// URLs).
import os

DEFAULT_RELAYS = [
    "wss://relay.damus.io",
    "wss://relay.primal.net",
    "wss://nos.lol",
    "wss://relay.noswhere.com",
    "wss://offchain.pub",
]


def get_relays():
    env = os.environ.get("OPENMARKET_RELAYS")
    if env:
        return [r.strip() for r in env.split(",") if r.strip()]
    return DEFAULT_RELAYS


# --------------------------------------------------------------------------- #
# Parsing NIP-99 (kind 30402) events into a flat listing dict.
# --------------------------------------------------------------------------- #
def parse_listing(event):
    """Turn a raw kind-30402 event into a flat, display-friendly dict."""
    tags = {}
    images = []
    hashtags = []
    for t in event.get("tags", []):
        if not t:
            continue
        key, *rest = t
        if key == "image" and rest:
            images.append(rest[0])
        elif key == "t" and rest:
            hashtags.append(rest[0])
        elif key not in tags:  # first wins for single-value tags
            tags[key] = rest

    price = tags.get("price", [])
    return {
        "id": event.get("id", ""),
        "seller": event.get("pubkey", ""),
        "created_at": event.get("created_at", 0),
        "title": (tags.get("title") or ["(untitled)"])[0],
        "summary": (tags.get("summary") or [event.get("content", "")])[0],
        "price": price[0] if len(price) > 0 else "",
        "currency": price[1] if len(price) > 1 else "",
        "location": (tags.get("location") or [""])[0],
        "condition": (tags.get("condition") or [""])[0],
        "hashtags": hashtags,
        "images": images,
    }


def matches(listing, query):
    """Case-insensitive keyword match over title/summary/tags/location."""
    q = query.lower()
    haystack = " ".join(
        [
            listing["title"],
            listing["summary"],
            listing["location"],
            " ".join(listing["hashtags"]),
        ]
    ).lower()
    return q in haystack


# --------------------------------------------------------------------------- #
# Display helpers.
# --------------------------------------------------------------------------- #
def price_str(listing):
    if listing["price"]:
        return f"{listing['price']} {listing['currency']}".strip()
    return "no price"


def print_short(i, listing):
    print(f"  [{i}] {listing['title']}  --  {price_str(listing)}")


def print_full(listing):
    line = "-" * 70
    print(line)
    print(f"TITLE    : {listing['title']}")
    print(f"PRICE    : {price_str(listing)}")
    if listing["location"]:
        print(f"LOCATION : {listing['location']}")
    if listing["condition"]:
        print(f"CONDITION: {listing['condition']}")
    if listing["hashtags"]:
        print(f"TAGS     : {', '.join(listing['hashtags'])}")
    print(f"SELLER   : {listing['seller'][:16]}... (nostr pubkey)")
    print("SUMMARY  :")
    for wrapped in textwrap.wrap(listing["summary"] or "(none)", width=66):
        print(f"    {wrapped}")
    if listing["images"]:
        print(f"IMAGES   : {len(listing['images'])} -> {listing['images'][0]}")
    print(line)


# --------------------------------------------------------------------------- #
# Screens.
# --------------------------------------------------------------------------- #
def fetch_listings(limit=50):
    from basic_nostr import NostrClient

    print(f"\nConnecting to relays and reading NIP-99 listings (limit {limit})...")
    with NostrClient(relay_urls=get_relays()) as nostr:
        raw = nostr.read_products(limit=limit)
    listings = [parse_listing(e) for e in raw]
    # Deduplicate by event id, newest first.
    seen, deduped = set(), []
    for lst in sorted(listings, key=lambda x: x["created_at"], reverse=True):
        if lst["id"] in seen:
            continue
        seen.add(lst["id"])
        deduped.append(lst)
    return deduped


def browse_or_search(query=None):
    listings = fetch_listings()
    if query:
        listings = [l for l in listings if matches(l, query)]
        print(f"\n{len(listings)} listing(s) matching '{query}':\n")
    else:
        print(f"\n{len(listings)} listing(s):\n")
    if not listings:
        print("  (nothing found)")
        return
    for i, lst in enumerate(listings, 1):
        print_short(i, lst)
    while True:
        sel = input("\nNumber to view, or Enter to go back: ").strip()
        if not sel:
            return
        if sel.isdigit() and 1 <= int(sel) <= len(listings):
            print()
            print_full(listings[int(sel) - 1])
        else:
            print("  invalid selection")


def create():
    print("\n--- Create a listing ---")
    title = input("Title            : ").strip()
    if not title:
        print("Aborted: a title is required.")
        return
    description = input("Description      : ").strip()
    price = input("Price            : ").strip()
    currency = input("Currency (XMR)   : ").strip() or "XMR"
    category = input("Category         : ").strip()
    tags = [t.strip() for t in input("Tags (comma-sep) : ").split(",") if t.strip()]
    location = input("Location (opt)   : ").strip()
    contact = input("Contact (npub/SimpleX/email): ").strip()

    listing = {
        "v": 1,
        "title": title,
        "description": description,
        "price": price,
        "currency": currency,
        "category": category,
        "tags": tags,
        "location": location,
        "contact": contact,
        "images": [],
        "created_at": int(input_now()),
    }

    # Deterministic content address, computed locally -- we do NOT upload it.
    print("\nComputing deterministic IPFS CID locally...")
    print("(first run downloads a Kubo node, ~115 MB -- one time)")
    _patch_requests_compat()
    import basic_ipfs

    payload = json.dumps(listing, sort_keys=True, separators=(",", ":")).encode()
    cid = basic_ipfs.compute_cid_locally(payload)
    print(f"\nListing JSON:\n{json.dumps(listing, indent=2)}")
    print(f"\nDeterministic CID: {cid}")
    print("(anyone who builds the same JSON gets this same CID)")

    ans = input(
        "\nAnnounce this as a NIP-99 listing on Nostr now? [y/N]: "
    ).strip().lower()
    if ans != "y":
        print("Not announced. The listing exists only locally.")
        return

    from basic_nostr import NostrClient, make_keys

    nsec = input("Paste your nsec1... (blank = throwaway anonymous key): ").strip()
    if not nsec:
        npub, nsec = make_keys()
        print(f"Generated throwaway identity: {npub}")

    with NostrClient(nsec, relay_urls=get_relays()) as nostr:
        nostr.list_product(
            title=title,
            description=description or title,
            price=int(float(price)) if price else 0,
            currency=currency,
            image_urls=[],
            categories=[category] if category else None,
            location=location or None,
        )
    print("Announced to relays. It should now appear in Browse (and on Shopstr etc.).")


def _patch_requests_compat():
    """basic-ipfs's download adapter passes ``allow_redirects`` to
    ``HTTPAdapter.send``, which newer ``requests`` (>=2.32) removed. Make the
    base adapter ignore the dropped kwarg so the one-time Kubo download works.
    Harmless on older ``requests`` (the param is present -> no patch applied)."""
    import inspect
    import requests.adapters as ra

    if getattr(ra.HTTPAdapter, "_om_compat", False):
        return
    base_send = ra.HTTPAdapter.send
    if "allow_redirects" in inspect.signature(base_send).parameters:
        return

    def send(self, request, *args, **kwargs):
        kwargs.pop("allow_redirects", None)
        return base_send(self, request, *args, **kwargs)

    ra.HTTPAdapter.send = send
    ra.HTTPAdapter._om_compat = True


def input_now():
    """Current unix time. Isolated so the rest stays import-light."""
    import time

    return time.time()


# --------------------------------------------------------------------------- #
# Menu loop.
# --------------------------------------------------------------------------- #
MENU = """
============================================================
 OpenMarket  --  the free market (desktop POC)
============================================================
 1) Browse listings
 2) Search listings
 3) Create a listing
 q) Quit
"""


def main():
    print(MENU)
    while True:
        choice = input("Choose: ").strip().lower()
        try:
            if choice == "1":
                browse_or_search()
            elif choice == "2":
                q = input("Search for: ").strip()
                browse_or_search(q or None)
            elif choice == "3":
                create()
            elif choice in ("q", "quit", "exit"):
                print("bye")
                return
            else:
                print("  pick 1, 2, 3, or q")
        except KeyboardInterrupt:
            print("\n(cancelled)")
        except Exception as exc:  # keep the POC alive on relay/network hiccups
            print(f"  error: {exc}")
        print(MENU)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nbye")
        sys.exit(0)
