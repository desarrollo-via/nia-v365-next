# Plan del piloto controlado Bitrix24 → NIA Next

## Estado de partida

- Negociación controlada: `614949`.
- Chat confirmado por OAuth: `chat_id=78733`, `dialog_id=chat78733`.
- Canal observado: `WAZZUP: WhatsApp`.
- Aplicación local instalada con `crm`, `imopenlines` e `imbot`.
- `member_id`, dominio, `application_token` y OAuth están almacenados sin exposición.
- Falta registrar el bot y, por tanto, todavía no existe `bot_id`.
- Estado obligatorio actual: `effective_mode=off`, `activation_locked=true`, `external_calls_enabled=false`, piloto deshabilitado y parada de emergencia activa.

## Decisión operativa adoptada

El piloto reutilizará `CONFIG_ID=13`, el WAZZUP existente y `chat78733` de la
negociación `614949`. No se creará una Línea Abierta o canal adicional.

La allowlist exacta impedirá que identidades distintas alcancen NIA o un envío
a Bitrix, pero la vinculación del bot propio sustituye temporalmente el bot de
bienvenida para toda la línea. Cada ensayo se limita a una ventana corta,
empieza y termina en `off`, exige ausencia operativa de otros ingresos y
restaura inmediatamente `Y / always / 245339 / 0 / close`.

El switch maestro del módulo y el modo operativo son controles distintos:
tener el módulo disponible no autoriza `review`, `shadow` o `active`.

El runbook fue ensayado completamente en memoria. El preview requiere ahora una
ventana UTC explícita de máximo 15 minutos; el chat controlado coincide con la
allowlist, otro chat falla cerrado, R0 devuelve `connector_locked_off` con cero
acciones externas y el rollback recupera exactamente
`Y / always / 245339 / 0 / close`.

El preflight real del 27 de julio de 2026 confirmó por cuatro lecturas oficiales
que `chat78733` continúa en la línea activa `CONFIG_ID=13`, que el snapshot
vigente sigue siendo `Y / always / 245339 / 0 / close` y que nuestra aplicación
no posee aún el bot controlado (`existing_bot_id=null`,
`registration_needed=true`). No se leyeron mensajes ni se realizaron
mutaciones.

Este documento es diseño. No autoriza registro, despliegue, cambio del Canal Abierto, lectura de mensajes, llamada a NIA ni envío a Bitrix.

## Decisión de compatibilidad

Se usará `imbot.v2.Bot.register`, no el método antiguo `imbot.register`.

Razones:

- Bitrix24 recomienda Chatbots 2.0 para desarrollos nuevos.
- El bot puede declararse con `type=openline`, `isSupportOpenline=true`, `eventMode=webhook` y una `webhookUrl` HTTPS.
- La suscripción `ONIMBOTV2*` se crea y mantiene automáticamente.
- El conector ya reconoce `ONIMBOTV2MESSAGEADD` y las claves form-urlencoded `data[bot][id]`, `data[message][chatId]`, `data[chat][dialogId]` y `auth[application_token]`.
- OAuth vincula el bot a la aplicación; no se necesita crear ni guardar un `botToken` adicional.

Referencias oficiales:

