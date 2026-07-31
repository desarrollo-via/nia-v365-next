# Diseño inerte de observación Wazzup para R0

Estado: **CAMINO ARCHIVADO Y CONGELADO · WAZZUP FUERA DE R0 · CERO CONSULTAS EJECUTADAS**

Estado operativo observado el `2026-07-31`: **NIA OK · 21/17/3 · OFF/LOCKED/NO-EXTERNAL · RUNTIME INERTE**

## Decisión posterior — 8/18

Este camino queda supersedido por
`docs/bitrix_r0_history_observation_design.md`. NIA Next se conectará sólo con
Bitrix para el primer ensayo controlado. No se usará la clave Sidecar indicada
por la persona, no se ejecutarán los GET diseñados y no se cambiarán webhook,
URI, suscripciones, canales o autenticación Wazzup.

El resto de este documento se conserva únicamente como evidencia histórica del
camino descartado; no constituye un siguiente paso ni una autorización.

## Decisión

La sustitución temporal de `WELCOME_BOT_ID=245339` por el bot controlado
`373259` sobre `CONFIG_ID=13` queda congelada. Ese cambio afecta globalmente a
los chats nuevos de la Línea 13 y no puede presentarse como un cambio limitado
a la negociación controlada.

Tampoco se adopta todavía la incorporación de `373259` como participante de
`chat78733`: Bitrix permite agregar un bot a un chat CRM concreto, pero un bot
`openline` conserva una visibilidad similar a un bot normal y la documentación
no garantiza que reciba todos los mensajes externos solo por participar.

La alternativa estudiada es una recepción pasiva desde Wazzup, separada de los
bots y de la configuración de la Línea 13. Este documento únicamente define el
trabajo local previo necesario para evaluar esa alternativa.

## Evidencia documental

- Wazzup documenta una clave Sidecar para ampliar una integración existente de
  Bitrix sin sustituirla. La clave Sidecar permite consultar y configurar el
  webhook mediante `GET /webhooks` y `PATCH /webhooks`.
- El contrato público v3 expone una sola `webhooksUri` junto con el conjunto de
  suscripciones. Un `PATCH` puede, por tanto, reemplazar una URI lateral ya
  configurada; no debe ejecutarse sin conocer y conservar el estado anterior.
- El contrato v2 documenta suscripciones independientes con identificador, pero
  utiliza `client_access_token`. No está demostrado que ese contrato pertenezca
  a la instalación Bitrix/Sidecar vigente.
- El conector NIA actual acepta exclusivamente `ONIMBOTV2MESSAGEADD` en formato
  Bitrix. No reconoce el JSON v3 de Wazzup con `messages` y estados `inbound`.

Referencias públicas:

- <https://wazzup24.com/help/api-en/connection-methods/>
- <https://wazzup24.com/help/api-en/webhooks/>
- <https://wazzup24.com/help/api-en/working-with-channels/>
- <https://wazzup24.com/help/api/webhooks/>
- <https://wazzup24.com/help/api/channels/>
- <https://apidocs.bitrix24.com/api-reference/chat-bots/chat-bots-v2/index.html>

## Frontera local propuesta

La primera fase quedó implementada como un adaptador hermético y desmontado:

1. Modelo estricto para el JSON Wazzup v3, con allowlist de campos necesarios.
2. Normalización independiente del parser Bitrix existente.
3. Aceptación exclusiva de mensajes con estado `inbound`.
4. Filtro exacto por identidad Wazzup comprobada; `chat78733` de Bitrix no se
   tratará como si fuera el `chatId` externo de Wazzup.
5. Resultado R0 exclusivamente inerte: `connector_locked_off`,
   `nia_called=false`, `bitrix_written=false`.
6. Switch nuevo ausente o `false` por defecto, sin ruta al estar apagado.
7. Cero importación desde `main.py`, montaje productivo, sockets, Mongo, NIA,
   OpenAI, Bitrix o Wazzup durante las pruebas herméticas.
8. Idempotencia en memoria con retención acotada.
9. Capa ASGI local con ruta POST exacta, autenticación antes del primer
   `receive()`, cuerpo máximo de 64 KiB, máximo 64 fragmentos y timeout de 5
   segundos.
