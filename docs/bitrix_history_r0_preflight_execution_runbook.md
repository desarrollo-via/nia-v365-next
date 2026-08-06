# Runbook protegido — ejecución futura del preflight de historial R0

Estado: **PREPARADO / NO-GO PARA EJECUTAR**.

Este documento acumula las fases D–L de `15/18`. No autoriza ejecutar la CLI,
consultar Mongo, obtener OAuth, llamar Bitrix ni enviar mensajes.

## Alcance exacto de la ejecución futura

La futura ejecución permitida se limitaría a:

1. cargar settings únicamente en el entorno de un proceso PowerShell nuevo;
2. obtener una sola vez el OAuth ya almacenado, sin renovarlo;
3. ejecutar una sola llamada Bitrix `imopenlines.dialog.get` para
   `dialog_id=chat78733`;
4. validar internamente `chat_id=78733`, sesión positiva y
   `last_message_id` positivo;
5. cerrar los recursos del preflight y conservar el ancla sólo en memoria;
6. exigir la segunda frase exacta y, sólo después, capturar sin eco el texto
   controlado esperado, calcular internamente su SHA-256 y fijar la ventana UTC;
7. obtener otra vez el OAuth almacenado, sin renovarlo, y construir el lector;
8. sondear `imopenlines.dialog.get` sin repetir el baseline durante 180 segundos,
   con máximo absoluto de 300, y hacer como máximo una lectura final
   `imopenlines.session.history.get` si cambia `last_message_id`;
9. cerrar cliente HTTP, OAuth y Mongo y mostrar sólo estados allowlisted.

No se permite persistir texto, hash, ancla o resultados, modificar Bitrix o
Wazzup, activar el conector, armar el puente, pedir mensajes ni continuar por
inferencia. El lector puede quedar esperando, pero la persona no enviará nada
hasta que una autorización futura permita mostrar literalmente `AHORA: envía
el primer mensaje`.

## Línea base pública exigida

Inmediatamente antes de cualquier autorización de ejecución deben aprobar dos
lecturas públicas consecutivas:

- NIA y conector con `status=ok`;
- producción `CONNECTOR_VERSION=v0.117`;
- `requested_mode=off`, `effective_mode=off`;
- `activation_locked=true`, `external_calls_enabled=false`;
- runtime `inert`, sin servicio ni recursos;
- piloto apagado, parada de emergencia activa y configuración válida;
- puente R0 montado, sin advertencias;
- OpenAPI `21/17/3`, con ambas rutas NIA presentes.

Cualquier diferencia produce `NO-GO` y no se carga el entorno protegido.

La fase L obtuvo dos lecturas consecutivas a
`2026-07-31T19:08:17.9148585Z` y `2026-07-31T19:08:29.1636005Z`. Ambas
aprobaron exactamente `v0.117 · 21/17/3`, NIA y conector `ok`, todas las
barreras inertes, piloto apagado, parada activa, puente montado sin advertencias
y las dos rutas NIA presentes. Las respuestas allowlisted fueron idénticas y no
se invocó ninguna ruta R0. Esta evidencia es puntual: cualquier deriva o demora
que le quite frescura exige repetirla antes de una ejecución futura.

## Entorno protegido automatizado — diseño pendiente

La preparación manual anterior queda sustituida por el mecanismo protegido del
protocolo propio. La ejecución futura debe realizarse mediante un helper local
dedicado, lanzado por Codex como proceso propietario y sin valores sensibles en
la línea de comandos. El núcleo, su entrypoint fixture-only y un adaptador
dotenv allowlisted ya existen, pero el adaptador sólo fue auditado contra
archivos temporales ficticios: no está integrado en ningún entrypoint y nunca
ha abierto el `.env` real. Esta sección no autoriza cargar fuentes protegidas ni
ejecutar la CLI R0.

El helper futuro extraerá exclusivamente esta allowlist:

- `NIA_BITRIX_DOMAIN`
- `NIA_BITRIX_MEMBER_ID`
- `NIA_BITRIX_CLIENT_ID`
- `NIA_BITRIX_CLIENT_SECRET`
- `NIA_BITRIX_MONGO_URI`
- `NIA_BITRIX_MONGO_DB`
- `NIA_BITRIX_INSTALLATIONS_COLLECTION`

La fuente preferida será el Administrador de credenciales de Windows. Como
alternativa transitoria, una autorización independiente podrá nombrar
literalmente `.env`; en ese caso el helper extraerá sólo la allowlist anterior,
sin inspección general, enumeración ni volcado. No emitirá valores, fragmentos,
longitudes, hashes, nombres descubiertos ni indicadores individuales.

La única salida admisible de esta preparación será agregada y fija, por
ejemplo `protected_source_opened`, `required_values_present`,
`operation_completed` y `resources_closed`, más contadores no sensibles. Un
faltante, error, timeout o estado ambiguo falla cerrado, sin reintento y antes de
nuevas llamadas externas. Los recursos y el entorno privado se limpian siempre;
un cierre no verificado es terminal.

La autorización para cargar esos valores será independiente de cualquier
permiso para OAuth, Mongo o Bitrix. No autoriza por sí misma ejecutar esta CLI,
armar el lector, modificar sistemas externos ni pedir o enviar mensajes.

### Evidencia hermética de M1

`bitrix_history_r0_protected_helper.py` implementa allowlist exacta, buffers
transferibles, vista efímera redactada, una sola operación, estados agregados,
fallo cerrado, cancelación, puesta a cero y cierre verificable.
`bitrix_history_r0_protected_helper_cli.py` es exclusivamente fixture-only y
exige la frase `VALIDAR HELPER R0 SOLO CON VALORES FICTICIOS`; no contiene
selector ni adaptador para fuentes reales.

La ejecución local autorizada de ese entrypoint devolvió únicamente `READY`,
siete lecturas, una operación y cierre verificado. Las ocho pruebas propias y
la suite completa de 637 pruebas aprobaron. El escaneo focal no encontró
patrones materiales de secretos. Esta evidencia no permite reutilizar la CLI
fixture como preflight ni conectarla por inferencia a una fuente real.

### Evidencia hermética de M2

`bitrix_history_r0_protected_dotenv_source.py` implementa una fuente one-shot de
máximo 64 KiB. Sólo conserva la allowlist exacta, procesa el archivo en binario,
retira comillas exteriores equivalentes, no expande variables, ignora nombres
ajenos, rechaza duplicados, valores vacíos, comillas inválidas, archivos no
regulares, exceso de tamaño y symlinks, y redacta ruta y contenido.

Las seis pruebas M2 usaron exclusivamente `TemporaryDirectory` y valores
ficticios. Cubrieron éxito, comillas, `export`, `=` y `#` internos, nombres
ajenos, faltantes, duplicados, formato inválido, tamaño, un solo uso, symlink,
redacción y ausencia de superficies externas. M1+M2 aprobaron 14/14, la
regresión R0 79/79 y la suite completa 643/643. No quedaron residuos temporales.

En cualquier fallo la salida pública informa `source_read_calls=0`; sólo una
allowlist completa puede informar `7`, evitando señalar la posición de un valor
ausente. El adaptador sigue sin ruta pública, selector de fuente o conexión con
la CLI R0.

### Evidencia hermética de M3

`bitrix_history_r0_protected_settings_composition.py` enlaza el helper, el
adaptador dotenv y `load_settings` mediante una ruta obligatoriamente inyectada.
El loader recibe un mapping efímero que sólo enumera la allowlist aprobada. La
operación inyectada se ejecuta una vez y únicamente después de verificar modo
`off`, bloqueo activo, llamadas externas deshabilitadas, instalación y puente
R0 apagados, piloto apagado, parada activa y configuración sin advertencias.

