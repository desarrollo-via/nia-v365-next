"""Fábrica same-origin aislada para el Review Lab administrativo.

No se importa desde ``router.py`` ni ``main.py``. Todas las dependencias que
podrían decidir o autenticar se reciben ya construidas.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from typing import Awaitable, Callable, Literal, Optional, Protocol
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from .review_approval import ReviewDecisionAction, ReviewPrincipal
from .review_admin_session import (
    InMemoryReviewAdminSessionStore,
    ReviewAdminSessionOutcome,
    SESSION_COOKIE_NAME,
)
from .review_lab_decision_adapter import ReviewLabDecisionResult
from .review_lab_adapter import ReviewLabSnapshot


CSRF_HEADER = "X-CSRF-Token"
SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "Content-Security-Policy": (
        "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
        "form-action 'self'; object-src 'none'; script-src 'self'; "
        "style-src 'self'; connect-src 'self'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": (
        "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    ),
}

_CONFIRMATIONS = {
    ReviewDecisionAction.APPROVE_INPUT: "APROBAR ENVIO A NIA",
    ReviewDecisionAction.REJECT_INPUT: "RECHAZAR ENTRADA",
    ReviewDecisionAction.APPROVE_OUTPUT: "APROBAR ENVIO A BITRIX",
    ReviewDecisionAction.REJECT_OUTPUT: "RECHAZAR SALIDA",
}

_HTML_SHELL = """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>NIA · Review Admin</title>
  <link rel="stylesheet" href="./assets/review-admin.css">
</head>
<body>
  <main>
    <header><div><p class="eyebrow">BITRIX_CONNECTOR</p><h1>Review Admin</h1>
      <p>Revisión humana same-origin · credenciales objetivo solo en servidor.</p></div>
      <span id="session-state" class="badge">Sesión no iniciada</span></header>
    <div id="safety-state" class="banner">Consultando barreras reales…</div>
    <section id="login-panel" class="panel narrow">
      <h2>Acceso controlado</h2>
      <p>Introduce el código bootstrap efímero. No se conservará en el navegador.</p>
      <form id="login-form">
        <label for="bootstrap-code">Código bootstrap</label>
        <div class="login-row"><input id="bootstrap-code" name="credential"
          type="password" minlength="32" maxlength="4096" autocomplete="one-time-code"
          required><button type="submit">Iniciar sesión</button></div>
      </form>
      <p id="login-message" class="muted" aria-live="polite">Código de un solo uso · cinco minutos.</p>
    </section>
    <section id="review-panel" class="panel" hidden>
      <div class="toolbar"><div><h2>Eventos para revisión</h2>
        <p id="review-banner" class="muted"></p></div>
        <div><select id="event-selector" aria-label="Evento"></select>
          <button id="refresh-button" type="button">Actualizar</button>
          <button id="logout-button" type="button">Cerrar sesión</button></div></div>
      <div class="badges"><span class="badge safe">effective_mode = off</span>
        <span class="badge safe">activation_locked = true</span>
        <span class="badge safe">external_calls = false</span>
        <span class="badge warn">Acciones bloqueadas</span></div>
      <div id="conversation" class="conversation"></div>
      <div class="grid">
        <article><h3>1. Evento original redactado</h3><pre id="original-event"></pre></article>
        <article><h3>2. Mensaje normalizado</h3><pre id="normalized-message"></pre></article>
        <article><h3>3. Manifiesto de adjuntos</h3><pre id="attachment-manifest"></pre></article>
        <article><h3>4. Payload exacto para NIA</h3><pre id="nia-payload"></pre>
          <p id="input-hash" class="hash"></p></article>
        <article><h3>5. Respuesta exacta de NIA</h3><pre id="nia-response"></pre></article>
        <article><h3>6. Salida exacta hacia Bitrix</h3><pre id="bitrix-preview"></pre>
          <p id="output-hash" class="hash"></p></article>
      </div>
      <div class="actions"><button disabled>Aprobar entrada</button>
        <button disabled>Rechazar entrada</button><button disabled>Aprobar salida</button>
        <button disabled>Rechazar salida</button>
        <p>Deshabilitadas: el modo operativo real permanece bloqueado en off.</p></div>
    </section>
  </main>
  <script src="./assets/review-admin.js" defer></script>