10. JSON estricto sin claves duplicadas y respuestas `no-store`/`nosniff` que
    nunca incluyen texto, URI, cabeceras o detalles de excepciones.

La implementación vive en `bitrix_connector/wazzup_r0_adapter.py`. Recibe el
mapping de configuración y un verificador de cabeceras por inyección; no lee el
entorno global. `NIA_WAZZUP_R0_ADAPTER_ENABLED` solo acepta `true`, permanece
`false` en `.env.example` y no está consumido por `main.py`, el router o un
workflow. Ausente o apagado no construye el adaptador; una configuración
incompleta o ambigua falla cerrada.

La capa HTTP vive separada en `bitrix_connector/wazzup_r0_ingress.py`. Su
composición devuelve `app=None` cuando el switch está ausente o apagado. No está
importada por `main.py`, el router o workflows y no inicia FastAPI, servidor,
socket o recurso externo. La autenticación se comprueba antes de leer el cuerpo
y el adaptador vuelve a verificar las mismas cabeceras antes de validar el
payload, conservando un fallo cerrado en ambas fronteras.

## Arnés host fail-closed

`optional_wazzup_r0_ingress.py` agrega una frontera diferida entre la aplicación
host y el ASGI inerte. Con el switch ausente o `false` no importa el paquete ni
agrega middleware. Un valor distinto de `true`/`false`, un import fallido, una
composición incompleta o un error de montaje deja la ruta ausente y expone solo
razones fijas; los logs conservan únicamente el tipo de excepción.

Cuando una prueba inyecta identidad y autenticador sintéticos, el arnés agrega
un dispatcher ASGI que intercepta exclusivamente
`/bitrix-connector/internal/wazzup-r0`. El dispatcher no lee ni transforma el
cuerpo: entrega la solicitud al ingreso existente, que autentica antes del
primer `receive()`. Cualquier otra ruta o evento ASGI continúa hacia FastAPI sin
cambio.

`main.py` llama el puente sin `WazzupR0Scope` ni `header_verifier` reales. Por
ello, incluso si el switch llegara a `true`, la composición queda
`unavailable`, sin ruta. Esta decisión es deliberada: todavía no existe una
identidad Wazzup verificada ni un contrato real de autenticidad, y no se
reutiliza el token de Bitrix.

La allowlist exacta de este segundo corte contiene siete rutas:

1. `optional_wazzup_r0_ingress.py`
2. `main.py`
3. `bitrix_connector/__init__.py`
4. `docs/wazzup_r0_passive_observation_design.md`
5. `tests/test_optional_wazzup_r0_ingress.py`
6. `tests/test_bitrix_wazzup_r0_ingress.py`
7. `tests/test_bitrix_g0_entrypoint.py`

`.env.example`, el adaptador, el ingreso ASGI, router, políticas, workflows y el
runbook P1-B quedan fuera. El rollback local previo a commit consiste en
revertir únicamente estas siete rutas hasta el árbol `b736020`; después de un
commit futuro será un `git revert` de ese commit. Este corte no autoriza commit,
push, despliegue o rollback externo.

## Auditoría local y allowlist Git

La allowlist exacta del corte contiene únicamente estas ocho rutas:

1. `.env.example`
2. `bitrix_connector/__init__.py`
3. `bitrix_connector/wazzup_r0_adapter.py`
4. `bitrix_connector/wazzup_r0_ingress.py`
5. `docs/wazzup_r0_passive_observation_design.md`
6. `tests/test_bitrix_g0_entrypoint.py`
7. `tests/test_bitrix_wazzup_r0_adapter.py`
8. `tests/test_bitrix_wazzup_r0_ingress.py`

`docs/bitrix_p1b_protected_settings_runbook.md` queda expresamente fuera porque
es un archivo local previo y ajeno a este corte. `nia_next.md` conserva la
continuidad local, pero no forma parte de la allowlist Git.