Las seis pruebas M3 usaron exclusivamente un archivo temporal y valores
ficticios. Cubrieron composición real de settings, loader inyectado, allowlist,
faltantes, configuración degradada, redacción y ausencia de CLI, entorno, red,
OAuth, Mongo o Bitrix. M1–M3 aprobaron 20/20 pruebas, la regresión de archivos
`history_r0` 80/80 y la suite completa 649/649. Los módulos compilaron, no hubo
secretos materiales o superficies externas y no quedaron residuos temporales.

M3 no instala un selector de fuente, no abre el `.env` real, no integra esta
composición con la CLI R0 y no construye recursos OAuth/Mongo o clientes Bitrix.

### Evidencia hermética de M4

`bitrix_history_r0_protected_preflight_composition.py` enlaza M3 con el
preflight almacenado existente. La fábrica OAuth/Mongo y el constructor del
cliente Bitrix son parámetros obligatorios sin implementación predeterminada.
La salida pública agrega únicamente estados fijos, contadores, barreras y la
disponibilidad booleana del ancla; nunca devuelve settings, token, portal,
identidades, sesión, baseline o el ancla privada.

Las siete pruebas M4 usaron exclusivamente un archivo temporal, valores
ficticios, fábrica, proveedor OAuth, recursos y cliente dobles. El éxito realizó
una construcción, una obtención de token, cero renovaciones, una lectura de
diálogo, cero historial y cero mutaciones, y cerró cliente, recursos y fuente.
También aprobaron faltantes, identidad divergente, fallo privado, cancelación y
fallos terminales de cierre.

M1–M4 aprobaron 27/27 pruebas, la regresión de archivos `history_r0` 87/87 y la
suite completa 656/656. Los módulos compilaron, no hubo secretos materiales o
superficies externas y no quedaron residuos temporales. M4 no tiene CLI, no
selecciona dependencias reales y no abrió el `.env` real.

### Evidencia hermética de M5

`bitrix_history_r0_protected_preflight_cli.py` posee el ciclo síncrono completo:
valida una frase literal fixture-only y una ruta explícita, exige fábrica y
constructor inyectados, ejecuta M4 una vez y emite una única línea JSON basada
exclusivamente en `ProtectedPreflightSnapshot`.

Una frase, forma o ruta vacía inválida se rechaza antes de abrir la fuente. La
ejecución directa del módulo también falla cerrado antes de la ruta porque no
existen dependencias reales predeterminadas. Los códigos son `0` para `READY`,
`1` para `NO-GO`, `2` para rechazo/dependencias ausentes y `130` para
cancelación. Ruta, frase inválida, valores, token y detalles privados no se
imprimen.

Las seis pruebas M5 usaron sólo archivos temporales y recursos ficticios.
M1–M5 aprobaron 33/33 pruebas, la regresión de archivos `history_r0` 93/93 y la
suite completa 662/662. Los módulos compilaron, no hubo secretos materiales,
selectores reales o superficies externas y no quedaron residuos temporales.

### Evidencia hermética de M6

`bitrix_history_r0_protected_preflight_launcher.py` compone el entrypoint M5 con
`PilotDiscoveryOAuthFactory` y `BitrixHistoryR0Client` como referencias reales
predeterminadas. Componer instancia únicamente la fábrica liviana; no invoca su
`build`, no construye el cliente HTTP y no abre la ruta.

La frase literal `PREPARAR LAUNCHER PREFLIGHT R0 SIN EJECUTAR` produce sólo un
preview `PREPARED`. La salida confirma launcher, entrypoint, fábrica y constructor
enlazados, con `source_open_calls=0`, `preflight_calls=0` y `external_calls=0`.
El launcher preparado se descarta sin invocarlo y su representación está
redactada.

Las seis pruebas M6 usaron exclusivamente constructores y owner dobles; no
crearon archivos o recursos. M1–M6 aprobaron 39/39 pruebas, la regresión de
archivos `history_r0` 99/99 y la suite completa 668/668. Los módulos compilaron,
no hubo superficies de ejecución externa, secretos materiales o residuos.

### Evidencia hermética de M7

`bitrix_history_r0_protected_preflight_execution_gate.py` añade una compuerta
separada con la frase literal `EJECUTAR PREFLIGHT R0 REAL PROTEGIDO UNA SOLA
VEZ`. Exige además una ruta explícita y una instancia ya preparada de
`PreparedProtectedPreflightLauncher`; no compone ni selecciona dependencias
reales y su ejecución directa falla cerrada antes de abrir la ruta.

La compuerta invoca el launcher como máximo una vez, captura su salida dentro
del proceso, exige el esquema público completo y normaliza únicamente
`READY`, `NO-GO` o `CANCELLED`. Una salida adicional o malformada, un código
incoherente, una mutación, persistencia, llamada NIA, escritura Bitrix o barrera
degradada produce un fallo terminal redactado y sin reintento.

Las siete pruebas M7 usaron exclusivamente launchers y resultados dobles; no
abrieron archivos ni recursos. M1–M7 aprobaron 46/46 pruebas, la regresión de
archivos `history_r0` 106/106 y la suite completa 675/675. Los módulos
compilaron y el módulo M7 contiene cero selectores reales, superficies externas
o secretos materiales.

### Evidencia hermética de M8

`bitrix_history_r0_protected_preflight_execution_owner.py` es el owner
propietario one-shot que une M6 y M7. Valida primero la misma frase M7 y una ruta
explícita; una solicitud inválida termina antes de componer. Una solicitud válida
compone exactamente un `PreparedProtectedPreflightLauncher` y llama exactamente
una vez a la compuerta M7, sin reintentos.

El owner captura la salida de M7 dentro del proceso, exige su esquema completo,
coherencia entre estado y código, un solo intento del launcher y todas las
barreras inertes. Sólo entonces publica un snapshot normalizado. Una composición
inválida, salida adicional o malformada, cierre ambiguo o barrera degradada es
terminal, queda redactada y no se reintenta.

Las ocho pruebas M8 sustituyeron composición, launcher, compuerta y resultados
por dobles. M1–M8 aprobaron 54/54 pruebas, la regresión de archivos `history_r0`
114/114 y la suite completa 683/683. Los archivos M8 compilaron y el owner no
contiene selectores de recursos, superficies externas o secretos directos. El
owner real no fue ejecutado y ninguna ruta protegida fue abierta.

### M9 — preflight final de ejecución congelado en NO-GO

El comando técnicamente ejecutable queda fijado únicamente para auditoría; **no
debe ejecutarse todavía**:

```powershell
.\.venv\Scripts\python.exe -m bitrix_connector.bitrix_history_r0_protected_preflight_execution_owner --confirm-code "EJECUTAR PREFLIGHT R0 REAL PROTEGIDO UNA SOLA VEZ" --dotenv-path "C:\Users\H\Desktop\f\web\phyton-codigo\nia-next\.env"
```

La fuente futura sería exclusivamente ese archivo regular local, no symlink y
de máximo 64 KiB. Su allowlist exacta, sin enumerar ni aceptar otros nombres, es:

1. `NIA_BITRIX_DOMAIN`;
2. `NIA_BITRIX_MEMBER_ID`;
3. `NIA_BITRIX_CLIENT_ID`;
4. `NIA_BITRIX_CLIENT_SECRET`;
5. `NIA_BITRIX_MONGO_URI`;
6. `NIA_BITRIX_MONGO_DB`;
7. `NIA_BITRIX_INSTALLATIONS_COLLECTION`.

Los valores nunca pueden aparecer en argumentos, consola, chat, archivos
temporales, logs, Agenda o documentación. La operación futura quedaría limitada
a una carga interna, una composición de recursos Mongo/OAuth, una obtención del
token almacenado, cero renovaciones y una sola lectura Bitrix
`imopenlines.dialog.get` para `chat78733`; quedan prohibidas lecturas de
historial, mutaciones, NIA, Wazzup y mensajes.

