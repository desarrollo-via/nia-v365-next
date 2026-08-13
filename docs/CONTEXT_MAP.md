# Mapa de contexto — nia-next

`nia_next.md` es la única autoridad variable. Este mapa sólo selecciona
referencias; no autoriza red, Azure, Git remoto, secretos, Bitrix ni ejecución.

## Carga inicial

1. Común central en el orden de `AGENTS.md`.
2. `PROTOCOLO_PROPIO_NIA_NEXT.md`.
3. `nia_next.md`.
4. Este mapa.
5. Únicamente la ruta activada por el objetivo.

## Continuidad general o `tc`

- Estado: `nia_next.md`.
- Pruebas: `docs/TEST_MAP.md`.
- Comprobar enlaces y las tres huellas históricas declaradas abajo.
- Recuperar una sola evidencia histórica focalizada; no abrir respaldos
  completos por rutina.
- Contrato EAOR R1 y coordinador hermético:
  `docs/r1_result_eaor_contract.md` y
  `bitrix_connector/r1_result_eaor_coordinator.py`.

## Azure: autenticación y diagnóstico de solo lectura

- Criterio vigente: sección final de
  `docs/r1_azure_key_vault_intervention_contract.md`.
- Manifiesto exacto: `docs/r1_key_vault_linux_provisioning_manifest_v1.md`.
- Binding one-shot:
  `bitrix_connector/r1_key_vault_linux_provisioning_real_binding.py`.
- Coordinador iterativo:
  `bitrix_connector/r1_azure_diagnostic_coordinator.py`.
- Adaptador real de construcción inerte:
  `bitrix_connector/r1_azure_diagnostic_real_attempt.py`.
- Lanzador y reporte sanitario local:
  `scripts/run_r1_azure_diagnostic_envelope.py`.
- Diagnóstico focal de identidad, una sola lectura:
  `scripts/run_r1_azure_operator_diagnostic.py`.
- Lanzador de provisión, inerte hasta el literal canónico:
  `scripts/run_r1_key_vault_provisioning.py`.
- Postlectura exacta del rollback del vault:
  `scripts/run_r1_key_vault_rollback_postread.py`.
- Sucesor de una sola lectura para el estado soft-deleted:
  `scripts/run_r1_key_vault_deleted_postread.py`.
- Diagnóstico acotado del Activity Log de `vault create`:
  `scripts/run_r1_key_vault_create_activity_diagnostic.py`.
- Diagnóstico causal mínimo, inerte hasta SP independiente:
  `scripts/run_r1_key_vault_create_cause_diagnostic.py`.
- Preflight exacto del proveedor, inerte hasta SP independiente:
  `scripts/run_r1_key_vault_provider_preflight.py`.
- Registro one-shot del proveedor, inerte hasta confirmación literal:
  `scripts/run_r1_key_vault_provider_registration.py`.
- Contrato exacto de preflight, mutación y recuperación:
  `docs/r1_key_vault_provider_registration_contract.md`.
- La envolvente general y luego el diagnóstico focal agotaron su único intento
  en la lectura de identidad, antes de salud. El segundo aisló una sintaxis CLI
  no soportada; el comando ya fue corregido y validado localmente. Cualquier
  nueva lectura Azure requiere SP específico y no debe repetir las seis lecturas
  de inventario superadas.
- La repetición focal y el preflight integral posterior terminaron `GO`; la
  divergencia literal quedó reconciliada usando `SEGUNDA CONFIRMACION…`.
- La provisión intentó crear el vault y ejecutó `keyvault delete`; la
  postlectura contractual se completó después mediante sucesores acotados.
- La primera postlectura probó ausencia activa; dos proyecciones soft-deleted
  previas fueron inconclusas. El sucesor ARM exacto resolvió finalmente el estado.
- El GET ARM devolvió `not_found`: junto con la ausencia activa, cierra el
  rollback como `ROLLBACK-VERIFIED-NO-RESOURCE`.
- El diagnóstico histórico encontró dos eventos ARM de escritura del vault y
  uno fallido. La lectura causal posterior devolvió
  `MissingSubscriptionRegistration`; la ruta activa es preparar de forma
  inerte la comprobación exacta de `Microsoft.KeyVault` y su remediación mínima.
  No consultar proveedores, registrar namespaces ni repetir provisión sin una
  autorización nueva y específica.
- El registro one-shot de `Microsoft.KeyVault` no devolvió evidencia terminal,
  pero una postlectura separada confirmó después `Registered`. La remediación
  quedó verificada sin repetir el registro ni hacer `unregister`.
- La ruta activa vuelve a un preflight integral fresco de provisión, sólo de
  lectura. La confirmación de provisión anterior fue consumida y no se reutiliza.

## Provisión Key Vault

- Owner y binding:
  `bitrix_connector/r1_key_vault_linux_provisioning_owner.py` y
  `bitrix_connector/r1_key_vault_linux_provisioning_real_binding.py`.
- Contrato/manifiesto:
  `docs/r1_key_vault_linux_provisioning_manifest_v1.md`.
- La confirmación literal de mutación permanece separada del preflight.
- No abrir Credential Manager ni ejecutar escrituras por inferencia.

## Activación R1 — Fase A

- Contrato: `docs/r1_pre_event_activation_session_contract.md`, Fase A.
- Preflight y evidencia:
  `bitrix_connector/r1_pre_event_activation_preflight.py`,
  `bitrix_connector/r1_pre_event_activation_compound_owner.py` y
  `bitrix_connector/r1_pre_event_activation_real_binding.py`.
