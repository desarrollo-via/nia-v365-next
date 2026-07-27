# Checklist de registro y primer piloto controlado

## Alcance

Este checklist prepara el registro del bot propio `nia_next_openline_controlled`
y el primer evento real R0. No autoriza por sí mismo despliegues, cambios de
Azure, registro de bots, creación o edición de Líneas Abiertas, lectura de
mensajes ni activación del conector.

El módulo seguirá alojado, con costo incremental previsto cero, dentro de
`nia-v365-next-api`. El proceso web y el worker permanecen separables; el
switch maestro puede desmontar el módulo sin afectar las rutas normales de
NIA Next.

## Estado confirmado antes del checklist

- Producción responde en `/health`, pero no publica rutas
  `/bitrix-connector` porque `NIA_BITRIX_MODULE_ENABLED` está ausente.
- El worker no está iniciado.
- El modo efectivo sigue `off`, con activación bloqueada y llamadas externas
  deshabilitadas.
- Nuestra aplicación no posee bots Open Line y el bot actual `245339` no le
  pertenece.
- El chat conocido `chat78733` pertenece a `CONFIG_ID=13`, cuya selección del
  bot de bienvenida es global para toda esa Línea Abierta.
- Existe un preview local no ejecutable para registrar el bot propio,
  vincularlo y restaurar los cinco campos originales.

## Decisión adoptada

El usuario eligió reutilizar la Línea Abierta productiva `CONFIG_ID=13`, el
canal WAZZUP existente y el chat controlado `chat78733` de la negociación
`614949`. El Camino B queda seleccionado para evitar recursos y costos
adicionales; el Camino A se conserva únicamente como alternativa.

La allowlist exacta limita el conector a la identidad controlada, pero no aísla
la incorporación del bot dentro de Bitrix: la selección del bot de bienvenida
es global para toda la línea 13. Por ello cada prueba requiere una ventana muy
corta, ausencia operativa de otros ingresos, snapshot previo y restauración
inmediata del bot `245339` con sus cinco campos originales.

`NIA_BITRIX_MODULE_ENABLED=true` solo significa que el módulo está disponible.
No equivale a `active`: R0 conserva `off/locked/no-external`; `review`, `shadow`
y `active` se habilitan, prueban y revierten en etapas posteriores e
independientes. Fuera de una prueba el modo vuelve a `off` y la parada de
emergencia permanece activa.

## Camino A — Alternativa no seleccionada

### A0 — Preparación local completada

- [x] Código del bot estable: `nia_next_openline_controlled`.
- [x] Contrato de registro `imbot.v2.Bot.register` no ejecutable.
- [x] Lectores limitados a `imbot.v2.Revision.get`, `imbot.v2.Bot.list`,
  `imopenlines.dialog.get` e `imopenlines.config.get`.
- [x] Preview `imopenlines.config.update` no ejecutable.
- [x] Rollback exacto y advertencia `impact_scope=open_line_global`.
- [x] Pruebas herméticas con dobles locales.

### A1 — Montar el router web todavía inerte

Autorización externa independiente.

- [x] Confirmar que el código desplegado conserva el switch maestro y que el
  hostname estable será el ya administrado por `nia-v365-next-api`.
- [x] Proyectar exclusivamente los nombres requeridos de App Settings, sin
  leer o mostrar sus valores.
- [x] Mantener el startup Gunicorn actual; no cambiar todavía al launcher del
  worker.
- [x] Habilitar el montaje web con `NIA_BITRIX_MODULE_ENABLED=true` mediante
  una autorización específica. Este cambio reinicia el Web App.
- [x] Confirmar `/bitrix-connector/health` y
  `/bitrix-connector/webhook` dentro de `nia-v365-next-api`.
- [x] Inventariar las demás rutas montadas y comprobar que las superficies de
  instalación, revisión y auditoría continúan protegidas o inertes; el router
  integrado no expone únicamente dos rutas.
- [x] Mantener `effective_mode=off`, `activation_locked=true`,
  `external_calls_enabled=false`, piloto deshabilitado y parada activa.
- [x] Confirmar que el worker no se inició: el startup sigue siendo Gunicorn
  directo a `main:app`, no `nia_process_launcher`.
- [x] Verificar que `/health`, `/nia/chat` y `/nia/chat/archivo` siguen
  presentes.