La salida `READY` sólo sería admisible con
`launcher_compositions=1`, `gate_calls=1`, `launcher_calls=1`,
`source_read_calls=7`, `preflight_calls=1`, `dialog_read_calls=1`,
`history_read_calls=0`, `mutation_calls=0`, `anchor_available=true`,
`resources_closed=true`, `connector_locked_off=true`, `persisted=false`,
`nia_called=false` y `bitrix_written=false`. Cualquier otra salida, timeout,
error, cierre ambiguo o texto adicional detiene el proceso sin reintento. Al ser
sólo lectura no existe rollback externo; la única recuperación admisible es el
cierre total de recursos. Un indicador de mutación se trata como incidente
terminal y no autoriza una mutación correctiva.

La autorización independiente futura tendría que repetir literalmente fuente,
allowlist, operación, única tentativa, salidas y cierre anteriores. No activaría
la doble confirmación de cambios Bitrix porque no autoriza mutaciones. Este
borrador **no debe solicitarse ni aceptarse todavía**: primero debe resolverse el
bloqueo de continuidad del ancla descrito abajo.

#### Bloqueo M9 confirmado

`execute_protected_dotenv_preflight_once` reduce el resultado privado a
`ProtectedPreflightSnapshot`, que publica únicamente `anchor_available`. M7 y M8
capturan y normalizan ese snapshot, por lo que el objeto de ancla no llega a
`BitrixHistoryR0InMemoryHandoff` y se pierde al cerrar el proceso. Ejecutar ahora
el comando haría una lectura real que no puede continuar de forma segura hacia
`16/18` sin repetir el baseline.

M9 permanece `NO-GO` hasta integrar el resultado privado directamente con el
handoff existente dentro del mismo proceso propietario. La prueba local con la
frase inválida `NO AUTORIZADO M9` devolvió
`protected_preflight_execution_owner_rejected`, con composición, compuerta,
launcher, apertura, lecturas y mutaciones en cero y `resources_closed=true`.

### Evidencia hermética de M10

M10 añadió `bitrix_history_r0_protected_handoff_composition.py`. Su owner recibe
el `BitrixHistoryR0PreflightOutcome` privado y lo entrega por identidad, una
sola vez y dentro de la misma corrutina, a
`BitrixHistoryR0InMemoryHandoff.from_preflight`. La salida pública conserva sólo
estado, contadores, barreras y `anchor_available`; nunca serializa sesión,
`last_message_id`, credenciales o valores de la fuente.

La fase se auditó exclusivamente con fuente, fábrica, cliente, outcome y
handoff falsos. Aprobó 8/8 pruebas M10, 62/62 pruebas protegidas M1–M10,
122/122 pruebas `history_r0` y 691/691 pruebas completas. También confirmó que
cancelación, outcome inválido, candidato inválido o cierre fallido eliminan el
ancla y terminan en salida cerrada. No se abrió `.env`, Credential Manager ni
hubo red, OAuth, Mongo, Bitrix, Wazzup, Azure, historial o mensajes reales.

M10 elimina la pérdida privada detectada en M9, pero no autoriza ejecutar el
preflight real: falta enlazar este owner con la compuerta de autorización y el
recorrido operativo existente sin ofrecer acceso público al handoff.

### Evidencia hermética de M11

M11 añadió al owner M10 una delegación privada de
`wait_for_authorization`. El owner sólo acepta el estado previo
`WAITING-AUTHORIZATION`, contabiliza una tentativa y publica el resultado
allowlisted `ARMED`, `CANCELLED`, `NO-GO` o `CLOSED`; nunca devuelve el handoff
ni el ancla. La compuerta conserva el máximo absoluto de 300 segundos y una
segunda invocación no vuelve a llamar la autorización.

La fase aprobó 14/14 pruebas del owner M10–M11, 68/68 pruebas protegidas
M1–M11, 128/128 pruebas `history_r0` y 697/697 pruebas completas. Armado,
cancelación, timeout, fallo, tiempo inválido y cancelación de tarea se probaron
exclusivamente con fuente, preflight y compuertas dobles. No se abrió `.env`,
Credential Manager ni hubo red, OAuth, Mongo, Bitrix, Wazzup, Azure, historial
o mensajes reales.

M11 no ejecuta el lector armado. Falta una delegación privada one-shot que
entregue el ancla al lector existente sin exponerla y la descarte siempre.

### Evidencia hermética de M12

M12 añadió al owner M11 la delegación privada `run_armed_reader_once`. Sólo se
acepta desde `ARMED`, el lector recibe el ancla una vez y el handoff la descarta
en éxito, `NO-GO`, resultado inválido, excepción o cancelación. El resultado
bruto permanece privado: el owner publica únicamente un snapshot fijo
`RECEIVED`, `NO-GO` o `CLOSED`, con contadores y barreras agregadas.

La fase aprobó 20/20 pruebas del owner M10–M12, 74/74 pruebas protegidas
M1–M12, 134/134 pruebas `history_r0` y 703/703 pruebas completas. La identidad
del ancla, razones ficticias privadas y objetos internos no aparecieron en
salidas. No se abrió `.env`, Credential Manager ni hubo red, OAuth, Mongo,
Bitrix, Wazzup, Azure, historial o mensajes reales.

M12 completa el recorrido privado del owner con dobles, pero no lo enlaza aún
al launcher real-ready ni a la CLI protegida. La ejecución real sigue prohibida.

### Evidencia hermética de M13

M13 añadió `bitrix_history_r0_protected_session_entrypoint.py`, un entrypoint
programático inyectable cuyo valor predeterminado es `execute=false`. En ese
modo sólo devuelve `PREPARED` y mantiene en cero owner, confirmación, fábrica y
lector. Cuando se habilita exclusivamente con dobles, exige la frase literal
M7, arma el owner M12, construye el lector de forma diferida y lo ejecuta una
sola vez; después verifica `CLOSED` en `finally`.

La fase aprobó 9/9 pruebas M13, 83/83 pruebas protegidas M1–M13, 143/143 pruebas
`history_r0` y 712/712 pruebas completas. La frase incorrecta canceló antes de
la fábrica; límites inválidos bloquearon antes del owner; timeout, excepción y
cancelación cerraron sin reintento. No se abrió `.env`, Credential Manager ni
hubo red, OAuth, Mongo, Bitrix, Wazzup, Azure, historial o mensajes reales.

M13 todavía exige `owner_builder` y `reader_factory` inyectados. Falta un
ensamblador real-ready que enlace esas dependencias únicamente en preview, sin
abrir la fuente ni ejecutar el entrypoint.

### Evidencia hermética de M14

M14 añadió `bitrix_history_r0_protected_session_launcher.py`, un ensamblador
real-ready exclusivamente de preview. Enlaza por referencia el entrypoint M13,
el preparador protegido M10, la fábrica OAuth/Mongo existente, los dos clientes
Bitrix y el compositor diferido del lector. El objeto preparado no implementa
`__call__`, su representación está redactada y no conserva valores de settings,
credenciales, anclas ni resultados.

La fase aprobó 5/5 pruebas M14, 88/88 pruebas protegidas M1–M14, 148/148 pruebas
`history_r0` y 717/717 pruebas completas. Aperturas de fuente, owner, preflight,
confirmación, fábrica del lector, lector y llamadas externas permanecieron en
cero. No se abrió `.env`, Credential Manager ni hubo red, OAuth, Mongo, Bitrix,
Wazzup, Azure, historial o mensajes reales.

M14 prueba el enlace de referencias, pero deliberadamente no demuestra todavía
la compatibilidad operativa entre el owner, los settings privados y la fábrica
sin argumentos que espera M13. La ejecución real continúa prohibida. Falta un
adaptador privado que mantenga settings e inputs efímeros dentro del proceso y
construya owner y lector únicamente con dobles antes de cualquier uso real.

### Evidencia hermética de M15

