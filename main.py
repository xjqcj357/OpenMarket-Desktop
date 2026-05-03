"""
OpenMarket: The free market.

The ability of the people to trade freely between one and other cannot be stopped.

By using this software, you agree that you are fully responsible for your use of it (and nobody else is).

There is no "platform" to shut down. There are no servers. There is only the code you run -- which interacts perfectly with copies of itself.

The code does not restrict, ban, or moderate. There are no limits on what you haev the ability to post, but you can optionally limit what is displayed to you.

If you want to hide certain content, add your own filters.

In the future there may be decentralized filters that everyone can contribute to and set their client to "follow" those filtering rules.

Eventually an anonymous decentralized reputation system is needed too -- one where everything committed to is public (if both parties agree), then both parties rate each other and add information on the interaction, or use a default.
this keeps it public and leave it up to the client to determine how to weight.
"""

# Posting Cotentent
import random
import basic_ipfs
import basic_nostr


DELAY = int
MOST_TRUSTED_OPENMARKET_NODES = []


# App Idle Actions()
def while_open():
    listen_for_bluetooth_broadcasts()
    listen_for_gossip_json()
    listen_to_nodes_gossip()
    get_new_cids_from_nostr()
    ocasionally_post_multiaddress_to_nostr()
    find_new_multiaddresses_on_nostr()


# App Active Actions()
def on_post(cid):
    bluetooth_broadcast_about(cid)
    gossip_json_to_most_trusted_node()
    nostr_broadcast_about(cid)

def on_nodes_requested():
    # either repond with the apps full list, or maybe make it a batch at a time and they can ask for more each time so it isn't spammed a ton? maybe it is just a channel where tons of nodes stream? like maybe its just a channel you can subscribe to where everyone is posting and it is ephemeral and you have to just go there and listen yourself. what is the best way to do this?
    pass

def on_cids_requested():
    pass

# Under-the-hood actions
def gossip_json_to_most_trusted_node(json):
    # send json to just one "most trusted" node
    pass

def on_recieve_json_gossip(json):
    """
    This is structured so that if someone sends you json, you will most likely forward it, but have a chance to post it.
    There is some randomness, but most of the time it will be passed to 5 nodes before one posts. Sometimes it will be passed farther.
    Each node only knows about itself and it's neighbor, but with this design, its neighbor is 80% likely to just be forwarding it.
    This ensures that posts travel far from the original node before they are made.
    Additionally, since this uses a random one of your most trusted nodes, (assuming most people set their trusted nodes and not everyone trusts the same nodes) this passes from most trusted to most trued (a.k.a. most UNLIKELY to be a maliscious node).
    Since the person posting to IPFS is the IP address that is visible and "standing by itself", we want trusted nodes to join, so the origin IP is "lost in the crowd" before maliscious logging nodes find the CID.
    """
    twenty_percent_chance = bool(random.randint(100) <= 20) # TODO: might need to fix this

    if twenty_percent_chance:
        on_post(cid) # make ipfs post with basic-ipfs pip package which returns cid
    else:
        gossip_json_to_most_trusted_node(json)
        #use basic-ipfs to compute CID locally
        # monitor for CID to show up on network.
        # possibly start countdown to make post if not seen in x time.

def bluetooth_broadcast_about(cid):
    # for flutter implementation. Not implemented in desktop.
    # Sends 2-part bluetooth advertisement.
    pass

def nostr_broadcast_about(cid):
    # done with basic-nostr pip package
    pass

# utility_functions
def process_gossip_json():
    pass

def pull_new_from_nostr():
    pass
