#!/usr/bin/env python3
"""
Chrome DevTools Protocol helper for automating Greenhouse/Lever job applications.
Uses the websockets library to communicate with Chrome's CDP endpoint.
"""

import asyncio
import base64
import json
import os
import sys
import time
from pathlib import Path

try:
    import websockets
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets", "-q", "--break-system-packages"])
    import websockets

CDP_URL = "ws://127.0.0.1:9222"
_msg_id = 0


async def _get_ws_url():
    """Get the WebSocket URL for the first page target."""
    import httpx
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{CDP_URL}/json", timeout=10)
        targets = resp.json()
        for t in targets:
            if t.get("type") == "page":
                return t["webSocketDebuggerUrl"]
        # If no page target, create one
        resp = await client.get(f"{CDP_URL}/json/new", timeout=10)
        return resp.json()["webSocketDebuggerUrl"]


class CDPBrowser:
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.ws = None
        self._msg_id = 0
        self._responses = {}

    async def connect(self):
        self.ws = await websockets.connect(self.ws_url, max_size=50 * 1024 * 1024)
        # Enable necessary domains
        await self.send("Page.enable")
        await self.send("Runtime.enable")
        await self.send("DOM.enable")

    async def send(self, method: str, params: dict = None) -> dict:
        self._msg_id += 1
        msg_id = self._msg_id
        msg = {"id": msg_id, "method": method}
        if params:
            msg["params"] = params
        await self.ws.send(json.dumps(msg))

        # Wait for response with matching id
        while True:
            resp = json.loads(await self.ws.recv())
            if resp.get("id") == msg_id:
                if "error" in resp:
                    raise Exception(f"CDP error: {resp['error']}")
                return resp.get("result", {})

    async def navigate(self, url: str):
        await self.send("Page.navigate", {"url": url})
        await asyncio.sleep(3)  # Wait for page load
        # Wait for load event
        try:
            await asyncio.wait_for(self._wait_load(), timeout=15)
        except asyncio.TimeoutError:
            pass
        await asyncio.sleep(2)  # Extra wait for JS rendering

    async def _wait_load(self):
        while True:
            resp = json.loads(await self.ws.recv())
            if resp.get("method") == "Page.loadEventFired":
                return

    async def evaluate(self, expression: str) -> any:
        result = await self.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        })
        return result.get("result", {}).get("value")

    async def get_document(self) -> dict:
        return await self.send("DOM.getDocument", {"depth": -1})

    async def query_selector(self, selector: str) -> int:
        root = await self.get_document()
        root_id = root["root"]["nodeId"]
        result = await self.send("DOM.querySelector", {
            "nodeId": root_id,
            "selector": selector,
        })
        return result.get("nodeId", 0)

    async def query_selector_all(self, selector: str) -> list:
        root = await self.get_document()
        root_id = root["root"]["nodeId"]
        result = await self.send("DOM.querySelectorAll", {
            "nodeId": root_id,
            "selector": selector,
        })
        return result.get("nodeIds", [])

    async def fill_input(self, selector: str, value: str):
        """Fill an input/textarea element."""
        node_id = await self.query_selector(selector)
        if not node_id:
            print(f"  Warning: Element not found: {selector}")
            return False

        # Focus the element
        await self.send("DOM.focus", {"nodeId": node_id})
        await asyncio.sleep(0.1)

        # Clear existing value and set new one via JavaScript
        escaped = value.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
        await self.evaluate(f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (el) {{
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value'
                    )?.set || Object.getOwnPropertyDescriptor(
                        window.HTMLTextAreaElement.prototype, 'value'
                    )?.set;
                    if (nativeInputValueSetter) {{
                        nativeInputValueSetter.call(el, '{escaped}');
                    }} else {{
                        el.value = '{escaped}';
                    }}
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                }}
            }})()
        """)
        return True

    async def set_input_files(self, selector: str, file_path: str):
        """Set files for a file input element."""
        node_id = await self.query_selector(selector)
        if not node_id:
            print(f"  Warning: File input not found: {selector}")
            return False

        # Read file and set via CDP
        with open(file_path, "rb") as f:
            file_data = f.read()

        file_name = os.path.basename(file_path)
        # Use DOM.setFileInputFiles
        await self.send("DOM.setFileInputFiles", {
            "nodeId": node_id,
            "files": [file_path],
        })
        return True

    async def click(self, selector: str):
        """Click an element."""
        result = await self.evaluate(f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (el) {{
                    el.click();
                    return true;
                }}
                return false;
            }})()
        """)
        return result

    async def get_form_info(self) -> dict:
        """Extract all form fields from the current page."""
        return await self.evaluate("""
            (function() {
                const form = document.querySelector('form') || document;
                const fields = [];
                
                // Text inputs, textareas
                form.querySelectorAll('input[name], textarea[name], select[name]').forEach(el => {
                    fields.push({
                        tag: el.tagName.toLowerCase(),
                        name: el.name,
                        type: el.type || '',
                        id: el.id || '',
                        placeholder: el.placeholder || '',
                        label: '',
                        required: el.required || false,
                        value: el.value || '',
                    });
                });
                
                // Find labels
                form.querySelectorAll('label').forEach(label => {
                    const forId = label.getAttribute('for');
                    const matchingField = fields.find(f => f.id === forId);
                    if (matchingField) {
                        matchingField.label = label.textContent.trim();
                    }
                });
                
                // Also try aria-label
                form.querySelectorAll('[aria-label]').forEach(el => {
                    const name = el.name || el.id || '';
                    const existing = fields.find(f => f.name === name || f.id === name);
                    if (existing && !existing.label) {
                        existing.label = el.getAttribute('aria-label');
                    }
                });
                
                return {
                    fields: fields,
                    action: form.action || '',
                    method: form.method || '',
                    formFound: !!document.querySelector('form'),
                };
            })()
        """)

    async def get_page_content(self) -> str:
        """Get the text content of the page for debugging."""
        return await self.evaluate("document.body.innerText")

    async def screenshot(self, output_path: str = "/tmp/cdp_screenshot.png"):
        """Take a screenshot."""
        result = await self.send("Page.captureScreenshot", {"format": "png"})
        data = base64.b64decode(result["data"])
        with open(output_path, "wb") as f:
            f.write(data)
        return output_path

    async def close(self):
        if self.ws:
            await self.ws.close()


async def create_browser() -> CDPBrowser:
    """Create and connect a CDP browser instance."""
    ws_url = await _get_ws_url()
    browser = CDPBrowser(ws_url)
    await browser.connect()
    return browser


async def main():
    """Test the CDP connection."""
    browser = await create_browser()
    print("Connected to Chrome via CDP")
    
    # Navigate to test page
    await browser.navigate("https://boards.greenhouse.io/capstoneintegratedsolutions/jobs/4917677007")
    print("Navigated to Greenhouse job page")
    
    # Get page content
    content = await browser.get_page_content()
    print(f"Page content (first 500 chars): {content[:500]}")
    
    # Get form info
    form_info = await browser.get_form_info()
    print(f"\nForm found: {form_info.get('formFound')}")
    print(f"Fields: {json.dumps(form_info.get('fields', []), indent=2)}")
    
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