M15 añadió `bitrix_history_r0_protected_session_adapter.py`, un puente privado
que entrega a M13 los closures sin argumentos `owner_builder` y
`reader_factory`. M10 captura `ConnectorSettings` una sola vez únicamente
después de un handoff seguro; el adaptador los retiene hasta `ARMED`, compone el
lector diferido y elimina sus referencias privadas. M13 incorporó un cleanup
inyectable ejecutado en `finally`, también ante rechazo, cancelación o fallo.

La fase aprobó 8/8 pruebas M15, 30/30 pruebas focales M10/M13/M15, 97/97 pruebas
protegidas M1–M15, 157/157 pruebas `history_r0` y 726/726 pruebas completas. El
recorrido integral usó exclusivamente settings, anclas, recursos, owner y lector
ficticios. La composición inerte no abrió fuentes ni retuvo settings; éxito,
frase incorrecta, owner `NO-GO` y cancelación terminaron sin settings u owner
retenidos.

No se abrió `.env`, Credential Manager ni hubo red, OAuth, Mongo, Bitrix,
Wazzup, Azure, historial o mensajes reales. M15 resuelve la compatibilidad
privada, pero todavía no enlaza M14, M15 y M13 en un coordinador real-ready
apagado por defecto. La ejecución real continúa prohibida.

### Evidencia hermética de M16

M16 añadió `bitrix_history_r0_protected_session_coordinator.py`. El coordinador
compone M14 una vez y devuelve `PREPARED` cuando `execute=false`, sin plan,
adaptador ni entrypoint. Un `execute=true` exige un
`ProtectedHistorySessionExecutionPlan` explícito y redactado; sólo entonces
compone M15 y llama M13 una vez, pasando su cleanup privado.

La fase aprobó 9/9 pruebas M16, 106/106 pruebas protegidas M1–M16, 166/166
pruebas `history_r0` y 735/735 pruebas completas. El lifecycle integral
M14–M15–M13 se verificó con settings, recursos, owner, ancla, confirmación y
lector ficticios. Sin plan se detuvo antes del adaptador; frase incorrecta,
fallos de launcher o adaptador y cancelación quedaron redactados y limpiaron el
estado privado.

No se abrió `.env`, Credential Manager ni hubo red, OAuth, Mongo, Bitrix,
Wazzup, Azure, historial o mensajes reales. M16 sigue apagado por defecto y no
incluye una compuerta exterior que autorice `execute=true`; la ejecución real
continúa prohibida.

### Evidencia hermética de M17

M17 añadió `bitrix_history_r0_protected_session_execution_gate.py`. La compuerta
posee de forma privada un `ProtectedHistorySessionExecutionPlan` redactado y
acepta un solo intento. La frase literal
`EJECUTAR SESION R0 PROTEGIDA UNA SOLA VEZ` es la única que permite llamar M16
una vez con `execute=true`; una frase incorrecta también consume el intento y
una segunda llamada nunca reintenta.

La fase aprobó 9/9 pruebas M17, 115/115 pruebas protegidas M1–M17, 175/175
pruebas `history_r0` y 744/744 pruebas completas. La composición fue inerte;
frase incorrecta, plan ausente, barrera degradada, excepción y cancelación
quedaron fail-closed, redactadas y sin segundo intento. El único resultado
aceptado exige cleanup privado, conector bloqueado y cero persistencia, llamadas
a NIA o escrituras Bitrix.

No se abrió `.env`, Credential Manager ni hubo red, OAuth, Mongo, Bitrix,
Wazzup, Azure, historial o mensajes reales. M17 implementa la compuerta pero no
autoriza usarla ni compone todavía un plan real. La ejecución real continúa
prohibida.

### Evidencia hermética y contrato congelado de M18

M18 añadió `bitrix_history_r0_protected_session_contract.py`, un snapshot público
sin identidad, ruta, hash, texto o credencial. Congela `execute=false`, plan
explícito, dos confirmaciones, un intento por compuerta/coordinador/owner/
preflight/lector, timeout de preflight de 10 segundos, máximos de autorización y
lector de 300 segundos, una lectura baseline de diálogo, cero lecturas de
historial antes del armado, cero mutaciones y cleanup obligatorio. El contrato
declara expresamente `real_execution_authorized=false` y
`message_request_authorized=false`.

La auditoría recorrió M17→M16→M15→M13 con dobles y aprobó 7/7 pruebas M18,
122/122 pruebas protegidas M1–M18, 182/182 pruebas `history_r0` y 751/751 pruebas
completas. El caso nominal registró exactamente una tentativa en cada capa y un
cleanup; el rechazo exterior no alcanzó ninguna capa interior, el rechazo
interior no compuso el lector y el timeout del lector fue terminal, limpio y sin
reintento.

#### Contrato operativo futuro — todavía no ejecutar

Una futura composición real necesitará, todos dentro del proceso y sin salida:

1. ruta protegida de la fuente allowlisted;
2. fábrica OAuth/Mongo y los dos builders Bitrix ya enlazados;
3. digest efímero del texto controlado y comienzo UTC de la ventana;
4. lector de la confirmación interior y límites 10/300/300;
5. frase exterior literal en una autorización independiente y posterior.

Cualquier plan ausente o divergente, barrera degradada, resultado no allowlisted,
timeout, excepción, cancelación o intento repetido termina en `NO-GO` o
`CANCELLED`, sin reintento. M18 no compuso ese plan real, no abrió fuentes y no
autoriza el preflight ni un mensaje. Falta un compositor real-ready del plan que
permanezca no invocable y sólo publique evidencia de enlaces en preview.

### Evidencia hermética de M19

M19 añadió `bitrix_history_r0_protected_session_plan_launcher.py`, un compositor
no invocable que enlaza por referencia `Path`, la fuente dotenv allowlisted, la
fábrica OAuth/Mongo, ambos clientes Bitrix, el constructor de inputs efímeros,
el plan M16 y la compuerta M17. La confirmación interior queda enlazada a un
lector fail-closed que nunca autoriza automáticamente.

La fase aprobó 6/6 pruebas M19, 128/128 pruebas protegidas M1–M19, 188/188
pruebas `history_r0` y 757/757 pruebas completas. Preview confirmó los nueve
enlaces y mantuvo en cero ruta, fuente, fábrica, clientes, inputs, confirmación,
plan, gate y llamadas externas. El objeto no contiene valores, no es invocable y
su representación está redactada.

No se abrió `.env`, Credential Manager ni hubo red, OAuth, Mongo, Bitrix,
Wazzup, Azure, historial o mensajes reales. M19 no materializa el plan; falta un
owner privado que reciba inputs inyectados y construya el plan sólo con dobles
antes de habilitar cualquier fuente real.

### Evidencia hermética de M20

M20 añadió `bitrix_history_r0_protected_session_plan_materializer.py`. Recibe
ruta, inputs, fábrica, clientes y confirmación ya inyectados; construye una vez
el plan M16 y la compuerta M17, sin abrir la ruta ni invocar recursos. El owner
resultante está redactado, puede entregar el gate una sola vez y elimina sus
referencias al plan, o descartarlas explícitamente mediante cleanup.

La fase aprobó 7/7 pruebas M20, 135/135 pruebas protegidas M1–M20, 195/195
pruebas `history_r0` y 764/764 pruebas completas. Builders de plan y gate se
invocaron una vez; clientes, confirmación y llamadas externas permanecieron en
cero. Entrega repetida, dependencia inválida y fallo de builder quedaron
fail-closed y sin detalles privados.

No se abrió `.env`, Credential Manager ni hubo red, OAuth, Mongo, Bitrix,
Wazzup, Azure, historial o mensajes reales. M20 no ejecutó el gate; falta un
owner que entregue el gate one-shot a una autorización exterior inyectada y lo
audite sólo con dobles.

### Evidencia hermética de M21

