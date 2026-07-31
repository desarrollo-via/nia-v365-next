# Diseño Bitrix-only de observación R0 por historial

Estado: **IMPLEMENTACIÓN LOCAL 9/18 COMPLETADA · CERO LLAMADAS REALES · CERO MUTACIONES**

## Decisión

R0 observará el primer mensaje controlado únicamente a través de Bitrix. Wazzup,
Sidecar, sus claves, webhooks, canales y suscripciones quedan fuera del camino.
También quedan congelados la Línea 13, el bot productivo `245339`, el bot
controlado `373259`, sus participantes y todas las vinculaciones.

La entrega push no puede obtenerse de forma documentada sin cambiar estado:

- `OnOpenLineMessageAdd` sólo entrega a una aplicación eventos de conectores
  agregados por esa misma aplicación; el conector Wazzup vigente es ajeno.
- `im.v2.Event.subscribe` crea una suscripción del usuario y su cola es exclusiva:
  una aplicación puede confirmar y retirar eventos que otra esperaba.
- El bot `373259` es `openline`; ese tipo se comporta como un bot normal y no
  recibe garantizadamente todos los mensajes mientras no esté vinculado o
  incorporado al diálogo.
- Un bot nuevo `supervisor` podría recibir todos los mensajes de los chats donde
  participe, pero registrarlo e incorporarlo sería una mutación Bitrix futura,
  visible y sujeta a la doble confirmación protegida.

Por ello, el primer ensayo no afirmará recepción push. Demostrará únicamente que
`nia-next` puede observar por OAuth un mensaje nuevo del diálogo controlado,
clasificarlo con identidad suficiente y terminar inerte.

Referencias oficiales:

- <https://apidocs.bitrix24.com/api-reference/imopenlines/openlines/events/on-open-line-message-add.html>
- <https://apidocs.bitrix24.com/api-reference/chat-bots/chat-bots-v2/index.html>
- <https://apidocs.bitrix24.com/api-reference/chat-bots/chat-bots-v2/im.v2/events/event-get.html>
- <https://apidocs.bitrix24.com/api-reference/imopenlines/openlines/sessions/imopenlines-dialog-get.html>
- <https://apidocs.bitrix24.com/api-reference/imopenlines/openlines/sessions/imopenlines-session-history-get.html>

## Superficie REST exacta

El futuro cliente tendrá únicamente tres operaciones públicas:

1. `get_dialog(dialog_id)` → `imopenlines.dialog.get`.
2. `get_session_history(session_id)` → `imopenlines.session.history.get`.
3. `close()`.

No ofrecerá una llamada REST genérica. Ambos métodos Bitrix se invocan como POST
HTTPS porque así funciona REST Bitrix, pero son operaciones documentadas de
lectura. Quedan prohibidos `event.bind`, `im.v2.Event.subscribe`, métodos `imbot`,
mensajería, participantes, configuración, conectores y cualquier método de
creación, actualización o eliminación.

El diálogo queda fijado en `dialog_id=chat78733` y `chat_id=78733`. La primera
lectura debe devolver exactamente ese diálogo, `entity_type=LINES`, un rol con
acceso, un `last_message_id` entero positivo y un `SESSION_ID` positivo extraído
del sexto segmento de `entity_data_1`. No se usarán `CHAT_ID` o sesión inferidos
de otro diálogo.

## Secuencia one-shot

### Preflight y ancla

1. Obtener un único token OAuth ya almacenado mediante una fábrica protegida e
   inyectada. No cargar `.env`, no renovar automáticamente y no imprimir valores.
2. Ejecutar una vez `imopenlines.dialog.get`; la interfaz recibe
   `dialog_id=chat78733`, valida su forma exacta y envía el `CHAT_ID=78733`
   requerido por el método REST, sin aceptar otra identidad.
3. Validar diálogo, tipo, acceso y sesión; conservar en memoria únicamente
   `SESSION_ID` y `baseline_last_message_id`.
