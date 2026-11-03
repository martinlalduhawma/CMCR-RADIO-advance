import json
from typing import Dict, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI()

# Mount static folder
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def get_index():
    return FileResponse("static/index.html")


class ChannelManager:
    def __init__(self):
        # socket: user_name
        self.active_users: Dict[WebSocket, str] = {}
        # User currently holding the PTT floor
        self.active_speaker: Optional[WebSocket] = None
        self.active_speaker_name: Optional[str] = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()

    def register_user(self, websocket: WebSocket, name: str):
        self.active_users[websocket] = name

    async def disconnect(self, websocket: WebSocket):
        if websocket in self.active_users:
            del self.active_users[websocket]

        if self.active_speaker == websocket:
            self.active_speaker = None
            self.active_speaker_name = None
            await self.broadcast_status("idle", None)

        await self.broadcast_user_count()

    async def broadcast_status(self, state: str, speaker_name: Optional[str]):
        """state can be 'idle' or 'busy'"""
        payload = json.dumps({
            "type": "channel_status",
            "state": state,
            "speaker": speaker_name
        })
        for ws in list(self.active_users.keys()):
            try:
                await ws.send_text(payload)
            except Exception:
                pass

    async def broadcast_user_count(self):
        payload = json.dumps({
            "type": "user_count",
            "count": len(self.active_users)
        })
        for ws in list(self.active_users.keys()):
            try:
                await ws.send_text(payload)
            except Exception:
                pass

    async def broadcast_audio(self, sender: WebSocket, pcm_bytes: bytes):
        for ws in list(self.active_users.keys()):
            if ws != sender:
                try:
                    await ws.send_bytes(pcm_bytes)
                except Exception:
                    pass


manager = ChannelManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            message = await websocket.receive()
            
            # Text frames handling (signaling, control commands)
            if "text" in message:
                data = json.loads(message["text"])
                msg_type = data.get("type")

                if msg_type == "join":
                    username = data.get("name", "Motor Driver")
                    manager.register_user(websocket, username)
                    await manager.broadcast_user_count()
                    
                    # Current channel status thawn nghal
                    curr_state = "busy" if manager.active_speaker else "idle"
                    await websocket.send_text(json.dumps({
                        "type": "channel_status",
                        "state": curr_state,
                        "speaker": manager.active_speaker_name
                    }))

                elif msg_type == "request_floor":
                    # Mi dangin an lo hmeh meuh loh chuan floor pe rawh
                    if manager.active_speaker is None:
                        manager.active_speaker = websocket
                        manager.active_speaker_name = manager.active_users.get(websocket, "Driver")
                        await websocket.send_text(json.dumps({"type": "floor_granted"}))
                        await manager.broadcast_status("busy", manager.active_speaker_name)
                    else:
                        await websocket.send_text(json.dumps({"type": "floor_denied"}))

                elif msg_type == "release_floor":
                    if manager.active_speaker == websocket:
                        manager.active_speaker = None
                        manager.active_speaker_name = None
                        await manager.broadcast_status("idle", None)

            # Audio binary frames handling
            elif "bytes" in message:
                # Floor chelh tu chauhin audio a broadcast thei
                if manager.active_speaker == websocket:
                    await manager.broadcast_audio(websocket, message["bytes"])

    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception:
        await manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    # .py dah tel loh tur
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)