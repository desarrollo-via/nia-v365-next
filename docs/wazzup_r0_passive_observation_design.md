# Diseño inerte de observación Wazzup para R0

Estado: **ARNÉS HOST LOCAL FAIL-CLOSED IMPLEMENTADO · SWITCH FALSE · NO AUTORIZA ACTIVACIÓN**

Estado Git del corte actual: **CAMBIOS LOCALES SIN COMMIT · PUBLICACIÓN NO AUTORIZADA**

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
- <https://wazzup24.com/help/api/webhooks/>
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

## Preflight externo futuro

Ningún preflight externo queda autorizado por este diseño. Antes de proponer
una suscripción real será indispensable:

- confirmar cuál contrato, v2 o v3, corresponde a la cuenta instalada;
- consultar solo la presencia y forma del webhook Sidecar vigente, sin mostrar
  URI, clave o valores;
- demostrar que añadir una recepción paralela no reemplaza ni degrada una
  integración existente;
- identificar de forma verificable el `channelId` y `chatId` Wazzup del caso
  controlado sin confundirlos con los identificadores Bitrix;
- tener el endpoint inerte publicado, autenticado, esperando y probado antes de
  cualquier cambio en Wazzup;
- fijar snapshot anterior, cambio literal, ventana, comprobación y rollback.

La consulta protegida que use una credencial requerirá autorización específica.
Cualquier `PATCH` de Wazzup es una mutación productiva y activa la barrera de
dos confirmaciones textuales, precisas y separadas. El rollback deberá restaurar
literalmente la URI y las suscripciones anteriores y verificarlas mediante una
lectura posterior. Un estado previo desconocido o una restauración no verificable
impone `NO-GO`.

## Operaciones congeladas

Hasta una nueva decisión expresa quedan prohibidos:

- `imopenlines.config.update` sobre `CONFIG_ID=13`;
- sustituir el bot productivo `245339`;
- vincular o agregar `373259` a la Línea 13 o a `chat78733`;
- cambiar Wazzup, su Sidecar, URI, suscripciones, canales o integración Bitrix;
- montar o desplegar un receptor Wazzup;
- solicitar o enviar el primer mensaje controlado.

## Criterio de avance

El contrato y la capa ASGI hermética están implementados, auditados y mantienen
el switch apagado. El parser rechaza las constantes JSON no finitas y las ocho
rutas exactas ya están preparadas en el índice. El siguiente avance requiere una
autorización separada para crear únicamente un commit local; el índice actual no
autoriza push, PR, despliegue, suscripción o mensaje.
