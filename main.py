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
  - the listing CID is a pure sha2-256 hash computed locally (no IPFS daemon,
    no network) so "compute locally, don't upload" doesn't leak your IP.

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

import base64
import getpass
import hashlib
import json
import re
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
# (comma-separated wss:// URLs) to pin an exact set and disable auto-widening.
import os

DEFAULT_RELAYS = [
    "wss://relay.damus.io",
    "wss://relay.primal.net",
    "wss://nos.lol",
    "wss://relay.noswhere.com",
    "wss://offchain.pub",
]

# Bounds against hostile relays (they control response size/count/content).
MAX_RELAYS = 30            # cap total relays we ever connect to
MAX_LISTINGS = 500         # cap listings we keep/render (memory / UI freeze)
MAX_TAGS_PER_EVENT = 200   # cap tags parsed per event (CPU/memory burn)
CLOCK_SKEW = 300           # tolerate 5 min of future timestamp, no more
# Discovered relays persist here so later launches start wide (gossip model).
RELAY_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".relay_cache.json")


def _pinned_relays():
    """An explicit OPENMARKET_RELAYS override, or None to use defaults+cache."""
    env = os.environ.get("OPENMARKET_RELAYS")
    if env:
        return [r.strip() for r in env.split(",") if r.strip()]
    return None


def load_cached_relays():
    try:
        with open(RELAY_CACHE, encoding="utf-8") as fh:
            return [r for r in json.load(fh) if isinstance(r, str)]
    except (OSError, ValueError):
        return []


def save_cached_relays(relays):
    extra = [r for r in relays if r not in DEFAULT_RELAYS]
    try:
        with open(RELAY_CACHE, "w", encoding="utf-8") as fh:
            json.dump(sorted(extra), fh)
    except OSError:
        pass


def get_relays():
    """Seed relays unioned with anything discovered on past runs (capped).
    A pinned OPENMARKET_RELAYS override wins outright."""
    pinned = _pinned_relays()
    if pinned:
        return pinned
    merged = list(dict.fromkeys(DEFAULT_RELAYS + load_cached_relays()))
    return merged[:MAX_RELAYS]


def _valid_relay(url):
    """wss:// only, no userinfo/whitespace, a real dotted host, and NOT a
    private/loopback/link-local address. Attacker-supplied NIP-65 entries drive
    outbound connections, so we refuse to be pointed at internal endpoints."""
    import ipaddress

    if not isinstance(url, str) or not url.startswith("wss://"):
        return False
    if "@" in url or any(c.isspace() for c in url):
        return False
    host = url[len("wss://") :].split("/", 1)[0].split(":", 1)[0]
    if not host or "." not in host:  # also rejects bare IPv6 / hostnames w/o TLD
        return False
    low = host.lower()
    if low in ("localhost", "njump.me") or low.endswith((".local", ".internal")):
        return False
    try:
        ip = ipaddress.ip_address(host)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            return False
    except ValueError:
        pass  # not an IP literal -> a hostname, allowed
    return True


def discover_relays(client, pubkeys):
    """Read the NIP-65 relay lists (kind 10002) of these sellers and count the
    valid wss:// relays they publish to. Type-safe and bounded: hostile 10002
    events can carry non-list tags or thousands of entries. Returns a dict so
    callers can prefer the most widely-cited relays."""
    from collections import Counter

    counts = Counter()
    if not pubkeys:
        return counts
    events = client.read_events(authors=pubkeys, kinds=[10002], limit=len(pubkeys) + 20)
    for e in events:
        if not isinstance(e, dict):
            continue
        raw = e.get("tags", [])
        if not isinstance(raw, list):
            continue
        for t in raw[:MAX_TAGS_PER_EVENT]:
            if not isinstance(t, (list, tuple)) or len(t) < 2 or t[0] != "r":
                continue
            marker = t[2] if len(t) > 2 else ""
            url = t[1].rstrip("/") if isinstance(t[1], str) else ""
            # "" == read+write, "write" == where they publish. Skip read-only.
            if marker != "read" and _valid_relay(url):
                counts[url] += 1
    return counts