- Owner transaccional dormido:
  `bitrix_connector/r1_pre_event_activation_apply_owner.py`.
- Binding productivo dormido y verificador anónimo:
  `bitrix_connector/r1_pre_event_activation_apply_real_binding.py`.
- Adaptador EAOR:
  `bitrix_connector/r1_result_eaor_activation_adapter.py`.
- Puerto único y constructor superior dormido:
  `bitrix_connector/r1_result_eaor_product_port.py`.
- Lanzador productivo gobernado, runner de dos fases y CLI de preflight local:
  `bitrix_connector/r1_result_eaor_product_launcher.py` y
  `bitrix_connector/r1_result_eaor_product_runner.py` y
  `scripts/run_r1_result_eaor_product_preflight.py`.
- Auditoría hermética integral del runner:
  `tests/test_r1_result_eaor_product_runner.py`.
- Binding dormido de factories productivas y su auditoría integral:
  `bitrix_connector/r1_result_eaor_product_real_binding.py` y
  `tests/test_r1_result_eaor_product_real_binding.py`.
- Supplier asíncrono de preflight y control remoto del owner montado:
  `bitrix_connector/r1_pre_event_activation_product_supplier.py`,
  `bitrix_connector/r1_result_eaor_remote_session_adapter.py` y
  `bitrix_connector/r1_remote_session_http_client.py`.
- EAOR diaria de preflight remoto, ejecutada y cerrada en `GO`:
  `docs/r1_remote_preflight_eaor_2026-08-13.md` y
  `bitrix_connector/r1_result_eaor_remote_preflight_coordinator.py`.
- Binding real diferido y auditoría local de construcción:
  `bitrix_connector/r1_result_eaor_remote_preflight_real_binding.py` y
  `scripts/run_r1_remote_preflight_construction_audit.py`.
- Lanzador exacto de ejecución, invocado una vez como módulo:
  `scripts/run_r1_remote_preflight_eaor.py`.
- Auditoría hermética de la cadena completa con dobles de I/O:
  `tests/test_r1_remote_preflight_full_chain_audit.py`.

## Sesión R1, participantes y tercer mensaje

- Contrato: `docs/r1_pre_event_activation_session_contract.md`, Fase B.
- Gate/control:
  `bitrix_connector/bitrix_event_scoped_r1_gate.py` y
  `bitrix_connector/bitrix_event_scoped_r1_control.py`.
- Lease/binding:
  `bitrix_connector/bitrix_event_scoped_r1_pre_event_lease.py`,
  `bitrix_connector/bitrix_event_scoped_r1_participant_mount.py` y
  `bitrix_connector/bitrix_event_scoped_r1_pre_event_binding.py`.
- Identidades fijas: Bot NIA `245339`, Bot Next `373259`, Chat Test
  `78733`/`chat78733`.
- Se conservan dos confirmaciones Bitrix. No existe confirmación manual
  intermedia; el baseline técnico debe probar ausencia de ambos bots.
- El tercer mensaje sigue siendo manual, único y sólo ante
  `ATTENTION-REQUIRED` más `human_message_required_now=true`.
- La coordinación de owners productivos y el monitoreo acotado están en
  `bitrix_connector/r1_result_eaor_product_port.py`; el supervisor es externo
  al proceso reiniciado de la Web App.

## R0, P1-B o credenciales protegidas

Abrir sólo cuando el objetivo los nombre:

- `docs/bitrix_history_r0_preflight_execution_runbook.md`;
- `docs/bitrix_p1b_protected_settings_runbook.md`;
- manejo protegido del protocolo propio.

Nunca abrir `.env`, enumerar App Settings ni observar valores privados.

## Git, PR y despliegues históricos

Para PR `#13`–`#16`, workflows, refs o rollbacks, buscar primero el identificador
en el respaldo v0.614. Éste conserva las rutas detalladas del mapa anterior.
Ninguna evidencia histórica autoriza otra publicación o despliegue.

## Mejora de común central

- Propuesta histórica ya trasladada a Agenda:
  `docs/propuesta_comun_envolvente_diagnostica_remota.md`.
- Cubre autoridad canónica, desduplicación, envolventes iterativas,
  EAOR, clasificación de pausas, pruebas proporcionales y migración segura.
- Común vigente ya incorporó EAOR y lectura interproyecto focal. La copia local
  conserva la propuesta histórica y no autoriza editar común.

## Historia verificable

- Hasta v0.455:
  `docs/nia_next_history_v0.001_v0.455.md`, `837538` bytes,
  SHA-256 `6ABB7D3E59F5A0C73535934767B7BAC16309FBCA9E8C587954A865DF203F1D53`.
- v0.456–v0.510:
  `docs/historial/nia_next_precompactacion_2026-08-09_v0.510.md`, `68516`
  bytes, SHA-256
  `E4FB2FF94E15E793CA4C6A339760C40A3B3FBDE6F7982E000A0F87715176484E`.
- Estado literal v0.614, codificado reversiblemente:
  `docs/historial/nia_next_precompactacion_2026-08-12_v0.614.b64`.
  Al decodificar: `15947` bytes, SHA-256
  `0E40FB939F2007568A851B2AB775F3FA98CF201D25115041B40BDDF67258AB04`.

## Regla de expansión

Abrir otra referencia sólo para resolver una pregunta necesaria. Si contradice
`nia_next.md`, tratarla como historia, detener su uso operativo y corregirla en
una unidad documental autorizada.
