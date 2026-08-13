# EAOR R1 — preflight remoto de solo lectura — 2026-08-13

Identificador: `NIA-NEXT-R1-REMOTE-PREFLIGHT-EAOR-2026-08-13-V1`.

Estado: ejecutado y cerrado en `GO-REMOTE-PREFLIGHT`. Su ejecución no autorizó
ni realizó secretos, App Settings, Credential Manager, Bitrix, activación,
bots, participantes o mensajes.

## Resultado y alcance

El único resultado exitoso es un preflight remoto saneado que confirme la
aptitud exacta para iniciar posteriormente la EAOR productiva de nia-next. Se
limita a la suscripción `0c4b9ea3-f35d-4a11-bfe7-794d40cf1ec9`, Web App
`nia-v365-next-api`, grupo `nia-v365-next-api_group`, vault dedicado previsto,
roles exactos del manifiesto de SHA-256
`16EDAC107B1B8041952D8ED324C0542ECAADDB0AA7EC316C2B557F135864AA49` y
la pareja pública de salud. No amplía el objetivo productivo ni lo ejecuta.

## Presupuesto por envolvente

- Fecha exclusiva: 2026-08-13, zona `America/Bogota`.
- Máximo tres intentos one-shot.
- Máximo ocho lecturas allowlisted por intento; el binding vigente usa siete:
  suscripción, Web App, ausencia del vault, disponibilidad del nombre, rol
  lector, rol escritor y principal del operador.
- Máximo una pareja de salud pública por intento.
- Continuación automática sólo ante `transport` o `unknown` recuperables.
- Cero escrituras, reintentos de mutación, listas amplias, enumeración de App
  Settings, apertura de fuentes protegidas, lecturas de secretos o mensajes.

## Aceptación y vigencia

La persona aceptó la envolvente mediante el `sp` ligado al SP que identificó
literalmente este documento e indicó ejecución inmediata. La aceptación fue
consumida el 2026-08-13. No autoriza repetir la ejecución. Un cambio de día,
recurso, manifiesto, identidad, presupuesto o allowlist exige una envolvente
nueva.

## Estados y detenciones

- `GO-REMOTE-PREFLIGHT`: evidencia exacta y saneada, recursos cerrados.
- `ATTENTION-REQUIRED-AZURE-AUTHENTICATION`: detener; la persona autentica Azure
  manualmente y nunca comparte contraseña, código, MFA, tokens o salida.
- `NO-GO-BUDGET-EXHAUSTED`: tres resultados recuperables consumidos.
- `NO-GO-TERMINAL`: autorización, recurso, deriva, evidencia inválida o cierre
  fallido; no reintentar por inferencia.
- `NO-GO-ACCEPTANCE` / `NO-GO-EXPIRED`: cero construcción diagnóstica.

El coordinador hermético es
`bitrix_connector/r1_result_eaor_remote_preflight_coordinator.py`. Sólo acepta
un `R1AzureDiagnosticCoordinator` inyectado después de validar aceptación y día;
no contiene binding real, red, secretos ni mutaciones. Esta unidad no construye
ni ejecuta el adaptador productivo.

## Enlace productivo dormido

`bitrix_connector/r1_result_eaor_remote_preflight_real_binding.py` enlaza ahora
el coordinador diario con `build_real_r1_azure_diagnostic_coordinator`. Conserva
guard local, runner Azure CLI y lector de salud como referencias diferidas; al
construir el coordinador no invoca ninguna. La auditoría local exacta devolvió
`BOUND-DORMANT`, coordinador `INERT`, una construcción del coordinador y cero
diagnósticos, runners, lectores de salud, guard calls, `run_once`, llamadas
externas, secretos, mutaciones o mensajes. La EAOR continúa no aceptada.

## Lanzador exacto

`scripts/run_r1_remote_preflight_eaor.py` implementa el entrypoint de ejecución
sin ejecutarlo en esta unidad. Exige el identificador y aceptación exactos,
calcula una huella local antes y después, inyecta el guard al binding dormido y
escribe atómicamente sólo un reporte allowlisted. Excluye de la huella únicamente
su reporte y temporal exactos. Deriva local, evidencia no allowlisted o fallo del
lanzador terminan saneados en `NO-GO-TERMINAL`; nunca se incluyen salida Azure,
paths privados, tokens o excepciones. El ciclo fue validado exclusivamente con
dobles; el entrypoint real y `run_once` productivo no fueron invocados.

## Auditoría hermética de cadena completa

`tests/test_r1_remote_preflight_full_chain_audit.py` atraviesa los componentes
reales launcher → binding → coordinador → intento diagnóstico → control Azure
CLI, sustituyendo únicamente runner, salud, huella y writer por dobles. Cubre
éxito con siete lecturas y una pareja de salud, autenticación, tres fallos de
transporte recuperables, fallo de cierre, deriva local y evidencia Web App
malformada. En todos los casos verifica cierre de recursos, límites exactos y
salida allowlisted sin texto privado. Resultado: 6/6; suite focal conjunta:
28/28. En esa auditoría el entrypoint real no fue ejecutado y los dobles no
aceptaron la EAOR.

## Resultado remoto

La primera invocación directa terminó antes de importar el proyecto por
`ModuleNotFoundError`; no construyó coordinador, no llamó Azure ni consumió un
intento. La misma ejecución autorizada se reanudó con el launcher como módulo y
cerró `GO-REMOTE-PREFLIGHT`: un intento, siete lecturas, una pareja de salud,
recursos cerrados y estado local preservado. Contadores de mutaciones, fuentes
protegidas, secretos, App Settings, listas amplias, Bitrix y mensajes: cero.
Reporte sanitario: `.tmp/r1_remote_preflight_eaor_2026-08-13_latest.json`, `356`
bytes, SHA-256
`993F03F28BC3C124271334F3E384886F4180C5A54E5266CA71AB931384D00051`.
