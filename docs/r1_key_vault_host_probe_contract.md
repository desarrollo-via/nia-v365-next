# Contrato de sonda host-side R1 Key Vault

Estado: `PROTECTED-APP-ROUTE-LAZY-BOUND-LOCAL-NOT-PUBLISHED`.

Este contrato prepara una única sonda no persistente en la Web App exacta. No
autoriza ejecutarla, abrir una shell interactiva, enumerar variables, leer o
mostrar valores, listar App Settings, instalar paquetes, escribir archivos,
reiniciar servicios, cambiar Azure, identidad, RBAC, vault, secretos, settings,
activar R1, consultar Bitrix o enviar mensajes.

## Alcance fijo

- Suscripción: `0c4b9ea3-f35d-4a11-bfe7-794d40cf1ec9`.
- Resource group: `nia-v365-next-api_group`.
- Web App: `nia-v365-next-api`; slot `Production`; Linux/Python 3.12.
- Despliegue: `main@d5b2325a7025fb00b9d5dde0f20e45ab8217f43b`.
- Payload local: `scripts/r1_key_vault_host_probe_payload.py`.
- Payload: 2315 bytes; SHA-256
  `069FCD51B81F34CA8C08A9EFC4B55D908BC34A7B2A9E2A2EEA726670BA486972`.

## Lecturas exactas y salida saneada

El payload llama `importlib.metadata.version` una vez para cada distribución:
`azure-identity`, `azure-keyvault-secrets` y `aiohttp`, exigiendo respectivamente
`1.25.3`, `4.11.0` y `3.14.3`. Después usa una sola suscripción directa sobre
`NIA_BITRIX_KEY_VAULT_URL`; nunca itera el mapping. Ausencia es un baseline
válido. Si está presente, valida la URL canónica pero no la devuelve.

La única salida permitida contiene esquema, tres versiones, `setting_present`,
`setting_valid`, `external_calls=0` y `writes=0`. Excepción, versión distinta,
valor inválido o campo adicional termina `NO-GO` sin reintento. No se importan
SDK de Azure ni se construyen credenciales o clientes.

## Transporte requerido y brecha vigente

El transporte futuro debe enviar el payload por entrada estándar directamente a
`python -` dentro del contenedor exacto, ejecutar un solo proceso, capturar sólo
una línea JSON allowlisted y cerrar inmediatamente túnel, SSH y proceso. Debe
tener límites finitos, cero archivos remotos, cero TTY y cero comandos libres.

La CLI instalada ofrece `az webapp ssh` interactivo y
`az webapp create-remote-connection`, pero todavía no existe un comando local
probado que una el túnel con ejecución no interactiva y autenticación saneada.
No se improvisan credenciales ni se consultan publishing profiles. Hasta ligar
y probar ese transporte con dobles, la ejecución productiva es `NO-GO`.

## Preflight futuro

Antes de una autorización separada deben coincidir SHA, Web App, runtime,
identidad ausente, salud dormida, payload tamaño/huella exactos, transporte
cerrable y salida allowlisted. Se permite una sesión, un proceso y cero
reintentos. El estado local debe preservarse.

## Criterio y rollback

Éxito futuro: `HOST-RUNTIME-BASELINE-VERIFIED`, con versiones exactas y setting
presente/válido o ausente demostrado. Como la sonda no escribe, no existe
rollback productivo; fallo de cierre deja `NO-GO-REMAINDER`. Cualquier recurso,
archivo o configuración inesperados prohíben compensación automática.

## Validación local del 2026-08-11

El payload aprobó 7/7 pruebas herméticas y compilación. Las pruebas cubrieron
setting ausente, presente canónico sin exposición, valores inválidos, versión
distinta, distribución ausente redactada, salida exacta y ausencia de
enumeración, red o persistencia. No se leyó el entorno real ni hubo Azure,
servicio o ejecución remota. Continúa
`PREPARED-TRANSPORT-UNBOUND-NOT-AUTHORIZED`.

## Prototipo fixture-only del 2026-08-11

`bitrix_connector/r1_key_vault_host_probe_transport.py` mide 6916 bytes y tiene
SHA-256 `00C76ACD3131D2D318CD5BFDC45166CD15D5F62F78F5C73B47BE7C9047F986F0`.
Sólo acepta túnel y proceso marcados `fixture-double`; no contiene subprocess,
socket, Fabric, Azure CLI, credenciales, HTTP ni salida propia.

El owner fija scope, timeouts 30/15 segundos, puerto loopback no privilegiado,
argv `python -`, stdin con payload exacto, una línea JSON allowlisted, cierre de
proceso/túnel, un uso y cero reintentos. Aprobó 10/10 pruebas; junto al payload,
17/17. La inspección estática de Azure CLI confirmó túnel separable, pero su
sesión SSH ejecuta una shell interactiva y no ofrece este runner exacto. No se
abrió conexión ni se leyó credencial. Estado:
`FIXTURE-TRANSPORT-VERIFIED-PRODUCTION-BINDING-BLOCKED`.

La auditoría oficial posterior rechazó ARM porque lista el diccionario completo,
Kudu porque combina publishing credentials con comando arbitrario y SSH porque
su contrato público entrega una shell/cliente, no una operación estructurada.
Se eligió preparar separadamente una ruta GET bajo el Bearer Review existente;
no fue implementada, desplegada ni invocada. Véase
`docs/r1_key_vault_host_probe_transport_decision.md`.

La ruta protegida y el owner inyectable fueron implementados localmente y
aprobaron 25/25 pruebas combinadas y 34/34 con la regresión del router. El
binding productivo local liga perezosamente el owner a `os.environ` e
`importlib.metadata.version`, y `router.py` lo inyecta en la ruta. Construirlo
no lee paquetes ni entorno; sólo una solicitud con Bearer Review válido puede
consumir la evidencia exacta una vez. El corte focal aprobó 71/71 pruebas y
compilación. No se leyó el entorno real ni hubo servicio, red, commit,
publicación, despliegue o invocación.

## Sucesión operativa

La ruta fue fusionada y desplegada después de este diseño histórico. El estado
operativo vigente y la barrera previa a su primera invocación están en
`docs/r1_key_vault_protected_probe_invocation_contract.md`; esta nota no
autoriza credenciales, red ni consumo.
