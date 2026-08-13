# Contrato R1 pre-evento para activación y tercera sesión controlada

Estado: `HOST-RUNTIME-VERIFIED-AZURE-PROVISIONING-BLOCKED`.

Este contrato no autoriza App Settings, reinicio, apertura de secretos, Azure,
OAuth, Bitrix, participantes, confirmaciones, sesión ni mensajes. Separa la
activación de configuración de la mutación temporal de Chat Test.

## Identidad y línea base

- Despliegue: `main@41ab2d5435cadf22db60574166d7eb29dd1dd57e`, árbol
  `370a5b4e5b2b55420e0c918fa8dfc12c6bd42b30`.
- Bot NIA: `245339`; debe permanecer ausente y nunca se restaura por inferencia.
- Bot Next: `373259`; sólo puede añadirse temporalmente.
- Chat Test: `78733` / `chat78733`; negociación `614949`.
- Conector: `v0.267/off/locked/no-external/inert`; R0 deshabilitado y desmontado.
- TTL máximo de la sesión y del lease: 600 segundos, compartido y sin rearme.
- Evento admisible: `ONIMBOTV2MESSAGEADD` con las identidades exactas.

## Evidencia previa

El corte desplegado aprobó 4/4: `main`, workflow `31405325991`, NIA y conector
dormido. Una extracción única del merge aprobó `1616/1616`; árbol, diff,
checkout, índice y limpieza quedaron exactos.

## Bloqueadores previos a cualquier activación

Debe existir un preflight protegido, saneado y one-shot que demuestre sin
mostrar valores:

1. compatibilidad del host con el backend protegido configurado;
2. existencia del target exacto `nia-next/bitrix-r1/protected-settings/v1`;
3. lectura permitida de siete claves allowlisted, sin enumeración ni fallback;
4. OAuth almacenado utilizable con presupuestos lectura/refresh/reintento
   `1/0/0` y cierre verificado;
5. presencia válida de autenticación del revisor, sólo como booleanos;
6. línea base reversible de los switches R0, R1 y estrategia, sin abrir el resto
   de App Settings;
7. Bot NIA y Bot Next ausentes del baseline exacto de Chat Test.

El builder desplegado usa un backend de Windows Credential Manager. Mientras no
se prueben compatibilidad del host y target exacto, el contrato permanece
bloqueado. No se activa para descubrirlo mediante fallo real.

El evaluador puro `bitrix_connector/r1_pre_event_activation_preflight.py`
recibe exclusivamente evidencia saneada y falla cerrado ante cualquier deriva.
Modela también el rollback literal de presencia/valor de los tres switches sin
leerlos. Su prueba focal `tests/test_r1_pre_event_activation_preflight.py`
aprobó 8/8 con dobles herméticos. Esto no demuestra todavía evidencia real del
host, Credential Manager, target, OAuth, App Settings o participantes.

El colector one-shot
`bitrix_connector/r1_pre_event_activation_evidence_collector.py` coordina sólo
cuatro sondas inyectadas y allowlisted: despliegue, fuente protegida, tres
switches y participantes exactos. Consume cada sonda como máximo una vez, sin
reintentos; cada deriva detiene la secuencia antes de la siguiente superficie y
las excepciones se reducen a un motivo fijo. Sus pruebas homónimas aprobaron
8/8; junto con el evaluador aprobaron 16/16. Este estrato no enlaza operaciones
reales.

La frontera real-ready dormida
`bitrix_connector/r1_pre_event_activation_real_binding.py` exige un permiso no
exportado y cuatro operaciones diferidas, sin defaults ejecutables. Construirla
o materializar el colector no llama operaciones; sólo una futura ejecución
autorizada de `collect()` podría hacerlo. Sus pruebas aprobaron 8/8 y el conjunto
completo 24/24. Las cuatro operaciones reales y su gate aún no están enlazados.

El contrato ejecutable puro
`bitrix_connector/r1_pre_event_activation_operation_contract.py` congela los
presupuestos de las cuatro operaciones y un gate literal one-shot que, incluso
si estuviera listo, sólo materializa el colector dormido. La auditoría vigente
termina `NO-GO` por dos brechas: no existe fuente demostrada de lectura exacta
de sólo tres App Settings y el cierre OAuth exigido antes de devolver evidencia
impide transferir el mismo recurso a la lectura posterior de participantes.
Contrato/gate aprobaron 9/9; el conjunto focal aprobó 33/33. No se emitió permiso.

La auditoría oficial/local en
`docs/r1_preflight_public_architecture_audit.md` confirma que producción es
Linux y `CredReadW` sólo soporta Windows. Recomienda un lector host-side de tres
switches exactos, un secreto exacto de Key Vault mediante identidad administrada
y un owner compuesto que conserve OAuth hasta leer participantes y cierre todo
antes de emitir evidencia. La decisión no autoriza implementación externa.

La implementación local aprobada añadió el lector exacto de switches y el owner
compuesto con cierre previo a evidencia; el esquema de fuente quedó fijado a
`azure-key-vault-exact-secret`. Las 48 pruebas R1 aprobaron. El gate continúa
`NO-GO` sólo porque falta el backend Linux de secreto exacto; no se enlazó ni
ejecutó Key Vault, identidad administrada, OAuth, Bitrix o Azure.

