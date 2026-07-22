"""
Capa de conversación: Claude decide qué preguntar, cuándo pedir video,
y cuándo llamar a Odoo (catálogo, ticket de helpdesk, oportunidad CRM,
cotización) usando tool use.
"""

import base64
import json
import logging
import os
import traceback
from datetime import datetime

from anthropic import Anthropic

from catalog import format_catalog_for_prompt
from odoo_client import odoo

logger = logging.getLogger("whatsapp_scooter_mvp")

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = f"""Eres el agente de servicio a cliente por WhatsApp de una tienda de \
scooters eléctricos.

Reglas:
0. Antes de crear cualquier ticket, oportunidad o cotización, asegúrate de tener al \
menos el nombre del cliente. Si no te lo ha dado, pídelo primero (aunque sea solo el \
nombre, no hace falta apellido).
1. Refacciones/garantía o facturación: recopila nombre completo, modelo del scooter, \
fecha de compra aproximada, dónde lo compró (canal_compra: tienda Instigo directo, \
Amazon, MercadoLibre, Walmart, Liverpool, Suburbia, u otro), folio/número de orden si \
lo tiene a la mano (si no lo tiene, sigue adelante sin insistir), y descripción del \
problema o solicitud. Si es un caso de Refacciones y Garantías, pregunta también en \
qué categoría cae la falla (batería, motor/tracción, frenos, llantas, \
electrónica/pantalla, estructura/plegado, u otro) y si el cliente puede seguir usando \
el scooter o quedó inservible — esto lo puedes ir sacando con 1-2 preguntas naturales \
dentro de la conversación, no como formulario. Espera a que el cliente confirme que \
ya adjuntó el video si se lo pediste (verás un mensaje tipo "[video adjunto: ...]") \
antes de crear el ticket. Cuando tengas todo, crea el ticket con \
create_helpdesk_ticket (team_name: "Refacciones y Garantías" o "Facturación").
1c. REGLA DURA sobre el video, sin excepciones: CADA VEZ que llames a request_video \
-- ya sea la primera vez o como recordatorio si el cliente aún no lo ha mandado -- tu \
mensaje de texto en ESE MISMO turno debe seguir esta estructura fija, sin importar qué \
tan corta o casual haya sido la respuesta del cliente:
"Para tener más claridad de [problema/falla concreta que mencionó el cliente], ¿nos \
podrías compartir un video mostrando [qué grabar específicamente]?"
Completa los corchetes con el caso real, guiándote por la categoría de falla para qué \
grabar:
   - Batería: encendiendo el scooter, mostrando qué hace la pantalla/luces al prender.
   - Motor/tracción: el scooter en movimiento (o intentando avanzar), para escuchar el \
ruido y ver si arranca parejo o se traba.
   - Frenos: frenando a baja velocidad, de perfil, para ver si la rueda se detiene y \
escuchar si truena.
   - Llantas: acercamiento a la llanta/rin mostrando el daño, girando la rueda a mano.
   - Electrónica/pantalla: la pantalla encendida mostrando el error o comportamiento \
raro.
   - Estructura/plegado: abriendo y plegando el scooter mostrando dónde truena o no \
cierra bien.
   - Otro/no está seguro: el scooter en uso normal, mostrando el momento exacto en \
que ocurre la falla.
PROHIBIDO terminantemente: llamar a request_video con un mensaje que solo diga cosas \
como "quedo al pendiente del video", "en cuanto lo tengas", "te espero con el video" \
o cualquier variante sin la pregunta explícita de qué grabar -- esas frases pueden ir \
como cierre amable DESPUÉS de la pregunta explícita, nunca reemplazándola. Esto aplica \
igual si es un recordatorio porque el cliente no ha respondido o dijo algo como "nada": \
vuelve a poner la pregunta completa, no solo un recordatorio genérico.
2. Información de producto: usa search_products antes de responder precio, nunca \
inventes datos. No menciones la existencia/stock (qty_available) al cliente por \
iniciativa propia — es un dato interno. Solo úsalo para revisar, en silencio, que \
alcance para la cantidad que pide antes de cotizar: si no alcanza, dile que esa \
cantidad no está disponible ahora mismo y ofrece la cantidad máxima que sí hay o \
avisar cuando haya más stock. Si el cliente muestra interés real de compra, crea una \
oportunidad con create_crm_opportunity. Si además pide cotización formal (y hay \
suficiente stock), primero pídele su correo (explícale que ahí le llegará la \
cotización en PDF), y luego usa create_quotation con el product_id que devolvió \
search_products, el email, y el opportunity_id de la oportunidad que acabas de crear \
(o de una ya creada en esta conversación) — toda cotización debe quedar ligada a una \
oportunidad. La cotización se manda por correo automáticamente al llamar la \
herramienta (usa la acción estándar de Odoo, con su reporte oficial en PDF); tú solo \
confírmale al cliente que ya se la enviaste a su correo.
2b. Si el cliente no sabe qué modelo quiere (dice cosas como "no sé cuál me conviene", \
"quiero uno pero no sé cuál", o simplemente pregunta qué scooters tienes), NO le \
avientes la lista completa de una vez. Actúa como lo haría un vendedor en piso: \
pregúntale de forma natural y de a una pregunta a la vez cosas como para qué lo va a \
usar (trayecto diario, paseo, trabajo/reparto), qué distancia suele recorrer, en qué \
tipo de terreno (calles pavimentadas, terracería, baches), y si le importa más la \
velocidad o la comodidad/autonomía. Con esas respuestas, usa la tabla de modelos de \
abajo para razonar y recomendar 1-2 opciones que mejor encajen, explicando en una o \
dos frases por qué (ej. "por la distancia que recorres y que es más terracería, te \
recomendaría el Rush o el Monster 2.0..."). Nunca muestres specs técnicas en bruto \
(watts, voltajes) al cliente — tradúcelo a experiencia (velocidad, autonomía, tipo de \
terreno). Después de recomendar, usa search_products con el nombre del modelo \
recomendado para confirmar precio/existencia real antes de seguir con la cotización.
3. Sé breve y natural, como una conversación real de WhatsApp, en español. Una \
pregunta a la vez.
4. Si una herramienta regresa un campo "error", explícale al cliente en términos \
sencillos que hubo un problema técnico y ofrece intentar de nuevo o escalarlo con el \
equipo, en vez de quedarte callado.

Catálogo vigente de modelos (para razonar recomendaciones, NO para copiar/pegar tal \
cual al cliente):
{format_catalog_for_prompt()}
"""

