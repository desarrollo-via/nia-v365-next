# Contrato de intervención Azure/Key Vault para R1

Estado: `EXPIRED-AWAITING-AZURE-AUTHENTICATION-AND-LISTO`.

Intervención: `R1-KV-2026-08-10-V1`.

Este documento no autoriza autenticación, red, instalación, Azure, GitHub,
App Settings, identidad administrada, RBAC, Key Vault, secretos, publicación,
despliegue, activación, Bitrix ni mensajes. Congela el alcance y el rollback;
los campos no demostrados no se completan por inferencia.

## Identidad fija y datos aún bloqueantes

- Suscripción verificada: `viaindustrial-core`, ID
  `0c4b9ea3-f35d-4a11-bfe7-794d40cf1ec9`.
- Web App exacta: `nia-v365-next-api`; slot: `Production`.
- Host verificado: Linux, `PYTHON|3.12`; Gunicorn pertenece al corte esperado.
- Corte desplegado: `main@641331c63253536ea2531f091b933af4380c95b3`,
  árbol `9e743a9bdde1ac5c1bb8786000c50e94ff9ac597`; PR `#16` y Action
  `31518711951 completed/success`.
- Conector esperado: `v0.267/off/locked/no-external/inert`.
- Secreto físico exacto: `nia-next-bitrix-r1-protected-settings-v1`.
- App Setting no secreta exacta: `NIA_BITRIX_KEY_VAULT_URL`.
- La sonda host-side V2 demostró runtime exacto: `azure-identity=1.25.3`,
  `azure-keyvault-secrets=4.11.0`, `aiohttp=3.14.3` y
  `NIA_BITRIX_KEY_VAULT_URL` ausente, con cero llamadas salientes/escrituras.
- El inventario V2 fresco confirmó identidad ausente, vault dedicado ausente,
  nombre disponible, RBAC no aplicable y resource IDs exactos. El manifiesto
  saneado queda fijado en
  `docs\r1_key_vault_linux_provisioning_manifest_v1.md`.

El nombre candidato comprobado y disponible es `nia-next-r1-kv-260810`. La
disponibilidad no lo reserva ni autoriza su creación.

## Fase I — inventario autenticado de solo lectura

Esta fase se ejecutó una vez sobre `nia-v365-next-api_group` y el único recurso
`Microsoft.Web/sites/nia-v365-next-api`. No se permitió un listado general.

Autorización literal histórica, consumida y no reutilizable:

```text
AUTORIZO INVENTARIO AZURE R1 SOLO LECTURA R1-KV-2026-08-10-V1
```

Fue válida porque el SP anterior declaró resource group y nombre candidato.
Permitió una autenticación y lecturas acotadas de cuenta, Web App, Linux/runtime,
identidad y disponibilidad. El baseline de `NIA_BITRIX_KEY_VAULT_URL` no se leyó:
se obtendrá únicamente mediante el lector host-side de esa clave exacta.

Quedan prohibidos la enumeración del diccionario de App Settings, secretos,
nombres o versiones de secretos, roles amplios, logs, recursos generales y
cualquier escritura. Presupuestos: una autenticación, una lectura por dato
exacto, cero refresh explícitos, cero reintentos y detención en la primera
deriva. La salida persistible se limita a booleanos, identificadores de recurso
no secretos exactos, presencia/ausencia de identidad y App Setting, versiones
de SDK y motivos allowlisted; nunca valores privados.

Resultado permitido: `INVENTORY-EXACT-READY` o `NO-GO-INVENTORY`. El segundo no
se reintenta automáticamente.

### Inventario one-shot del 2026-08-10

La autorización literal se consumió una vez y terminó
`INVENTORY-PARTIAL-BLOCKED`, con cero escrituras y cero reintentos:

- cuenta `viaindustrial-core` y subscription ID esperado: coincidencia exacta;
- resource group `nia-v365-next-api_group`; Web App exacta `Running`;
- host `app,linux`, `PYTHON|3.12`;
- identidad administrada ausente: tipo nulo y principal ausente;
- `nia-next-r1-kv-260810`: nombre disponible;
- faltan lectura host-side del baseline exacto de
  `NIA_BITRIX_KEY_VAULT_URL` y evidencia desplegada de los SDK.