La auditoría confirmó las ocho rutas exactas en el índice, cero faltantes o
extras, cero referencias de montaje o despliegue, cero patrones de secretos de
alta confianza, compilación aprobada, diff staged sin errores y 560/560 pruebas
en `tests/`. El único URI detectado pertenece al placeholder ilustrativo de
`MONGO_URI` en `.env.example`; no es una credencial. El runbook P1-B permanece
sin seguimiento y fuera del índice.

El hallazgo de JSON no finito quedó resuelto: `json.loads()` recibe ahora un
`parse_constant` fail-closed que rechaza `NaN`, `Infinity` y `-Infinity` antes
de Pydantic. Una regresión recorre las tres constantes dentro de un payload por
lo demás válido y exige `422`, cero persistencia y cero llamadas NIA/Bitrix. El
verificador se ejecuta dos veces y deberá mantenerse puro, determinista y no
bloqueante mientras ese contrato siga vigente; un fallo en cualquiera de las
dos comprobaciones permanece cerrado.

El adaptador no debe reutilizar silenciosamente `NIA_BITRIX_APPLICATION_TOKEN`
ni asumir que una credencial Sidecar es intercambiable con la autenticación
Bitrix. El contrato de autenticidad Wazzup deberá diseñarse y probarse por
separado, sin almacenar o mostrar valores en fixtures, logs o documentación.

## Preflight Wazzup protegido de solo lectura — diseño 6/18

Este apartado diseña el preflight futuro, pero no lo autoriza ni lo ejecuta. La
persona deberá indicar únicamente el tipo no secreto de credencial disponible:
`sidecar_v3` o `client_v2`. El valor se introducirá por un canal protegido y no
se mostrará, copiará, contará, validará en el chat ni persistirá en archivos.
No se cargará `.env` y una misma credencial nunca se probará contra ambos
contratos.

### Contratos mutuamente excluyentes

**Sidecar/User API v3**, para la clave Sidecar creada por la integración
existente de Bitrix:

1. `GET https://api.wazzup24.com/v3/webhooks`.
2. `GET https://api.wazzup24.com/v3/channels`.

La primera respuesta debe tener únicamente la forma esperada de
`webhooksUri + subscriptions`; la segunda, una lista de canales con
`channelId`, `transport`, `plainId` y `state`. El contrato v3 ofrece una sola
`webhooksUri`: si ya está configurada, añadir un receptor paralelo mediante
`PATCH` la reemplazaría y el resultado del preflight será `NO-GO` para una
recepción paralela sin un diseño adicional.

**Tech Partner API v2**, únicamente para un `client_access_token` de la cuenta
final:

1. `GET https://tech.wazzup24.com/v2/webhooks`.
2. `GET https://tech.wazzup24.com/v2/channels`.

Ambas respuestas deben conservar la envoltura `data + meta`. Las suscripciones
v2 tienen `id`, `url` y `event`; el canal usa `channel_id`, `transport` y
`status`. La existencia de identificadores independientes permite inventariar
suscripciones separadas, pero no prueba por sí sola que este contrato controle
la instalación Bitrix/Sidecar vigente ni que acepte una duplicación segura del
evento `message.add`.

Un `401`, `403`, redirect, host distinto, forma ambigua o mezcla de nombres v2
y v3 termina inmediatamente en `NO-GO`; no activa un intento alternativo.

### Límites exactos

- Exactamente dos solicitudes HTTPS `GET`, secuenciales y sin cuerpo.
- Hosts allowlisted literalmente: `api.wazzup24.com` para v3 o
  `tech.wazzup24.com` para v2; verificación TLS obligatoria y redirects
  deshabilitados.
- Timeout de conexión/lectura de 10 segundos por solicitud y máximo total de
  30 segundos.
- Cero reintentos, paginación, sondeos, llamadas paralelas o fallback de
  contrato.
- Máximo 256 KiB por respuesta; exceso, JSON inválido o claves duplicadas
  termina en `NO-GO`.
- Un único cliente HTTP efímero, cerrado en `finally`; cualquier error debe
  terminar con `resources_closed=true` o quedar como fallo terminal visible.
- Solo se permite `Authorization: Bearer <valor protegido>` y
  `Accept: application/json`. No se registran cabeceras, cuerpos, URI vigentes,
  teléfonos, nombres, identificadores o texto libre de errores.

