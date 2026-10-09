"""Capture a fully rendered local Streamlit page through Chrome's debugging protocol."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
from pathlib import Path

import httpx
import websockets


async def capture(url: str, output: Path, debug_port: int) -> None:
    pages = httpx.get(f"http://127.0.0.1:{debug_port}/json", timeout=10).json()
    target = next(page for page in pages if page.get("type") == "page")
    request_id = 0

    async with websockets.connect(target["webSocketDebuggerUrl"], max_size=20_000_000) as socket:

        async def command(method: str, params: dict | None = None) -> dict:
            nonlocal request_id
            request_id += 1
            current = request_id
            await socket.send(json.dumps({"id": current, "method": method, "params": params or {}}))
            while True:
                message = json.loads(await socket.recv())
                if message.get("id") == current:
                    if "error" in message:
                        raise RuntimeError(message["error"])
                    return message.get("result", {})

        await command("Page.enable")
        await command(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1440, "height": 1000, "deviceScaleFactor": 1, "mobile": False},
        )
        await command("Page.navigate", {"url": url})
        await asyncio.sleep(12)
        result = await command(
            "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False}
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(base64.b64decode(result["data"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("output", type=Path)
    parser.add_argument("--debug-port", type=int, default=9222)
    args = parser.parse_args()
    asyncio.run(capture(args.url, args.output, args.debug_port))


if __name__ == "__main__":
    main()