M21 añadió `bitrix_history_r0_protected_session_gate_owner.py`. El owner toma
una sola vez el gate materializado antes de pedir la frase exterior, consume un
único lector asíncrono inyectado, ejecuta el gate como máximo una vez, normaliza
el resultado a `RECEIVED`, `CANCELLED` o `NO-GO` y limpia el materializador en
`finally`, incluso ante error o cancelación.

La fase aprobó 7/7 pruebas M21, 142/142 pruebas protegidas M1–M21, 202/202
pruebas `history_r0` y 771/771 pruebas completas. Frase incorrecta, segundo
intento, fallo del lector, cancelación y barrera degradada quedaron cerrados;
la fuente no contiene acceso directo a entorno, dotenv, OAuth, Mongo, Bitrix,
red, procesos ni entrada interactiva.

No se abrió `.env`, Credential Manager ni hubo red, OAuth, Mongo, Bitrix,
Wazzup, Azure, historial o mensajes reales. M21 sólo consumió dobles; falta
auditar y congelar la frontera humana exterior antes de proponer cualquier
composición real.

### Evidencia hermética de M22

M22 añadió `bitrix_history_r0_protected_session_human_boundary_contract.py` y
su auditoría hermética. El contrato público congela un solo owner, una sola
lectura de confirmación, máximo de 300 segundos, frase literal obligatoria,
estados, razones y campos de salida allowlisted, timeout y cancelación
terminales, cleanup obligatorio y las cuatro barreras inertes. No contiene la
frase, identidades, ruta, texto, hash ni valores protegidos.

La fase aprobó 7/7 pruebas M22, 149/149 pruebas protegidas M1–M22, 209/209
pruebas `history_r0` y 778/778 pruebas completas. El recorrido M20→M21 con
dobles confirmó éxito, rechazo previo al coordinador, timeout exterior,
cancelación humana, fallo redactado, allowlist exacta y cleanup único.

No se abrió `.env`, Credential Manager ni hubo red, OAuth, Mongo, Bitrix,
Wazzup, Azure, historial o mensajes reales. El contrato conserva
`real_source_configured=false`, `real_execution_authorized=false` y
`message_request_authorized=false`.

### Cierre estático M23 — NO-GO

M23 añadió `bitrix_history_r0_protected_session_readiness_contract.py` y auditó
M19–M22 como una sola cadena. Las cuatro piezas están completas con dobles, pero
ninguna CLI actual es su proceso propietario: `bitrix_history_r0_handoff_cli`
pertenece al camino anterior y `bitrix_history_r0_protected_helper_cli` es sólo
fixture. El módulo futuro
`bitrix_connector.bitrix_history_r0_protected_session_cli` no existe todavía.
Por evidencia, el cierre es `NO-GO` con razón
`protected_history_session_owner_command_missing`.

La fuente futura queda fijada, sin abrirla, como
`C:\Users\H\Desktop\f\web\phyton-codigo\nia-next\.env` consumida una sola vez
por `AllowlistedDotenvSource` y limitada a `NIA_BITRIX_DOMAIN`,
`NIA_BITRIX_MEMBER_ID`, `NIA_BITRIX_CLIENT_ID`, `NIA_BITRIX_CLIENT_SECRET`,
`NIA_BITRIX_MONGO_URI`, `NIA_BITRIX_MONGO_DB` y
`NIA_BITRIX_INSTALLATIONS_COLLECTION`. El comando futuro congelado es:

```powershell
.\.venv\Scripts\python.exe -m bitrix_connector.bitrix_history_r0_protected_session_cli --confirm-code "EJECUTAR SESION R0 PROTEGIDA UNA SOLA VEZ" --protected-source local-dotenv --preflight-timeout-seconds 10 --confirmation-timeout-seconds 300
```

Este comando no debe ejecutarse y actualmente no puede ejecutarse. La siguiente
plantilla queda conservada únicamente como evidencia histórica M23; M32 la
invalidó y **no debe copiarse ni usarse**:

```text
AUTORIZACIÓN INDEPENDIENTE R0 — PREFLIGHT BITRIX DE SOLO LECTURA: Autorizo exclusivamente, después de verificar que el owner M23 figura command_available=true, una ejecución única del proceso propietario local de nia-next mediante el comando exacto congelado. Autorizo una sola apertura interna de C:\Users\H\Desktop\f\web\phyton-codigo\nia-next\.env por AllowlistedDotenvSource para transferir únicamente NIA_BITRIX_DOMAIN, NIA_BITRIX_MEMBER_ID, NIA_BITRIX_CLIENT_ID, NIA_BITRIX_CLIENT_SECRET, NIA_BITRIX_MONGO_URI, NIA_BITRIX_MONGO_DB y NIA_BITRIX_INSTALLATIONS_COLLECTION, sin mostrar, copiar, transcribir, contar, validar ni registrar sus valores. Autorizo obtener una vez el OAuth almacenado sin renovarlo y realizar exactamente una lectura Bitrix imopenlines.dialog.get para chat78733, conservando sesión y last_message_id sólo en memoria como ancla privada. La salida queda limitada a estados, booleanos y contadores allowlisted. No autorizo lectura de historial, mensajes, Mongo fuera de la instalación OAuth, renovación OAuth, mutaciones, Bitrix config.update, bots, Línea 13, Wazzup, Azure, armado del lector, solicitud o envío de mensajes, NIA ni reintentos. Cualquier fuente, identidad, barrera, salida, timeout, error, cancelación o cierre ambiguo obliga a detenerse, limpiar en finally y terminar el proceso; no existe rollback externo porque la operación autorizada es sólo lectura.
```

La fase aprobó 7/7 pruebas M23, 156/156 pruebas protegidas M1–M23, 216/216
pruebas `history_r0` y 785/785 pruebas completas. No abrió fuente, ruta,
credencial o servicio; todos los permisos reales permanecen en `false`.

### Owner fixture-only M24

M24 añadió el módulo futuro congelado
`bitrix_history_r0_protected_session_cli.py`, pero deliberadamente sólo admite
la fuente `fixture` y la frase
`VALIDAR OWNER SESION R0 SOLO CON DOBLES FICTICIOS`. Parser, builder, lector de
confirmación, owner y emisor son inyectables. Sin builder inyectado termina
`NO-GO`; el recorrido ficticio consume M20–M21 una sola vez, normaliza la salida
y verifica cleanup y las cuatro barreras inertes.

El comando real congelado con `local-dotenv` y la frase de ejecución es
rechazado por `argparse` antes de llamar al builder. El módulo no importa
`AllowlistedDotenvSource`, no conoce `.env`, entorno, OAuth, Mongo, Bitrix,
historial, red o entrada humana. El readiness cambia de owner ausente a
`protected_history_session_owner_fixture_only`; `owner_module_present=true` y
`fixture_command_available=true`, pero `command_available=false`,
`source_open_authorized=false`, `real_execution_authorized=false` y
`message_request_authorized=false`.

M24 aprobó 7/7 pruebas propias, 14/14 focales junto al readiness actualizado,
163/163 protegidas M1–M24, 223/223 `history_r0` y 792/792 completas. No abrió
fuentes, credenciales ni servicios y no realizó llamadas externas.

### Composición owner real-ready M25

M25 añadió `bitrix_history_r0_protected_session_cli_composition.py`. El objeto
redactado y no invocable enlaza el selector nominal `local-dotenv`, `Path`,
`AllowlistedDotenvSource`, el launcher M19, materializador M20, confirmaciones
interior y exterior fail-closed, owner M21 y CLI fixture M24. No contiene ruta
concreta, valores, inputs, plan, gate ni método de ejecución.

El preview confirmó las nueve referencias enlazadas y mantuvo exactamente en
cero selección de fuente, ruta, fuente, launcher, materializador,
confirmaciones, owners y llamadas externas. Dependencias espía no fueron
invocadas; fuente o dependencia divergente cierran `NO-GO`. El readiness queda
`protected_history_session_owner_preview_only`, con
`real_ready_composition_bound=true`, pero parser real bloqueado,
`command_available=false`, `source_open_authorized=false`,
`real_execution_authorized=false` y `message_request_authorized=false`.

