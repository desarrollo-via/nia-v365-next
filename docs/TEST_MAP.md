# Mapa de pruebas — nia-next

Este mapa selecciona la prueba mínima suficiente durante una iteración. No
autoriza red, Azure, secretos, servicios ni efectos externos. Se usa la venv
existente y `PYTHONDONTWRITEBYTECODE=1`.

## Regla de selección

1. Ejecutar la suite del componente modificado.
2. Si cambia un contrato compartido, ejecutar también su conjunto acoplado.
3. Ejecutar la regresión hermética completa una sola vez al cerrar un corte,
   commit, publicación, despliegue o cambio transversal de alto impacto.
4. Un fallo de importación por intérprete incorrecto no cuenta como fallo del
   producto: repetir con `.venv\Scripts\python.exe`, sin instalar nada.

## Azure diagnóstico de solo lectura

Archivos:

- `bitrix_connector/r1_azure_diagnostic_coordinator.py`
- `bitrix_connector/r1_azure_diagnostic_real_attempt.py`
- `scripts/run_r1_azure_diagnostic_envelope.py`
- `scripts/run_r1_azure_operator_diagnostic.py`
- `scripts/run_r1_key_vault_provisioning.py`
- `scripts/run_r1_key_vault_rollback_postread.py`
- `scripts/run_r1_key_vault_deleted_postread.py`
- `scripts/run_r1_key_vault_create_activity_diagnostic.py`
- `scripts/run_r1_key_vault_create_cause_diagnostic.py`
- `scripts/run_r1_key_vault_provider_preflight.py`
- `scripts/run_r1_key_vault_provider_registration.py`
- `bitrix_connector/r1_result_eaor_coordinator.py`
- `tests/test_r1_azure_diagnostic_coordinator.py`
- `tests/test_r1_azure_diagnostic_real_attempt.py`
- `tests/test_run_r1_azure_diagnostic_envelope.py`
- `tests/test_run_r1_azure_operator_diagnostic.py`
- `tests/test_run_r1_key_vault_provisioning.py`
- `tests/test_run_r1_key_vault_rollback_postread.py`
- `tests/test_run_r1_key_vault_deleted_postread.py`
- `tests/test_run_r1_key_vault_create_activity_diagnostic.py`
- `tests/test_run_r1_key_vault_create_cause_diagnostic.py`
- `tests/test_run_r1_key_vault_provider_preflight.py`
- `tests/test_run_r1_key_vault_provider_registration.py`
- `tests/test_r1_result_eaor_coordinator.py`

Suite focal:

```powershell
.\.venv\Scripts\python.exe -B -m unittest `
  tests.test_r1_azure_diagnostic_coordinator `
  tests.test_r1_azure_diagnostic_real_attempt `
  tests.test_run_r1_azure_diagnostic_envelope `
  tests.test_run_r1_azure_operator_diagnostic `
  tests.test_run_r1_key_vault_provisioning `
  tests.test_run_r1_key_vault_rollback_postread `
  tests.test_run_r1_key_vault_deleted_postread `
  tests.test_run_r1_key_vault_create_activity_diagnostic `
  tests.test_run_r1_key_vault_create_cause_diagnostic `
  tests.test_run_r1_key_vault_provider_preflight `
  tests.test_run_r1_key_vault_provider_registration `
  tests.test_r1_result_eaor_coordinator
```

## Provisión R1 Key Vault

Suite acoplada:

```powershell
.\.venv\Scripts\python.exe -B -m unittest `
  tests.test_r1_key_vault_linux_provisioning_owner `
  tests.test_r1_key_vault_linux_provisioning_real_binding `
  tests.test_r1_azure_diagnostic_coordinator `
  tests.test_r1_azure_diagnostic_real_attempt
```

No ejecuta Azure: usa dobles inyectados.

## Activación R1 Fase A

Suite acoplada:

```powershell
.\.venv\Scripts\python.exe -B -m unittest `
  tests.test_r1_pre_event_activation_preflight `
  tests.test_r1_pre_event_activation_evidence_collector `
  tests.test_r1_pre_event_activation_exact_switch_reader `
  tests.test_r1_pre_event_activation_real_binding `
  tests.test_r1_pre_event_activation_operation_contract `
  tests.test_r1_pre_event_activation_compound_owner `
  tests.test_r1_pre_event_activation_apply_owner `
  tests.test_r1_pre_event_activation_apply_real_binding `
  tests.test_r1_result_eaor_coordinator `
  tests.test_r1_result_eaor_product_port `
  tests.test_r1_result_eaor_product_real_binding `
  tests.test_r1_result_eaor_product_runner `
  tests.test_r1_result_eaor_product_launcher
