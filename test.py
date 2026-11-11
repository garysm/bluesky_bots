import asyncio
import json
import websockets

URI = (
  "wss://jetstream.us-east.bsky.network/xrpc/network.bsky.jetstream.subscribeEvents"
  "?collections=app.bsky.feed.post&kinds=commit"
)

async def listen():
  async with websockets.connect(URI, subprotocols=["xrpc.v1.json"]) as ws:
    async for frame in ws:
      event = json.loads(frame)["payload"]
      if event["operation"] != "delete":
        print(event["seq"], event["did"], event["record"]["text"])

asyncio.run(listen())