M25 aprobó 7/7 pruebas propias, 14/14 focales junto al readiness, 170/170
protegidas M1–M25, 230/230 `history_r0` y 799/799 completas. No abrió `.env`,
credenciales, red o servicios y no realizó llamadas externas.

### Auditoría hermética y delta de activación M26

M26 añadió `bitrix_history_r0_protected_session_activation_delta.py`. La
auditoría recorre una sola vez el owner fixture M24 y el preview M25 mediante
dependencias inyectadas: exige resultado `RECEIVED`, cleanup privado, conector
bloqueado, cero persistencia, NIA, escritura Bitrix, fuente real o llamadas
externas. Cualquier tipo, resultado o barrera divergente termina en `NO-GO`
redactado.

El delta de activación queda congelado en cuatro cambios todavía no aplicados:

1. aceptar el contrato exacto del parser real sólo después de autorización
   independiente;
2. componer la fuente allowlisted one-shot y el builder privado de sesión;
3. enlazar la confirmación humana exterior con límite absoluto de 300 segundos;
4. habilitar el comando únicamente después de auditoría hermética y
   autorización independiente.

El readiness avanza a M26 con razón
`protected_history_session_activation_delta_unapplied` y
`activation_delta_frozen=true`. Parser real, builder real, confirmación humana,
comando, apertura de fuente, llamadas externas, ejecución y solicitud de
mensaje continúan en `false`.

M26 aprobó 7/7 pruebas propias, 28/28 focales M24–M26, 177/177 protegidas
M1–M26, 237/237 `history_r0` y 806/806 completas. No abrió `.env`, credenciales,
red o servicios y no realizó llamadas externas.

### Adaptador dormido del parser real M27

M27 añadió `bitrix_history_r0_protected_session_real_parser_adapter.py`. El
adaptador valida exclusivamente en memoria la frase, fuente nominal y límites
exactos ya congelados. La activación predeterminada es `false` y no consulta la
autorización inyectada; cualquier divergencia se rechaza antes de esa lectura.

Con un doble de autorización exacto puede producir únicamente un contrato
`PREPARED`. Incluso en ese recorrido, `parser_real_enabled=false`,
`command_available=false`, `builder_calls=0`, `source_calls=0` y
`external_calls=0`. El módulo no contiene `argparse`, ruta, fuente, builder,
helper, clientes ni superficies externas.

El readiness avanza a M27 con razón
`protected_history_session_real_parser_adapter_dormant`, adaptador enlazado y
contrato probado con dobles; parser real, comando, fuente, ejecución y solicitud
de mensaje continúan bloqueados.

M27 aprobó 7/7 pruebas propias, 21/21 focales M26–M27/readiness, 184/184
protegidas M1–M27, 244/244 `history_r0` y 813/813 completas. No abrió `.env`,
credenciales, red o servicios y no realizó llamadas externas.

### Composición dormida del builder protegido M28

M28 añadió `bitrix_history_r0_protected_session_builder_composition.py`. La
composición acepta únicamente un snapshot M27 `PREPARED` creado con un doble,
con contrato exacto, una autorización ficticia y todas las capacidades reales
en `false`. Un snapshot dormido, divergente o degradado termina en `NO-GO`.

El objeto resultante es redactado y no invocable. Enlaza `Path`,
`AllowlistedDotenvSource` y el materializador privado sin retener el snapshot,
crear ruta, abrir fuente o materializar plan y gate. Los contadores de ruta,
fuente, builder, materializador y llamadas externas permanecen exactamente en
cero.

El readiness avanza a M28 con razón
`protected_history_session_builder_composition_dormant`; bindings y preparación
con dobles están verificados, pero parser, builder real, comando, apertura de
fuente, ejecución y solicitud de mensaje continúan en `false`.

M28 aprobó 7/7 pruebas propias, 28/28 focales, 191/191 protegidas M1–M28,
251/251 `history_r0` y 820/820 completas. No abrió `.env`, credenciales, red o
servicios y no realizó llamadas externas.

### Confirmación humana exterior dormida M29

M29 añadió
`bitrix_history_r0_protected_session_outer_confirmation_composition.py`. La
composición consume únicamente un snapshot M28 `PREPARED` exacto y enlaza una
fuente asíncrona de confirmación inyectable. Su activación predeterminada es
`false`; en ese estado no lee la confirmación.

La preparación sólo se probó con dobles. Admite exactamente una lectura
contractual bajo un máximo absoluto de 300 segundos y normaliza rechazo,
timeout y cancelación en estados cerrados. Incluso al preparar el contrato con
un doble, builder, fuente, materializador y llamadas externas quedan en cero;
parser real, builder real, comando, apertura de fuente, ejecución y solicitud
de mensaje permanecen en `false`.

El readiness avanza a M29 con razón
`protected_history_session_outer_confirmation_dormant`. M29 aprobó 7/7 pruebas
propias, 28/28 focales, 198/198 protegidas M1–M29, 258/258 `history_r0` y
827/827 completas. No abrió `.env`, credenciales, red o servicios y no realizó
llamadas externas.

### Auditoría hermética de la composición final M30

M30 añadió `bitrix_history_r0_protected_session_final_composition_audit.py`.
La auditoría consume exactamente una vez cuatro sondas inyectadas: éxito
ficticio, rechazo, timeout y cancelación. Cada resultado debe conservar el
contrato M29 exacto, todas las capacidades reales en `false`, contadores
operativos en cero y cleanup verificado. Una divergencia detiene las sondas
restantes y termina en `NO-GO` con salida agregada y redactada.

La prueba integral recorre M27–M29 con dobles. El timeout de 300 segundos se
verifica sin esperar ese tiempo: el runner ficticio confirma el límite, cancela
y espera su tarea antes de devolver el estado terminal. Rechazo y cancelación
también ejecutan su cleanup; no quedan tareas pendientes ni detalles privados en
la salida pública.

El readiness avanza a M30 con razón
`protected_history_session_final_composition_audited_dormant`. M30 aprobó 7/7
pruebas propias, 35/35 focales, 205/205 protegidas M1–M30, 265/265 `history_r0`
y 834/834 completas. No abrió `.env`, credenciales, red o servicios y no
realizó llamadas externas.

### Cierre estático del readiness técnico M31

M31 añadió
`bitrix_history_r0_protected_session_command_readiness_closure.py`. El cierre
consume únicamente el contrato M30 exacto y publica
`READY-AWAITING-AUTHORIZATION`, `owner_complete=true` y
`command_available=true`. Esta disponibilidad es un indicador estático de que
la composición fue completada y auditada; no convierte el módulo en invocable
ni ejecuta el comando congelado.

Las barreras quedan explícitas en `owner_module_invocable=false`,
`command_invocation_authorized=false`, `source_open_authorized=false`,
`oauth_read_authorized=false`, `bitrix_read_authorized=false`,
`real_execution_authorized=false` y `message_request_authorized=false`. Parser,
builder, fuente, materializador, confirmación, comando y llamadas externas
permanecen en cero. La CLI real continúa fixture-only y rechaza el comando
futuro sin ejecutar su builder.

El readiness avanza a M31 con razón
`protected_history_session_command_available_static_only`. M31 aprobó 7/7
pruebas propias, 28/28 focales, 212/212 protegidas M1–M31, 272/272 `history_r0`
y 841/841 completas. No abrió `.env`, credenciales, red o servicios y no
realizó llamadas externas.

### Alineación del owner ejecutable M32

