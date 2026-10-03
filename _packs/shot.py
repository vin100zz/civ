import asyncio, json, subprocess, sys, time, base64, urllib.request
import websockets

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9333
URL = "http://127.0.0.1:8006/"


async def main(out_prefix, script_steps):
    proc = subprocess.Popen([EDGE, "--headless=new", f"--remote-debugging-port={PORT}", "--window-size=1920,1080",
                             "--user-data-dir=C:\\V\\civ\\_packs\\edge_profile", "--disable-gpu", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
                break
            except Exception:
                time.sleep(0.5)
        page = [t for t in tabs if t["type"] == "page"][0]
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=64 * 1024 * 1024) as ws:
            n = 0

            async def call(method, params=None):
                nonlocal n
                n += 1
                await ws.send(json.dumps({"id": n, "method": method, "params": params or {}}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == n:
                        return msg.get("result", {})

            await call("Page.enable")
            await call("Network.enable")
            await call("Network.setCacheDisabled", {"cacheDisabled": True})
            await call("Emulation.setDeviceMetricsOverride", {"width": 1920, "height": 1080, "deviceScaleFactor": 1, "mobile": False})
            await call("Page.navigate", {"url": URL})
            await asyncio.sleep(3)
            for i, (kind, arg, wait) in enumerate(script_steps):
                if kind == "eval":
                    r = await call("Runtime.evaluate", {"expression": arg, "awaitPromise": True, "returnByValue": True})
                    print("eval ->", json.dumps(r.get("result", {}).get("value"))[:300])
                elif kind == "shot":
                    r = await call("Page.captureScreenshot", {"format": "png"})
                    open(f"{out_prefix}_{arg}.png", "wb").write(base64.b64decode(r["data"]))
                await asyncio.sleep(wait)
    finally:
        proc.terminate()


if __name__ == "__main__":
    steps = json.loads(sys.argv[2])
    asyncio.run(main(sys.argv[1], steps))
