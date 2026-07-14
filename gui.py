"""
OpenMarket Desktop -- tkinter GUI (alpha).

A clickable front end over the same logic as main.py:
  * Market tab -- browse/search live NIP-99 (kind 30402) listings from Nostr.
  * Sell tab   -- build a listing, compute its deterministic IPFS CID locally,
                  and optionally announce it as NIP-99.

Network / IPFS work runs on background threads so the window never freezes;
results are marshalled back to the UI thread with root.after().
"""

import json
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

from main import (
    get_relays,
    fetch_listings,
    matches,
    price_str,
    compute_cid,
)


class OpenMarketApp:
    def __init__(self, root):
        self.root = root
        self.listings = []          # currently displayed listings
        self._all = []              # last full fetch (for local search)

        root.title("OpenMarket -- alpha")
        root.geometry("940x620")
        root.minsize(760, 480)

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self._build_market_tab(nb)
        self._build_sell_tab(nb)

        # Auto-load the market on startup.
        self.refresh()

    # ------------------------------------------------------------------ #
    # Market tab (browse + search)
    # ------------------------------------------------------------------ #
    def _build_market_tab(self, nb):
        tab = ttk.Frame(nb)
        nb.add(tab, text="Market")

        bar = ttk.Frame(tab)
        bar.pack(fill="x", padx=6, pady=6)
        self.search_var = tk.StringVar()
        entry = ttk.Entry(bar, textvariable=self.search_var)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda e: self.search())
        ttk.Button(bar, text="Search", command=self.search).pack(side="left", padx=4)
        ttk.Button(bar, text="Clear", command=self.clear_search).pack(side="left")
        ttk.Button(bar, text="Refresh", command=self.refresh).pack(side="left", padx=4)

        body = ttk.Panedwindow(tab, orient="horizontal")
        body.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        left = ttk.Frame(body)
        self.listbox = tk.Listbox(left, activestyle="none")
        sb = ttk.Scrollbar(left, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        body.add(left, weight=1)

        right = ttk.Frame(body)
        self.detail = tk.Text(right, wrap="word", state="disabled", width=44)
        self.detail.pack(fill="both", expand=True)
        body.add(right, weight=1)

        self.status = ttk.Label(tab, text="", anchor="w")
        self.status.pack(fill="x", padx=6, pady=(0, 4))

    def refresh(self):
        self._set_status("Connecting to relays and reading listings...")
        self._run_bg(self._fetch_worker)

    def _fetch_worker(self):
        def log(msg):
            self.root.after(0, lambda: self._set_status(msg))

        try:
            listings = fetch_listings(limit=100, log=log)
        except Exception as exc:
            self.root.after(0, lambda: self._set_status(f"Fetch failed: {exc}"))
            return
        self.root.after(0, lambda: self._show(listings, full=True))

    def _show(self, listings, full=False):
        if full:
            self._all = listings
        self.listings = listings
        self.listbox.delete(0, "end")
        for lst in listings:
            self.listbox.insert("end", f"{lst['title']}  --  {price_str(lst)}")
        self._set_status(f"{len(listings)} listing(s).")
        self._set_detail("")

    def search(self):
        q = self.search_var.get().strip()
        if not q:
            self._show(self._all)
            return
        self._show([l for l in self._all if matches(l, q)])
        self._set_status(f"{len(self.listings)} match(es) for '{q}'.")

    def clear_search(self):
        self.search_var.set("")
        self._show(self._all)

    def on_select(self, _event):
        sel = self.listbox.curselection()
        if not sel:
            return
        lst = self.listings[sel[0]]
        lines = [
            f"TITLE     : {lst['title']}",
            f"PRICE     : {price_str(lst)}",
        ]
        if lst["location"]:
            lines.append(f"LOCATION  : {lst['location']}")
        if lst["condition"]:
            lines.append(f"CONDITION : {lst['condition']}")
        if lst["hashtags"]:
            lines.append(f"TAGS      : {', '.join(lst['hashtags'])}")
        lines.append(f"SELLER    : {lst['seller'][:24]}... (nostr pubkey)")
        lines.append("")
        lines.append(lst["summary"] or "(no description)")
        if lst["images"]:
            lines.append("")
            lines.append(f"IMAGES ({len(lst['images'])}):")
            lines.extend(lst["images"])
        self._set_detail("\n".join(lines))

    # ------------------------------------------------------------------ #
    # Sell tab (create)
    # ------------------------------------------------------------------ #
    def _build_sell_tab(self, nb):
        tab = ttk.Frame(nb)
        nb.add(tab, text="Sell")

        form = ttk.Frame(tab)
        form.pack(fill="x", padx=10, pady=10)
        self.fields = {}
        rows = [
            ("title", "Title"),
            ("price", "Price"),
            ("currency", "Currency"),
            ("category", "Category"),
            ("tags", "Tags (comma-sep)"),
            ("location", "Location"),
            ("contact", "Contact (npub / SimpleX / email)"),
        ]
        for i, (key, label) in enumerate(rows):
            ttk.Label(form, text=label).grid(row=i, column=0, sticky="e", padx=4, pady=3)
            var = tk.StringVar(value="XMR" if key == "currency" else "")
            ttk.Entry(form, textvariable=var, width=52).grid(
                row=i, column=1, sticky="we", padx=4, pady=3
            )
            self.fields[key] = var
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Description").grid(row=len(rows), column=0, sticky="ne", padx=4)
        self.desc = tk.Text(form, height=4, width=52, wrap="word")
        self.desc.grid(row=len(rows), column=1, sticky="we", padx=4, pady=3)

        btns = ttk.Frame(tab)
        btns.pack(fill="x", padx=10)
        ttk.Button(btns, text="Compute CID", command=self.compute_cid).pack(side="left")
        ttk.Button(btns, text="Announce on Nostr", command=self.announce).pack(
            side="left", padx=6
        )
        ttk.Label(btns, text="nsec (blank = anonymous throwaway):").pack(side="left", padx=(12, 4))
        self.nsec_var = tk.StringVar()
        ttk.Entry(btns, textvariable=self.nsec_var, show="*", width=24).pack(side="left")

        self.sell_out = tk.Text(tab, height=14, wrap="word", state="disabled")
        self.sell_out.pack(fill="both", expand=True, padx=10, pady=10)

    def _build_listing(self):
        f = {k: v.get().strip() for k, v in self.fields.items()}
        if not f["title"]:
            messagebox.showwarning("OpenMarket", "A title is required.")
            return None
        return {
            "v": 1,
            "title": f["title"],
            "description": self.desc.get("1.0", "end").strip(),
            "price": f["price"],
            "currency": f["currency"] or "XMR",
            "category": f["category"],
            "tags": [t.strip() for t in f["tags"].split(",") if t.strip()],
            "location": f["location"],
            "contact": f["contact"],
            "images": [],
            "created_at": int(time.time()),
        }

    def compute_cid(self):
        listing = self._build_listing()
        if not listing:
            return
        # Pure local sha2-256 hash -- instant, no daemon, no network, no IP leak.
        payload = json.dumps(listing, sort_keys=True, separators=(",", ":")).encode()
        cid = compute_cid(payload)
        self._sell_log(json.dumps(listing, indent=2))
        self._sell_log(f"\nDeterministic CID (hashed locally, nothing uploaded): {cid}")

    def announce(self):
        listing = self._build_listing()
        if not listing:
            return
        if not messagebox.askyesno(
            "OpenMarket",
            "Publish this listing to public Nostr relays as NIP-99?\n\n"
            "It becomes visible on Shopstr, Plebeian Market, etc. -- and the\n"
            "relays (including attacker-run ones you've auto-discovered) see your\n"
            "IP next to your npub. Use Tor/VPN if that link matters to you.",
        ):
            return
        nsec = self.nsec_var.get().strip()
        self._sell_log("\nAnnouncing to relays...")

        def worker():
            from basic_nostr import NostrClient, make_keys

            key = nsec
            if not key:
                npub, key = make_keys()
                self.root.after(0, lambda: self._sell_log(
                    f"Throwaway identity: {npub} (one-time, not saved -- can't edit/delete later)"))
            try:
                price_val = int(float(listing["price"])) if listing["price"] else 0
            except ValueError:
                price_val = 0
            try:
                with NostrClient(key, relay_urls=get_relays()) as nostr:
                    nostr.list_product(
                        title=listing["title"],
                        description=listing["description"] or listing["title"],
                        price=price_val,
                        currency=listing["currency"],
                        image_urls=[],
                        categories=[listing["category"]] if listing["category"] else None,
                        location=listing["location"] or None,
                    )
            except Exception as exc:
                self.root.after(0, lambda: self._sell_log(f"Announce failed: {exc}"))
                return
            self.root.after(
                0, lambda: self._sell_log("Announced. It should appear under Market -> Refresh.")
            )

        self._run_bg(worker)

    # ------------------------------------------------------------------ #
    # Small helpers
    # ------------------------------------------------------------------ #
    def _run_bg(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def _set_status(self, text):
        self.status.config(text=text)

    def _set_detail(self, text):
        self.detail.config(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.config(state="disabled")

    def _sell_log(self, text):
        self.sell_out.config(state="normal")
        self.sell_out.insert("end", text + "\n")
        self.sell_out.see("end")
        self.sell_out.config(state="disabled")


def main():
    root = tk.Tk()
    OpenMarketApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