</body>
</html>
"""

_CSS = """:root{color-scheme:dark;--bg:#06121c;--panel:#10212d;--line:#294252;
--text:#e8f2f8;--muted:#91a7b7;--blue:#58a6ff;--safe:#50d49b;--warn:#ffc857}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 15% 0,#183551,transparent 34%),var(--bg);
color:var(--text);font:15px/1.5 system-ui,sans-serif}main{max-width:1180px;margin:auto;padding:42px 22px 70px}
header,.toolbar,.login-row{display:flex;align-items:center;justify-content:space-between;gap:16px}
h1{font-size:42px;line-height:1;margin:5px 0 8px}h2{margin:0 0 8px}.eyebrow{color:var(--blue);
font-weight:800;letter-spacing:.13em;margin:0}.panel{margin:18px 0;padding:20px;background:var(--panel);
border:1px solid var(--line);border-radius:16px}.narrow{max-width:720px}.banner{padding:13px 16px;
border:1px solid #7c6424;background:#2b250e;color:#ffe298;border-radius:11px;font-weight:800;text-align:center}
.badge{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:6px 10px;background:#091923}
.safe{color:var(--safe)}.warn{color:var(--warn)}.muted{color:var(--muted)}label{display:block;margin:14px 0 6px}
input,select,button{font:inherit;border:1px solid var(--line);border-radius:9px;padding:10px 12px;background:#091923;color:var(--text)}
input{flex:1}button:not(:disabled){cursor:pointer;border-color:#3975aa}button:disabled{color:#778895;cursor:not-allowed}
.badges{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}.conversation{display:grid;gap:10px;margin:18px 0}
.bubble{max-width:78%;padding:13px 15px;border-radius:14px;background:#193751}.bubble.nia{justify-self:end;background:#164332}
.bubble small{display:block;color:var(--muted);margin-bottom:4px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
article{padding:16px;background:#0a1924;border:1px solid var(--line);border-radius:13px}h3{margin:0 0 10px;font-size:15px}
pre{margin:0;padding:12px;background:#06111a;border-radius:9px;overflow:auto;max-height:300px;font:12px/1.5 Consolas,monospace;color:#c9dff0}
.hash{word-break:break-all;color:var(--muted);font:11px Consolas,monospace}.actions{margin-top:16px;padding:16px;border:1px solid var(--line);border-radius:13px}
.actions p{color:var(--warn);margin-bottom:0}@media(max-width:760px){header,.toolbar,.login-row{align-items:stretch;flex-direction:column}.grid{grid-template-columns:1fr}.bubble{max-width:94%}}"""

_JS = """'use strict';
let csrfToken='';
const byId=id=>document.getElementById(id);
const pretty=value=>JSON.stringify(value==null?null:value,null,2);
function takeBootstrapFragment(){
  const fragment=window.location.hash;if(!fragment)return '';
  window.history.replaceState(null,'',window.location.pathname+window.location.search);
  const parameters=new URLSearchParams(fragment.slice(1));
  return parameters.get('nia-bootstrap')||'';
}
let fragmentBootstrap=takeBootstrapFragment();
async function jsonRequest(path,options={}){
  const {headers={},...requestOptions}=options;
  const response=await fetch(path,{credentials:'same-origin',...requestOptions,headers:{'Accept':'application/json',...headers}});
  let body={};try{body=await response.json();}catch(_error){body={code:'invalid_response'};}
  return {response,body};
}
async function loadState(){
  const response=await fetch('./state',{credentials:'same-origin',
    headers:{'Accept':'application/json'}});
  const state=await response.json();
  byId('safety-state').textContent=
    `Modo real: ${state.effective_mode}; locked: ${state.activation_locked}; `+
    `llamadas externas: ${state.external_calls_enabled}; decisiones: ${state.decisions_allowed}`;
}
function renderSnapshot(snapshot){
  byId('review-banner').textContent=`${snapshot.banner} · fuente ${snapshot.source} · solo lectura`;
  const selector=byId('event-selector');selector.replaceChildren();
  snapshot.events.items.forEach(item=>{const option=document.createElement('option');option.value=item.event_key;
    option.textContent=`${item.dialog_id||'sin diálogo'} · ${item.status}`;selector.append(option);});
  const detail=snapshot.selected;if(!detail)return;
  selector.value=detail.event_key;
  byId('original-event').textContent=pretty(detail.original_event_redacted);
  byId('normalized-message').textContent=pretty(detail.normalized_message);
  byId('attachment-manifest').textContent=pretty(detail.attachment_manifest);
  byId('nia-payload').textContent=pretty(detail.nia_payload);
  byId('input-hash').textContent=`SHA-256: ${detail.input_content_hash||'no disponible'}`;
  byId('nia-response').textContent=pretty(detail.nia_response);
  byId('bitrix-preview').textContent=pretty(detail.bitrix_payload_preview);
  byId('output-hash').textContent=`SHA-256: ${detail.output_content_hash||'no disponible'}`;
  const conversation=byId('conversation');conversation.replaceChildren();
  const pairs=[['Cliente · mensaje normalizado',detail.normalized_message&&detail.normalized_message.text,'bubble'],
    ['NIA Next · respuesta auditada',detail.nia_response&&detail.nia_response.respuesta,'bubble nia']];
  pairs.forEach(([label,text,className])=>{if(!text)return;const bubble=document.createElement('div');bubble.className=className;
    const small=document.createElement('small');small.textContent=label;bubble.append(small,document.createTextNode(text));conversation.append(bubble);});
}
async function loadReviews(eventKey=''){
  const path=eventKey?`./reviews/${eventKey}`:'./reviews';
  const {response,body}=await jsonRequest(path);
  if(!response.ok)throw new Error(body.code||'reviews_unavailable');
  renderSnapshot(body);byId('review-panel').hidden=false;byId('login-panel').hidden=true;
}
async function resumeSession(){
  const status=await jsonRequest('./session');if(!status.response.ok)return false;
  const rotated=await jsonRequest('./session/csrf',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
  if(!rotated.response.ok)return false;csrfToken=rotated.body.csrf_token;
  byId('session-state').textContent='Sesión administrativa activa';await loadReviews();return true;
}
async function loginWithCredential(credential){
  const result=await jsonRequest('./session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({credential})});
  if(!result.response.ok)return false;
  csrfToken=result.body.csrf_token;byId('session-state').textContent=`Sesión activa · ${result.body.actor}`;await loadReviews();
  return true;
}
async function consumeBootstrapFragment(){
  const credential=fragmentBootstrap;fragmentBootstrap='';
  if(credential.length<32)return false;
  byId('login-message').textContent='Iniciando sesión local automáticamente…';
  const authenticated=await loginWithCredential(credential);
  if(!authenticated)byId('login-message').textContent='Acceso automático no disponible.';
  return authenticated;
}
byId('login-form').addEventListener('submit',async event=>{event.preventDefault();const input=byId('bootstrap-code');
  byId('login-message').textContent='Validando código…';
  const authenticated=await loginWithCredential(input.value);
  input.value='';if(!authenticated){byId('login-message').textContent='Acceso no disponible o código inválido.';return;}
});
byId('refresh-button').addEventListener('click',()=>loadReviews(byId('event-selector').value).catch(()=>{}));
byId('event-selector').addEventListener('change',()=>loadReviews(byId('event-selector').value).catch(()=>{}));
byId('logout-button').addEventListener('click',async()=>{await jsonRequest('./session',{method:'DELETE',
  headers:{'Content-Type':'application/json','X-CSRF-Token':csrfToken},body:'{}'});
  csrfToken='';byId('review-panel').hidden=true;byId('login-panel').hidden=false;byId('session-state').textContent='Sesión cerrada';
});
loadState().then(async()=>{if(await resumeSession()){fragmentBootstrap='';return;}await consumeBootstrapFragment();})
  .catch(()=>{fragmentBootstrap='';byId('safety-state').textContent='Estado no disponible; las decisiones continúan bloqueadas.';});
"""


class ReviewAdminAuthenticationOutcome(str, Enum):
    AUTHENTICATED = "authenticated"
    UNAUTHORIZED = "unauthorized"
    UNAVAILABLE = "unavailable"


class ReviewAdminAuthenticationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: ReviewAdminAuthenticationOutcome
    principal: Optional[ReviewPrincipal] = None


class ReviewAdminAuthenticator(Protocol):
    def authenticate(self, credential: str) -> ReviewAdminAuthenticationResult: ...


class ReviewAdminDecisionController(Protocol):
    async def decide(
        self,
        *,
        event_key: str,
        action: ReviewDecisionAction,
        content_hash: str,
        reason: Optional[str] = None,
        decision_id: Optional[UUID] = None,
    ) -> ReviewLabDecisionResult: ...


class ReviewAdminReadController(Protocol):
    async def load(
        self,
        *,
        event_key: Optional[str] = None,
    ) -> ReviewLabSnapshot: ...


class ReviewAdminSafetyState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    effective_mode: str
    activation_locked: bool
    external_calls_enabled: bool
    pilot_enabled: bool = False
    pilot_emergency_stop: bool = True

    @property
    def decisions_allowed(self) -> bool:
        return (
            self.effective_mode == "review"
            and not self.activation_locked
            and self.external_calls_enabled
            and self.pilot_enabled
            and not self.pilot_emergency_stop
        )

    def public(self) -> dict[str, object]:
        return {
            **self.model_dump(),
            "decisions_allowed": self.decisions_allowed,
        }


class _LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential: SecretStr = Field(min_length=1, max_length=4096)


class _DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision_id: UUID
    confirmation: str = Field(min_length=1, max_length=64)
    reason: Optional[str] = Field(default=None, max_length=500)


def _normalize_origin(origin: str) -> str:
    cleaned = origin.strip().rstrip("/")
    parsed = urlsplit(cleaned)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("review_admin_origin_invalid")
    return cleaned


def _error(status_code: int, code: str, *, clear_cookie: bool = False) -> JSONResponse:
    response = JSONResponse(status_code=status_code, content={"code": code})
    if clear_cookie:
        _clear_session_cookie(response)
    return response


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        secure=True,
        httponly=True,
        samesite="strict",
    )


def _same_origin_json(request: Request, admin_origin: str) -> Optional[JSONResponse]:
    if request.headers.get("origin", "").rstrip("/") != admin_origin:
        return _error(403, "review_admin_origin_forbidden")
    if request.headers.get("sec-fetch-site", "").lower() != "same-origin":
        return _error(403, "review_admin_fetch_site_forbidden")
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type != "application/json":
        return _error(415, "review_admin_json_required")
    return None


def create_review_admin_app(
    *,
    admin_origin: str,
    authenticator: ReviewAdminAuthenticator,
    decision_controller: ReviewAdminDecisionController,
    safety_loader: Callable[[], ReviewAdminSafetyState],
    review_controller: Optional[ReviewAdminReadController] = None,
    session_store: Optional[InMemoryReviewAdminSessionStore] = None,
    shutdown_callback: Optional[Callable[[], Awaitable[None]]] = None,
) -> FastAPI:
    """Crea una aplicación desmontada; no lee entorno ni abre recursos."""

    origin = _normalize_origin(admin_origin)
    sessions = session_store or InMemoryReviewAdminSessionStore()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            try:
                await sessions.close()
            finally:
                if shutdown_callback is not None:
                    await shutdown_callback()

    app = FastAPI(
        title="NIA Review Admin",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.review_admin_sessions = sessions

    @app.middleware("http")
    async def secure_responses(request: Request, call_next):
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers[name] = value
        return response

    @app.get("/", response_class=HTMLResponse)
    async def shell() -> HTMLResponse:
        return HTMLResponse(_HTML_SHELL)

    @app.get("/assets/review-admin.css")
    async def stylesheet() -> Response:
        return Response(_CSS, media_type="text/css")

    @app.get("/assets/review-admin.js")
    async def script() -> Response:
        return Response(_JS, media_type="text/javascript")

    @app.get("/state")
    async def state() -> JSONResponse:
        try:
            snapshot = ReviewAdminSafetyState.model_validate(safety_loader())
            public_state = snapshot.public()
        except Exception:
            return _error(503, "review_admin_state_unavailable")
        return JSONResponse(public_state)

    @app.post("/session")
    async def login(request: Request) -> JSONResponse:
        rejected = _same_origin_json(request, origin)
        if rejected is not None:
            return rejected
        try:
            payload = _LoginRequest.model_validate(await request.json())
        except Exception:
            return _error(422, "review_admin_invalid_request")
        try:
            authentication = ReviewAdminAuthenticationResult.model_validate(
                authenticator.authenticate(
                    payload.credential.get_secret_value()
                )
            )
        except Exception:
            return _error(503, "review_admin_auth_unavailable")
        if authentication.outcome is ReviewAdminAuthenticationOutcome.UNAVAILABLE:
            return _error(503, "review_admin_auth_unavailable")
        if (
            authentication.outcome
            is not ReviewAdminAuthenticationOutcome.AUTHENTICATED
            or authentication.principal is None
        ):
            return _error(401, "review_admin_unauthorized")
        try:
            issued = sessions.issue(authentication.principal)
        except Exception:
            return _error(503, "review_admin_session_unavailable")
        response = JSONResponse(
            {
                "code": "review_admin_session_created",
                "csrf_token": issued.csrf_token,
                "actor": issued.principal.actor,
                "idle_expires_at": issued.idle_expires_at.isoformat(),
                "absolute_expires_at": issued.absolute_expires_at.isoformat(),
            }
        )
        response.set_cookie(
            SESSION_COOKIE_NAME,
            issued.session_id,
            path="/",
            secure=True,
            httponly=True,
            samesite="strict",
        )
        return response

    @app.get("/session")
    async def session_status(request: Request) -> JSONResponse:
        resolution = sessions.resolve(
            request.cookies.get(SESSION_COOKIE_NAME),
            touch=False,
        )
        if not resolution.authenticated or resolution.principal is None:
            return _error(
                401,
                "review_admin_session_required",
                clear_cookie=resolution.outcome
                in {
                    ReviewAdminSessionOutcome.EXPIRED,
                    ReviewAdminSessionOutcome.REVOKED,
                },
            )
        return JSONResponse(
            {
                "code": "review_admin_session_active",
                "actor": resolution.principal.actor,
                "idle_expires_at": resolution.idle_expires_at.isoformat(),
                "absolute_expires_at": resolution.absolute_expires_at.isoformat(),
            }
        )

    @app.post("/session/csrf")
    async def refresh_csrf(request: Request) -> JSONResponse:
        rejected = _same_origin_json(request, origin)
        if rejected is not None:
            return rejected
        csrf_token = sessions.rotate_csrf(
            request.cookies.get(SESSION_COOKIE_NAME)
        )
        if csrf_token is None:
            return _error(
                401,
                "review_admin_session_required",
                clear_cookie=True,
            )
        return JSONResponse(
            {
                "code": "review_admin_csrf_rotated",
                "csrf_token": csrf_token,
            }
        )

    async def review_snapshot(
        request: Request,
        event_key: Optional[str] = None,
    ) -> JSONResponse:
        resolution = sessions.resolve(
            request.cookies.get(SESSION_COOKIE_NAME)
        )
        if not resolution.authenticated:
            return _error(
                401,
                "review_admin_session_required",
                clear_cookie=resolution.outcome
                in {
                    ReviewAdminSessionOutcome.EXPIRED,
                    ReviewAdminSessionOutcome.REVOKED,
                },
            )
        if review_controller is None:
            return _error(503, "review_admin_reviews_unavailable")
        if event_key is not None and (
            len(event_key) != 64
            or any(character not in "0123456789abcdef" for character in event_key)
        ):
            return _error(404, "review_admin_event_not_found")
        try:
            snapshot = ReviewLabSnapshot.model_validate(
                await review_controller.load(event_key=event_key)
            )
        except Exception:
            return _error(503, "review_admin_reviews_unavailable")
        if event_key is not None and snapshot.selected is None:
            return _error(404, "review_admin_event_not_found")
        return JSONResponse(snapshot.model_dump(mode="json", exclude_none=True))

    @app.get("/reviews")
    async def reviews(request: Request) -> JSONResponse:
        return await review_snapshot(request)

    @app.get("/reviews/{event_key}")
    async def review_event(request: Request, event_key: str) -> JSONResponse:
        return await review_snapshot(request, event_key)

    def authorize_mutation(request: Request) -> tuple[Optional[ReviewPrincipal], Optional[JSONResponse]]:
        rejected = _same_origin_json(request, origin)
        if rejected is not None:
            return None, rejected
        resolution = sessions.resolve(
            request.cookies.get(SESSION_COOKIE_NAME),
            csrf_token=request.headers.get(CSRF_HEADER),
            require_csrf=True,
        )
        if not resolution.authenticated or resolution.principal is None:
            code = (
                "review_admin_csrf_invalid"
                if request.cookies.get(SESSION_COOKIE_NAME)
                else "review_admin_session_required"
            )
            return None, _error(
                403 if code == "review_admin_csrf_invalid" else 401,
                code,
                clear_cookie=resolution.outcome
                in {
                    ReviewAdminSessionOutcome.EXPIRED,
                    ReviewAdminSessionOutcome.REVOKED,
                },
            )
        return resolution.principal, None

    @app.delete("/session")
    async def logout(request: Request) -> JSONResponse:
        _principal, rejected = authorize_mutation(request)
        if rejected is not None:
            return rejected
        sessions.revoke(request.cookies.get(SESSION_COOKIE_NAME))
        response = JSONResponse({"code": "review_admin_session_revoked"})
        _clear_session_cookie(response)
        return response

    @app.post("/decisions/{event_key}/{action}")
    async def decide(
        request: Request,
        event_key: str,
        action: Literal[
            "approve-input",
            "reject-input",
            "approve-output",
            "reject-output",
        ],
    ) -> JSONResponse:
        _principal, rejected = authorize_mutation(request)
        if rejected is not None:
            return rejected
        try:
            safety = ReviewAdminSafetyState.model_validate(safety_loader())
        except Exception:
            return _error(503, "review_admin_state_unavailable")
        if not safety.decisions_allowed:
            return _error(503, "review_admin_decisions_locked")
        try:
            parsed_action = ReviewDecisionAction(action.replace("-", "_"))
            payload = _DecisionRequest.model_validate(await request.json())
        except (TypeError, ValueError, ValidationError):
            return _error(422, "review_admin_invalid_request")
        if payload.confirmation != _CONFIRMATIONS[parsed_action]:
            return _error(409, "review_admin_confirmation_mismatch")
        try:
            result = await decision_controller.decide(
                event_key=event_key,
                action=parsed_action,
                content_hash=payload.content_hash,
                reason=payload.reason,
                decision_id=payload.decision_id,
            )
        except Exception:
            return _error(503, "review_admin_decision_unavailable")
        return JSONResponse(
            status_code=result.status_code,
            content=result.model_dump(mode="json", exclude_none=True),
        )

    return app


__all__ = [
    "CSRF_HEADER",
    "ReviewAdminAuthenticationOutcome",
    "ReviewAdminAuthenticationResult",
    "ReviewAdminReadController",
    "ReviewAdminSafetyState",
    "SECURITY_HEADERS",
    "create_review_admin_app",
]