No se leyeron App Settings, RBAC, secretos, logs ni otros recursos. Esta
evidencia no autoriza crear identidad, vault, rol, secreto o setting.

## Fase II — cambio de código y despliegue dormido

Una autorización distinta debe fijar versiones de ambos SDK, conectar el
backend ya hermético y desplegarlo con R1 apagado. No puede crear recursos ni
migrar el secreto. Preflight, publicación, workflow, despliegue y postlectura
son barreras separadas. Salud, SHA, árbol y estado dormido deben permanecer
exactos; cualquier deriva activa el rollback de código.

Preparación local: `azure-identity==1.25.3`,
`azure-keyvault-secrets==4.11.0` y el transporte requerido
`aiohttp==3.14.3` quedaron fijados sin instalación. El lector exacto dormido
`bitrix_connector/r1_key_vault_url_exact_reader.py` recibe un mapping inyectado,
no lo enumera y no lee hasta `collect()` con el único nombre permitido. Esto no
demuestra todavía instalación ni baseline en producción. Lector 9/9 y conjunto
focal 30/30 aprobaron; la regresión hermética válida aprobó 1734/1734 en la
`.venv` Python 3.12 existente.

### Auditoría posterior al despliegue del 2026-08-11

El artefacto exacto `python-app` del run `31449006990`, ID `9085616102`, tamaño
3584150 bytes y digest
`sha256:44777ef0b462d372729c80720f89ebe1968add0a47516f494cfce3f38e4805b2`,
contiene los tres pines y ambos módulos Key Vault. Es el artefacto descargado
por el job que desplegó `main@d5b2325a7025fb00b9d5dde0f20e45ab8217f43b`.
La auditoría 11/11 confirmó cuenta, Web App Linux/Python 3.12, identidad ausente,
nombre de vault disponible, salud dormida y estado local preservado. Hubo cero
escrituras y reintentos; el temporal fue eliminado.

El entorno virtual de build fue excluido del artefacto y la instalación depende
de Oryx. Por ello el payload prueba versiones declaradas, no import/versiones
runtime. Tampoco se enumeraron App Settings: el baseline exacto de
`NIA_BITRIX_KEY_VAULT_URL` sigue pendiente. Resultado:
`ARTIFACT-VERIFIED-RUNTIME-SETTING-EXTERNAL-BLOCKED`.

Una sonda host-side saneada quedó preparada localmente con 7/7 pruebas, 2315
bytes y SHA-256 `069FCD51B81F34CA8C08A9EFC4B55D908BC34A7B2A9E2A2EEA726670BA486972`.
Su lifecycle fixture-only aprobó 10/10 adicionales. La ruta protegida, owner y
binding productivo perezoso quedaron ligados sólo localmente a `os.environ` e
`importlib.metadata.version`; el corte focal aprobó 71/71. La construcción no
lee el entorno y no hubo servicio, red, commit, publicación, despliegue ni
invocación productiva.

La auditoría oficial descartó ARM, Kudu y SSH. La ruta GET protegida fue
publicada y desplegada mediante PR `#15`; su invocación V2 terminó
`HOST-RUNTIME-BASELINE-VERIFIED-SETTING-ABSENT`. Hubo una lectura del Bearer,
un GET, cero redirects/reintentos, buffer borrado y recursos cerrados. La sonda
quedó consumida y no se repite.

## Fase III — provisión productiva

Sólo procede tras refrescar `INVENTORY-V2-EXACT-READY` y con un manifiesto cerrado que incluya
subscription ID, resource group, resource ID de Web App, vault dedicado y su
resource ID, baseline de identidad, App Setting y RBAC, SHA desplegable y
acciones de rollback. Se recomienda vault dedicado para que la propiedad y el
rollback sean inequívocos.

El delta máximo es:

1. crear un vault dedicado nuevo con soft-delete activo y sin purge;
2. conservar la identidad system-assigned si ya existe o crearla si estaba
   ausente, capturando su baseline;
3. crear una única asignación RBAC mínima para lectura del secreto exacto y
   conservar el assignment ID;
4. crear una asignación temporal `Key Vault Secrets Officer`
   (`b86a8fe4-44ce-4948-aee5-eccb2c155cd7`) para el operador exacto, con ID
   preasignado `5e76b332-d208-4129-9ad2-cc760bb23d1f`;