M32 corrigió la deriva detectada entre la plantilla M23, el cierre M31 y la CLI
de sesión M24. El preflight `19/27` no pertenece a esa CLI de sesión: su owner
correcto ya existente es
`bitrix_history_r0_protected_preflight_execution_owner.py`. La CLI M24 conserva
intacta su condición `fixture-only` y continúa rechazando fuentes reales.

El comando único alineado, todavía no ejecutado, es:

```powershell
.\.venv\Scripts\python.exe -m bitrix_connector.bitrix_history_r0_protected_preflight_execution_owner --confirm-code "EJECUTAR PREFLIGHT R0 REAL PROTEGIDO UNA SOLA VEZ" --dotenv-path .env
```

El contrato M32 publica `command_available=true`,
`owner_module_invocable=true`, `authorization_ready_for_use=true` y mantiene
`command_invocation_authorized=false`, `source_open_authorized=false`,
`real_execution_authorized=false` y `message_request_authorized=false`. Por
tanto, preparar el owner no abre `.env`, no obtiene OAuth y no llama Bitrix.

La única plantilla vigente para solicitar `19/27` es:

```text
AUTORIZACIÓN INDEPENDIENTE R0 — PREFLIGHT BITRIX DE SOLO LECTURA: Autorizo exclusivamente, después de verificar que el owner M32 figura command_available=true y owner_module_invocable=true, una ejecución única del proceso propietario local de nia-next mediante el comando exacto congelado. Autorizo una sola apertura interna de C:\Users\H\Desktop\f\web\phyton-codigo\nia-next\.env por AllowlistedDotenvSource para transferir únicamente NIA_BITRIX_DOMAIN, NIA_BITRIX_MEMBER_ID, NIA_BITRIX_CLIENT_ID, NIA_BITRIX_CLIENT_SECRET, NIA_BITRIX_MONGO_URI, NIA_BITRIX_MONGO_DB y NIA_BITRIX_INSTALLATIONS_COLLECTION, sin mostrar, copiar, transcribir, contar, validar ni registrar sus valores. Autorizo obtener una vez el OAuth almacenado sin renovarlo y realizar exactamente una lectura Bitrix imopenlines.dialog.get para chat78733, conservando sesión y last_message_id sólo en memoria como ancla privada. La salida queda limitada a estados, booleanos y contadores allowlisted. No autorizo lectura de historial, mensajes, Mongo fuera de la instalación OAuth, renovación OAuth, mutaciones, Bitrix config.update, bots, Línea 13, Wazzup, Azure, armado del lector, solicitud o envío de mensajes, NIA ni reintentos. Cualquier fuente, identidad, barrera, salida, timeout, error, cancelación o cierre ambiguo obliga a detenerse, limpiar en finally y terminar el proceso; no existe rollback externo porque la operación autorizada es sólo lectura.
```

La alineación M32 no ejecutó comandos propietarios, no abrió fuentes y no hizo
llamadas externas. `19/27` permanece pendiente hasta recibir nuevamente esta
plantilla exacta. Aprobó 46/46 pruebas focales, 212/212 protegidas, 272/272
`history_r0`, 841/841 completas y compilación estática.

### Resultado de la ejecución única autorizada M32

La autorización M32 exacta se recibió y el comando congelado se ejecutó una
sola vez, sin reintentos. La salida pública terminó `NO-GO` con
`protected_source_opened=true`, `source_read_calls=7`, `preflight_calls=1`,
`dialog_read_calls=1`, `history_read_calls=0`, `mutation_calls=0`,
`anchor_available=false` y `resources_closed=true`.

Las barreras permanecieron `connector_locked_off=true`, `persisted=false`,
`nia_called=false` y `bitrix_written=false`. No hubo renovación OAuth,
historial, mutaciones, mensajes ni cambios en Bitrix, Wazzup, Azure o NIA.
`19/27`–`22/27` quedan completados por evidencia directa; `23/27` permanece
pendiente y el preflight no puede repetirse con la autorización consumida.

### Diagnóstico allowlisted M33

El análisis exclusivamente local confirmó que la causa se perdía en tres
normalizaciones: composición, gate y owner. M33 añade `failure_category` a las
tres salidas y sólo admite esta allowlist fija:

- `none`
- `protected_source_or_settings_failed`
- `barrier_degraded`
- `oauth_or_resources_failed`
- `oauth_token_expired`
- `dialog_read_unavailable`
- `dialog_read_rejected`
- `dialog_response_invalid`
- `dialog_identity_mismatch`
- `anchor_invalid`
- `resources_close_failed`
- `cancelled`
- `other_safe_failure`

Cualquier categoría desconocida se descarta antes de llegar a la salida del
gate u owner. Ningún código, cuerpo, URL, token, identificador privado o detalle
de excepción remoto puede atravesar esta frontera. La causa exacta del intento
M32 ya consumido no puede recuperarse retrospectivamente.

El contrato M33 conserva `command_available=true` y
`owner_module_invocable=true`, marca `m32_authorization_consumed=true` y
`repeat_authorization_required=true`, y mantiene la ejecución real bloqueada
hasta recibir una autorización textual M33 nueva e independiente. La mejora
aprobó 55/55 pruebas focales, 215/215 protegidas, 275/275 `history_r0`, 844/844
completas y compilación estática, sin abrir fuentes ni hacer llamadas externas.

## Comando futuro fijado — no ejecutar todavía

```powershell
.\.venv\Scripts\python.exe -m bitrix_connector.bitrix_history_r0_handoff_cli --confirm-code "PREPARAR ANCLA BITRIX CHAT78733 SOLO LECTURA" --preflight-timeout-seconds 10 --authorization-wait-seconds 300 --armed-hold-seconds 300
```

La ejecución necesitará una autorización independiente que repita una lectura
Mongo de la instalación OAuth, cero renovaciones y una sola lectura Bitrix
`imopenlines.dialog.get`. Un resultado distinto de la allowlist exacta, un
timeout, salida adicional o cierre no verificado es terminal y prohíbe reintento.

Después de `WAITING-AUTHORIZATION`, la única segunda frase admisible será:

```text
ARMAR HISTORIAL CHAT78733 SIN ENVIAR MENSAJE
```

Una frase distinta cancela, elimina el ancla y no ejecuta el hook armado.

Tras aceptarla, la CLI solicita `Texto controlado esperado (entrada oculta)`.
El texto no se muestra, imprime, persiste ni devuelve: se transforma dentro de
la captura en SHA-256, el búfer se limpia y sólo el digest llega al lector. Este
prompt prepara la identidad del mensaje; no autoriza enviarlo.

## Checklist protegido congelado

Antes de una ejecución futura deben cumplirse todos estos puntos, en orden:

1. existe autorización independiente y literal sólo para el preflight de
   lectura; no incluye armar el lector ni pedir o enviar mensajes;
2. dos lecturas públicas consecutivas confirman íntegramente la línea base;
3. existe un helper local auditado que recibe sólo parámetros no sensibles y
   limita la carga a la allowlist exacta;
4. una autorización independiente identifica literalmente la fuente protegida
   y permite una única carga interna, sin autorizar operaciones externas;
5. otra autorización independiente permite ejecutar el comando futuro dentro
   del proceso propietario del helper;
6. sólo se aceptan salidas allowlisted y en el orden fijado; durante `15/18`,
   `16/18` y `17/18` nunca se muestra la instrucción humana de envío;
7. al terminar, fallar o cancelar, se verifica el cierre total y la terminación
   del proceso propietario.

Ningún punto puede adelantarse, agruparse con una autorización posterior ni
inferirse desde una comprobación anterior.

## Salidas allowlisted esperadas

El primer estado público de la CLI handoff debe ser:

- `state=WAITING-AUTHORIZATION`;
- `reason=bitrix_history_handoff_waiting_authorization`;
- `preflight_ready=true`, `anchor_available=true`, `history_armed=false`;
- `dialog_read_calls=1`, `history_read_calls=0`, `mutation_calls=0`;
- `connector_locked_off=true`, `persisted=false`, `nia_called=false`,
  `bitrix_written=false`, `resources_closed=true`.