TOOLS = [
    {
        "name": "search_products",
        "description": "Busca modelos de scooter en el catálogo de Odoo por nombre o palabra clave.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "request_video",
        "description": "Solo activa el botón de adjuntar video en el chat -- NO le dice nada al "
        "cliente por sí sola. SIEMPRE que llames esta herramienta (primera vez o recordatorio), tu "
        "mensaje de texto de este mismo turno debe incluir la pregunta explícita 'Para tener más "
        "claridad de [problema], ¿nos podrías compartir un video mostrando [qué grabar]?' -- ver "
        "regla 1c del system prompt. PROHIBIDO llamarla después de un mensaje que solo diga cosas "
        "como 'quedo al pendiente del video' sin la pregunta explícita de qué grabar.",
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    },
    {
        "name": "create_helpdesk_ticket",
        "description": "Crea un ticket en Odoo Helpdesk con la info recopilada del cliente. La "
        "transcripción completa de la conversación se adjunta automáticamente, no hace falta "
        "incluirla en 'description'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "team_name": {"type": "string", "enum": ["Refacciones y Garantías", "Facturación"]},
                "name": {"type": "string", "description": "Título corto del ticket"},
                "description": {"type": "string", "description": "Resumen del problema o solicitud"},
                "partner_name": {"type": "string"},
                "partner_phone": {"type": "string"},
                "modelo_scooter": {"type": "string", "description": "Modelo que dijo el cliente"},
                "fecha_compra": {
                    "type": "string",
                    "description": "Fecha de compra tal como la dio el cliente (puede ser aproximada)",
                },
                "canal_compra": {
                    "type": "string",
                    "enum": [
                        "Tienda Instigo (directo)",
                        "Amazon",
                        "MercadoLibre",
                        "Walmart",
                        "Liverpool",
                        "Suburbia",
                        "Otro",
                        "No especificado",
                    ],
                },
                "folio_orden": {
                    "type": "string",
                    "description": "Folio/número de orden si lo tiene, o 'no proporcionado'",
                },
                "categoria_falla": {
                    "type": "string",
                    "description": "Solo para Refacciones y Garantías; omitir en Facturación",
                    "enum": [
                        "Batería",
                        "Motor/tracción",
                        "Frenos",
                        "Llantas",
                        "Electrónica/pantalla",
                        "Estructura/plegado",
                        "Otro",
                        "N/A",
                    ],
                },
                "scooter_utilizable": {
                    "type": "boolean",
                    "description": "true si el cliente puede seguir usando el scooter pese a la falla",
                },
            },
            "required": [
                "team_name",
                "name",
                "description",
                "partner_name",
                "partner_phone",
                "modelo_scooter",
                "fecha_compra",
                "canal_compra",
            ],
        },
    },
    {
        "name": "create_crm_opportunity",
        "description": "Crea una oportunidad en el CRM de Odoo para un cliente interesado en un "
        "producto. La transcripción completa de la conversación se adjunta automáticamente, no "
        "hace falta incluirla en 'description'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "contact_name": {"type": "string"},
                "phone": {"type": "string"},
                "description": {"type": "string", "description": "Resumen del interés del cliente"},
            },
            "required": ["name", "contact_name", "phone", "description"],
        },
    },
    {
        "name": "create_quotation",
        "description": "Genera una cotización (sale order) vinculada a un producto y a una "
        "oportunidad de CRM, y la manda por correo al cliente usando la acción estándar de "
        "Odoo (reporte oficial en PDF adjunto). Requiere el correo del cliente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "partner_name": {"type": "string"},
                "phone": {"type": "string"},
                "email": {"type": "string", "description": "Correo del cliente para enviarle el PDF"},
                "product_id": {"type": "integer"},
                "qty": {"type": "number"},
                "opportunity_id": {
                    "type": "integer",
                    "description": "ID de la oportunidad de CRM a la que se liga esta cotización",
                },
            },
            "required": ["partner_name", "phone", "email", "product_id", "qty", "opportunity_id"],
        },
    },
]