- [x] Verificar desde Internet solo salud y un POST sintético sin secretos.
- [x] Confirmar que el POST termina inerte, sin persistencia, NIA o Bitrix.

**Criterio de parada:** cualquier regresión en NIA, ruta Bitrix ausente,
respuesta no inerte o barrera distinta de la esperada impide A2.

#### Evidencia del preflight A1 de solo lectura — 26 de julio de 2026

- Web App: `nia-v365-next-api`, estado `Running`, HTTPS obligatorio y hostname
  estable
  `nia-v365-next-api-ekd4fza7e0fzevfd.canadacentral-01.azurewebsites.net`.
- Runtime: `PYTHON|3.12`, un worker, `alwaysOn=false`, sin health check de
  plataforma y Gunicorn directo a `main:app` con el comando observado.
- Producción respondió HTTP 200 en `/health` y `/openapi.json`; conserva
  `/nia/chat` y `/nia/chat/archivo`.
- El OpenAPI productivo contiene cuatro paths y cero paths
  `/bitrix-connector`; `GET /bitrix-connector/health` respondió 404.
- Se proyectó únicamente la presencia de nueve nombres de App Settings, nunca
  sus valores. Están ausentes: `NIA_BITRIX_MODULE_ENABLED`,
  `NIA_BITRIX_MODE`, `NIA_BITRIX_INSTALLATION_ENABLED`,
  `NIA_BITRIX_PILOT_ENABLED`, `NIA_BITRIX_PILOT_EMERGENCY_STOP`,
  `NIA_BITRIX_PILOT_RULES_JSON`, `NIA_BITRIX_DOMAIN`,
  `NIA_BITRIX_MEMBER_ID` y `NIA_BITRIX_APPLICATION_TOKEN`.
- La ausencia conserva los predeterminados locales: módulo desmontado, modo
  efectivo `off`, activación bloqueada, llamadas externas deshabilitadas,
  instalación deshabilitada, piloto deshabilitado, parada activa y reglas
  vacías.
- Al montar el módulo bajo Gunicorn, `ConnectorStorageFactory` y
  `ReviewDecisionRuntime` fallan antes de construir Mongo por las barreras
  `off/locked/no-external`; el worker tampoco puede iniciarse porque el startup
  no usa `nia_process_launcher`.
- El router local que se montaría contiene 14 operaciones: salud, webhook,
  instalación, diagnóstico de instalación, lectura/revisión, cuatro decisiones
  administrativas y auditoría. Instalación permanece deshabilitada; revisión,
  decisiones y auditoría fallan cerradas sin credencial/runtime.

**Decisión A1:** técnicamente listo para proponer un montaje web inerte, pero
no ejecutado. El cambio mínimo debe agregar explícitamente seis controles
seguros y nada más:

```text
NIA_BITRIX_MODULE_ENABLED=true
NIA_BITRIX_MODE=off
NIA_BITRIX_INSTALLATION_ENABLED=false
NIA_BITRIX_PILOT_ENABLED=false
NIA_BITRIX_PILOT_EMERGENCY_STOP=true
NIA_BITRIX_PILOT_RULES_JSON=[]
```

No se necesitan todavía dominio, `member_id`, `application_token`, OAuth,
Mongo propio, `NIA_BASE_URL` o secretos para verificar salud y un rechazo
sintético inerte. No debe probarse un evento auténtico hasta un SP posterior.

**Rollback exacto del montaje A1:** si salud o rutas normales fallan, eliminar
los seis nombres agregados —todos estaban ausentes— y verificar después del
reinicio que `/health` vuelve a 200, las rutas NIA permanecen y
`/bitrix-connector/health` vuelve a 404. No cambiar startup, código ni otros App
Settings.

#### Primer intento A1 y rollback — 26 de julio de 2026

- La fotografía inmediata confirmó seis nombres ausentes, `/health=200` y
  `/bitrix-connector/health=404`.
- Azure aceptó exactamente los seis App Settings previstos y no se modificaron
  startup, código u otros nombres.
- Diez comprobaciones iniciales conservaron NIA en 200 y Bitrix en 404. Al no
  observar el montaje dentro de esa ventana se ejecutó el rollback acordado.
- Azure eliminó exactamente los seis nombres. Durante la propagación del
  rollback, una lectura transitoria mostró 18 paths totales, 14 paths Bitrix y
  `/bitrix-connector/health=200`: esto demuestra que el montaje anterior sí
  llegó a la instancia, pero después de la ventana inicial de observación.