4. Revalidar localmente `off/locked/no-external`, piloto apagado y parada de
   emergencia activa antes de armar la espera.

### Espera

- Duración normal: 180 segundos; máximo absoluto: 300 segundos.
- Sondeo: una lectura `imopenlines.dialog.get` cada 5 segundos.
- Máximo normal: 36 sondeos; máximo absoluto: 60.
- Timeout por llamada: 10 segundos; cero reintentos internos, concurrencia,
  paginación o llamadas paralelas.
- Cada lectura debe conservar el mismo diálogo y `SESSION_ID`.
- Mientras `last_message_id` sea igual al ancla no se consulta el historial.
- Una disminución, sesión nueva, identidad distinta, error, timeout o respuesta
  ambigua termina en `NO-GO`.

### Lectura única del mensaje

Cuando `last_message_id` aumente, se ejecuta exactamente una vez
`imopenlines.session.history.get` con el `SESSION_ID` fijado. No vuelve a
consultarse el historial, incluso si la respuesta es incompleta o ambigua.

La respuesta se limita a 2 MiB. Como Bitrix devuelve el historial completo de la
sesión y no ofrece un límite en este método, todo exceso termina en `NO-GO`; no se
intenta paginar ni usar otra API. El contenido histórico se mantiene sólo en
memoria el tiempo indispensable para seleccionar candidatos y se descarta al
cerrar.

Un recibo válido exige:

- exactamente un mensaje no sistémico con `id > baseline_last_message_id`;
- `chatid=78733` y `recipientid=chat78733`;
- fecha dentro de la ventana armada;
- autor presente en el mapa `users` con `connector=true`;
- texto no vacío y coincidencia con el hash esperado del mensaje controlado;
- ningún segundo mensaje externo o de operador posterior al ancla.

El texto, nombres, IDs de autor, `entity_id`, metadatos del conector, mensajes
anteriores, archivos y cuerpos Bitrix nunca se imprimen, persisten o incluyen en
errores. No se descargan adjuntos.

## Frontera con el conector

La lectura de historial no se presentará falsamente como
`ONIMBOTV2MESSAGEADD`: no existe bot destinatario ni `application_token` de un
evento webhook. El adaptador futuro deberá producir una entrada separada con
origen fijo `bitrix_history_r0`, identidad comprobada y texto efímero.

Esa entrada sólo puede recorrer la compuerta R0 inerte y terminar con:

- `connector_locked_off`;
- `persisted=false`;
- `nia_called=false`;
- `bitrix_written=false`.

No puede alcanzar el worker activo, NIA, OpenAI, Mongo de negocio o un cliente de
escritura Bitrix.

## Salida redactada

La salida allowlisted contendrá únicamente:

- `status`: `READY`, `RECEIVED` o `NO-GO`;
- `reason`: código fijo;
- `dialog_read_calls`, `history_read_calls` y `mutation_calls`;
- `dialog_verified`, `session_verified` y `baseline_captured`;
- `new_last_message_detected`, `candidate_count` y
  `controlled_message_verified`;
- `connector_locked_off`, `persisted`, `nia_called` y `bitrix_written`;
- `resources_closed`.

Nunca mostrará mensajes, hashes, tokens, URI, nombres, teléfonos, IDs protegidos,
cabeceras, cuerpos o errores remotos libres.

## Cierre y detención

El cliente OAuth/HTTP se cierra en `finally` ante éxito, timeout, cancelación o
error. La espera admite cancelación humana inmediata. Un cierre no verificado
queda como fallo terminal visible.

La prueba se detiene sin mensaje aceptado ante cualquier barrera degradada,
identidad divergente, sesión nueva, más de un candidato, respuesta excesiva,
OAuth vencido, timeout o error. No hay rollback externo porque el diseño no
modifica Bitrix ni Wazzup.

## Alcance de la evidencia

