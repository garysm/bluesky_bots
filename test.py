import asyncio, json
from urllib.parse import urlencode
import websockets

HOST = "wss://jetstream.us-east.bsky.network"
PATH = "/xrpc/network.bsky.jetstream.subscribeEvents"

def build_url(collections, dids=(), cursor=None):
    q = [("collections", c) for c in collections]
    q += [("dids", d) for d in dids]
    q.append(("kinds", "commit"))
    if cursor is not None:
        q.append(("cursor", str(cursor)))
    return f"{HOST}{PATH}?{urlencode(q)}"

print(build_url(["app.bsky.feed.post", "app.bsky.feed.repost"]))

async def consume(collections, handle, dids=(), cursor=None):
    backoff = 1
    while True:
        try:
            url = build_url(collections, dids, cursor)
            async with websockets.connect(url, subprotocols=["xrpc.v1.json"]) as ws:
                backoff = 1
                async for frame in ws:
                    event = json.loads(frame)["payload"]
                    await handle(event)
                    cursor = event["seq"]
        except (websockets.ConnectionClosed, OSError):
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

async def handle(event):
  print(json.dumps(event) + "\n")

asyncio.run(consume(["app.bsky.feed.post", "app.bsky.feed.repost"], handle))