La sesión, `last_message_id`, OAuth, `member_id` y demás valores protegidos no
pueden aparecer. Después debe emitir `ARMED` y exactamente una señal
`WAITING-MESSAGE` con `reader_ready=true`, cero lecturas, cero mutaciones,
`connector_locked_off=true`, `persisted=false`, `nia_called=false`,
`bitrix_written=false` y `resources_closed=false`, porque el lector sigue
abierto durante la espera. Sólo si en una fase futura se autoriza el mensaje,
podrá aparecer un resultado `RECEIVED` con
`controlled_message_verified=true`, una lectura final y las cuatro barreras
inertes. Cualquier `NO-GO`, timeout o salida distinta termina la operación.

## Criterios terminales de detención

Se detiene sin reintento y se cierra el proceso propietario ante cualquiera de
estos casos:

- una lectura pública diverge o las dos lecturas no son consecutivas e iguales;
- autorización, fuente, helper, frase, comando, carpeta, entorno o identidad
  resultan ambiguos;
- aparece cualquier campo o valor no allowlisted;
- falta `WAITING-MESSAGE`, aparece más de una vez o llega fuera de orden;
- ocurre una renovación OAuth, más de una lectura baseline, más de una lectura
  final de historial, una mutación o cualquier persistencia;
- una barrera deja de estar inerte o aparece actividad ajena incompatible;
- hay timeout, excepción, cancelación, salida adicional o cierre no verificado.

Un nuevo intento exige proceso propietario, línea base y autorización nuevos. No existe
rollback externo porque este camino no modifica Bitrix, Wazzup ni Azure.

## Cierre protegido

Después de éxito, fallo o cancelación, el helper debe cerrar todos sus recursos,
eliminar su entorno privado y terminar el proceso propietario. No existe
rollback externo porque esta operación no modifica Bitrix, Wazzup ni Azure.

## Evolución del bloqueo D–L

La CLI vigente conserva el ancla sólo dentro de
`BitrixHistoryR0PreflightOutcome._anchor`. `main()` imprime exclusivamente el
resultado allowlisted y el proceso termina; por tanto, sesión y
`last_message_id` se destruyen y no pueden entregarse a `16/18`.

La fase E añadió el núcleo inyectable
`BitrixHistoryR0InMemoryHandoff`: conserva el ancla sólo en memoria, queda en
`WAITING-AUTHORIZATION`, puede pasar una vez a `ARMED` y descarta el ancla ante
cancelación, timeout, error o cierre. No contiene lector de historial ni forma
pública de extraer el ancla.

La fase F añadió `bitrix_history_r0_handoff_cli.py`. La CLI integra el handoff,
emite `WAITING-AUTHORIZATION`, exige la segunda frase exacta y sólo entonces
invoca un hook armado dentro del mismo proceso. La lectura manual no usa un hilo
bloqueante, tiene máximo de 300 segundos y Ctrl+C elimina el ancla.

La fase G conectó el hook al lector one-shot mediante una entrega privada del
ancla y sin repetir baseline. La fase H compuso de forma diferida el cliente
propietario y sus entradas efímeras. La fase I integró en la CLI la captura
oculta, el SHA-256 interno, la ventana UTC y la construcción del lector después
del armado. La fase J añadió la señal pública cerrada `WAITING-MESSAGE`: se
emite una sola vez con el cliente ya construido, después de validar barreras,
ventana y ancla, y exactamente antes del primer sondeo. Su payload no contiene
sesión, ancla, texto, hash, OAuth, `member_id` ni credenciales; conserva cero
lecturas, cero mutaciones y las barreras inertes.

La secuencia futura exigida queda fijada como
`WAITING-AUTHORIZATION -> ARMED -> WAITING-MESSAGE -> RECEIVED/NO-GO -> CLOSED`.
Sólo después de observar `WAITING-MESSAGE` podrá una fase 18/18 autorizada
mostrar literalmente `AHORA: envía el primer mensaje`. La ausencia, duplicación
o desorden de esa señal obliga a detenerse y cerrar el proceso.

La fase K auditó herméticamente el recorrido completo usando la CLI y la
composición reales con recursos y cliente dobles. Confirmó cinco estados
públicos exactos, una obtención del token almacenado, cero renovaciones, una
lectura de diálogo, una lectura final, cierre total y ausencia de datos
protegidos en toda la salida. También congeló el checklist humano y los
criterios terminales anteriores.

La fase L confirmó mediante dos lecturas públicas consecutivas la línea base
completa exigida, con diez segundos de separación y cero rutas R0 invocadas. No
consultó Azure, App Settings, secretos, OAuth, Mongo ni Bitrix.

La fase M0 sustituyó la preparación manual por este contrato de automatización
protegida. No creó el helper, no cargó fuentes ni ejecutó Python o servicios.

La fase M1 implementó y ejecutó sólo el helper fixture-only con valores
ficticios. Aprobó allowlist, redacción, un solo uso, cancelación, puesta a cero,
cierre y regresión completa; no contiene fuente real ni integra la CLI R0.

La fase M2 implementó el adaptador dotenv allowlisted y lo ejercitó sólo sobre
archivos temporales ficticios. No abrió el `.env` real, no instaló un selector
de fuente y no entregó settings a OAuth, Mongo o Bitrix.

La fase M3 compuso y auditó helper, adaptador y settings sólo con dobles y un
archivo temporal ficticio. La fase M4 integró el preflight con fábrica y cliente
obligatoriamente inyectados, también ficticios. La fase M5 agregó el entrypoint
propietario fixture-only sin selector real y M6 ensambló el launcher real-ready
en preview no operativo. M7 añadió la compuerta separada, M8 el owner one-shot y
M9 congeló el contrato final, donde detectó la pérdida del ancla privada. M10
resolvió esa discontinuidad entregando el outcome directamente al handoff en el
mismo proceso, sin exponerlo. M11 delegó la compuerta de autorización desde el
owner, con una sola tentativa, máximo de 300 segundos y cierre fail-closed. La
fase M12 delegó también el lector one-shot, conservando tanto el ancla como el
resultado bruto dentro del owner. M13 enlazó owner, frase literal y fábrica
diferida en un entrypoint inyectable que queda `PREPARED` por defecto. M14 unió
las referencias reales en un ensamblador de preview deliberadamente no
invocable y confirmó todos los contadores operativos en cero. M15 adaptó
privadamente settings, owner y lector, con cleanup terminal y recorrido integral
sólo mediante dobles. M16 enlazó M14–M15–M13 en un coordinador real-ready que
permanece `PREPARED` y sin plan por defecto. M17 añadió una compuerta exterior
one-shot con frase literal y plan obligatorio, también auditada sólo con dobles.
M18 auditó el conjunto completo con dobles y congeló límites, intentos, barreras
y detenciones. M19 enlazó todas las referencias del plan en un compositor no
invocable y con confirmación interior fail-closed. M20 materializó plan y gate
privadamente con dobles y entrega one-shot. M21 consumió ese gate mediante una
frase exterior inyectada, ejecución única, normalización cerrada y cleanup
terminal, todo con dobles. M22 auditó esa frontera, congeló su contrato público
y mantuvo fuente y autoridad reales en `false`. M23 cerró el readiness en
`NO-GO` porque falta el proceso propietario M19–M22; fijó fuente, comando y
autorización futuros sin invocarlos. M24 implementó ese módulo únicamente como
owner fixture-only; el comando real continúa rechazado antes del builder. La
fase M25 enlazó las dependencias reales en preview no invocable, con todos los
contadores en cero. La ejecución real sigue prohibida hasta una auditoría
hermética del conjunto M24–M25 y un delta de activación explícito. Pedir o
enviar el primer mensaje sigue reservado exclusivamente a `18/18`.