# --------------------------------------------------------------------------- #
# Parsing NIP-99 (kind 30402) events into a flat listing dict.
# --------------------------------------------------------------------------- #
# Every listing field is attacker-controlled and gets rendered to a terminal or
# a tk widget, so we sanitize at this single choke point:
#   * strip C0/C1 control bytes incl. ESC  -> no ANSI/OSC escape injection
#     (screen spoofing, OSC-8 hyperlink IP-leak, OSC-52 clipboard hijack)
#   * strip bidi-override / zero-width      -> no title/price spoofing
#   * newlines are controls too, so removed  -> no forged extra rows/fields
#   * cap length                            -> no multi-MB field freezing the UI
_UNSAFE_RANGES = (
    (0x00, 0x1f), (0x7f, 0x9f),          # C0 controls (ESC/CR/LF/TAB), DEL, C1
    (0x200b, 0x200f),                    # zero-width space/joiners, LRM, RLM
    (0x202a, 0x202e),                    # bidi embeddings / overrides
    (0x2066, 0x2069),                    # bidi isolates
    (0x00ad, 0x00ad), (0xfeff, 0xfeff),  # soft hyphen, BOM / ZWNBSP
)
_UNSAFE = re.compile("[" + "".join(chr(lo) + "-" + chr(hi) for lo, hi in _UNSAFE_RANGES) + "]")


def clean(value, maxlen=280):
    """Coerce to str and strip anything that could inject or spoof on display."""
    if not isinstance(value, str):
        value = str(value)
    value = _UNSAFE.sub("", value)
    return value[:maxlen]


def _first(seq, maxlen):
    """Sanitized first element of a tag value list, or '' if absent/empty."""
    return clean(seq[0], maxlen) if isinstance(seq, list) and seq else ""