```

El binding y el adaptador permanecen dormidos; la suite prueba argv exactos,
rollback, verificación HTTP anónima, composición hermética con la EAOR,
factories perezosas, monitoreo acotado y cierres por fallo/expiración. El runner
se audita de launcher a coordinador: pausa humana, reanudación, reuso, cierre y
rollback de participante antes de Fase A. El launcher valida identidades,
alcance, literales, presupuestos, aceptación, fecha y salida CLI saneada sin
construir owners durante el gate.

El binding real dormido prueba por separado construcción de binding, plan,
runner y coordinador con cero invocaciones; identidad exacta de builders;
fail-closed ante deriva; y recorrido integral con dobles hasta restauración.

EAOR diaria de preflight remoto:

```powershell
.\.venv\Scripts\python.exe -B -m unittest `
  tests.test_r1_result_eaor_remote_preflight_coordinator `
  tests.test_r1_azure_diagnostic_coordinator `
  tests.test_r1_azure_diagnostic_real_attempt `
  tests.test_r1_result_eaor_product_launcher
```

La suite sólo usa intentos inyectados: valida día, aceptación, tres intentos,
ocho lecturas, una pareja de salud, categorías saneadas y cero efectos.

Enlace real dormido:

```powershell
.\.venv\Scripts\python.exe -B -m unittest `
  tests.test_r1_result_eaor_remote_preflight_real_binding `
  tests.test_r1_result_eaor_remote_preflight_coordinator `
  tests.test_r1_azure_diagnostic_real_attempt
```

La auditoría construye sólo binding y coordinador; demuestra cero construcción
de diagnóstico, runner o salud y cero invocación del guard o `run_once`.

Lanzador exacto con dobles:

```powershell
.\.venv\Scripts\python.exe -B -m unittest `
  tests.test_r1_remote_preflight_full_chain_audit `
  tests.test_run_r1_remote_preflight_eaor `
  tests.test_r1_result_eaor_remote_preflight_real_binding `
  tests.test_r1_result_eaor_remote_preflight_coordinator `
  tests.test_r1_azure_diagnostic_real_attempt
```

Valida huella antes/después, guard inyectado, deriva fail-closed, reporte
atómico/allowlisted y CLI mediante executor ficticio. La auditoría integral
atraviesa los componentes reales launcher, binding, coordinador, intento y
control CLI, sustituyendo sólo runner, salud, huella y writer; cubre éxito,
autenticación, transporte agotado, cierre fallido, deriva y evidencia
malformada. No ejecuta Azure.

## Sesión R1 y participantes

Suite acoplada:

```powershell
.\.venv\Scripts\python.exe -B -m unittest `
  tests.test_bitrix_event_scoped_r1_gate `
  tests.test_bitrix_event_scoped_r1_control `
  tests.test_bitrix_event_scoped_r1_mount `
  tests.test_bitrix_event_scoped_r1_participant_mount `
  tests.test_bitrix_event_scoped_r1_pre_event_lease `
  tests.test_bitrix_event_scoped_r1_pre_event_lease_factory `
  tests.test_bitrix_event_scoped_r1_pre_event_binding `
  tests.test_bitrix_event_scoped_r1_pre_event_binding_preflight
```

## Topología EAOR productiva corregida

```powershell
.\.venv\Scripts\python.exe -B -m unittest `
  tests.test_r1_pre_event_activation_product_supplier `
  tests.test_r1_remote_session_http_client `
  tests.test_r1_result_eaor_remote_session_adapter `
  tests.test_r1_result_eaor_product_real_binding `
  tests.test_r1_result_eaor_product_port
```

## Regresión hermética final

Sólo en los hitos indicados por la regla de selección:

```powershell
.\.venv\Scripts\python.exe -B scripts\run_isolated_unittest.py `
  --root . --start tests --pattern "test*.py" --quiet
```

La salida válida declara `ISOLATED-UNITTEST-PASS`; cualquier dependencia de red
o secreto es un defecto del aislamiento y bloquea el corte.