- La siguiente comprobación ya mostró NIA 200 y Bitrix 404. La fotografía final
  estable confirmó cero de seis nombres, cuatro paths totales, rutas NIA
  presentes y cero paths Bitrix.
- No se envió el POST sintético porque no se alcanzó un estado estable con el
  router montado antes de iniciar el rollback. No se llamó a Bitrix, MongoDB,
  NIA chat, OpenAI, ViaIndustrial o WhatsApp.

**Lección operativa:** el próximo intento debe esperar la convergencia conjunta
de App Settings y proceso HTTP durante una ventana mayor y observar dos lecturas
consecutivas de `/bitrix-connector/health=200` antes de evaluar el cuerpo de
salud o enviar el POST sintético. La demora por sí sola no autoriza ampliar el
cambio ni inspeccionar logs o secretos.

#### Segundo intento A1 completado — 26 de julio de 2026

- La fotografía previa volvió a confirmar cero de seis nombres, NIA 200 y
  Bitrix 404.
- Azure aplicó los mismos seis controles, sin agregar otros nombres ni cambiar
  startup. NIA permaneció en 200 durante toda la convergencia.
- Bitrix continuó en 404 durante 13 intentos; los intentos 14 y 15 devolvieron
  200 consecutivamente. No se activó rollback por una demora sin regresión.
- El health seguro confirmó versión productiva del conector `v0.097`, modo
  solicitado y efectivo `off`, `activation_locked=true`,
  `external_calls_enabled=false`, runtime `inert`, cero servicio/recursos,
  piloto deshabilitado, parada activa y cero reglas.
- Los seis nombres permanecen presentes. Gunicorn continúa directo a
  `main:app`; no se inició el worker.
- OpenAPI contiene 18 paths: las cuatro rutas previas y 14 operaciones bajo
  `/bitrix-connector`. `/nia/chat` y `/nia/chat/archivo` permanecen presentes.
- El único POST sintético usó el evento ficticio `NIA_A1_SYNTHETIC`, ids `1`,
  dominio `synthetic.invalid` y ningún token. Respondió HTTP 200,
  `ignored/unsupported_event`, identidad no verificada, modo `off`, sin
  persistencia, NIA o escritura Bitrix.
- La fotografía final confirmó NIA 200, Bitrix 200 y todas las barreras
  invariantes. El router web queda montado e inerte; el rollback sigue
  preparado pero no fue necesario.

**Estado A1:** completado. Esto demuestra disponibilidad del ingreso sintético,
no recepción de un evento auténtico. No habilita A2, registro de bot, Línea
Abierta, worker, Mongo, NIA o envíos reales sin sus autorizaciones propias.

### A2 — Confirmar capacidad de prueba en Bitrix

Lectura o inspección humana separada; todavía sin crear objetos.

- [x] Confirmar que el plan permite otra Línea Abierta sin costo adicional del
  plan Bitrix.
- [ ] Confirmar que puede usarse un canal/contacto de prueba controlado sin
  conectar el WAZZUP productivo.
- [ ] Definir nombre visible de la línea, por ejemplo
  `NIA PILOTO CONTROLADO`.
- [ ] Confirmar que no tiene cola, automatizaciones o tráfico productivo
  heredado.

**Criterio de parada:** si exige pago, altera el canal productivo o no puede
aislarse, no se crea y se vuelve a decisión humana.

#### Evidencia A2 — 26 de julio de 2026

La documentación oficial vigente define estos límites de Líneas Abiertas:

- Free: 1.
- Basic: 2.
- Standard: 10.
- Professional y Enterprise: ilimitadas.

Referencias:

