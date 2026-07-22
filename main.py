"""
Backend del MVP: sirve el chat falso (static/) y el endpoint que orquesta
la conversación con Claude + Odoo.

Correr local:
  uvicorn main:app --reload

Desplegar en Render:
  build command: pip install -r requirements.txt
  start command: uvicorn main:app --host 0.0.0.0 --port $PORT
"""

import base64
import logging
import traceback
import uuid
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from claude_agent import run_turn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("whatsapp_scooter_mvp")

app = FastAPI(title="WhatsApp scooter MVP")

# Estado de sesión en memoria. Suficiente para el MVP (un solo proceso).
# Si Render reinicia el dyno se pierde el historial, es esperado en esta fase.
SESSIONS: dict[str, dict] = {}


def get_session(session_id: str) -> dict:
    return SESSIONS.setdefault(
        session_id, {"history": [], "ui_flags": {}, "pending_video": None}
    )


class ChatIn(BaseModel):
    session_id: Optional[str] = None
    message: str


class ChatOut(BaseModel):
    session_id: str
    reply: str
    request_video: bool


@app.post("/api/chat", response_model=ChatOut)
def chat(payload: ChatIn):
    session_id = payload.session_id or str(uuid.uuid4())
    session = get_session(session_id)

    try:
        reply = run_turn(session, payload.message)
    except Exception as e:
        # Red o Claude caídos, etc. Nunca dejamos la conversación sin
        # respuesta -- eso es lo que se sentía como "quedarse atorado".
        # El detalle completo sí queda en los logs de Render para diagnosticar.
        logger.error("Fallo en run_turn:\n%s", traceback.format_exc())
        reply = f"Ups, algo falló de mi lado ({type(e).__name__}). ¿Puedes intentar de nuevo?"

    return ChatOut(
        session_id=session_id,
        reply=reply,
        request_video=session["ui_flags"].get("request_video", False),
    )


@app.post("/api/upload")
async def upload(session_id: str = Form(...), file: UploadFile = File(...)):
    """Sube el archivo de video del cliente. Se guarda en la sesión en
    memoria (base64) y se adjunta al ticket de Helpdesk en cuanto se crea.
    Para producción real conviene mover esto a un storage externo en vez
    de tenerlo en memoria del proceso."""
    session = get_session(session_id)
    data = await file.read()
    session["pending_video"] = {
        "filename": file.filename,
        "data_b64": base64.b64encode(data).decode("ascii"),
    }
    return {"ok": True, "filename": file.filename, "size": len(data)}


@app.post("/api/reset")
def reset(session_id: str):
    SESSIONS.pop(session_id, None)
    return {"ok": True}


# El chat falso vive en static/index.html y se sirve directo desde aquí.
app.mount("/", StaticFiles(directory="static", html=True), name="static")
