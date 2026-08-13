# Contrato de refresco Azure R1 Key Vault V2

Estado: `INVENTORY-V2-EXACT-READY`.

Objetivo: convertir el resultado host-side V2 en un baseline Azure fresco y
saneado antes de cualquier provisión. Este contrato no autoriza autenticación,
Azure, App Settings, identidad, RBAC, vault, secretos, escrituras, activación,
Bitrix ni mensajes.

## Identidad fija

- Suscripción: `0c4b9ea3-f35d-4a11-bfe7-794d40cf1ec9`.
- Resource group único: `nia-v365-next-api_group`.
- Web App única: `nia-v365-next-api`, slot Production.
- Main desplegado: `2631f8483ca5e565b4ca53874e32f4d6035c09f8`.
- Vault candidato: `nia-next-r1-kv-260810`.
- Secreto futuro: `nia-next-bitrix-r1-protected-settings-v1`.
- Baseline host V2: SDK exactos y `NIA_BITRIX_KEY_VAULT_URL` ausente.

## Único inventario futuro

Una autorización literal independiente podrá permitir una autenticación Azure
y sólo estas lecturas proyectadas:

1. cuenta/suscripción exactas;
2. Web App, slot, estado, Linux/Python e identidad system-assigned;
3. disponibilidad o resource ID exacto del vault candidato;
4. modo RBAC del vault exacto si ya existe;
5. asignaciones de rol limitadas al principal y scope exactos, sólo si ambos
   existen;
6. salud pública dormida antes y después;
7. estado local preservado.

Quedan prohibidos listados generales, valores o diccionario de App Settings,
nombres/versiones/valores de secretos, logs, otros grupos o recursos y toda
escritura. Presupuesto: una lectura por dato, cero reintentos y detención ante
deriva o respuesta ambigua.

## Resultado y siguiente barrera

Éxito: `INVENTORY-V2-EXACT-READY`, con resource IDs no secretos, identidad
presente/ausente, vault presente/ausente, RBAC exacto/ausente y cero escrituras.
Después se prepara un manifiesto final con SHA-256 y rollback por superficie;
la provisión sigue requiriendo las dos confirmaciones literales del contrato
Azure. Un inventario `NO-GO` no se reintenta automáticamente.

## Ejecución one-shot del 2026-08-11

El inventario autorizado terminó `INVENTORY-V2-EXACT-READY`:

- cuenta, suscripción, resource group y Web App coincidieron;
- Web App `Running`, `app,linux`, `PYTHON|3.12`;
- identidad system-assigned y `principalId` ausentes;
- vault candidato ausente y nombre disponible;
- RBAC no se consultó porque no existían vault ni principal;
- la definición exacta `Key Vault Secrets User` quedó fijada;
- salud dormida estable antes y después;
- estado local preservado por conteo y SHA-256 saneado.

Presupuesto consumido: cuenta 1, Web App 1, vault 1, disponibilidad 1,
definición de rol 1, RBAC 0, escrituras 0 y reintentos 0. No se leyeron App
Settings, secretos, logs ni otros recursos. El manifiesto resultante es
`docs\r1_key_vault_linux_provisioning_manifest_v1.md`; toda provisión continúa
bloqueada hasta sus dos confirmaciones literales separadas.
