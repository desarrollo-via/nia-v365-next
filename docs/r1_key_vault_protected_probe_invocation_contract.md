# Contrato de invocación de la sonda protegida R1

Estado: `HTTP-TRANSPORT-READY-SOURCE-DECISION-REQUIRED`.

Este contrato prepara una única lectura host-side ya desplegada. No autoriza
abrir una fuente protegida, obtener el Bearer Review, hacer red, invocar la
ruta, reiniciar la Web App, cambiar Azure, activar R1, consultar Bitrix ni
enviar mensajes.

## Identidad congelada

- Web App: `nia-v365-next-api`, Production, resource group
  `nia-v365-next-api_group`.
- Main desplegado: merge `2631f8483ca5e565b4ca53874e32f4d6035c09f8`.
- Workflow automático: `31497045244 completed/success`.
- Ruta GET exacta:
  `https://nia-v365-next-api-ekd4fza7e0fzevfd.canadacentral-01.azurewebsites.net/bitrix-connector/review/r1-key-vault-host-probe`.
- Autenticación existente: encabezado `Authorization: Bearer` construido sólo
  dentro de un proceso propietario a partir de `NIA_BITRIX_REVIEW_TOKEN`.
- Evidencia esperada: esquema `nia-next-r1-host-probe-v1`, versiones
  `azure-identity=1.25.3`, `azure-keyvault-secrets=4.11.0`, `aiohttp=3.14.3`,
  `external_calls=0` y `writes=0`.

## Brecha previa y autorización futura mínima

`bitrix_connector/r1_key_vault_protected_probe_invocation_owner.py` implementa
el helper propietario exclusivamente con dobles inyectados. Rechaza cualquier
dependencia que no declare `fixture-double`; no importa HTTP, entorno,
Credential Manager o `.env`. Fija la allowlist única, endpoint, timeout de 15
segundos, cero redirects/retries, clasificación cerrada, borrado del buffer y
cierre en `finally`.

Todavía no existe binding real completo porque falta la fuente. Los helpers R0
manejan otros blobs/allowlists y no se reutilizan por analogía. Antes de
cualquier red debe decidirse y autorizarse separadamente ese origen exacto, sin
exponer valor, longitud, hash, cabecera, URL autenticada, payload bruto o
excepción.

El transporte HTTP real quedó implementado después de esa brecha inicial y se
probó sólo con `httpx.MockTransport`. Continúa faltando exclusivamente la
identidad no secreta de la fuente local del Review token; véase
`docs/r1_key_vault_protected_probe_real_binding_preflight.md`.

La autorización posterior deberá identificar literalmente: fuente protegida,
allowlist única `NIA_BITRIX_REVIEW_TOKEN`, endpoint anterior, una sola petición
GET, timeout finito, cero redirects, cero retries y salida pública limitada al
estado allowlisted. No permite App Settings, Azure, Bitrix, activación ni
mensajes.

## Preflight fresco anterior al envío

1. Confirmar `main`, merge, PR `#15`, ref candidata y run automáticos exactos.
2. Confirmar dos lecturas de salud separadas: `ok/v0.267/off/off/locked`,
   `external=false`, `inert`.
3. Ejecutar las pruebas de ruta, owner y evaluador puros; exigir PASS.
4. Confirmar que el helper dedicado conserva fuente/allowlist exactas, una
   carga, una petición, timeout finito, no redirects y no retries.
5. Comprobar que el estado local y las barreras R1 siguen intactos.
6. Si cualquier identidad, prueba, salud o límite deriva, terminar `NO-GO`
   antes de abrir la fuente protegida.

## Respuesta allowlisted y consumo

`bitrix_connector/r1_key_vault_protected_probe_invocation_policy.py` exige
claves, tipos y valores exactos. Sólo HTTP 200 con setting ausente/null o
presente/true termina `HOST-RUNTIME-BASELINE-VERIFIED`; nunca devuelve nombre o
valor del setting.