- [Chatbots 2.0](https://apidocs.bitrix24.com/api-reference/chat-bots/chat-bots-v2/index.html)
- [Registro de bot v2](https://apidocs.bitrix24.com/api-reference/chat-bots/chat-bots-v2/imbot.v2/bots/bot-register.html)
- [Formato de eventos v2](https://apidocs.bitrix24.com/api-reference/chat-bots/chat-bots-v2/imbot.v2/events/events.html)
- [Chats de Canal Abierto](https://apidocs.bitrix24.com/api-reference/imopenlines/openlines/chats/index.html)

## Arquitectura del ensayo

```text
Cliente controlado
  → WAZZUP / Canal Abierto
  → bot v2 openline de NIA
  → HTTPS estable /bitrix-connector/webhook
  → autenticidad + allowlist + persistencia propia
  → Review Admin
  → aprobación de entrada
  → NIA_BASE_URL /nia/chat
  → aprobación de salida
  → envío al mismo dialogId
```

La instalación OAuth conserva su callback separado en `/bitrix-connector/installation` y deshabilitado fuera de una reinstalación explícita. El webhook operativo no debe reutilizar un túnel rápido con URL variable.

## Compuertas obligatorias

### G0 — HTTPS estable

La topología local propuesta y sus incertidumbres están detalladas en
[`bitrix_g0_deployment_topology.md`](bitrix_g0_deployment_topology.md). Ese
diseño no autoriza infraestructura ni despliegue.

Antes de registrar el bot debe existir un host HTTPS persistente con certificado válido y estas rutas separadas:

- `GET /healthz`: salud mínima sin secretos.
- `POST /bitrix-connector/webhook`: único receptor de eventos del bot.
- `POST /bitrix-connector/installation`: deshabilitada normalmente.
- Review Admin: origen propio, autenticación humana y sin CORS abierto.

El host debe limitar tamaño, timeout, tasa y métodos; registrar solo metadatos redactados y permitir parada inmediata. La URL temporal `trycloudflare` ya cerrada no sirve como destino estable.

### G1 — Preflight de solo lectura

Antes de cualquier registro:

1. Consultar `imbot.v2.Revision.get`.
2. Consultar `imbot.v2.Bot.list` para evitar duplicados.
3. Identificar por lectura el `CONFIG_ID` de la Línea Abierta que contiene `chat78733` y conservar su configuración previa.
4. Verificar desde Internet que el webhook responde, sin enviar un evento de chat.

Si cualquiera falla, no se registra el bot.

### G2 — Registro único y reversible

La futura llamada, bajo autorización independiente, tendrá este contrato lógico:

```json
{
  "fields": {
    "code": "nia_next_openline_controlled",
    "properties": {
      "name": "NIA Next Controlado",
      "workPosition": "Piloto supervisado"
    },
    "type": "openline",
    "isSupportOpenline": true,
    "eventMode": "webhook",
    "webhookUrl": "https://HOST-ESTABLE/bitrix-connector/webhook",
    "isHidden": true,
    "isReactionsEnabled": false
  }
}
```

La respuesta se reduce a `bot_id`, código, tipo y modo; no se muestran tokens. El código estable hace el registro idempotente. Se prepara previamente el rollback mediante `imbot.v2.Bot.unregister`, pero nunca se ejecuta automáticamente.

### G3 — Vinculación al Canal Abierto

Registrar un bot no lo conecta por sí solo a la Línea Abierta. La vinculación se hará después, con evidencia de `CONFIG_ID` y copia de la configuración anterior. No se creará ni sustituirá el conector WAZZUP.

**ATENCIÓN ESPECIAL:** este paso puede afectar todos los chats nuevos de esa Línea Abierta, no únicamente `chat78733`. Requiere confirmación humana inmediata de la línea exacta, ventana temporal, comportamiento de bienvenida y rollback antes de guardar.

Aunque Bitrix entregue eventos ajenos, el conector debe rechazarlos antes de NIA y antes de cualquier envío.

### G4 — Allowlist exacta

Después de obtener `bot_id`, se construye una sola regla:

```json
{
  "member_id": "VALOR_ALMACENADO",
  "bot_id": "BOT_ID_OBTENIDO",
  "dialog_id": "chat78733",
  "chat_id": 78733,
  "valid_from": "UTC_INICIO",
  "valid_until": "UTC_FIN"
}
```

La ventana inicial será corta y explícita. Fuera de ella, con identidad distinta o con parada de emergencia, el evento falla cerrado. La negociación `614949` se conserva como evidencia de procedencia, pero la compuerta operativa usa las cuatro identidades exactas del evento.

### G5 — Desbloqueo técnico todavía pendiente

La configuración actual fuerza `off`, bloqueo y cero llamadas externas aun si se solicita otro modo. Antes de un ensayo `review` debe implementarse un desbloqueo deliberado que:

- no cambie el predeterminado `off`;
- exija simultáneamente modo permitido, activación desbloqueada, llamadas externas habilitadas, piloto habilitado, regla exacta, ventana vigente y parada desactivada;
- relea todas las barreras antes de NIA y antes de Bitrix;
- se pruebe con dobles, concurrencia, expiración y parada durante un lease;
- permita volver a `off` sin reiniciar datos ni borrar auditoría.

Sin este corte, un evento real puede comprobar el webhook y la identidad, pero debe terminar como `connector_locked_off` sin persistencia funcional, NIA o Bitrix.

## Ensayos reales, en orden

### Ensayo R0 — Recepción inerte

- Bot registrado y vinculado durante una ventana controlada.
- Estado real continúa `off/locked/no-external`.
- El usuario envía un solo texto distintivo desde el chat controlado.
- Resultado esperado: evento auténtico, `bot_id`, `chat78733` y `application_token` válidos; respuesta `connector_locked_off`; `nia_called=false`, `bitrix_written=false`.
- Se cierra la ventana o se desvincula el bot inmediatamente.

**ATENCIÓN ESPECIAL:** aquí el usuario debe confirmar que está en la negociación `614949` y avisar justo antes de enviar el único mensaje.

### Ensayo R1 — Review hasta aprobación de entrada

- Solo después de implementar y probar G5.
- Se habilita `review` con allowlist y ventana corta.
- El evento queda durable en `needs_input_review`.
- Review Admin muestra evento redactado, mensaje normalizado, adjuntos y payload exacto para NIA.
- No se aprueba todavía; NIA y Bitrix permanecen en cero llamadas.

### Ensayo R2 — NIA real, sin envío

- Aprobación humana de entrada.
- El worker llama únicamente a `NIA_BASE_URL /nia/chat`.
- La respuesta real y la salida exacta quedan en `needs_output_review`.
- No se aprueba salida; Bitrix permanece en cero envíos.

### Ensayo R3 — Una respuesta controlada

- Revisión humana final de texto, diálogo y hashes.
- Aprobación de salida una sola vez.
- Segunda revalidación de modo, allowlist, ventana y parada.
- Un envío idempotente al mismo `dialogId=chat78733`.
- Confirmación visual del mensaje en la negociación `614949` y cierre inmediato de la ventana.

**ATENCIÓN ESPECIAL:** R3 requiere atención completa porque es el primer mensaje visible al cliente controlado.

## Parada y rollback

Orden de emergencia:

1. Activar `NIA_BITRIX_PILOT_EMERGENCY_STOP=true`.
2. Volver a `NIA_BITRIX_MODE=off` y bloquear activación.
3. Detener el worker separado.
4. Desvincular el bot de la Línea Abierta y restaurar su configuración anterior.
5. Si se autoriza, desregistrar únicamente el bot con el código exacto.
6. Conservar auditoría redactada y no borrar la instalación OAuth.

Ningún rollback debe borrar mensajes, sesiones internas de NIA, la negociación o el conector WAZZUP.

## Criterio para avanzar

La secuencia operativa concreta, con la ruta recomendada de Línea Abierta de
prueba, la alternativa reforzada sobre `CONFIG_ID=13` y los dos únicos puntos
de atención humana superior a la habitual, está en
[`bitrix_controlled_pilot_registration_checklist.md`](bitrix_controlled_pilot_registration_checklist.md).

G1 dispone ya de una implementación local probada en `bot_v2_preflight.py`: el cliente solo expone `get_revision`, `list_bots` y `close`; rechaza fallos con resultados seguros y obliga a completar la paginación antes de decidir. El contrato de registro es únicamente un preview `executable=false` y rechaza HTTP, localhost, IP, `trycloudflare`, rutas distintas y query strings.

La compatibilidad oficial del webhook v2 también está recorrida bajo `off`: el formulario `ONIMBOTV2MESSAGEADD` autenticado produce `connector_locked_off`, con identidad verificada y cero persistencia, NIA o Bitrix.

El runner efímero ya compone el OAuth almacenado, renueva una sola vez únicamente ante `expired_token` y cierra Mongo/OAuth/HTTP. La consulta real confirmó `rest_revision=35`, lista completa sin el código `nia_next_openline_controlled`, `existing_bot_id=null` y `registration_needed=true`; esto no ejecutó registro.

G2 dispone ahora de un runner one-shot inyectable y probado exclusivamente
con dobles. El cliente solo puede invocar `imbot.v2.Bot.register`; el runner
exige el preflight exacto, valida todos los campos seguros de la respuesta y
hace como máximo un intento. Una segunda ejecución con el mismo bot ya
compatible termina como idempotente sin otra mutación. El rollback queda como
preview fijo de `imbot.v2.Bot.unregister`, `executable=false`, sin capacidad de
ejecución en ese cliente.

G2 fue ejecutado una vez con autorización especial. Antes del alta se detectó
y corrigió que las respuestas oficiales de registro/lista no incluyen
`webhookUrl`; exigirlo habría producido un falso fallo después de una mutación
correcta. El payload exacto sí fijó la URL estable. Bitrix creó el bot
`373259`, la lista posterior verificó sus campos documentados y la Línea 13
conservó el bot `245339` sin cambios. El bot propio queda registrado pero no
vinculado.

La vinculación del Camino B dispone ahora de un coordinador hermético separado.
Valida `373259 + chat78733 + CONFIG_ID 13`, ventana vigente, barreras `off` y
snapshot original; admite como máximo una vinculación inyectada. El rollback a
`245339` se ejecuta en `finally` aun si la actualización se aplicó y luego se
perdió la respuesta. Un rollback rechazado queda como estado terminal visible;
nunca se oculta como éxito. Este coordinador todavía no posee transporte real.

El límite HTTP futuro también está aislado en `openline_update_adapter.py`.
Solo publica `imopenlines.config.update`, acepta los dos contratos exactos de
vinculación/restauración y cada instancia se consume una vez. Tras
`result=true` obliga a leer `CONFIG_ID=13` mediante el cliente `config.get` y
comparar los cinco campos. Los resultados ambiguos nunca se reintentan: quedan
`uncertain` para que el coordinador ejecute rollback con una instancia nueva.

`openline_link_composition.py` enlaza ahora el coordinador con dos pares HTTP
independientes: uno para vincular y otro para restaurar. El proveedor OAuth y
su contenedor se reciben por inyección; el token se solicita una sola vez,
únicamente después de validar alcance, ventana y barreras. Cada mutación usa
una instancia one-shot distinta y toda salida cierra primero los cuatro
clientes y luego el contenedor OAuth. La composición no carga `.env`, no
renueva tokens, no reintenta mutaciones y todavía no tiene CLI real.

El runner `openline_r0_runner.py` añade la compuerta inmediatamente superior.
Exige literalmente `VINCULAR 373259 LINEA 13 CHAT78733 Y RESTAURAR 245339`
antes de construir recursos. Después abre el OAuth almacenado desde una
fábrica que recibe configuración ya inyectada, obtiene un único token, relee
el diálogo y la configuración y exige el snapshot original completo. Solo con
esa evidencia crea una ventana fija de diez minutos y delega en la composición
reversible. No carga `.env`, no renueva el token, no reintenta y no ofrece CLI.

`openline_r0_cli.py` ofrece ahora la única entrada manual prevista. Su parser
solo admite la frase completa y un timeout; no acepta bot, chat, línea, URL,
token o método variables. Cuando sea autorizada, cargará `.env` localmente y
entregará `ConnectorSettings` al runner una sola vez. La sonda posterior a la
vinculación recorre el handler G0 real mediante ASGI en memoria, con identidad
controlada y sin socket, y combina esa respuesta con las barreras reconsultadas
del mismo settings. La salida JSON contiene únicamente el resultado tipado y
reduce cualquier excepción a `r0_cli_failed_safe`.

El go/no-go real de solo lectura del 27 de julio de 2026 terminó `NO-GO` antes
de obtener datos del bot o de la línea: el token OAuth almacenado estaba
vencido y ambos clientes devolvieron `token_expired`. La consulta no renovó el
token, no llamó `config.update`, no ejecutó la CLI R0 y cerró Mongo/OAuth/HTTP.
Las barreras locales sí permanecieron `off/locked/no-external`, piloto apagado
y parada de emergencia activa. Se requiere autorización separada para una
renovación única antes de repetir estas lecturas.

La renovación separada fue autorizada y ejecutada exactamente una vez el mismo
día. El proveedor OAuth la completó y persistió sin exponer secretos. Las
cuatro lecturas posteriores emitieron `GO`: revisión REST `35`, bot `373259`
existente y compatible, `chat78733`, `CONFIG_ID=13` y snapshot original
`Y / always / 245339 / 0 / close`, con los cuatro bots auxiliares en `0`.
Permanecieron `off/locked/no-external`, piloto apagado y parada activa. Los
recursos cerraron y no hubo `config.update`, vinculación, CLI R0 ni mensajes.

La sonda local sintética de la primera CLI no demostraba recepción real ni
permitía el turno humano. Fue sustituida por una compuerta inyectable que se
arma antes de vincular, acepta solo `member_id + bot 373259 + chat78733 +
78733` dentro de la ventana y conserva únicamente hash e identidades. El
handler G0 puede entregarle un recibo real que debe terminar
`connector_locked_off`, sin persistencia, NIA o escritura Bitrix. La espera es
de 180 segundos, con máximo absoluto de 300, y timeout, divergencia o error
obligan a restaurar `245339`. Mientras no exista un puente real entre el
proceso web y el coordinador, la CLI se bloquea antes de OAuth con
`r0_receipt_gate_required`.

El puente entre procesos ya tiene una implementación aislada y un montaje
opcional exclusivo de G0. El proceso web admite una sola sesión en memoria,
conserva el identificador de
corrida únicamente como SHA-256 y ofrece cuatro operaciones autenticadas:
armar, consultar, consumir y desarmar. La autenticación reutiliza el contrato
de revisor y ocurre antes de leer JSON. La sesión expira en diez minutos como
máximo y se elimina al consumir o cerrar. El cliente mantiene token e
identificador como secretos, consulta con frecuencia acotada y consume un solo
recibo. Una prueba ASGI completa recorrió vínculo simulado, webhook G0,
consulta, consumo y rollback a `245339`. El router solo se monta con
`NIA_BITRIX_R0_BRIDGE_ENABLED=true`; el valor seguro predeterminado es `false`.
La CLI compone su cliente únicamente con ese switch, autenticación completa y
las barreras `off/locked/no-external`. No se publicó ni desplegó esta
composición y este corte no habilita una ejecución real.

El ingreso G0 dispone de una fábrica ASGI mínima: exige un origen HTTPS estable con host exacto, rechaza localhost, IP, `trycloudflare`, comodines y puertos no estándar, y por defecto expone únicamente `GET /healthz` y `POST /bitrix-connector/webhook`. Las cuatro rutas R0 solo aparecen con el switch independiente exacto. No incorpora runtime, startup, documentación, instalación OAuth, Review Admin, CORS, servidor ni túnel. Bajo `off`, el formulario v2 autenticado termina `connector_locked_off` con cero persistencia, NIA o Bitrix.

La capa G0 limita por defecto el cuerpo completo a 256 KiB, cada solicitud a 5 segundos y la tasa global a 60 solicitudes por 60 segundos. El exceso de tamaño se comprueba por `Content-Length` y nuevamente mientras se reciben fragmentos; el timeout cancela la tarea y las respuestas de rechazo no se almacenan en caché. La ventana conserva como máximo 60 marcas.

`G0StopController` ofrece una parada terminal local sin ruta HTTP de reactivación: bloquea solicitudes nuevas, cancela las que estén en curso y mantiene `/healthz` disponible con `accepting_webhooks=false`. Tanto la tasa como la parada pertenecen a un único proceso; el primer ensayo debe conservar un solo worker hasta diseñar coordinación compartida.

Antes de desplegar G0 todavía debe elegirse una topología y un hostname HTTPS estable, y definirse el mecanismo propietario que activará la parada local. El registro, la vinculación al Canal Abierto, el desbloqueo `review` y cada ensayo R0–R3 requieren autorizaciones separadas.