5. migrar una sola vez el blob exacto desde Windows Credential Manager mediante
   el owner protegido, sin imprimir, registrar ni persistir su valor fuera de
   los dos backends;
6. retirar una sola vez la asignación temporal del escritor;
7. fijar únicamente `NIA_BITRIX_KEY_VAULT_URL` con la URL no secreta del vault;
8. verificar salud dormida. App Settings puede reciclar la Web App y se trata
   como una mutación productiva.

El manifiesto saneado mide `12061` bytes y su SHA-256 es
`16EDAC107B1B8041952D8ED324C0542ECAADDB0AA7EC316C2B557F135864AA49`.
Las dos barreras separadas son:

```text
SP inmediatamente anterior: preflight Azure R1 de solo lectura, recursos y presupuestos exactos, cero escrituras
Respuesta ligada: sp
SEGUNDA CONFIRMACION R1 KEYVAULT LINUX R1-KV-2026-08-10-V1 EJECUCION INMEDIATA 16EDAC107B1B8041952D8ED324C0542ECAADDB0AA7EC316C2B557F135864AA49
```

El `sp` sólo autoriza el preflight final descrito inmediatamente antes: lecturas
exactas, cero escrituras y cero apertura de Credential Manager. La confirmación
literal debe ser independiente, posterior e inmediatamente previa al primer
cambio. Ambas barreras expiran ante deriva, cambio de manifiesto o pausa
operativa. No autorizan Fase A R1, Bitrix, participantes ni el tercer mensaje.

## Rollback exacto

- Sin mutación verificada: no ejecutar rollback ni acciones compensatorias.
- Código/deploy: revertir mediante un cambio normal al corte exacto previo y
  redesplegar; nunca hard reset, force push ni alteración de historia.
- App Setting: restaurar exactamente presencia y valor no secreto previos; si
  estaba ausente, eliminar sólo esa clave. Tras el reciclaje, exigir dos lecturas
  de salud dormida.
- RBAC: eliminar sólo el assignment ID creado por esta intervención y confirmar
  su ausencia exacta.
- Escritor temporal: eliminar sólo su assignment ID preasignado. Una retirada
  ambigua no se reintenta; el soft-delete posterior del vault contiene el
  remanente y debe quedar visible.
- Identidad: si era previa se preserva; si fue creada exclusivamente aquí, se
  deshabilita sólo después de retirar RBAC y comprobar que no tiene otro uso.
- Secreto/vault: si el vault dedicado fue creado por esta intervención, conserva
  el mismo resource ID y sólo contiene el secreto exacto, se elimina el vault
  mediante soft-delete. `purge` está prohibido. Si alguna condición no se
  demuestra, se conserva el recurso y termina `NO-GO-REMAINDER`.
- Cierre: exigir `v0.267/off/locked/no-external/inert`, R0 desmontado, R1 apagado
  y Bot NIA `245339` todavía retirado. No tocar Bot Next ni Chat Test.

El rollback tiene presupuesto de una acción exacta y una postlectura por
superficie, salvo las dos lecturas de salud. No hay reintento automático. Toda
ambigüedad deja el remanente visible y exige intervención humana.

## Inventario V2 del 2026-08-11

Terminó `INVENTORY-V2-EXACT-READY`: cuenta y recursos exactos; Web App
`Running/app,linux/PYTHON|3.12`; identidad ausente; vault ausente y nombre
disponible; definición mínima de rol exacta; salud dormida estable y estado
local preservado. Se consumieron una lectura de cuenta, Web App, vault,
disponibilidad y definición de rol; RBAC 0, escrituras 0 y reintentos 0. No se
leyeron App Settings, secretos, logs ni recursos amplios.

## Primer preflight productivo y corrección local

El `sp` ligado fue consumido por un intento que terminó `NO-GO-PREFLIGHT` en el
primer comando lógico. Windows resolvió `az` como `az.cmd` y
`create_subprocess_exec` no pudo crear ese proceso directamente; por tanto no
quedó demostrado contacto con Azure. No se ejecutaron postlecturas ni salud:
comandos lógicos 1, evidencia Azure 0, salud 0, escrituras 0, App Settings 0,
secretos 0, Credential Manager 0 y reintentos 0; recursos locales cerrados.

