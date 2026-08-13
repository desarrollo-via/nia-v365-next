# Decisión de transporte para sonda host-side R1 Key Vault

Estado: `PROTECTED-APP-ROUTE-LAZY-BOUND-LOCAL-NOT-PUBLISHED`.

Fecha: 2026-08-11. Esta auditoría fue documental y local. No abrió Azure, túnel,
SSH, Kudu, aplicación productiva, App Settings, secretos o credenciales y no
modificó código funcional, servicios o configuración.

## Requisitos no negociables

La vía debe leer dentro del proceso desplegado sólo tres versiones y
`NIA_BITRIX_KEY_VAULT_URL` por suscripción exacta; nunca enumerar el entorno,
mostrar el valor, abrir shell libre, usar publishing profiles, persistir archivos
o permitir reintentos. Debe producir el esquema saneado ya probado y conservar
R1 apagado.

## Alternativas auditadas

### ARM App Settings — rechazada

La operación oficial `List Application Settings` responde un
`StringDictionary` completo. No ofrece una lectura server-side de una sola clave;
filtrar después ya habría obtenido todos los valores. Viola la prohibición de
enumeración.

Fuente: https://learn.microsoft.com/en-us/rest/api/appservice/web-apps/list-application-settings

### Kudu command API — rechazada

`POST /api/command` acepta una línea de comando arbitraria y usa las mismas
credenciales que el endpoint Git de despliegue. Aunque podría ejecutar Python,
introduce publishing credentials y una superficie de shell libre.

Fuente: https://github.com/projectkudu/kudu/wiki/REST-API

### SSH de App Service — no elegida

Microsoft documenta `az webapp create-remote-connection` como túnel WebSocket
autenticado que después entrega el puerto a un cliente SSH, y `az webapp ssh`
como sesión de shell. La inspección de Azure CLI instalado confirmó que
`create_tunnel_and_session` termina en una shell interactiva; no existe un
contrato público de comando one-shot estructurado. Un binding sobre detalles
internos y autenticación SSH sería frágil y ampliaría la superficie.

Fuentes:
https://learn.microsoft.com/en-us/azure/app-service/configure-linux-open-ssh-session
https://learn.microsoft.com/en-us/cli/azure/webapp#az-webapp-create-remote-connection

## Vía preferida

Preparar en una fase separada un GET fijo bajo el router protegido existente:

```text
/bitrix-connector/review/r1-key-vault-host-probe
```

La ruta debe reutilizar `validate_review_access` y la configuración Review; el
token nunca se lee, devuelve o entrega a Codex. Debe definirse antes de la ruta
dinámica `/{event_key}`, funcionar con runtime R1 apagado y llamar un owner
one-shot inyectable que:

1. usa `importlib.metadata.version` sólo para los tres nombres allowlisted;
2. usa suscripción directa únicamente para `NIA_BITRIX_KEY_VAULT_URL`;
3. valida URL presente sin devolverla, o preserva ausencia;
4. responde sólo el esquema saneado, sin cabeceras o errores privados;
5. rechaza Bearer inválido antes del owner; una evidencia autenticada inválida
   sí consume el intento;
6. no contiene clientes, red saliente, persistencia o mutaciones.

La implementación, pruebas, commit, PR, merge, despliegue y una invocación
humana autenticada son fases independientes. Antes de implementar debe probarse
con dobles que la ruta no colisiona con `/{event_key}`, exige Bearer válido,
permanece disponible con el conector inerte y no habilita decisiones Review.

## Dictamen

`PROTECTED-APP-ROUTE-PREFERRED-NOT-IMPLEMENTED` fue el dictamen de auditoría. Es
la única opción que evita enumeración, publishing credentials y shell usando una
compuerta propia. En ese punto faltaban implementación y evidencia de Review
auth funcional. La auditoría no autorizó publicar, desplegar o invocar.

## Implementación local del 2026-08-11

Se añadió la ruta fija antes de `/{event_key}` y un owner exacto one-shot
inyectable. Bearer inválido se rechaza antes de consumirlo; una colección
autenticada inválida sí consume el intento. La salida Pydantic prohíbe extras y
no incluye nombre o valor del setting. Sin owner, un Bearer válido recibe
`503 host_probe_not_bound`.

El owner mide 3731 bytes y su SHA-256 es
`6A3A6518811847E03DC751148254C1F90033AE73B3AE340904EBEB0DA4BF0CC1`.
Ruta/owner y prototipos aprobaron 25/25 pruebas; la regresión con el router
aprobó 34/34. No hubo entorno real, import runtime, servicio, red, commit,
publicación o despliegue.

## Binding productivo local del 2026-08-11

`r1_key_vault_protected_host_probe_binding.py` liga el owner a `os.environ` e
`importlib.metadata.version` sin efectuar lecturas al construirlo. `router.py`
inyecta ese owner en la ruta protegida; sólo una petición con Bearer Review
válido puede disparar `collect_once`. Las pruebas con mappings no iterables
demostraron cero lecturas en construcción, tres nombres de distribución y una
clave exactos al consumir, saneamiento y consumo one-shot.

El corte focal completo aprobó 71/71 pruebas y compilación; no leyó el entorno
real ni abrió servicio o red. No hubo commit, publicación, despliegue o
invocación. Estado: `PROTECTED-APP-ROUTE-LAZY-BOUND-LOCAL-NOT-PUBLISHED`.

## Sucesión operativa

La ruta fue fusionada y desplegada después de esta decisión histórica. El
contrato vigente de consumo one-shot es
`docs/r1_key_vault_protected_probe_invocation_contract.md`; continúa sin
autorizar fuente protegida, red o invocación.
