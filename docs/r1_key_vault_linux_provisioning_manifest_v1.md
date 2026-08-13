# Manifiesto saneado de provisión R1 Key Vault Linux V1

Estado: `ATTENTION-REQUIRED-AZURE-AUTHENTICATION`.

Intervención: `R1-KV-2026-08-10-V1`.

Este manifiesto fija el delta máximo y el rollback. No autoriza abrir la fuente
protegida, leer valores, escribir Azure, activar R1, consultar Bitrix ni enviar
mensajes. Su SHA-256 externo vincula la confirmación literal de mutación del
contrato de intervención; el hash no se inserta aquí para evitar una referencia
circular.

## Baseline exacto del 2026-08-11

- Suscripción: `viaindustrial-core`, ID
  `0c4b9ea3-f35d-4a11-bfe7-794d40cf1ec9`.
- Resource group único: `nia-v365-next-api_group`.
- Web App: `nia-v365-next-api`, slot `Production`, estado `Running`,
  `app,linux`, `PYTHON|3.12`.
- Resource ID de Web App:
  `/subscriptions/0c4b9ea3-f35d-4a11-bfe7-794d40cf1ec9/resourceGroups/nia-v365-next-api_group/providers/Microsoft.Web/sites/nia-v365-next-api`.
- Host:
  `nia-v365-next-api-ekd4fza7e0fzevfd.canadacentral-01.azurewebsites.net`.
- Identidad system-assigned: ausente; `principalId` ausente.
- Vault `nia-next-r1-kv-260810`: ausente y nombre disponible.
- Resource ID futuro determinista del vault:
  `/subscriptions/0c4b9ea3-f35d-4a11-bfe7-794d40cf1ec9/resourceGroups/nia-v365-next-api_group/providers/Microsoft.KeyVault/vaults/nia-next-r1-kv-260810`.
- URL futura no secreta: `https://nia-next-r1-kv-260810.vault.azure.net/`.
- RBAC de ese vault: no aplicable en el baseline porque el vault y el principal
  no existen; asignaciones exactas: cero por construcción.
- Rol futuro único: `Key Vault Secrets User`, definition ID
  `4633458b-17de-408a-b874-0445c86b69e6`.
- Assignment ID futuro único y preasignado:
  `eb70d2d7-bfe7-49ed-8ccc-0fd43d1c6447`; permite rollback exacto incluso si
  la respuesta de creación resulta ambigua.
- Escritor temporal mínimo: `Key Vault Secrets Officer`, definition ID
  `b86a8fe4-44ce-4948-aee5-eccb2c155cd7`, verificado en documentación oficial.
- Assignment ID temporal preasignado del escritor:
  `5e76b332-d208-4129-9ad2-cc760bb23d1f`; el principal humano exacto se obtiene
  en el preflight sin persistir UPN ni otros datos de cuenta.
- Secreto futuro único: `nia-next-bitrix-r1-protected-settings-v1`.
- App Setting única futura: `NIA_BITRIX_KEY_VAULT_URL`; baseline host-side:
  ausente, sin enumerar el diccionario de App Settings.
- Fuente futura: target exacto de Windows Credential Manager
  `nia-next/bitrix-r1/protected-settings/v1`, con las siete claves allowlisted
  ya fijadas por el contrato M80 y sin enumeración ni fallback.
- Corte desplegado: `main@641331c63253536ea2531f091b933af4380c95b3`,
  árbol `9e743a9bdde1ac5c1bb8786000c50e94ff9ac597`; PR `#16` y Action
  automática `31518711951 completed/success`.
- Salud posterior: NIA `200/ok`; conector `200`, `v0.267`,
  `off/off`, `activation_locked=true`, `external_calls_enabled=false`,
  `runtime_state=inert`.

## Evidencia del inventario

- Resultado: `INVENTORY-V2-EXACT-READY`.
- Lecturas autenticadas: cuenta 1, Web App 1, vault exacto 1, disponibilidad
  del nombre 1, definición de rol exacta 1 y asignaciones RBAC 0.
- Salud pública: una pareja antes y una pareja después.
- Estado local: 125 entradas antes y después; SHA-256 saneado idéntico
  `8A10BF5824349B7218889F7F5D6959C9AED2623001CBC78E8DA6B958188E9C20`.
- Escrituras Azure 0; lecturas de App Settings 0; lecturas de secretos 0;
  reintentos 0.

## Delta productivo máximo

Tras un `sp` ligado al SP de preflight, un preflight fresco exacto y la
confirmación literal de mutación:

