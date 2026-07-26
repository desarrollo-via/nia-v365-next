"""Review Lab local: fixture y HTML puro, sin FastAPI ni recursos externos."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape
import json

from .audit import AuditEventView, build_audit_event_view
from .event_parser import parse_webhook_form
from .idempotency import build_event_key
from .modes import ConnectorMode
from .models import ConnectorEventRecord
from .nia_client import NiaChatResponse
from .output_review import build_output_review
from .preflight import build_text_preflight
from .security import redact_form_data
from .workflow_policy import WorkflowGuard


DEMO_RECEIVED_AT = datetime(2026, 7, 21, 15, 0, tzinfo=timezone.utc)


def build_simulated_review_lab_view() -> AuditEventView:
    """Crea una conversación ficticia recorriendo los modelos productivos."""

    form = {
        "event": "ONIMBOTV2MESSAGEADD",
        "data[bot][id]": "456",
        "data[message][id]": "9001",
        "data[message][chatId]": "73",
        "data[message][authorId]": "27",
        "data[message][text]": (
            "  Necesito una bomba centrífuga para agua limpia, 10 HP.  "
        ),
        "data[message][isSystem]": "0",
        "data[chat][dialogId]": "chat-controlado-001",
        "data[chat][type]": "openChannel",
        "data[chat][entityType]": "LINES",
        "data[user][id]": "27",
        "data[user][bot]": "0",
        "data[user][connector]": "1",
        "auth[domain]": "demo.bitrix24.invalid",
        "auth[member_id]": "member-demo",
        "auth[application_token]": "fixture-secret-never-display",
    }
    event = parse_webhook_form(form)
    record = ConnectorEventRecord(
        event_key=build_event_key(event),
        received_at=DEMO_RECEIVED_AT,
        updated_at=DEMO_RECEIVED_AT,
        normalized_event=event.model_dump(mode="python"),
        raw_redacted=redact_form_data(form),
        identity_verified=True,
        security_reason="fixture_identity_verified",
        workflow_guard=WorkflowGuard.from_mode(ConnectorMode.SHADOW),
    )
    preflight = build_text_preflight(record)
    response = NiaChatResponse(
        respuesta=(
            "Para recomendar la bomba correcta, ¿qué caudal y altura "
            "dinámica total necesitas?"
        ),
        etapa="descubrimiento",
        items_resultado=[],
        cliente={"kind": "fixture", "id": "contacto-controlado"},
    )
    output = build_output_review(record, response)
    guard = WorkflowGuard.from_mode(ConnectorMode.SHADOW)
    return build_audit_event_view(
        title="Chat controlado · bomba centrífuga",
        received_at=DEMO_RECEIVED_AT,
        updated_at=DEMO_RECEIVED_AT + timedelta(seconds=2),
        preflight=preflight,
        output=output,
        guard=guard,
    )


def _json_panel(value: object) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return escape(json.dumps(value, ensure_ascii=False, indent=2))


def render_review_lab_html(view: AuditEventView) -> str:
    """Renderiza una página autocontenida, sin scripts ni recursos remotos."""

    timeline = "".join(
        f"<li><span>{escape(item.stage)}</span><b>{escape(item.status)}</b>"
        f"<p>{escape(item.detail)}</p></li>"
        for item in view.timeline
    )
    safety = view.safety
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>NIA · Review Lab</title>
  <style>
    :root {{ color-scheme: dark; --bg:#071019; --panel:#101d29; --line:#263746;
      --text:#e8f0f7; --muted:#92a7b8; --safe:#59d49a; --warn:#ffc857;
      --accent:#62a8ff; --danger:#ff7b7b; }}
    * {{ box-sizing:border-box }} body {{ margin:0; font:15px/1.5 Inter,Segoe UI,sans-serif;
      background:radial-gradient(circle at 15% 0,#17304a 0,transparent 36%),var(--bg);
      color:var(--text) }} main {{ max-width:1180px; margin:auto; padding:32px 20px 64px }}
    header {{ display:flex; justify-content:space-between; gap:20px; align-items:end; margin-bottom:22px }}
    h1 {{ margin:0; font-size:clamp(28px,5vw,48px); letter-spacing:-.04em }}
    h2 {{ font-size:17px; margin:0 0 14px }} .eyebrow {{ color:var(--accent); font-weight:700;
      letter-spacing:.12em; text-transform:uppercase }} .banner {{ padding:14px 18px; border:1px solid #8f7427;
      background:#2c260f; color:#ffe49b; border-radius:12px; font-weight:800; text-align:center }}
    .badges {{ display:flex; flex-wrap:wrap; gap:8px; margin:18px 0 }} .badge {{ border:1px solid var(--line);
      border-radius:999px; padding:6px 10px; background:#0b1721 }} .safe {{ color:var(--safe) }}
    .warn {{ color:var(--warn) }} .grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr));
      gap:16px }} .panel {{ border:1px solid var(--line); border-radius:16px; padding:18px;
      background:color-mix(in srgb,var(--panel) 94%,transparent); box-shadow:0 16px 40px #0003 }}
    .wide {{ grid-column:1/-1 }} .chat {{ display:grid; gap:12px }} .bubble {{ max-width:78%;
      padding:13px 15px; border-radius:16px; background:#18324a }} .nia {{ justify-self:end; background:#173c31 }}
    .bubble small {{ display:block; color:var(--muted); margin-bottom:5px }} pre {{ margin:0; padding:14px;
      border-radius:10px; background:#07111a; overflow:auto; max-height:360px; color:#c9def0; font:12px/1.55 Consolas,monospace }}
    ol {{ list-style:none; padding:0; margin:0; display:grid; grid-template-columns:repeat(4,1fr); gap:10px }}
    li {{ border-top:3px solid var(--accent); padding:10px; background:#0a1620; border-radius:8px }}
    li span {{ color:var(--muted); text-transform:uppercase; font-size:11px }} li b {{ display:block }} li p {{ margin:7px 0 0 }}
    button {{ padding:10px 14px; border-radius:9px; border:1px solid var(--line); margin-right:8px }}
    button:disabled {{ color:#788895; background:#111a22; cursor:not-allowed }} .hash {{ word-break:break-all;
      color:var(--muted); font:12px Consolas,monospace }} footer {{ color:var(--muted); margin-top:20px; text-align:center }}
    @media (max-width:760px) {{ header {{ display:block }} .grid {{ grid-template-columns:1fr }}
      .wide {{ grid-column:auto }} ol {{ grid-template-columns:1fr }} .bubble {{ max-width:94% }} }}
  </style>
</head>
<body data-simulation="true">
<main>
  <header><div><div class="eyebrow">bitrix_connector</div><h1>Review Lab</h1>
    <div>{escape(view.title)}</div></div><div class="badge warn">Escenario: SHADOW</div></header>
  <div class="banner">SIMULACIÓN LOCAL · MODO REAL OFF · SIN CONEXIONES EXTERNAS</div>
  <div class="badges"><span class="badge safe">activation_locked = true</span>
    <span class="badge safe">external_calls_enabled = false</span>
    <span class="badge safe">Bitrix escritos = 0</span>
    <span class="badge">Estado simulado: {escape(view.status)}</span></div>
  <section class="panel wide"><h2>Recorrido del evento</h2><ol>{timeline}</ol></section>
  <div class="grid" style="margin-top:16px">
    <section class="panel wide"><h2>Conversación visible</h2><div class="chat">
      <div class="bubble"><small>Cliente · mensaje normalizado</small>{escape(view.normalized_message.text)}</div>
      <div class="bubble nia"><small>NIA · respuesta del doble local</small>{escape(view.nia_response.respuesta)}</div>
    </div></section>
    <section class="panel"><h2>1. Evento original redactado</h2><pre>{_json_panel(view.original_event_redacted)}</pre></section>
    <section class="panel"><h2>2. Mensaje normalizado</h2><pre>{_json_panel(view.normalized_message)}</pre></section>
    <section class="panel"><h2>3. Manifiesto de adjuntos</h2><pre>{_json_panel(view.attachment_manifest)}</pre></section>
    <section class="panel"><h2>4. Payload exacto para NIA</h2><pre>{_json_panel(view.nia_payload)}</pre>
      <p class="hash">SHA-256: {escape(view.input_content_hash)}</p></section>
    <section class="panel"><h2>5. Respuesta exacta de NIA</h2><pre>{_json_panel(view.nia_response)}</pre></section>
    <section class="panel"><h2>6. Salida exacta hacia Bitrix</h2><pre>{_json_panel(view.bitrix_payload_preview)}</pre>
      <p class="hash">SHA-256: {escape(view.output_content_hash)}</p></section>
    <section class="panel"><h2>Guard operativo</h2><pre>{_json_panel(view.workflow_guard)}</pre></section>
    <section class="panel"><h2>Resultado shadow</h2><pre>{_json_panel(view.shadow_result)}</pre></section>
    <section class="panel wide"><h2>Acciones de revisión</h2>
      <button disabled>Aprobar entrada</button><button disabled>Rechazar entrada</button>
      <button disabled>Aprobar salida</button><button disabled>Enviar a Bitrix</button>
      <p class="warn">Deshabilitadas: esta vista no contiene rutas de escritura.</p></section>
  </div>
  <footer>Evento {escape(view.event_key)} · fixture local · ninguna llamada real</footer>
</main>
</body>
</html>"""


def build_simulated_review_lab_html() -> str:
    return render_review_lab_html(build_simulated_review_lab_view())