Un resultado `RECEIVED` probará sólo lectura controlada desde Bitrix y recorrido
inerte local. No probará webhook, push, tiempo real, participación de bot,
respuesta NIA ni capacidad de escribir en Bitrix. Cualquier arquitectura futura
en tiempo real requerirá una decisión separada y, si incorpora un bot o una
suscripción, el preflight y las dos confirmaciones protegidas aplicables.

## Implementación local de 9/18

- `bitrix_connector/bitrix_history_r0_client.py`: dos lecturas públicas y
  `close`, endpoints fijos, timeout máximo de 10 segundos, límite de 2 MiB y
  errores cerrados sin cuerpos remotos.
- `bitrix_connector/bitrix_history_r0_adapter.py`: origen
  `bitrix_history_r0`, selección por identidad, ventana y hash, con texto
  efímero excluido de la salida.
- `bitrix_connector/bitrix_history_r0_runner.py`: barreras obligatorias,
  180/300 segundos, 36/60 sondeos, un solo historial y salida inerte allowlisted.
- Tres módulos de pruebas con dobles locales aprobaron junto con la prueba G0:
  20/20, sin `.env`, red, OAuth real, servicios ni mutaciones externas.

La regresión completa, revisión de secretos, allowlist Git y rollback local se
aprobaron de forma separada en `10/18`.

## Allowlist Git y rollback local de 10/18

La allowlist exacta del corte contiene diez rutas:

1. `bitrix_connector/__init__.py`
2. `bitrix_connector/bitrix_history_r0_adapter.py`
3. `bitrix_connector/bitrix_history_r0_client.py`
4. `bitrix_connector/bitrix_history_r0_runner.py`
5. `docs/bitrix_r0_history_observation_design.md`
6. `docs/wazzup_r0_passive_observation_design.md`
7. `tests/test_bitrix_g0_entrypoint.py`
8. `tests/test_bitrix_history_r0_adapter.py`
9. `tests/test_bitrix_history_r0_client.py`
10. `tests/test_bitrix_history_r0_runner.py`

`docs/bitrix_p1b_protected_settings_runbook.md` es un archivo local previo y
queda expresamente fuera. `nia_next.md` conserva continuidad y tampoco forma
parte de la allowlist Git.

Antes de crear un commit, el rollback local exacto al `HEAD`
`41a76de480d4cc21ab8e2711b06331aabc66cd16` consiste en restaurar sólo las tres
rutas versionadas:

```powershell
git restore --source=41a76de480d4cc21ab8e2711b06331aabc66cd16 -- bitrix_connector/__init__.py docs/wazzup_r0_passive_observation_design.md tests/test_bitrix_g0_entrypoint.py
```

y eliminar únicamente las siete rutas nuevas de esta allowlist:

```powershell
Remove-Item -LiteralPath bitrix_connector/bitrix_history_r0_adapter.py,bitrix_connector/bitrix_history_r0_client.py,bitrix_connector/bitrix_history_r0_runner.py,docs/bitrix_r0_history_observation_design.md,tests/test_bitrix_history_r0_adapter.py,tests/test_bitrix_history_r0_client.py,tests/test_bitrix_history_r0_runner.py
```

Después debe verificarse que esas diez rutas ya no aparezcan en `git status
--short`, que el índice continúe vacío y que el runbook P1-B siga presente y
sin seguimiento. Estos comandos quedan documentados pero **no ejecutados**.
Después de un commit futuro, el rollback cambiará a un `git revert` exclusivo
de ese commit, sujeto a una autorización separada.

La evidencia de `10/18` confirmó 579/579 pruebas, compilación en memoria de 228
archivos Python, allowlist exacta 10/10, índice vacío, cero whitespace y cero
firmas de secretos de alta confianza. El rollback quedó validado en solo lectura:
3/3 rutas existen en el `HEAD` y las 7/7 rutas nuevas están ausentes de él.