1. crear únicamente el vault indicado, con RBAC, soft-delete y sin purge;
2. habilitar una sola identidad system-assigned en la Web App y capturar su
   `principalId` devuelto por Azure;
3. crear una sola asignación del rol lector al principal capturado y al scope
   exacto del vault, conservando el assignment ID devuelto;
4. crear el assignment temporal escritor exacto para el operador autenticado;
5. leer una sola vez el target protegido exacto y escribir una sola versión del
   secreto exacto, sin exponer ni persistir el valor fuera de los backends;
6. retirar una sola vez el assignment temporal escritor antes de continuar;
7. fijar únicamente `NIA_BITRIX_KEY_VAULT_URL` con la URL no secreta exacta;
8. exigir salud dormida estable y conservar R1 apagado.

No se permiten listados generales, otras identidades, otros roles, otros
vaults, otros secretos, otras App Settings, `purge`, reintentos ni ampliaciones.

## Detención y rollback por superficie

- Antes de la primera escritura: cualquier deriva termina `NO-GO` y no ejecuta
  compensaciones.
- App Setting: si se escribió, retirar únicamente
  `NIA_BITRIX_KEY_VAULT_URL`, pues su baseline era ausente, y exigir dos
  lecturas de salud dormida.
- RBAC: retirar únicamente el assignment ID creado y confirmar su ausencia.
- Escritor temporal: retirar sólo
  `5e76b332-d208-4129-9ad2-cc760bb23d1f`; si su retirada resulta ambigua no se
  reintenta y el rollback continúa hasta soft-delete del vault exacto.
- Identidad: deshabilitarla sólo si fue creada por esta intervención, después
  de retirar RBAC y comprobar ausencia de otro uso.
- Vault/secreto: si el vault conserva el resource ID exacto, fue creado por
  esta intervención y sólo contiene el secreto exacto, eliminarlo mediante
  soft-delete; `purge` queda prohibido.
- Toda identidad, assignment ID, secret version ID y operación iniciada se
  captura internamente y se devuelve sólo como evidencia no secreta.
- Si una condición no puede demostrarse, preservar el recurso y terminar
  `NO-GO-REMAINDER`; no improvisar ni reintentar.

## Presupuestos de la futura ejecución

- `sp` de preflight: autoriza exclusivamente lecturas exactas y preparación del
  owner; escrituras 0 y fuentes protegidas 0.
- Confirmación literal de mutación: una ejecución inmediata, un efecto por cada superficie,
  una retirada normal del escritor temporal y cero reintentos.
- Rollback: una acción exacta y una postlectura por superficie; salud permite
  dos lecturas.
- Resultado terminal permitido: `PROVISIONED-DORMANT-VERIFIED`,
  `NO-GO-BEFORE-WRITE` o `NO-GO-REMAINDER`.

La provisión no habilita R1, no modifica Bitrix y no autoriza el tercer mensaje.

## Owner hermético

`bitrix_connector/r1_key_vault_linux_provisioning_owner.py` implementa el gate
de `sp` para preflight y confirmación literal para mutación, preflight exacto,
serialización allowlisted al formato
Key Vault, presupuestos one-shot, borrado de buffers y rollback inverso por
superficie, incluido el escritor temporal. Sólo acepta puertos inyectados y no
contiene binding real, CLI, entorno, Credential Manager, SDK, red o ejecución
productiva. Sus 16 pruebas
herméticas cubren éxito, deriva, confirmaciones incorrectas, fallos ambiguos,
rollback, remanentes, cierre y ausencia de listados.

La ruta local nueva
`/bitrix-connector/review/r1-key-vault-provisioning-preflight` dispone de un
owner one-shot independiente de la sonda histórica consumida. Lee sólo la
clave exacta y versiones allowlisted después del Bearer; 5/5 pruebas prueban
aislamiento, autenticación y salida saneada. Quedó desplegada mediante PR
`#16`; su única invocación terminó
`HOST-RUNTIME-BASELINE-VERIFIED-SETTING-ABSENT`, con una lectura, un GET, cero
redirects/reintentos y cierre/limpieza completos. La sonda quedó consumida. El
binding real conserva esta evidencia como baseline fijo y no puede sustituirla
por una enumeración de App Settings.

## Binding real dormido