El backend Linux de secreto exacto y su binding SDK perezoso aprobaron 12/12;
la regresión total aprobó 1716/1716. El nombre físico queda fijado a
`nia-next-bitrix-r1-protected-settings-v1`, sin enumeración ni escritura. El gate
sigue `NO-GO` hasta demostrar dependencias SDK e identidad administrada/RBAC.

El contrato exacto de la intervención externa, sus autorizaciones separadas y
el rollback condicional quedó preparado en
`docs/r1_azure_key_vault_intervention_contract.md`. Ningún marcador constituye
confirmación válida y toda mutación externa continúa bloqueada.

El inventario one-shot resolvió resource group, Linux/Python 3.12, ausencia de
identidad y disponibilidad del vault candidato, sin escrituras. Localmente se
fijaron los dos SDK, su transporte async y el lector exacto dormido de la URL;
lector 9/9, focales 30/30 y regresión 1734/1734 aprobaron. Faltan
instalación/despliegue y baseline productivo, aún no autorizados.

La ruta protegida fue después fusionada/desplegada y la invocación V2 verificó
en el host los tres paquetes exactos y la ausencia de
`NIA_BITRIX_KEY_VAULT_URL`, sin llamadas salientes ni escrituras. La sonda quedó
consumida. Ya no bloquean runtime o baseline del setting; continúa bloqueada la
provisión Azure de vault, identidad, RBAC, secreto y URL, que exige inventario
fresco y autorizaciones propias antes de cualquier cambio.

## Fase A — activación de configuración

Requiere contrato de cambio de App Settings con dos confirmaciones externas
independientes. El delta máximo es:

- `NIA_BITRIX_R0_BRIDGE_ENABLED=false`;
- `NIA_BITRIX_EVENT_R1_ENABLED=true`;
- `NIA_BITRIX_EVENT_R1_PARTICIPANT_STRATEGY=pre-event`.

El owner hermético
`bitrix_connector/r1_pre_event_activation_apply_owner.py` implementa las dos
confirmaciones, aplicación exacta, un reinicio, postlectura activa y rollback
literal con reinicio y postlectura dormida. El binding productivo dormido
`bitrix_connector/r1_pre_event_activation_apply_real_binding.py` traduce sólo
ese delta y su rollback a argv Azure CLI exactos, sin shell, y cierra cada
runner. Su verificador HTTP anónimo comprueba la pareja de salud, R0 desmontado
y la transición de la ruta protegida R1 `401 review_unauthorized` → `404`, sin
leer tokens. Construir owner, binding o verificador no ejecuta red ni Azure.

No cambia modo del conector, piloto, parada, credenciales o cualquier otro
setting. Tras un único reinicio se exige salud estable, R0 sin montar, R1
montado una vez con estrategia `pre-event`, lease factory enlazada, cinco rutas
protegidas y acceso anónimo rechazado. Fallo o ambigüedad restaura exactamente
la existencia/valor previo de los tres switches, reinicia una vez y exige la
línea base dormida.

## Fase B — sesión y mutación temporal de participantes

Sólo después de Fase A estable se usan las dos confirmaciones one-shot ya
congeladas por el código:

```text
PRIMERA CONFIRMACION R1 EVENTO EFIMERO CHAT78733 BOT373259
```

No existe una confirmación manual intermedia: el baseline técnico leído justo
antes de la mutación debe demostrar que Bot NIA y Bot Next están ausentes. La
segunda confirmación, separada e inmediatamente previa a la mutación, es:

```text
SEGUNDA CONFIRMACION R1 EVENTO EFIMERO EJECUCION INMEDIATA
```

La segunda confirmación puede abrir una sola fuente protegida, leer el baseline
de Chat Test, exigir ausencia de ambos bots, añadir Bot Next una vez y verificar
que es la única diferencia. Cualquier lectura vacía, identidad distinta,
respuesta incierta o adición no verificada termina `NO-GO` y ejecuta una sola
eliminación compensatoria de Bot Next con postlectura exacta.

## Atención humana y éxito

La persona sólo envía el tercer texto, nuevo y fijado en esa autorización,
cuando la salida autenticada muestre simultáneamente `ATTENTION-REQUIRED`,
`pre_event_lease_state=AWAITING-EVENT`, `human_message_required_now=true`, una
adición verificada y ventana vigente. Codex nunca envía el mensaje y la persona
lo envía una sola vez desde Chat Test.

Éxito exige evento exacto aceptado, recibo técnico auténtico y respuesta de Bot
Next en Chat Test. Tras evento, timeout o fallo se elimina Bot Next una sola vez
y se exige restauración literal del baseline; Bot NIA permanece ausente.

## Cierre y rollback

Después del resultado terminal se desarma la sesión, se verifica el rollback de
participantes y se ejecuta por separado el rollback de Fase A. Dos lecturas de
salud deben recuperar `v0.267/off/locked/no-external/inert`, R0 desmontado y R1
apagado. No se reintenta sesión, mensaje, OAuth, mutación o reinicio.

Resultados permitidos:

- `VERIFIED-RESTORED`: evento, recibo, respuesta y ambos rollbacks verificados.
- `EXPIRED-RESTORED` o `FAILED-RESTORED`: sin éxito funcional, baseline íntegro.
- `NO-GO-REMAINDER`: rollback no verificable; se detiene y conserva visible.