El binding local ahora traduce exclusivamente el wrapper oficial `az.cmd` al
`python.exe -IBm azure.cli` de la misma instalación. Conserva ejecución sin
shell, argv allowlisted, salida saneada y presupuesto one-shot. Aprobó 27/27
pruebas focales con el owner y 1878/1878 en regresión hermética. La corrección
no se ha ejecutado contra Azure y requiere un nuevo `sp` ligado para un solo
preflight fresco; la confirmación literal y toda mutación siguen bloqueadas.

## Criterio vigente

La intervención está `EXPIRED-AWAITING-AZURE-AUTHENTICATION-AND-LISTO`.
Inventario, manifiesto y owner hermético quedaron cerrados. La nueva ruta fue
publicada/desplegada mediante PR `#16` y su invocación one-shot demostró el
baseline ausente con limpieza completa; quedó consumida y no se reutiliza.
El primer preflight consumió su presupuesto en el problema local del wrapper
`az.cmd`, sin evidencia Azure ni efectos. El runner quedó corregido localmente
para usar el Python incluido por Azure CLI, todavía sin ejecución externa. La
siguiente barrera es un nuevo `sp` ligado al SP inmediatamente anterior para un
solo preflight de lectura. La confirmación literal permanece reservada para la
primera mutación; Credential Manager y toda escritura continúan bloqueados.

El segundo `sp` de preflight quedó consumido: Azure CLI inició, pero la segunda
lectura no produjo evidencia aceptable. Hubo dos comandos, salud 0, escrituras
0, App Settings 0, secretos 0, Credential Manager 0 y reintentos 0; recursos
cerrados. No se repitió la consulta. La corrección local posterior fija la
suscripción exacta en cada comando y hace fail-fast tras cada lectura; aprobó
29/29 pruebas con el owner y 1880/1880 en regresión hermética, pero permanece
sin ejecución externa.

El tercer `sp` también quedó consumido en dos comandos. La coincidencia de
`az account show` era sólo caché local; el comando Web App, primera llamada ARM
real, devolvió fallo. Salud, escrituras, App Settings, secretos, Credential
Manager y reintentos permanecieron en 0; recursos cerrados. El subcomando carga
correctamente con ayuda local, pero no existe evidencia para escoger entre
autenticación, autorización, recurso o transporte.

La preparación posterior reemplaza la primera lectura por un GET ARM exacto de
la suscripción y reduce stderr internamente a una categoría allowlisted sin
exponer texto. Aprueba 30/30 con el owner y 1881/1881 en regresión hermética;
permanece sin ejecución externa.

La envolvente iterativa autorizada consumió 1/4 intentos y una lectura ARM. El
resultado fue `r1_kv_binding_command_failed_authentication`; las demás lecturas,
salud, efectos, secretos y reintentos permanecieron en 0 y los recursos cerraron.
Los tres intentos restantes permanecen dentro de la misma autorización, pero no
se usan hasta que la persona complete su autenticación Azure CLI normal y lo
indique sin compartir credenciales. No se requiere otro SP para reanudar.

Al cambiar el día de Bogotá a 2026-08-12, esa envolvente venció por protocolo
después de consumir 1/4 intentos. Para evitar una confirmación redundante, el SP
vigente define que la respuesta exacta `listo`, posterior al `az login` manual,
confirma la intervención humana y acepta simultáneamente una nueva envolvente
del mismo alcance con máximo tres intentos restantes. No amplía recursos,
lecturas, riesgos ni efectos y continúa excluyendo secretos y mutaciones.

El coordinador hermético
`bitrix_connector/r1_azure_diagnostic_coordinator.py` materializa el presupuesto
de tres intentos, ocho lecturas y una pareja de salud por intento. Reconstruye
intentos one-shot dentro de la misma envolvente, continúa sólo ante categorías
recuperables y detiene por autenticación, deriva, evidencia inválida, cierre
fallido o agotamiento. No contiene binding, secreto, red ni mutación.
`bitrix_connector/r1_azure_diagnostic_real_attempt.py` aporta el adaptador al
binding exacto existente; su construcción permanece inerte y sólo crea efectos
cuando la envolvente autorizada ejecuta `run_once`.
