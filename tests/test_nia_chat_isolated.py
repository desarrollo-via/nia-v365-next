"""Ensayo hermético del contrato público usando la lógica real de main.py.

No importa ``main`` porque hacerlo carga la configuración Mongo del servicio.
En su lugar compila desde el AST únicamente las funciones de producción que
participan en este escenario. Las dependencias de infraestructura se inyectan
como dobles en memoria y cualquier intento de llegar a OpenAI falla la prueba.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import httpx

from bitrix_connector.config import ConnectorMode, load_settings
from bitrix_connector.models import (
    ConnectorEventStatus,
    ConnectorIngestionStatus,
    NormalizedBitrixEvent,
)
from bitrix_connector.mode_policy import ExternalCallPolicy
from bitrix_connector.nia_client import NiaClient, NiaClientDecision
from bitrix_connector.preflight import NiaTextPayloadPreview
from bitrix_connector.pilot_scope import PilotScopePolicy, PilotScopeRule
from bitrix_connector.review import ReviewDecisionOutcome
from bitrix_connector.service import ConnectorIngestionService
from bitrix_connector.storage import MongoConnectorEventStore
from bitrix_connector.worker import ConnectorWorkerRunStatus
from bitrix_connector.worker_composition import compose_workers
from bitrix_connector.workflow_policy import WorkflowGuard
from response_engine import (
    contiene_placeholder,
    respuesta_producto_encontrado,
    respuesta_producto_relacionado,
    respuesta_sin_resultado,
)


MAIN_PATH = Path(__file__).parents[1] / "main.py"
CONTROLLED_MESSAGE = "Necesito una bomba centrífuga para agua limpia, 10 HP."
PRODUCTION_FUNCTIONS = {
    "_marcar_respuesta_segura",
    "_extraer_respuesta_segura",
    "construir_respuesta_desde_resultado",
    "_buscar_y_responder_descubrimiento",
    "procesar_turno",
    "nia_chat_texto",
}


class RecordingLogger:
    def info(self, *_args, **_kwargs):
        return None

    def warning(self, *_args, **_kwargs):
        return None


class InMemorySessionStore:
    def __init__(self):
        self.sessions = {}
        self.reads = 0
        self.writes = 0

    async def get(self, session_id):
        self.reads += 1
        value = self.sessions.get(session_id)
        return copy.deepcopy(value) if value is not None else None

    async def save(self, **payload):
        self.writes += 1
        self.sessions[payload["session_id"]] = copy.deepcopy(payload)


class ControlledCatalog:
    PRODUCT = {
        "codigo": "LAB-001",
        "referencia": "BOMBA-LAB-10HP",
        "nombre": "Bomba centrífuga de ensayo controlado",
        "marca": "Marca fixture",
        "descripcion_corta": "Bomba para agua limpia, 10 HP",
        "existencia": "Fixture local",
        "stock_total": 0,
    }
    SECOND_PRODUCT = {
        "codigo": "LAB-002",
        "referencia": "BOMBA-LAB-30M3H",
        "nombre": "Bomba centrífuga candidata para validación",
        "marca": "Marca fixture",
        "descripcion_corta": "Candidata controlada para 30 m³/h y 25 mca",
        "existencia": "Fixture local",
        "stock_total": 0,
    }

    def __init__(self):
        self.queries = []

    async def search(self, query):
        self.queries.append(query)
        if len(self.queries) > 1:
            return {
                "estado": "relacionado",
                "producto": copy.deepcopy(self.SECOND_PRODUCT),
                "razon": (
                    "El catálogo controlado la considera candidata, pero "
                    "el punto de operación requiere validación técnica."
                ),
                "pregunta_sugerida": (
                    "¿Puedes confirmar si los 25 mca incluyen todas las pérdidas?"
                ),
                "preguntas_tecnicas": [],
                "query_catalogo": query,
            }
        return {
            "estado": "encontrado",
            "producto": copy.deepcopy(self.PRODUCT),
            "query_catalogo": query,
        }


class ChatResponseDouble:
    def __init__(self, **payload):
        self._payload = payload
        for key, value in payload.items():
            setattr(self, key, value)

    def model_dump(self):
        return copy.deepcopy(self._payload)


def _load_production_namespace(store, catalog, openai_attempts):
    source = MAIN_PATH.read_text(encoding="utf-8-sig")
    parsed = ast.parse(source, filename=str(MAIN_PATH))
    selected = []

    for node in parsed.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in PRODUCTION_FUNCTIONS:
                cloned = copy.deepcopy(node)
                cloned.decorator_list = []
                selected.append(cloned)

    found = {node.name for node in selected}
    if found != PRODUCTION_FUNCTIONS:
        raise AssertionError(
            "nia_isolated_missing_production_functions: "
            + ",".join(sorted(PRODUCTION_FUNCTIONS - found))
        )

    async def no_openai(*_args, **_kwargs):
        openai_attempts.append("call_nia")
        raise AssertionError("isolated_lab_must_not_call_openai")

    async def empty_learning(_key):
        return {}

    async def no_active_flow(*_args, **_kwargs):
        return None

    async def classify(_message, _stage):
        return {"tipo": "consulta_producto", "confianza": 1.0, "razon": "fixture"}

    async def no_persistent_client(*_args, **_kwargs):
        return None

    namespace = {
        "Optional": __import__("typing").Optional,
        "Request": object,
        "ChatRequest": object,
        "ChatResponse": ChatResponseDouble,
        "datetime": datetime,
        "logger": RecordingLogger(),
        "get_session": store.get,
        "save_session": store.save,
        "get_cliente": no_persistent_client,
        "resolver_clave_aprendizaje": lambda *_args: "session:chat-controlado-001",
        "obtener_memoria_aprendizaje": empty_learning,
        "activar_memoria_aprendizaje": lambda _value: None,
        "_ultimo_turno_pide_datos_contacto": lambda _history: False,
        "_try_resolver_turno_hibrida": no_active_flow,
        "_try_resolver_turno_corta_larga": no_active_flow,
        "extraer_datos_cliente": lambda _message, current: dict(current),
        "_sanitizar_cliente_control": lambda current: dict(current),
        "clasificar_mensaje": classify,
        "_manejar_estado_comercial_prioritario": lambda **_kwargs: None,
        "_persistir_aprendizaje_si_corresponde": no_persistent_client,
        "ESTADOS_COMERCIALES": set(),
        "es_solo_saludo": lambda _message: False,
        "_en_flujo_corta_larga": lambda _context: False,
        "detectar_modo_busqueda": lambda _message: "producto",
        "_debe_preguntar_antes_de_buscar": lambda _message: False,
        "detectar_categoria": lambda _message: "bombas",
        "buscar_en_catalogo": catalog.search,
        "debe_intentar_enriquecimiento": lambda _result: False,
        "_ctx_descubrimiento_base": lambda context, query: {
            **dict(context),
            "query_evaluada": query,
        },
        "construir_contexto_aprendizaje_desde_necesidad": lambda _context: {},
        "_ctx_confirmacion_producto": lambda: {
            "fase_descubrimiento": "confirmacion_producto"
        },
        "respuesta_producto_encontrado": respuesta_producto_encontrado,
        "respuesta_producto_relacionado": respuesta_producto_relacionado,
        "respuesta_sin_resultado": respuesta_sin_resultado,
        "_normalizar_preguntas": lambda values: list(values or []),
        "PALABRAS_MAS": set(),
        "PALABRAS_FIN": set(),
        "PROMPT_MAESTRO": "",
        "call_nia": no_openai,
        "contiene_placeholder": contiene_placeholder,
        "datos_faltantes": lambda *_args: [],
        "_persistir_cliente_permanente": no_persistent_client,
    }

    module = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__",
                names=[ast.alias(name="annotations")],
                level=0,
            ),
            *selected,
        ],
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    exec(compile(module, str(MAIN_PATH), "exec"), namespace)
    return namespace


class IsolatedNiaTransport(httpx.AsyncBaseTransport):
    """Entrega el contrato HTTP al endpoint aislado sin abrir sockets."""

    def __init__(self, production):
        self.production = production
        self.requests = []

    async def handle_async_request(self, request):
        self.requests.append(request)
        payload = json.loads(request.content)
        response = await self.production["nia_chat_texto"](
            object(),
            SimpleNamespace(**payload, phone_id=None),
        )
        return httpx.Response(
            200,
            json=response.model_dump(),
            request=request,
        )


class ForbiddenBitrixClient:
    def __init__(self):
        self.calls = 0

    async def send_approved_message(self, _payload):
        self.calls += 1
        raise AssertionError("isolated_worker_lab_must_not_call_bitrix")


class IsolatedNiaChatContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_composed_worker_stops_at_output_review_after_isolated_nia(self):
        from tests.test_bitrix_full_flow import InMemoryCollection, event_form

        real_settings = load_settings({})
        self.assertIs(real_settings.effective_mode, ConnectorMode.OFF)
        self.assertTrue(real_settings.activation_locked)
        self.assertFalse(real_settings.external_calls_enabled)

        review_policy = ExternalCallPolicy(
            effective_mode=ConnectorMode.REVIEW,
            activation_locked=False,
            external_calls_enabled=True,
        )
        controlled_settings = replace(
            load_settings(
                {
                    "NIA_BITRIX_DOMAIN": "viaindustrial.bitrix24.es",
                    "NIA_BITRIX_MEMBER_ID": "member-123",
                    "NIA_BITRIX_APPLICATION_TOKEN": "secret-token",
                }
            ),
            effective_mode=ConnectorMode.REVIEW,
            activation_locked=False,
        )
        form = event_form()
        form["data[message][text]"] = CONTROLLED_MESSAGE

        collection = InMemoryCollection()
        store = MongoConnectorEventStore(collection)
        service = ConnectorIngestionService(store)
        ingested = await service.ingest(form, controlled_settings)
        self.assertIs(ingested.status, ConnectorIngestionStatus.STORED)

        session_store = InMemorySessionStore()
        catalog = ControlledCatalog()
        openai_attempts = []
        production = _load_production_namespace(
            session_store,
            catalog,
            openai_attempts,
        )
        transport = IsolatedNiaTransport(production)
        bitrix_client = ForbiddenBitrixClient()

        async with httpx.AsyncClient(transport=transport) as http_client:
            nia_client = NiaClient(
                base_url="http://nia-next.isolated",
                timeout_seconds=3,
                http_client=http_client,
            )
            workers = compose_workers(
                store,
                nia_client,
                bitrix_client,
                worker_id="isolated-full-flow",
                policy_provider=lambda: review_policy,
            )

            first_cycle = await workers.run_once()
            input_review = await store.get_review(ingested.event_key)

            self.assertIs(
                first_cycle.preflight.status,
                ConnectorWorkerRunStatus.COMPLETED,
            )
            self.assertIs(first_cycle.nia.status, ConnectorWorkerRunStatus.IDLE)
            self.assertIs(first_cycle.bitrix.status, ConnectorWorkerRunStatus.IDLE)
            self.assertEqual(
                input_review["status"],
                ConnectorEventStatus.NEEDS_INPUT_REVIEW.value,
            )
            self.assertEqual(len(transport.requests), 0)

            approval = await store.approve_input(
                ingested.event_key,
                content_hash=input_review["preflight_review"]["content_hash"],
                actor="controlled-human-reviewer",
            )
            self.assertIs(approval.outcome, ReviewDecisionOutcome.APPLIED)

            second_cycle = await workers.run_once()
            output_review = await store.get_output_review(ingested.event_key)

            self.assertIs(
                second_cycle.preflight.status,
                ConnectorWorkerRunStatus.IDLE,
            )
            self.assertIs(
                second_cycle.nia.status,
                ConnectorWorkerRunStatus.COMPLETED,
            )
            self.assertIs(
                second_cycle.bitrix.status,
                ConnectorWorkerRunStatus.IDLE,
            )
            self.assertEqual(len(transport.requests), 1)
            self.assertEqual(transport.requests[0].url.path, "/nia/chat")
            self.assertEqual(
                output_review["status"],
                ConnectorEventStatus.NEEDS_OUTPUT_REVIEW.value,
            )
            exact_output = output_review["output_review"]
            self.assertEqual(exact_output["decision"], "ready_for_review")
            self.assertIn("LAB-001", exact_output["nia_response"]["respuesta"])
            self.assertEqual(
                exact_output["bitrix_payload_preview"]["fields"]["message"],
                exact_output["nia_response"]["respuesta"],
            )

            persisted = await store.get_by_key(ingested.event_key)
            html = (
                MAIN_PATH.parent
                / "bitrix_connector"
                / "review_lab_dynamic_demo.html"
            ).read_text(encoding="utf-8")
            fixture_text = html.split(
                '<script id="composedWorkerFixture" type="application/json">',
                1,
            )[1].split("</script>", 1)[0]
            visible_fixture = json.loads(fixture_text)
            persisted_preflight = persisted["preflight_review"]
            persisted_output = persisted["output_review"]

            self.assertEqual(visible_fixture["event_key"], persisted["event_key"])
            self.assertEqual(
                visible_fixture["status"],
                ConnectorEventStatus.NEEDS_OUTPUT_REVIEW.value,
            )
            self.assertEqual(
                visible_fixture["original_event_redacted"],
                persisted_preflight["raw_redacted"],
            )
            self.assertEqual(
                visible_fixture["normalized_message"],
                persisted_preflight["normalized_input"],
            )
            self.assertEqual(
                visible_fixture["attachment_manifest"],
                persisted_preflight["preflight_manifest"],
            )
            self.assertEqual(
                visible_fixture["nia_payload"],
                persisted_preflight["nia_payload_preview"],
            )
            self.assertEqual(
                visible_fixture["input_content_hash"],
                persisted_preflight["content_hash"],
            )
            self.assertEqual(
                visible_fixture["nia_response"],
                persisted_output["nia_response"],
            )
            self.assertEqual(
                visible_fixture["bitrix_payload_preview"],
                persisted_output["bitrix_payload_preview"],
            )
            self.assertEqual(
                visible_fixture["output_content_hash"],
                persisted_output["content_hash"],
            )
            self.assertEqual(
                visible_fixture["workflow_guard"],
                WorkflowGuard.model_validate(
                    persisted["workflow_guard"]
                ).model_dump(mode="json"),
            )
            self.assertEqual(
                visible_fixture["input_decision"]["decision"],
                persisted["input_decision"]["decision"],
            )
            self.assertEqual(
                visible_fixture["input_decision"]["actor"],
                persisted["input_decision"]["actor"],
            )
            self.assertEqual(
                visible_fixture["dispatch_result"]["nia_http_requests"],
                persisted["nia_attempt_count"],
            )
            self.assertEqual(
                visible_fixture["dispatch_result"]["bitrix_attempt_count"],
                persisted["bitrix_attempt_count"],
            )
            self.assertEqual(
                visible_fixture["real_safety"],
                {
                    "effective_mode": "off",
                    "activation_locked": True,
                    "external_calls_enabled": False,
                    "services_started": False,
                    "pilot_enabled": False,
                    "pilot_emergency_stop": True,
                },
            )
            pilot_evidence = visible_fixture["pilot_gate_evidence"]
            identity = pilot_evidence["evaluated_identity"]
            self.assertEqual(
                identity,
                {
                    "member_id": persisted["normalized_event"]["member_id"],
                    "bot_id": persisted["normalized_event"]["bot_id"],
                    "dialog_id": persisted["normalized_event"]["dialog_id"],
                    "chat_id": persisted["normalized_event"]["chat_id"],
                },
            )
            window = pilot_evidence["window"]
            pilot_policy = PilotScopePolicy(
                enabled=pilot_evidence["scenario"]["enabled"],
                emergency_stop=pilot_evidence["scenario"]["emergency_stop"],
                rules=(
                    PilotScopeRule(
                        **identity,
                        valid_from=datetime.fromisoformat(window["valid_from"]),
                        valid_until=datetime.fromisoformat(window["valid_until"]),
                    ),
                ),
                clock=lambda: datetime.fromisoformat(window["evaluated_at"]),
            )
            pilot_decision = pilot_policy.evaluate(
                NormalizedBitrixEvent.model_validate(
                    persisted["normalized_event"]
                )
            )
            self.assertTrue(pilot_decision.accepted)
            self.assertEqual(pilot_decision.reason, "pilot_scope_allowed")
            self.assertEqual(
                [gate["status"] for gate in pilot_evidence["gates"]],
                ["allowed", "pending"],
            )
            self.assertEqual(
                [case["reason"] for case in pilot_evidence["verified_cases"]],
                [
                    "pilot_scope_allowed",
                    "outside_pilot_scope",
                    "pilot_scope_expired",
                    "pilot_emergency_stop",
                ],
            )

            third_cycle = await workers.run_once()

        self.assertTrue(
            all(
                result.status is ConnectorWorkerRunStatus.IDLE
                for result in (
                    third_cycle.preflight,
                    third_cycle.nia,
                    third_cycle.bitrix,
                )
            )
        )
        self.assertEqual(bitrix_client.calls, 0)
        self.assertEqual(session_store.reads, 1)
        self.assertEqual(session_store.writes, 1)
        self.assertEqual(openai_attempts, [])

    async def test_nia_client_reaches_isolated_public_endpoint_without_socket(self):
        store = InMemorySessionStore()
        catalog = ControlledCatalog()
        openai_attempts = []
        production = _load_production_namespace(store, catalog, openai_attempts)
        transport = IsolatedNiaTransport(production)
        payload = NiaTextPayloadPreview(
            session_id="bitrix:member-demo:chat-controlado-001",
            mensaje="Necesito una bomba centrífuga para agua limpia, 10 HP.",
        )

        async with httpx.AsyncClient(transport=transport) as http_client:
            nia_client = NiaClient(
                base_url="http://nia-next.isolated",
                timeout_seconds=3,
                http_client=http_client,
            )
            result = await nia_client.send_approved_text(payload)

        self.assertIs(result.decision, NiaClientDecision.SUCCESS)
        self.assertEqual(result.http_status, 200)
        self.assertIsNotNone(result.response)
        self.assertIn("LAB-001", result.response.respuesta)
        self.assertEqual(result.response.etapa, "producto_encontrado")
        self.assertEqual(len(transport.requests), 1)
        request = transport.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.url.path, "/nia/chat")
        self.assertEqual(json.loads(request.content), payload.model_dump())
        self.assertEqual(store.reads, 1)
        self.assertEqual(store.writes, 1)
        self.assertEqual(openai_attempts, [])

    async def test_public_contract_uses_real_nia_orchestration_and_response_engine(self):
        store = InMemorySessionStore()
        catalog = ControlledCatalog()
        openai_attempts = []
        production = _load_production_namespace(store, catalog, openai_attempts)

        response = await production["nia_chat_texto"](
            object(),
            SimpleNamespace(
                session_id="bitrix:member-demo:chat-controlado-001",
                mensaje="Necesito una bomba centrífuga para agua limpia, 10 HP.",
                phone_id=None,
            ),
        )

        self.assertEqual(response.etapa, "producto_encontrado")
        self.assertIn("LAB-001", response.respuesta)
        self.assertIn("Bomba centrífuga de ensayo controlado", response.respuesta)
        self.assertEqual(catalog.queries, [
            "Necesito una bomba centrífuga para agua limpia, 10 HP."
        ])
        self.assertEqual(store.reads, 1)
        self.assertEqual(store.writes, 1)
        self.assertEqual(openai_attempts, [])

        saved = store.sessions["bitrix:member-demo:chat-controlado-001"]
        self.assertEqual(len(saved["turnos"]), 2)
        self.assertEqual(saved["turnos"][0]["role"], "user")
        self.assertEqual(saved["turnos"][1]["role"], "assistant")
        self.assertEqual(saved["turnos"][1]["content"], response.respuesta)

        preview = {
            "botId": 456,
            "dialogId": "chat-controlado-001",
            "fields": {"message": response.respuesta},
        }
        canonical = json.dumps(
            {"kind": "bitrix_message", "payload": preview},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        output_hash = hashlib.sha256(canonical).hexdigest()
        demo = (
            MAIN_PATH.parent
            / "bitrix_connector"
            / "review_lab_dynamic_demo.html"
        ).read_text(encoding="utf-8")
        self.assertIn(json.dumps(response.respuesta, ensure_ascii=False), demo)
        self.assertIn(output_hash, demo)

    async def test_second_turn_reads_same_in_memory_session(self):
        store = InMemorySessionStore()
        catalog = ControlledCatalog()
        production = _load_production_namespace(store, catalog, [])
        request = SimpleNamespace(
            session_id="bitrix:member-demo:chat-controlado-001",
            mensaje="Necesito una bomba centrífuga para agua limpia, 10 HP.",
            phone_id=None,
        )

        first = await production["nia_chat_texto"](object(), request)
        request.mensaje = "¿También funciona para 30 m³/h y 25 mca?"
        second = await production["nia_chat_texto"](object(), request)

        self.assertEqual(store.reads, 2)
        self.assertEqual(store.writes, 2)
        self.assertEqual(len(store.sessions[request.session_id]["turnos"]), 4)
        self.assertIn("LAB-001", first.respuesta)
        self.assertEqual(second.etapa, "validando_relacionado")
        self.assertIn("LAB-002", second.respuesta)
        self.assertIn("requiere validación técnica", second.respuesta)
        self.assertEqual(catalog.queries[1], request.mensaje)
        history = store.sessions[request.session_id]["turnos"]
        self.assertEqual(history[0]["content"], (
            "Necesito una bomba centrífuga para agua limpia, 10 HP."
        ))
        self.assertEqual(history[2]["content"], request.mensaje)
        self.assertEqual(history[3]["content"], second.respuesta)

        preview = {
            "botId": 456,
            "dialogId": "chat-controlado-001",
            "fields": {"message": second.respuesta},
        }
        canonical = json.dumps(
            {"kind": "bitrix_message", "payload": preview},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        output_hash = hashlib.sha256(canonical).hexdigest()
        demo = (
            MAIN_PATH.parent
            / "bitrix_connector"
            / "review_lab_dynamic_demo.html"
        ).read_text(encoding="utf-8")
        self.assertIn(json.dumps(second.respuesta, ensure_ascii=False), demo)
        self.assertIn(output_hash, demo)
        self.assertIn("fixtureDetails.length", demo)
        self.assertIn("Cliente · turno 2 · misma sesión", demo)


if __name__ == "__main__":
    unittest.main()