def build_transcript(history):
    """Arma un transcript legible (texto plano, con encabezado y una línea
    en blanco entre cada intervención) a partir del historial de la
    conversación, ignorando los bloques de tool use / tool result."""
    lines = [
        "Transcripción de la conversación de WhatsApp",
        f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "-" * 50,
        "",
    ]
    for msg in history:
        role = msg["role"]
        content = msg["content"]
        if role == "user" and isinstance(content, str):
            lines.append(f"Cliente: {content}")
            lines.append("")
        elif role == "assistant":
            for block in content:
                if getattr(block, "type", None) == "text" and block.text.strip():
                    lines.append(f"Agente: {block.text}")
                    lines.append("")
    return "\n".join(lines)


def sync_transcript(session):
    """Mantiene actualizado el .txt de transcript adjunto en Odoo. Se llama
    al final de CADA turno (no solo cuando se crea el ticket/oportunidad),
    así que si la conversación sigue después de generar el registro, el
    archivo adjunto se va reescribiendo con la versión completa hasta ese
    momento en vez de quedarse congelado con la conversación a medias."""
    targets = session.get("transcript_targets")
    if not targets:
        return
    transcript = build_transcript(session["history"])
    data_b64 = base64.b64encode(transcript.encode("utf-8")).decode("ascii")
    attachment_ids = session.setdefault("transcript_attachment_ids", {})
    for res_model, res_id in targets.items():
        att_id = attachment_ids.get(res_model)
        if att_id:
            odoo.update_attachment(att_id, data_b64)
        else:
            attachment_ids[res_model] = odoo.create_attachment(
                res_model, res_id, "transcripcion_whatsapp.txt", data_b64
            )


