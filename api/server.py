"""
MemoryMap — FastAPI Server
REST and WebSocket interface for the MemoryMap engine.

Endpoints:
  GET  /status          → system health
  GET  /objects         → all memory records
  GET  /objects/{label} → find object by label
  POST /query           → natural language query
  POST /observe         → submit a base64 frame
  DELETE /memory        → wipe memory
  WS   /ws/live         → real-time object feed
"""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Optional

import cv2
import numpy as np
from fastapi import FastAPI, Form, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from loguru import logger

from core.engine import MemoryMapEngine
from memory.store import MemoryStore


# ── App factory ────────────────────────────────────────────────────────────

def create_app(
    engine: MemoryMapEngine,
    server_ip: str = "YOUR_COMPUTER_IP",
    on_detections=None,   # optional callback(labels: list[str], total: int)
) -> FastAPI:
    app = FastAPI(
        title="MemoryMap API",
        description="A second brain for physical space.",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Attach engine to app state so routes can access it
    app.state.engine = engine

    # WebSocket connection manager
    manager = ConnectionManager()
    app.state.ws_manager = manager

    # ── Health ─────────────────────────────────────────────────────────────

    @app.get("/status", tags=["System"])
    async def status():
        """System health and stats."""
        return engine.status()

    # ── Phone Camera Stream ────────────────────────────────────────────────

    @app.get("/phone-stream", tags=["Vision"])
    async def phone_stream_page():
        """HTML page for phone camera stream."""
        observe_url = f"http://{server_ip}:8000/observe"
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>MemoryMap — iPhone Shortcuts</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    margin: 0;
                    padding: 20px;
                }}
                .container {{
                    background: white;
                    border-radius: 12px;
                    padding: 30px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.3);
                    max-width: 600px;
                    margin: 0 auto;
                }}
                h1 {{
                    color: #333;
                    margin: 0 0 10px 0;
                }}
                .subtitle {{
                    color: #666;
                    margin-bottom: 30px;
                    font-size: 14px;
                }}
                .section {{
                    margin: 30px 0;
                    padding: 20px;
                    background: #f5f5f5;
                    border-radius: 8px;
                    border-left: 4px solid #667eea;
                }}
                .section h2 {{
                    margin: 0 0 15px 0;
                    font-size: 18px;
                    color: #333;
                }}
                .steps {{
                    list-style: none;
                    padding: 0;
                }}
                .steps li {{
                    padding: 8px 0;
                    color: #555;
                }}
                .steps li:before {{
                    content: "→ ";
                    color: #667eea;
                    font-weight: bold;
                    margin-right: 8px;
                }}
                code {{
                    background: #eee;
                    padding: 2px 6px;
                    border-radius: 3px;
                    font-family: monospace;
                    font-size: 13px;
                }}
                .endpoint {{
                    background: #333;
                    color: #0f0;
                    padding: 15px;
                    border-radius: 6px;
                    font-family: monospace;
                    font-size: 13px;
                    margin: 15px 0;
                    word-break: break-all;
                }}
                .info {{
                    background: #e7f3ff;
                    border-left: 4px solid #2196F3;
                    padding: 15px;
                    border-radius: 4px;
                    margin: 15px 0;
                    color: #0277BD;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>📱 MemoryMap + iPhone Shortcuts</h1>
                <p class="subtitle">Stream video directly from your iPhone camera</p>

                <div class="info">
                    ✅ No external apps needed<br>
                    ✅ Runs on iPhone native Shortcuts<br>
                    ✅ Real-time video analysis
                </div>

                <div class="section">
                    <h2>📋 Setup Instructions</h2>
                    <ol class="steps" style="list-style: decimal; margin-left: 20px;">
                        <li>Open <strong>Shortcuts app</strong> on your iPhone</li>
                        <li>Tap <strong>"Create Shortcut"</strong> or <strong>"+"</strong></li>
                        <li>Add the actions listed below in order</li>
                    </ol>
                </div>

                <div class="section">
                    <h2>🔧 Shortcut Actions</h2>
                    
                    <h3 style="margin-top: 0;">1️⃣ Repeat</h3>
                    <p style="font-size: 13px; color: #666;">Search "Repeat" → Select "Repeat with each item"</p>
                    <code>Set to: Infinite Loop</code>
                    
                    <h3>2️⃣ Take Photo</h3>
                    <p style="font-size: 13px; color: #666;">Add inside the repeat block</p>
                    <code>Camera: Back | Save to: Don't Save</code>
                    
                    <h3>3️⃣ Encode Data</h3>
                    <p style="font-size: 13px; color: #666;">Search "Get base64 Encoded Data"</p>
                    <code>Input: [Photo Result] | Format: JPEG | Quality: 70%</code>
                    
                    <h3>4️⃣ Make HTTP Request</h3>
                    <p style="font-size: 13px; color: #666;">Search "Post" → Select "Post" under "URL"</p>
                    
                    <div style="background: #fff; padding: 15px; border: 1px solid #ddd; border-radius: 6px; margin: 10px 0;">
                        <strong>URL:</strong>
                        <div class="endpoint">{observe_url}</div>

                        <strong style="display: block; margin-top: 10px;">Method:</strong>
                        <code>POST</code>

                        <strong style="display: block; margin-top: 10px;">Request Body:</strong>
                        <code>JSON</code>

                        <strong style="display: block; margin-top: 10px;">Body fields (key → value):</strong>
                        <code>image_b64</code> → [base64 encoded data from step 3]
                    </div>
                    
                    <h3>5️⃣ Wait</h3>
                    <p style="font-size: 13px; color: #666;">Search "Wait" and add after the POST</p>
                    <code>Duration: 1 second</code>
                </div>

                <div class="section">
                    <h2>🌐 Your Computer IP</h2>
                    <p style="margin: 0 0 10px 0;">Check the terminal output for something like:</p>
                    <div class="endpoint">192.168.x.x or 127.0.0.1</div>
                    <p style="font-size: 12px; color: #666; margin: 0;">Replace <code>YOUR_IP</code> with this address</p>
                </div>

                <div class="section">
                    <h2>💡 Tips</h2>
                    <ul style="margin: 0; padding-left: 20px; color: #555; font-size: 14px;">
                        <li><strong>Test first:</strong> Remove repeat, run once, check terminal</li>
                        <li><strong>Network:</strong> Phone and computer must be on same WiFi</li>
                        <li><strong>Adjust timing:</strong> Change wait time (1-3 sec) based on speed</li>
                        <li><strong>Permissions:</strong> Open Settings > Shortcuts > Allow Untrusted if needed</li>
                        <li><strong>Debug:</strong> Watch terminal for incoming requests</li>
                    </ul>
                </div>

                <div class="info">
                    📍 <strong>Pro tip:</strong> Save the shortcut as "MemoryMap Scan" for quick access
                </div>
            </div>
        </body>

        </html>
        """
        return HTMLResponse(content=html_content)

    # ── Objects ───────────────────────────────────────────────────────────

    @app.get("/objects", tags=["Memory"])
    async def list_objects(stale: bool = False):
        """
        Return all objects in memory.
        Set ?stale=true to include stale (unseen for a long time) records.
        """
        records = engine.store.all() if stale else engine.store.all_current()
        return [r.to_dict() for r in records]

    @app.get("/objects/{label}", tags=["Memory"])
    async def find_object(label: str, include_stale: bool = True):
        """Find all memory records for a given object label."""
        records = engine.store.query_by_label(label, include_stale=include_stale)
        if not records:
            raise HTTPException(status_code=404, detail=f"No records found for '{label}'.")
        return [r.to_dict() for r in records]

    # ── Query ─────────────────────────────────────────────────────────────

    class QueryRequest(BaseModel):
        text: str

    class QueryResponse(BaseModel):
        query: str
        answer: str

    @app.post("/query", response_model=QueryResponse, tags=["Query"])
    async def query(req: QueryRequest):
        """Submit a natural language question about the environment."""
        if not req.text.strip():
            raise HTTPException(status_code=400, detail="Query text cannot be empty.")
        answer = engine.ask(req.text)
        return QueryResponse(query=req.text, answer=answer)

    # ── Observe ───────────────────────────────────────────────────────────

    class ObserveRequest(BaseModel):
        image_b64: str       # Base64-encoded JPEG
        mime_type: str = "image/jpeg"

    async def _decode_and_run(image_b64: str) -> dict:
        """Shared logic: decode base64 frame, run detection, return result."""
        # iPhone Shortcuts sometimes prepends a data-URI prefix — strip it
        if "," in image_b64 and image_b64.startswith("data:"):
            image_b64 = image_b64.split(",", 1)[1]

        # Remove any whitespace/newlines that can sneak in
        image_b64 = image_b64.strip()

        if len(image_b64) < 100:
            raise HTTPException(status_code=400, detail="Image data too small")

        try:
            img_bytes = base64.b64decode(image_b64)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 data")

        arr = np.frombuffer(img_bytes, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)

        if frame is None:
            raise HTTPException(status_code=400, detail="Could not decode image — make sure it is a JPEG")

        count = engine.observe_frame(frame)
        total = engine.store.object_count()

        # Fire the detection callback so main.py can print to console
        if on_detections and count > 0:
            recent = engine.store.all_current()
            labels = [r.label for r in sorted(recent, key=lambda r: r.last_seen, reverse=True)][:count]
            try:
                on_detections(labels, total)
            except Exception:
                pass  # never let a callback crash the API

        return {"status": "ok", "detections": count, "total_objects": total}

    @app.post("/observe", tags=["Vision"])
    async def observe(request: Request):
        """
        Submit a single frame for object detection and memory update.

        Accepts two content types so iPhone Shortcuts works out of the box:
          • application/json      → { "image_b64": "<base64 JPEG>" }
          • application/x-www-form-urlencoded or multipart/form-data
                                  → image_b64=<base64 JPEG>
        """
        content_type = request.headers.get("content-type", "")

        try:
            if "application/json" in content_type:
                body = await request.json()
                image_b64 = body.get("image_b64", "")
            else:
                # Form data (application/x-www-form-urlencoded or multipart)
                form = await request.form()
                image_b64 = form.get("image_b64", "")

            if not image_b64:
                raise HTTPException(status_code=400, detail="Missing image_b64 field")

            return await _decode_and_run(str(image_b64))

        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Observe error: {exc}")
            raise HTTPException(status_code=500, detail=f"Processing error: {str(exc)}")

    # ── Memory management ─────────────────────────────────────────────────

    @app.delete("/memory", tags=["Memory"])
    async def clear_memory():
        """Wipe the entire memory store."""
        engine.store.clear()
        return {"status": "cleared"}

    @app.post("/memory/merge", tags=["Memory"])
    async def merge_memory():
        """Trigger a duplicate-merge pass over the memory store."""
        removed = engine.store.run_merge_pass()
        return {"removed_duplicates": removed, "total_objects": engine.store.object_count()}

    # ── WebSocket live feed ────────────────────────────────────────────────

    @app.websocket("/ws/live")
    async def websocket_live(websocket: WebSocket):
        """
        Live object feed — pushes the current memory state every second.
        Client receives JSON: { "objects": [...], "count": N }
        """
        await manager.connect(websocket)
        try:
            while True:
                records = engine.store.all_current()
                payload = {
                    "objects": [r.to_dict() for r in records],
                    "count": len(records),
                }
                await websocket.send_text(json.dumps(payload, default=str))
                await asyncio.sleep(1.0)
        except WebSocketDisconnect:
            manager.disconnect(websocket)
            logger.info("WebSocket client disconnected.")
        except Exception as exc:
            logger.error("WebSocket error: {}", exc)
            manager.disconnect(websocket)

    return app


# ── WebSocket connection manager ──────────────────────────────────────────

class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)
        logger.info("WebSocket connected. Active connections: {}", len(self.active))

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)