"""Peint les cases de terrain dessinées en code (tiles.js) et les écrit dans resources/terrain.

Plaines, désert, collines, forêt et jungle : style plat, motif « ton sur ton » (dans la teinte
du sol) à AMOUNT d'opacité, pour que l'irrigation, les routes, les mines et les villes restent
lisibles par-dessus. Les versions ChatGPT remplacées sont dans _packs/out/terrain2.

Usage : python export.py [dossier_sortie]   (par défaut resources/terrain)
Le dessin se fait dans un Edge sans fenêtre piloté par le protocole DevTools.
"""
import asyncio
import base64
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

import websockets
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "resources", "terrain")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9447
AMOUNT = 0.40
TERRAINS = ["plains", "desert", "hills", "forest", "jungle"]


async def paint():
    profile = tempfile.mkdtemp(prefix="edge_tiles_")
    proc = subprocess.Popen([EDGE, "--headless=new", f"--remote-debugging-port={PORT}", "--disable-gpu",
                             f"--user-data-dir={profile}", "--no-first-run", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        page = None
        for _ in range(60):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=2))
                page = next((t for t in tabs if t["type"] == "page"), None)
                if page:
                    break
            except Exception:
                pass
            time.sleep(0.5)
        if not page:
            sys.exit("Edge ne répond pas sur le port de débogage")
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=64 * 1024 * 1024) as ws:
            async def evaluate(expression):
                await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                          "params": {"expression": expression, "returnByValue": True}}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == 1:
                        result = msg["result"]
                        if "exceptionDetails" in result:
                            sys.exit(result["exceptionDetails"].get("exception", {}).get("description", result))
                        return result["result"].get("value")

            await evaluate(open(os.path.join(HERE, "tiles.js"), encoding="utf-8").read())
            return await evaluate(
                "JSON.stringify(Object.fromEntries(%s.map((id) => "
                "[id, TILES.paint(document.createElement('canvas'), id, %s).toDataURL('image/png')])))"
                % (json.dumps(TERRAINS), AMOUNT))
    finally:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)


def main():
    urls = json.loads(asyncio.run(paint()))
    os.makedirs(OUT, exist_ok=True)
    for name in TERRAINS:
        data = base64.b64decode(urls[name].split(",", 1)[1])
        image = Image.open(io.BytesIO(data)).convert("RGB")     # opaque, like the other terrain tiles
        path = os.path.join(OUT, name + ".png")
        image.save(path, optimize=True)
        print(os.path.normpath(path), image.size)


if __name__ == "__main__":
    main()