def run_tool(tool_name, tool_input, session):
    if tool_name == "search_products":
        return odoo.search_products(tool_input["query"])

    if tool_name == "request_video":
        return {"ok": True}

    if tool_name == "create_helpdesk_ticket":
        vals = dict(tool_input)
        modelo = vals.pop("modelo_scooter", None)
        fecha_compra = vals.pop("fecha_compra", None)
        canal_compra = vals.pop("canal_compra", None)
        folio_orden = vals.pop("folio_orden", None)
        categoria_falla = vals.pop("categoria_falla", None)
        scooter_utilizable = vals.pop("scooter_utilizable", None)

        if scooter_utilizable is None:
            utilizable_txt = "no especificado"
        else:
            utilizable_txt = "sí" if scooter_utilizable else "no, quedó inservible"

        vals["description"] = (
            f"Cliente: {vals.get('partner_name') or '(sin nombre)'}\n"
            f"Teléfono: {vals.get('partner_phone') or '(sin teléfono)'}\n"
            f"Modelo: {modelo or '(sin especificar)'}\n"
            f"Fecha de compra: {fecha_compra or '(sin especificar)'}\n"
            f"Canal de compra: {canal_compra or 'No especificado'}\n"
            f"Folio/orden: {folio_orden or 'no proporcionado'}\n"
            f"Categoría de falla: {categoria_falla or 'N/A'}\n"
            f"¿Scooter utilizable?: {utilizable_txt}\n\n"
            f"{vals['description']}\n\n"
            "(la transcripción completa de la conversación queda adjunta como archivo .txt)"
        )
        ticket_id = odoo.create_helpdesk_ticket(**vals)
        session.setdefault("transcript_targets", {})["helpdesk.ticket"] = ticket_id
        video = session.get("pending_video")
        if video:
            odoo.create_attachment(
                "helpdesk.ticket", ticket_id, video["filename"], video["data_b64"]
            )
            session["pending_video"] = None
        return {"ticket_id": ticket_id}

    if tool_name == "create_crm_opportunity":
        vals = dict(tool_input)
        vals["description"] = (
            f"Cliente: {vals.get('contact_name') or '(sin nombre)'}\n"
            f"Teléfono: {vals.get('phone') or '(sin teléfono)'}\n\n"
            f"{vals['description']}\n\n"
            "(la transcripción completa de la conversación queda adjunta como archivo .txt)"
        )
        opportunity_id = odoo.create_crm_opportunity(**vals)
        session.setdefault("transcript_targets", {})["crm.lead"] = opportunity_id
        session["last_opportunity_id"] = opportunity_id
        return {"opportunity_id": opportunity_id}

    if tool_name == "create_quotation":
        vals = dict(tool_input)
        email = vals.pop("email")
        order_id = odoo.create_quotation(**vals)
        odoo.send_quotation_email(order_id, email)
        return {"quotation_id": order_id, "email_sent_to": email}

    return {"error": f"unknown tool {tool_name}"}


def run_turn(session, user_message):
    """Corre un turno completo (incluyendo el loop de tool use) y regresa el
    texto que se le debe mostrar al cliente. Muta `session` in-place.
    `session` trae: history, ui_flags, pending_video."""
    history = session["history"]
    ui_flags = session["ui_flags"]
    history.append({"role": "user", "content": user_message})
    ui_flags["request_video"] = False

    reply = "Se me complicó procesar eso, ¿puedes reformular tu mensaje?"

    for _ in range(6):  # tope de seguridad contra loops infinitos de tools
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=history,
        )
        history.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            reply = "".join(b.text for b in response.content if b.type == "text")
            break

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            try:
                result = run_tool(block.name, block.input, session)
            except Exception as e:
                # Nunca dejamos que un error de Odoo/red tumbe el turno sin
                # respuesta: se lo pasamos a Claude como error para que le
                # explique al cliente qué pasó, en vez de quedarse "atorado".
                # Pero SÍ dejamos rastro completo en los logs (Render >
                # Logs) para poder diagnosticar qué falló de verdad.
                logger.error(
                    "Fallo en tool '%s' con input %s:\n%s",
                    block.name,
                    block.input,
                    traceback.format_exc(),
                )
                result = {"error": f"{type(e).__name__}: {e}"}
            if block.name == "request_video":
                ui_flags["request_video"] = True
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
        history.append({"role": "user", "content": tool_results})

    # Se llama siempre al final del turno (no solo cuando se creó el
    # ticket/oportunidad) para que el archivo adjunto refleje la
    # conversación completa aunque siga después de crear el registro.
    sync_transcript(session)
    return reply