- [FAQ oficial de Contact Center](https://helpdesk.bitrix24.com/open/25813887/)
- [Comparación oficial de planes](https://www.bitrix24.com/prices/compare_cloud_plans.php)
- [`app.info` y campos de licencia](https://apidocs.bitrix24.com/api-reference/common/system/app-info.html)

`app.info` puede devolver `LICENSE` y `LICENSE_TYPE`; el inventario mínimo se
obtiene con `imopenlines.config.list.get`. Ambos requieren una autenticación
Bitrix válida.

El único runner OAuth local disponible carga `.env`. No se ejecutó porque el
protocolo prohíbe leer ese archivo, incluso indirectamente. El proceso actual
tampoco contiene las variables necesarias en su entorno. No se usaron tokens,
Mongo, webhooks heredados ni credenciales de navegador.

La captura aportada por el usuario muestra el plan **Professional**, válido
hasta el 3 de septiembre de 2026. Como ese plan admite Líneas Abiertas
ilimitadas, queda confirmada la capacidad para una línea de prueba adicional y
no es necesario contar las líneas existentes.

**Estado A2 de capacidad:** completado. Esta conclusión evita un costo adicional
del plan Bitrix; no demuestra que un canal o proveedor externo sea gratuito.
Todavía debe seleccionarse un canal de prueba sin costo, aislado de WAZZUP y del
tráfico productivo, antes de crear la línea.

### A3 — Crear la línea y obtener la identidad controlada

Mutación Bitrix independiente. No registra ni vincula aún el bot.

- [ ] Crear únicamente la Línea Abierta/canal de prueba aprobado.
- [ ] Abrir un chat de prueba controlado por el usuario.
- [ ] Obtener por lectura `CONFIG_ID`, `chat_id`, `dialog_id`, conector e
  identidad CRM resultantes.
- [ ] Ejecutar el preflight local y conservar el snapshot completo de los
  cinco campos de bienvenida.
- [ ] Construir la allowlist exacta con la identidad nueva; no reutilizar
  automáticamente `chat78733`.

### A4 — Validar y registrar el bot propio sin vincularlo

Mutación Bitrix independiente.

- [x] Revalidar el hostname HTTPS estable y la ruta exacta
  `/bitrix-connector/webhook`.
- [x] Repetir `Revision.get` y la lista completa de bots de la aplicación.
- [x] Confirmar que no existe un bot compatible con el código estable.
- [x] Mostrar el payload redactado de registro y obtener aprobación.
- [x] Ejecutar una sola llamada idempotente a `imbot.v2.Bot.register`.
- [x] Conservar únicamente `bot_id`, código, tipo y modo como evidencia.
- [x] Confirmar que el bot registrado todavía no está vinculado a una línea.

**Rollback disponible:** `imbot.v2.Bot.unregister` solo para el `bot_id`
obtenido, mediante autorización separada y después de confirmar que no está
vinculado.

#### Preparación local de A4 completada

- [x] Cliente de mutación limitado a `imbot.v2.Bot.register`; no expone
  método REST genérico ni desregistro.
- [x] Runner one-shot que exige preflight `ready`, valida el contrato exacto
  de `nia_next_openline_controlled` y hace como máximo un intento.
- [x] Segunda ejecución con preflight `existing_compatible` resuelta como
  idempotente, sin una segunda mutación y conservando el mismo `bot_id`.
- [x] Resultado de alta validado contra código, tipo, soporte Open Line, modo,
  webhook y barreras visuales antes de aceptarlo.
- [x] Preview de `imbot.v2.Bot.unregister` fijo, no ejecutable y sujeto a una
  autorización independiente.
- [x] Dobles locales y suite completa aprobados sin leer `.env` ni conectarse
  con Bitrix.

#### Evidencia real de A4

- Salud pública previa: `off`, `activation_locked=true`, llamadas externas
  deshabilitadas, piloto apagado y parada de emergencia activa.
- Revisión REST 35 y preflight previo sin bot propio compatible.
- Una única llamada real registró `nia_next_openline_controlled` con
  `bot_id=373259`, tipo `openline`, soporte Open Line y modo `webhook`.
- La lista posterior confirmó el mismo bot como compatible. La respuesta
  oficial no proyecta `webhookUrl`; su valor exacto queda demostrado por el
  payload validado que se envió.
- `CONFIG_ID=13` conservó exactamente `Y / always / 245339 / 0 / close` y los
  cuatro bots auxiliares en `0`; el bot nuevo no fue vinculado.
- No se enviaron mensajes, no se inició worker y no se ejecutó desregistro.
- La salud pública posterior conservó `off/locked/no-external`, piloto
  apagado y parada de emergencia activa.

### A5 — Vincular el bot a la línea de prueba

**ATENCIÓN ESPECIAL DEL USUARIO.** Es el primer cambio que puede provocar que
Bitrix entregue eventos reales al webhook.

- [ ] Mostrar `CONFIG_ID`, nombre de la línea, bot anterior y bot nuevo.
- [ ] Confirmar que la línea es exclusivamente de prueba y no es la 13.
- [ ] Confirmar parada activa, worker detenido y modo real `off`.
- [ ] Mostrar juntos el payload de vinculación y el rollback exacto.
- [ ] Obtener autorización inmediata para una sola actualización.
- [ ] Ejecutar `imopenlines.config.update` únicamente sobre los cinco campos
  del bot de bienvenida.
- [ ] Releer la línea y comprobar que coincide con el preview.

### A6 — R0, un evento real pero inerte

**ATENCIÓN ESPECIAL DEL USUARIO.** El usuario avisa justo antes de enviar un
único texto distintivo desde el chat de prueba.

- [ ] Abrir una ventana UTC corta en la allowlist sin retirar la parada ni el
  bloqueo `off`.
- [ ] Enviar un único mensaje desde el contacto/chat controlado.
- [ ] Confirmar autenticidad y coincidencia exacta de `member_id`, `bot_id`,
  `dialog_id` y `chat_id`.
- [ ] Confirmar resultado `connector_locked_off`.
- [ ] Confirmar `persisted=false`, `nia_called=false` y
  `bitrix_written=false`.
- [ ] Probar que una identidad distinta falla cerrada mediante evidencia del
  receptor, sin generar otro chat real deliberadamente.
- [ ] Cerrar la ventana inmediatamente.

### A7 — Cierre de R0

- [ ] Restaurar el snapshot anterior de la línea de prueba o desvincular el
  bot, según lo aprobado en A5.
- [ ] Releer la configuración y verificar la restauración exacta.
- [ ] Mantener el bot registrado pero sin línea solo si habrá R1 próximo; de
  lo contrario proponer su desregistro por separado.
- [ ] Mantener módulo, worker y llamadas externas apagados.
- [ ] Conservar auditoría redactada; no borrar chats ni mensajes.

## Camino B — Ventana sobre la línea 13

Este es el camino seleccionado. Conserva la negociación `614949` y reutiliza
los recursos existentes, pero no puede aislar la incorporación del bot a otros
diálogos de la misma Línea Abierta.

**ATENCIÓN ESPECIAL REFORZADA:** requiere una autorización que mencione
literalmente `CONFIG_ID=13`, `chat78733`, el riesgo global y la restauración
inmediata de `Y / always / 245339 / 0 / close`.

La decisión documental ya fue autorizada. La vinculación real continúa siendo
una autorización externa separada y deberá reconfirmarse justo antes de
guardar el cambio en Bitrix.

Antes de vincular:

- [ ] Confirmar ausencia operativa de otros ingresos durante una ventana muy
  corta.
- [ ] Releer y comparar el snapshot; cualquier cambio cancela el ensayo.
- [ ] Confirmar bot propio, allowlist exacta y rollback listo.
- [ ] Mantener `off/locked/no-external`, parada activa y worker detenido.

Después de vincular:

- [ ] Ejecutar solo R0 con un mensaje controlado.
- [ ] Restaurar inmediatamente los cinco campos, incluso si R0 falla.
- [ ] Releer `CONFIG_ID=13` y demostrar la restauración exacta.
- [ ] No avanzar a R1 en la misma ventana.

### Validación hermética del Camino B — 26 de julio de 2026

- [x] Construir el snapshot de `CONFIG_ID=13` con los cinco campos originales.
- [x] Simular la sustitución temporal de `245339` por un bot propio.
- [x] Exigir allowlist exacta para `member_id + bot_id + chat78733 + 78733`.
- [x] Rechazar un chat distinto antes de cualquier acción externa.
- [x] Entregar el formulario R0 al entrypoint ASGI real, completamente en memoria.
- [x] Confirmar `connector_locked_off`, identidad verificada, cero persistencia,
  cero NIA y cero escritura Bitrix.
- [x] Aplicar el rollback simulado y comparar exactamente
  `Y / always / 245339 / 0 / close`.

La revisión detectó que el preview anterior permitía una allowlist sin límites
temporales. El constructor exige ahora `valid_from` y `valid_until` con zona
horaria y rechaza ventanas superiores a 15 minutos. Pasaron 19/19 pruebas
focales y 478/478 pruebas completas. Todo el ensayo usó dobles y transporte
ASGI en memoria; no consultó ni modificó Bitrix, WAZZUP, Azure, Mongo o NIA.

### Ensayo hermético del coordinador de vinculación — 27 de julio de 2026

- [x] Fijar el bot real ya registrado `373259` como único bot nuevo admitido.
- [x] Exigir `CONFIG_ID=13`, `chat78733`, `dialog_id=chat78733`, `member_id`
  exacto y ventana UTC vigente de máximo 15 minutos.
- [x] Rechazar snapshot distinto de `Y / always / 245339 / 0 / close` antes
  de intentar cualquier actualización.
- [x] Limitar el recorrido a una vinculación simulada y un rollback simulado.
- [x] Verificar el estado vinculado antes de ejecutar la sonda R0 en `off`.
- [x] Ejecutar el rollback desde `finally`, incluso ante pérdida de transporte
  después de aplicar la vinculación.
- [x] Releer y demostrar restauración exacta a `245339`.
- [x] Hacer terminal y visible cualquier rechazo o fallo del rollback.

El coordinador `openline_link_rehearsal.py` no contiene OAuth, cliente HTTP,
CLI ni capacidad de conectarse a Bitrix. Pasaron 14/14 pruebas focales y
495/495 completas. No se leyó `.env` ni se modificaron Bitrix, Línea 13,
WAZZUP, Azure, Mongo o NIA.

### Adaptador one-shot verificado — 27 de julio de 2026

- [x] Cliente limitado a la ruta fija `imopenlines.config.update`.
- [x] Payload limitado a `CONFIG_ID=13` y los cinco campos de bienvenida.
- [x] Únicos bot ids admitidos: `373259` para vincular y `245339` para
  restaurar.
- [x] Instancia consumible una sola vez, sin método REST genérico ni reintento.
- [x] `result=true` seguido obligatoriamente por `imopenlines.config.get`.
- [x] Timeout, 5xx y respuesta ambigua clasificados como `uncertain`, porque la
  mutación pudo haberse aplicado y debe activarse el rollback superior.
- [x] `result=false`, rechazo confirmado, conflicto de lectura y segundo uso
  diferenciados sin exponer cuerpos o tokens.

Pasaron 19/19 pruebas focales y 501/501 completas con `MockTransport`. El
adaptador no tiene CLI, no carga `.env` y no fue compuesto con OAuth real.

### Composición OAuth inyectada y reversible — 27 de julio de 2026

- [x] Dos adaptadores one-shot independientes: vinculación y rollback.
- [x] Un solo token obtenido desde un proveedor OAuth inyectado.
- [x] Cero lectura de `.env`, renovación automática o CLI ejecutable.
- [x] Validación de identidad, ventana y `off/locked/no-external` antes del
  primer acceso al proveedor.
- [x] Lectura exacta tras cada mutación y restauración final a `245339`.
- [x] Cierre en reversa de los cuatro clientes y cierre final del contenedor
  OAuth en éxito, bloqueo o excepción.
- [x] Fallo al obtener token o snapshot reducido a salida segura sin secretos.

Pasaron 14/14 pruebas focales combinadas y 504/504 completas. Todo el recorrido
usó `MockTransport` y recursos OAuth dobles; la Línea 13 real no fue tocada.

### Runner R0 fail-closed sin CLI — 27 de julio de 2026

- [x] Confirmación literal que nombra bot, Línea 13, chat y rollback.
- [x] Confirmación incorrecta bloqueada antes de construir OAuth.
- [x] OAuth almacenado abierto mediante fábrica y configuración inyectadas.
- [x] Un único token, sin renovación y sin segundo acceso al proveedor real.
- [x] Preflight fresco obligatorio de `chat78733` y `CONFIG_ID=13`.
- [x] Snapshot exacto `Y / always / 245339 / 0 / close` y auxiliares en cero.
- [x] Ventana fija de diez minutos y webhook estable prefijado.
- [x] Delegación exclusiva en la composición reversible y cierre total.
- [x] Sin `.env`, parser, `main()`, ejecución real o envío de mensajes.

Pasaron 18/18 pruebas focales combinadas y 508/508 completas. El recorrido
integrado utilizó OAuth doble y `MockTransport`, terminó restaurado en `245339`
y no tocó la Línea 13 real.

### CLI R0 one-shot — 27 de julio de 2026

- [x] Única frase aceptada como `--confirm-code`.
- [x] Único parámetro adicional: timeout; sin IDs, URL, token o método libres.
- [x] Configuración local cargada solo dentro de `main()` y entregada una vez.
- [x] Sonda del handler G0 real mediante ASGI en memoria, sin socket.
- [x] Barreras tomadas del `ConnectorSettings` reconsultado y resultado del
  webhook tipado como `OffProbeResult`.
- [x] Una sola delegación al runner y salida JSON allowlisted.
- [x] Excepción reducida a `r0_cli_failed_safe`, sin cuerpo ni secreto.
- [x] Cero ejecución de la CLI, lectura de `.env` real o conexión externa.

Pasaron 23/23 pruebas focales combinadas y 513/513 completas. La prueba de la
sonda usó el handler G0 por `ASGITransport`; no inició FastAPI/Uvicorn ni abrió
puertos.

### Go/no-go real de solo lectura — 27 de julio de 2026

- [x] `.env` usado internamente sin imprimir nombres sensibles ni valores.
- [x] Un único token almacenado solicitado, sin renovación automática.
- [x] Barreras confirmadas: `off/locked/no-external`, piloto apagado y parada
  activa.
- [x] Recursos Mongo/OAuth/HTTP cerrados.
- [ ] Bot `373259` revalidado: bloqueado por `bot_v2_preflight_token_expired`.
- [ ] `chat78733` y Línea 13 revalidados: bloqueados por
  `openline_preflight_token_expired`.
- [ ] GO real: no emitido.

Resultado: `NO-GO`. No se renovó el token, no se ejecutó la CLI R0, no se
modificó Bitrix y no se envió ningún mensaje.

### Renovación única y repetición del go/no-go — 27 de julio de 2026

- [x] Una sola renovación OAuth ejecutada y persistida sin exponer secretos.
- [x] Barreras confirmadas: `off/locked/no-external`, piloto apagado y parada
  activa.
- [x] Bot `373259` revalidado como existente y compatible; revisión REST `35`.
- [x] `chat78733`, `CONFIG_ID=13` y estado activo revalidados.
- [x] Snapshot exacto `Y / always / 245339 / 0 / close`.
- [x] Cuatro bots auxiliares revalidados en `0`.
- [x] Recursos Mongo/OAuth/HTTP cerrados.
- [x] GO real emitido exclusivamente para preparar el recorrido R0.

No se ejecutó la CLI R0, `config.update`, vinculación, rollback, lectura de
mensajes ni envío. La Línea 13 permaneció intacta.

### Compuerta de recibo R0 hermética — 27 de julio de 2026

- [x] Compuerta armada antes de cualquier vinculación.
- [x] Identidad exacta: miembro, bot `373259`, chat `78733` y `chat78733`.
- [x] Observación del handler G0 real ejercitada por ASGI en memoria.
- [x] Recibo limitado a hash, identidades y banderas; sin texto o secretos.
- [x] Exigencia de `off/locked/no-external` y cero persistencia/NIA/Bitrix.
- [x] Espera humana predeterminada de 180 segundos; máximo 300.
- [x] Timeout, divergencia y error terminan con rollback verificado.
- [x] CLI bloqueada antes de OAuth cuando no existe fuente real de recibos.
- [x] 30/30 pruebas focales y 516/516 completas con dobles locales.

Pendiente: construir el puente efímero entre el proceso web y el coordinador.
No se ejecutó FastAPI, `.env`, Mongo, red, Bitrix, vinculación o mensajes.

### Puente HTTP R0 autenticado y no montado — 27 de julio de 2026

- [x] Registro en memoria limitado a una sesión y un recibo.
- [x] Identificador almacenado solo como SHA-256; token e ID ocultos en cliente.
- [x] Autenticación constante antes de leer cualquier JSON.
- [x] Cuatro operaciones fijas: armar, consultar, consumir y desarmar.
- [x] Expiración máxima de diez minutos sin proceso recurrente.
- [x] Consulta acotada y consumo único; cierre desarma pendientes.
- [x] Recorrido completo coordinador → webhook G0 → consumo → rollback.
- [x] Bot final simulado restaurado exactamente a `245339`.
- [x] Router ausente de `main.py` y del router productivo.
- [x] 36/36 pruebas focales y 522/522 completas con dobles.

Pendiente: montar el puente detrás de un switch separado, apagado por defecto,
y componer la fábrica CLI. No hubo despliegue, conexión o modificación real.

### Montaje opcional R0 y fábrica CLI — 27 de julio de 2026

- [x] Switch independiente `NIA_BITRIX_R0_BRIDGE_ENABLED=false` por defecto.
- [x] Montaje limitado a la aplicación aislada G0; `main.py` permanece ajeno.
- [x] Valor inválido o autenticación incompleta bloquean el inicio de G0.
- [x] Una sola instancia en memoria compartida por webhook y rutas de recibo.
- [x] Fábrica CLI compuesta desde origen G0 y token protegido.
- [x] CLI sin switch activo conserva `r0_receipt_gate_required` antes de OAuth.
- [x] Recorrido integral con ASGI y dobles termina restaurado en `245339`.
- [x] 48/48 pruebas focales y 528/528 completas aprobadas.

Pendiente: auditar y preparar el delta de despliegue y rollback. Este punto ya
requiere atención especial antes de publicar, desplegar, habilitar el switch o
ejecutar R0. No hubo conexión ni modificación real.

### Montaje R0 integrado en main:app — 27 de julio de 2026

- [x] Prefijo embebido sin duplicar `/bitrix-connector`.
- [x] Switch apagado conserva cero rutas R0 y el comportamiento previo.
- [x] Switch exacto añade tres plantillas y cuatro operaciones autenticadas.
- [x] El webhook integrado entrega el recibo al mismo puente en memoria.
- [x] Configuración incompleta falla cerrada antes de montar.
- [x] `main.py`, startup, supervisor y worker permanecen sin cambios.
- [x] Workflow local ejecutará la suite completa antes del artefacto.
- [x] 38/38 pruebas focales y 535/535 completas aprobadas con dobles.

Pendiente: auditoría pre-publicación del corte exacto. No hubo stage, commit,
push, PR, merge, workflow, Azure, Bitrix o R0 real.

### Preflight real de solo lectura del Camino B — 27 de julio de 2026

Una autorización específica permitió usar `.env` internamente, sin mostrar
valores, para abrir el OAuth almacenado y ejecutar únicamente:

- `imbot.v2.Revision.get`;
- `imbot.v2.Bot.list`;
- `imopenlines.dialog.get`;
- `imopenlines.config.get`.

Resultado seguro:

- `rest_revision=35`;
- nuestra aplicación no posee todavía `nia_next_openline_controlled`:
  `existing_bot_id=null` y `registration_needed=true`;
- `chat_id=78733`, `dialog_id=chat78733` y `CONFIG_ID=13` siguen coincidiendo;
- la línea `WhatApp Wazzup OFICIAL` continúa activa;
- el snapshot coincide exactamente con
  `Y / always / 245339 / 0 / close`;
- los cuatro bots auxiliares observados permanecen en `0`;
- estado conjunto: `ready=true`.

Los dos primeros intentos no mutaron datos: uno falló por pérdida de comillas
entre PowerShell y `python -c`; el segundo completó las lecturas pero falló al
proyectar un atributo local inexistente. El tercer intento usó los modelos
seguros y terminó correctamente. Mongo/OAuth/HTTP se cerraron en cada intento.
No se leyeron mensajes ni se registraron, vincularon o modificaron bots, Línea
Abierta, WAZZUP, negociación o configuración.

## Participación humana mínima

Codex puede preparar, validar con dobles, comparar snapshots, generar previews,
reunir evidencia y ejecutar comprobaciones convencionales dentro de cada SP.

El usuario necesita atención superior a la habitual únicamente en:

1. **A5 o B:** confirmar la Línea Abierta exacta justo antes de vincular.
2. **A6 o B:** avisar y enviar el único mensaje R0, y confirmar visualmente el
   chat correcto.

Registro del bot, despliegue, creación de línea, vinculación, R0, desbloqueo
`review`, llamada real a NIA y primer envío a Bitrix permanecen como
autorizaciones externas separadas.

## Resultado que habilita R1

R0 solo demuestra recepción auténtica e inerte. No demuestra persistencia,
worker, NIA ni respuesta a Bitrix. Para R1 todavía se necesita implementar y
probar localmente G5: desbloqueo deliberado de `review`, persistencia durable,
doble aprobación y revalidación de barreras antes de cada frontera externa.