`bitrix_connector/r1_key_vault_linux_provisioning_real_binding.py` conecta el
owner con un runner Azure CLI sin shell y argv allowlisted. En Windows resuelve
el wrapper oficial `az.cmd` hacia el `python.exe -IBm azure.cli` incluido por la
misma instalación, sin ejecutar `cmd.exe`; en otras plataformas usa el
ejecutable resuelto directamente. También aporta control one-shot por
superficie, dos endpoints públicos de salud, fuente Credential Manager
construida sin apertura y sink Key Vault SDK materializado únicamente durante
la escritura. La construcción no crea procesos, importa SDK Azure, autentica,
hace red ni lee la fuente protegida.

Sus 11 pruebas verifican allowlist y rechazo de listados amplios, ejecución por
argv sin shell ni wrapper `.cmd`, descarte de stderr, preflight exacto,
detención por deriva, comandos de
mutación/rollback, presupuestos one-shot, composición inerte, lifecycle
fixture-only completo y cierre del SDK. Junto con el owner aprobaron 27/27; la
regresión hermética completa terminó `1878/1878`. No se ejecutaron comandos
Azure, SDK reales, Credential Manager ni escrituras.

El primer preflight productivo autorizado terminó `NO-GO-PREFLIGHT` al reclamar
el primer comando lógico (`az account show`): el proceso externo no llegó a
crearse porque Windows expone Azure CLI mediante `az.cmd`. Se consumió el
presupuesto del intento y no se repitió. Evidencia: comandos lógicos 1,
resultados Azure demostrados 0, salud 0, escrituras 0, App Settings 0, secretos
0, Credential Manager 0 y reintentos 0; recursos locales cerrados. La corrección
del runner descrita arriba permanece local, aprobó 27/27 pruebas focales con el
owner y 1878/1878 en regresión hermética, y exige un nuevo `sp` ligado antes de
un único preflight fresco.

El segundo preflight autorizado demostró que el runner corregido inicia Azure
CLI, pero terminó `NO-GO-PREFLIGHT` durante la segunda lectura. Presupuesto
consumido: comandos Azure 2, salud 0, escrituras 0, App Settings 0, secretos 0,
Credential Manager 0 y reintentos 0; recursos cerrados. La salida saneada no
permite distinguir retrospectivamente entre fallo del comando Web App y salida
inválida. La revisión local detectó que la cuenta se validaba sólo al final y
los demás comandos dependían de la suscripción predeterminada.

El binding ahora fija `--subscription` con el ID exacto en todos los comandos y
valida cada lectura inmediatamente antes de habilitar la siguiente. Dos pruebas
nuevas demuestran detención tras una cuenta divergente y suscripción explícita
en toda la allowlist; el conjunto binding+owner aprueba 29/29 y la regresión
hermética 1880/1880. Esta corrección no se ha ejecutado contra Azure y no
autoriza otro intento.

El tercer preflight autorizado volvió a detenerse en el comando Web App. La
cuenta cacheada coincidió con la suscripción explícita, luego el primer comando
remoto devolvió un código no exitoso: comandos 2, categoría saneada
`r1_kv_binding_command_failed`, salud 0, escrituras 0, App Settings 0, secretos
0, Credential Manager 0, reintentos 0 y recursos cerrados. `webapp show --help`
aprobó localmente, por lo que el subcomando está instalado; no se conservó ni
mostró stderr y no es lícito atribuir aún la causa a autenticación, permisos,
recurso o transporte.

La lectura inicial ahora usa un GET ARM exacto de la suscripción, de modo que
demuestra autenticación remota en vez de limitarse a `az account show`. El
runner captura stderr de forma acotada, lo reduce inmediatamente a una categoría
fija (`authentication`, `authorization`, `not_found`, `transport` o `unknown`)
y nunca devuelve el texto original. El binding+owner aprueba 30/30 y la
regresión hermética 1881/1881. No se ha ejecutado este diagnóstico contra Azure
y no autoriza otro intento.

La envolvente diagnóstica autónoma fue autorizada con máximo cuatro intentos,
ocho lecturas exactas y una pareja de salud por intento. El intento 1 corrigió
primero la proyección ARM a `subscriptionId`, aprobó 30/30 pruebas locales y
ejecutó una sola lectura. Terminó `NO-GO-PREFLIGHT` con categoría saneada
`r1_kv_binding_command_failed_authentication`; salud 0, escrituras 0, App
Settings 0, secretos 0, Credential Manager 0, reintentos 0 y recursos cerrados.
Quedan tres intentos, pero la envolvente está detenida por intervención humana
real hasta que la persona autentique Azure CLI mediante su flujo normal. Esa
acción no es una nueva autorización y no debe compartir credenciales en el chat.