Quedan prohibidos `POST`, `PATCH`, `PUT`, `DELETE`, `sendMessage`, lectura de
mensajes, historial, contactos, negocios, usuarios, plantillas, QR, archivos o
cualquier endpoint no enumerado arriba.

### Identidad y autenticidad

El preflight recibe internamente tres valores esperados protegidos y separados:
identidad del canal, `chatType` y `chatId` externo controlado. Nunca reutiliza
`CONFIG_ID=13`, `chat78733`, `dialog_id=chat78733`, negociación `614949` o un
identificador de bot como identidad Wazzup.

La consulta de canales puede verificar que exista un único canal activo y que
su identidad coincida con la esperada, pero no enumera chats ni demuestra por
sí sola la existencia del `chatId` controlado. Para WhatsApp, el contrato v3
documenta `chatId` como el identificador numérico del interlocutor; deberá
provenir de una fuente humana protegida e independiente y quedar validado solo
como booleano.

Wazzup v3 documenta que agrega `Authorization: Bearer ${crmKey}` al webhook
únicamente cuando dispone de `crmKey`. La documentación pública revisada no
demuestra de forma inequívoca que el valor esperado por nuestro receptor sea
intercambiable con la clave Sidecar usada para los GET. Por tanto el preflight
de solo lectura debe informar `incoming_auth_equivalence_verified=false` salvo
evidencia específica de la cuenta o del proveedor; nunca inferirá esa
equivalencia ni reutilizará el token Bitrix.

### Salida redactada

La salida allowlisted contendrá únicamente:

- `status`: `GO` o `NO-GO`;
- `reason`: código fijo;
- `contract_requested` y `contract_verified`;
- `http_get_calls` y `mutation_calls`;
- `webhook_read_ok`, `webhook_configured` y
  `messages_subscription_enabled`;
- `single_webhook_uri_model` o `independent_subscription_model`;
- `channel_read_ok`, `channel_count`, `active_channel_count` y
  `controlled_channel_unique`;
- `chat_identity_source_present`, `chat_identity_verified` e
  `incoming_auth_equivalence_verified`;
- `parallel_reception_proven_safe` y `resources_closed`.

No se mostrarán valores de URI, tokens, IDs, teléfonos, `plainId`, nombres,
suscripciones, cabeceras, cuerpos, hashes o mensajes del proveedor.

### GO/NO-GO

`GO` exige contrato y formas exactos, dos GET exitosos, un único canal activo
controlado, fuente protegida del `chatId`, autenticidad entrante demostrada,
recepción paralela probada como no sustitutiva, cero mutaciones y recursos
cerrados. Con la evidencia pública actual, v3 conserva un modelo de URI única y
la equivalencia de autenticación entrante no está probada; esos resultados
serán `NO-GO` seguro, no defectos que habiliten más consultas.

Antes de proponer una suscripción real seguirá siendo obligatorio tener el
endpoint inerte publicado, autenticado y esperando, además de fijar snapshot
anterior, cambio literal, ventana, comprobación y rollback. Cualquier `PATCH`
de Wazzup es una mutación productiva y activa dos confirmaciones textuales,
precisas y separadas. El rollback deberá restaurar literalmente URI y
suscripciones anteriores mediante una lectura posterior. Un estado previo
desconocido o una restauración no verificable impone `NO-GO`.

## Operaciones congeladas

Hasta una nueva decisión expresa quedan prohibidos:

- `imopenlines.config.update` sobre `CONFIG_ID=13`;
- sustituir el bot productivo `245339`;
- vincular o agregar `373259` a la Línea 13 o a `chat78733`;
- cambiar Wazzup, su Sidecar, URI, suscripciones, canales o integración Bitrix;
- montar o desplegar un receptor Wazzup;
- solicitar o enviar el primer mensaje controlado.

## Criterio de avance

No existe avance operativo por Wazzup. El arnés desplegado permanece inerte, sin
identidad, autenticador o ruta efectiva, y el receptor continúa ausente/404.
Los GET, la preparación de credenciales y cualquier mutación quedan cancelados.