- 401 `review_unauthorized`: rechazo previo al owner; no consumido.
- 503 `review_token_not_configured`: rechazo previo al owner; no consumido.
- 503 `host_probe_not_bound`: owner no ligado; no consumido.
- 503 `host_probe_evidence_unavailable`: fallo autenticado; intento consumido.
- 409 `host_probe_already_consumed`: evidencia ya consumida; terminal.
- timeout/corte después de un posible envío: consumo ambiguo; terminal.
- estado, cuerpo, campo o tipo distinto: deriva; terminal.

No se reintenta ningún resultado. Incluso cuando un rechazo conocido no
consume el owner, una nueva petición exige una autorización nueva y preflight
fresco.

## Rollback y detención

La lectura no escribe, por lo que no tiene rollback productivo. El consumo vive
en memoria del proceso desplegado y no se compensa: queda prohibido reiniciar o
redesplegar la Web App para recuperar el intento. Éxito, fallo consumido, 409,
deriva o transporte ambiguo terminan la unidad sin segunda petición. Cualquier
recurso local del futuro helper debe cerrarse en `finally`; cierre no verificado
termina `NO-GO-REMAINDER`.

## Evidencia hermética del owner

El owner fixture-only fija `NIA_BITRIX_REVIEW_TOKEN`, el endpoint exacto, una
carga y una llamada simulada. Sus resultados públicos contienen sólo estado,
contadores, cero red real y booleanos de borrado/cierre. Construcción inerte,
baselines presente/ausente, rechazo HTTP, fallos saneados, remainder, uso único
y rechazo de dependencias reales quedan cubiertos por pruebas locales. Esta
evidencia no prueba credencial, autenticación, red ni runtime productivos.

## Ejecución protegida V1 del 2026-08-11

La autorización agrupó preflight fresco, una apertura interna de `.env`
allowlisted y un GET máximo. El preflight aprobó 9/9: main, ref, PR `#15`,
merge, workflow, cero Actions del candidato, dos pares de salud y estado local
exactos.

El owner fue invocado una sola vez y terminó
`NO-GO-PROTECTED-SOURCE-UNAVAILABLE`, con `protected_source_opened=false`, cero
lecturas, cero solicitudes, cero red, cero reintentos, fuente cerrada y
transporte cerrado. La salida no distingue ausencia, formato o identidad inválida para no
exponer información protegida. La autorización V1 quedó consumida y no se
reintenta ni se inspecciona `.env`. La sonda desplegada no fue consumida.

## Preflight V2 y bloqueo técnico del 2026-08-11

La persona declaró `.env` lista y aceptó V2 mediante `sp`. El preflight fresco
volvió a aprobar 9/9. La plataforma rechazó el comando antes de crear el
proceso: exige aprobación literal posterior a informar que el token será
materializado internamente y enviado como Bearer por HTTPS, y que el GET puede
consumir la sonda aun con fallo o transporte ambiguo.

No se abrió `.env`, no se materializó token y hubo cero GET de sonda. No se
intentó workaround ni repetición. V2 no fue invocada ni consumida a nivel del
owner; queda pendiente la aprobación literal exigida por la plataforma.

## Invocación de provisión V3 del 2026-08-11

La nueva ruta independiente
`/bitrix-connector/review/r1-key-vault-provisioning-preflight` aprobó un
preflight fresco: main/PR/Action exactos, ruta presente en OpenAPI, 22/22
pruebas focales y salud 2/2. Después se abrió `.env` exclusivamente mediante
la fuente allowlisted para `NIA_BITRIX_REVIEW_TOKEN` y se realizó un único GET
Bearer.

Resultado: `HOST-RUNTIME-BASELINE-VERIFIED-SETTING-ABSENT`; una apertura, una
lectura, una solicitud y una llamada real, cero redirects/reintentos, token
borrado y fuente/transporte cerrados. La sonda nueva quedó consumida y no se
repite. No se operó Azure, Credential Manager, activación, Bitrix ni mensajes.
