"""FractalClaw Monitor Server - WebSocket server for real-time monitoring."""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

WORKSPACE_PATH = PROJECT_ROOT / "workspace"


class MonitorWebSocketServer:
    """WebSocket server that broadcasts fractal events to connected clients."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self.clients: set = set()
        self.event_file: Optional[Path] = None
        self.last_position = 0
        self.current_task_id: Optional[str] = None
        self._running = False
        self._server = None

    def set_task(self, task_id: str) -> None:
        """Set the current task to monitor."""
        self.current_task_id = task_id
        monitor_dir = WORKSPACE_PATH / ".monitor"
        self.event_file = monitor_dir / f"{task_id}_events.jsonl"
        self.last_position = 0

    def auto_detect_task(self) -> Optional[str]:
        """Auto-detect the most recent active task."""
        if not WORKSPACE_PATH.exists():
            return None

        monitor_dir = WORKSPACE_PATH / ".monitor"
        if monitor_dir.exists():
            event_files = sorted(
                monitor_dir.glob("*_events.jsonl"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if event_files:
                return event_files[0].stem.replace("_events", "")

        date_folders = sorted(
            [d for d in WORKSPACE_PATH.iterdir() if d.is_dir() and d.name.isdigit()],
            key=lambda x: x.name,
            reverse=True,
        )

        for date_folder in date_folders:
            task_folders = sorted(
                [t for t in date_folder.iterdir() if t.is_dir()],
                key=lambda x: x.stat().st_mtime,
                reverse=True,
            )
            if task_folders:
                parts = task_folders[0].name.split("_")
                return parts[1] if len(parts) > 1 else task_folders[0].name

        return None

    def read_new_events(self) -> list[dict[str, Any]]:
        """Read new events from the event file."""
        if not self.event_file or not self.event_file.exists():
            return []

        events = []
        try:
            with open(self.event_file, "r", encoding="utf-8") as f:
                f.seek(self.last_position)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        events.append(data)
                    except json.JSONDecodeError:
                        continue
                self.last_position = f.tell()
        except Exception:
            pass

        return events

    async def register_client(self, websocket) -> None:
        """Register a new WebSocket client."""
        self.clients.add(websocket)
        print(f"[Monitor] Client connected. Total: {len(self.clients)}")

        # Send current tree snapshot
        snapshot = self.get_tree_snapshot()
        await websocket.send(json.dumps({
            "type": "snapshot",
            "data": snapshot,
        }))

    async def unregister_client(self, websocket) -> None:
        """Unregister a WebSocket client."""
        self.clients.discard(websocket)
        print(f"[Monitor] Client disconnected. Total: {len(self.clients)}")

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Broadcast a message to all connected clients."""
        if not self.clients:
            return

        data = json.dumps(message)
        disconnected = set()

        for client in self.clients:
            try:
                await client.send(data)
            except Exception:
                disconnected.add(client)

        # Clean up disconnected clients
        for client in disconnected:
            self.clients.discard(client)

    def get_tree_snapshot(self) -> dict[str, Any]:
        """Get the current tree snapshot from events."""
        agents: dict[str, dict[str, Any]] = {}

        if self.event_file and self.event_file.exists():
            try:
                with open(self.event_file, "r", encoding="utf-8") as f:
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

        return {
            "task_id": self.current_task_id,
            "agents": agents,
            "total": len(agents),
        }

    async def event_publisher(self) -> None:
        """Periodically read and publish new events."""
        while self._running:
            events = self.read_new_events()
            for event in events:
                await self.broadcast({
                    "type": "event",
                    "data": event,
                })
            await asyncio.sleep(0.5)

    async def handle_client(self, websocket, path) -> None:
        """Handle a WebSocket client connection."""
        await self.register_client(websocket)
        try:
            async for message in websocket:
                # Handle client messages if needed
                try:
                    data = json.loads(message)
                    msg_type = data.get("type", "")
                    if msg_type == "ping":
                        await websocket.send(json.dumps({"type": "pong"}))
                    elif msg_type == "set_task":
                        task_id = data.get("task_id")
                        if task_id:
                            self.set_task(task_id)
                            await websocket.send(json.dumps({
                                "type": "task_set",
                                "task_id": task_id,
                            }))
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass
        finally:
            await self.unregister_client(websocket)

    async def start(self) -> None:
        """Start the WebSocket server."""
        import websockets

        self._running = True

        # Auto-detect task if not set
        if not self.current_task_id:
            task_id = self.auto_detect_task()
            if task_id:
                self.set_task(task_id)

        self._server = await websockets.serve(
            self.handle_client,
            self.host,
            self.port,
        )

        print(f"[Monitor] WebSocket server started at ws://{self.host}:{self.port}")
        if self.current_task_id:
            print(f"[Monitor] Monitoring task: {self.current_task_id}")
        else:
            print("[Monitor] Waiting for tasks...")

        # Start event publisher
        publisher_task = asyncio.create_task(self.event_publisher())

        try:
            await self._server.wait_closed()
        finally:
            self._running = False
            publisher_task.cancel()

    def stop(self) -> None:
        """Stop the server."""
        self._running = False
        if self._server:
            self._server.close()


def main():
    """Main entry point for the monitor server."""
    import argparse

    parser = argparse.ArgumentParser(description="FractalClaw Monitor Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on")
    parser.add_argument("--task", help="Specific task ID to monitor")
    args = parser.parse_args()

    server = MonitorWebSocketServer(host=args.host, port=args.port)

    if args.task:
        server.set_task(args.task)

    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\n[Monitor] Server stopped.")
        server.stop()


if __name__ == "__main__":
    main()
