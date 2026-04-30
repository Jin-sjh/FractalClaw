"""FractalClaw Monitor Web - HTTP server for web-based monitoring."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

STATIC_DIR = PROJECT_ROOT / "src" / "fractalclaw" / "monitor" / "static"
WORKSPACE_PATH = PROJECT_ROOT / "workspace"


class MonitorWebServer:
    """HTTP server that serves the web-based monitoring interface."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8080, ws_port: int = 8765):
        self.host = host
        self.port = port
        self.ws_port = ws_port
        self._app = None
        self._runner = None
        self._site = None

    async def handle_index(self, request):
        """Serve the main HTML page."""
        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            return self._json_response({"error": "index.html not found"}, status=404)

        content = index_path.read_text(encoding="utf-8")
        # Inject WebSocket port
        content = content.replace(
            "const devUrl = 'ws://127.0.0.1:8765';",
            f"const devUrl = 'ws://127.0.0.1:{self.ws_port}';",
        )

        from aiohttp import web
        return web.Response(text=content, content_type="text/html")

    async def handle_static(self, request):
        """Serve static files (CSS, JS)."""
        filename = request.match_info.get("filename", "")
        file_path = STATIC_DIR / filename

        # Security: prevent directory traversal
        try:
            file_path.resolve().relative_to(STATIC_DIR.resolve())
        except ValueError:
            return self._json_response({"error": "Invalid path"}, status=403)

        if not file_path.exists() or not file_path.is_file():
            return self._json_response({"error": "File not found"}, status=404)

        from aiohttp import web

        content_type = "text/plain"
        if filename.endswith(".css"):
            content_type = "text/css"
        elif filename.endswith(".js"):
            content_type = "application/javascript"
        elif filename.endswith(".html"):
            content_type = "text/html"

        return web.FileResponse(file_path, headers={"Content-Type": content_type})

    async def handle_api_snapshot(self, request):
        """API endpoint to get current tree snapshot."""
        task_id = request.query.get("task_id")

        if not task_id:
            # Auto-detect latest task
            monitor_dir = WORKSPACE_PATH / ".monitor"
            if monitor_dir.exists():
                event_files = sorted(
                    monitor_dir.glob("*_events.jsonl"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                if event_files:
                    task_id = event_files[0].stem.replace("_events", "")

        if not task_id:
            return self._json_response({"error": "No active task found"}, status=404)

        agents = {}
        event_file = WORKSPACE_PATH / ".monitor" / f"{task_id}_events.jsonl"

        if event_file.exists():
            try:
                with open(event_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                            event_type = event.get("event_type", "")
                            agent_id = event.get("agent_id")

                            if event_type == "agent_spawned" and agent_id:
                                agents[agent_id] = {
                                    "id": agent_id,
                                    "name": event.get("agent_name", "Unknown"),
                                    "role": event.get("agent_role", "worker"),
                                    "parent_id": event.get("parent_agent_id"),
                                    "state": event.get("state", "idle"),
                                    "depth": event.get("depth", 0),
                                    "branch_path": event.get("branch_path", "root"),
                                }
                            elif event_type == "agent_state_changed" and agent_id and agent_id in agents:
                                agents[agent_id]["state"] = event.get("state", "idle")
                        except json.JSONDecodeError:
                            continue
            except Exception:
                pass

        return self._json_response({
            "task_id": task_id,
            "agents": agents,
            "total": len(agents),
        })

    def _json_response(self, data: dict[str, Any], status: int = 200):
        from aiohttp import web
        return web.Response(
            text=json.dumps(data),
            status=status,
            content_type="application/json",
        )

    async def start(self) -> None:
        """Start the HTTP server."""
        from aiohttp import web

        self._app = web.Application()
        self._app.router.add_get("/", self.handle_index)
        self._app.router.add_get("/static/{filename}", self.handle_static)
        self._app.router.add_get("/api/snapshot", self.handle_api_snapshot)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()

        print(f"[Monitor Web] Server started at http://{self.host}:{self.port}")
        print(f"[Monitor Web] WebSocket server at ws://{self.host}:{self.ws_port}")
        print(f"[Monitor Web] Open http://{self.host}:{self.port} in your browser")

        # Keep running
        while True:
            await asyncio.sleep(3600)

    def stop(self) -> None:
        """Stop the server."""
        if self._runner:
            asyncio.create_task(self._runner.cleanup())


def main():
    """Main entry point for the web monitor."""
    import argparse

    parser = argparse.ArgumentParser(description="FractalClaw Monitor Web")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port")
    parser.add_argument("--ws-port", type=int, default=8765, help="WebSocket port")
    args = parser.parse_args()

    # Start WebSocket server in background
    from entry.monitor_server import MonitorWebSocketServer

    ws_server = MonitorWebSocketServer(host=args.host, port=args.ws_port)

    async def run_both():
        ws_task = asyncio.create_task(ws_server.start())

        # Wait a moment for WS server to start
        await asyncio.sleep(1)

        web_server = MonitorWebServer(
            host=args.host,
            port=args.port,
            ws_port=args.ws_port,
        )
        web_task = asyncio.create_task(web_server.start())

        try:
            await asyncio.gather(ws_task, web_task)
        except KeyboardInterrupt:
            pass
        finally:
            ws_server.stop()
            web_server.stop()

    try:
        asyncio.run(run_both())
    except KeyboardInterrupt:
        print("\n[Monitor Web] Servers stopped.")


if __name__ == "__main__":
    main()