def parse_listing(event):
    """Turn a raw kind-30402 event into a flat, sanitized dict. Returns None for
    structurally invalid events. Never raises on hostile input."""
    if not isinstance(event, dict):
        return None
    raw_tags = event.get("tags", [])
    if not isinstance(raw_tags, list):
        raw_tags = []

    tags = {}
    images = []
    hashtags = []
    for t in raw_tags[:MAX_TAGS_PER_EVENT]:
        if not isinstance(t, (list, tuple)) or not t:
            continue
        key, rest = t[0], list(t[1:])
        if key == "image" and rest and len(images) < 12:
            images.append(clean(rest[0], 400))
        elif key == "t" and rest and len(hashtags) < 30:
            hashtags.append(clean(rest[0], 60))
        elif isinstance(key, str) and key not in tags:  # first wins
            tags[key] = rest

    created = event.get("created_at", 0)
    if not isinstance(created, int) or isinstance(created, bool) or created < 0:
        created = 0

    price = tags.get("price", [])
    return {
        "id": clean(event.get("id", ""), 64),
        "seller": clean(event.get("pubkey", ""), 64),
        "created_at": created,
        "title": _first(tags.get("title"), 200) or "(untitled)",
        "summary": _first(tags.get("summary"), 2000) or clean(event.get("content", ""), 2000),
        "price": _first(price, 32),
        "currency": clean(price[1], 16) if isinstance(price, list) and len(price) > 1 else "",
        "location": _first(tags.get("location"), 120),
        "condition": _first(tags.get("condition"), 40),
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
def _most_common(counts):
    """(relay, count) pairs sorted by count desc, then name for stable order."""
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def _dedupe(events):
    """Parse, drop invalid/duplicate events, newest first. One hostile event can
    never abort the batch, and future-dated listings can't sort to the top."""
    import time

    if not isinstance(events, list):
        return []
    ceiling = int(time.time()) + CLOCK_SKEW
    listings = []
    for e in events:
        lst = parse_listing(e)
        if lst and lst["id"]:
            listings.append(lst)
    listings.sort(key=lambda x: min(x["created_at"], ceiling), reverse=True)
    seen, deduped = set(), []
    for lst in listings:
        if lst["id"] in seen:
            continue
        seen.add(lst["id"])
        deduped.append(lst)
        if len(deduped) >= MAX_LISTINGS:
            break
    return deduped


def fetch_listings(limit=50, widen=True, log=print):
    """Fetch NIP-99 listings. When ``widen`` and no OPENMARKET_RELAYS override is
    set, discover the sellers' NIP-65 relays and re-query the widened set,
    persisting new relays for next time."""
    from basic_nostr import NostrClient

    relays = get_relays()
    log(f"Reading NIP-99 listings from {len(relays)} relay(s)...")
    with NostrClient(relay_urls=relays) as nostr:
        raw = nostr.read_products(limit=limit)

        if widen and _pinned_relays() is None:
            pubkeys = list({e.get("pubkey") for e in raw if e.get("pubkey")})[:60]
            try:
                counts = discover_relays(nostr, pubkeys)
            except Exception:
                counts = {}
            # Keep the seeds, then fill remaining slots with the most-cited relays.
            ranked = [r for r, _ in _most_common(counts) if r not in relays]
            merged = (relays + ranked)[:MAX_RELAYS]
            new = [r for r in merged if r not in relays]
            if new:
                save_cached_relays(merged)
                log(f"Discovered {len(new)} new relay(s) via NIP-65; widening to {len(merged)}...")
                with NostrClient(relay_urls=merged) as wide:
                    raw = raw + wide.read_products(limit=limit)

    return _dedupe(raw)


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

    # Deterministic content address, computed purely locally: a sha2-256 hash of
    # the JSON. No IPFS daemon, no network, nothing uploaded or broadcast.
    payload = json.dumps(listing, sort_keys=True, separators=(",", ":")).encode()
    cid = compute_cid(payload)
    print(f"\nListing JSON:\n{json.dumps(listing, indent=2)}")
    print(f"\nDeterministic CID: {cid}")
    print("(hashed locally -- nothing was uploaded; anyone who builds the same")
    print(" JSON gets this same CID)")

    ans = input(
        "\nAnnounce this as a NIP-99 listing on Nostr now? [y/N]: "
    ).strip().lower()
    if ans != "y":
        print("Not announced. The listing exists only locally.")
        return

    from basic_nostr import NostrClient, make_keys

    print(
        "\n! Announcing sends a SIGNED event to public relays over the clearnet."
        "\n  Those relays -- including attacker-run ones you've auto-discovered --"
        "\n  see your IP next to your npub and this listing. Use Tor/VPN if that"
        "\n  link matters to you."
    )
    nsec = getpass.getpass(
        "Paste your nsec1... (hidden input; blank = throwaway key): "
    ).strip()
    if not nsec:
        npub, nsec = make_keys()
        print(f"Generated throwaway identity: {npub}")
        print("(one-time key, NOT saved -- you cannot edit or delete this listing later)")

    try:
        price_val = int(float(price)) if price else 0
    except ValueError:
        price_val = 0
    with NostrClient(nsec, relay_urls=get_relays()) as nostr:
        nostr.list_product(
            title=title,
            description=description or title,
            price=price_val,
            currency=currency,
            image_urls=[],
            categories=[category] if category else None,
            location=location or None,
        )
    print("Announced to relays. It should now appear in Browse (and on Shopstr etc.).")


def compute_cid(data):
    """Deterministic IPFS CIDv1 (raw codec, sha2-256) of the given bytes/text,
    computed entirely locally -- no daemon, no network, nothing uploaded. For a
    small single-block payload this equals `ipfs add --cid-version=1 --raw-leaves`.
    Doing it this way (vs. booting a Kubo node) avoids joining the public IPFS
    DHT, which would leak the user's IP -- the whole point of 'compute locally'."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    digest = hashlib.sha256(data).digest()
    cid_bytes = bytes([0x01, 0x55, 0x12, 0x20]) + digest  # cidv1, raw, sha2-256, 32B
    return "b" + base64.b32encode(cid_bytes).decode("ascii").lower().rstrip("=")


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
