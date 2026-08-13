# Preflight del binding real de la sonda protegida R1

Estado: `NO-GO-SOURCE-DECISION-REQUIRED`.

La preparación local cerró el transporte GET productivo sin ejecutarlo. No
abre credenciales, `.env`, App Settings o Credential Manager; no construye el
owner real completo, no materializa Bearer y no realiza red.

## Resultado exacto

- Allowlist: sólo `NIA_BITRIX_REVIEW_TOKEN`.
- Endpoint: la ruta productiva fija de la sonda protegida.
- Presupuesto: un GET, timeout 15 segundos, cero redirects y cero retries.
- Respuesta: máximo 4096 bytes, JSON sin claves duplicadas y clasificación por
  la política allowlisted; transporte incierto termina consumo ambiguo.
- `build_dormant_production_http_transport` construye un cliente con
  `trust_env=false` y no hace solicitud al construirlo.
- El transporte se probó únicamente con `httpx.MockTransport`.

## Fuente protegida: única decisión pendiente

El target existente `nia-next/bitrix-r1/protected-settings/v1` contiene la
allowlist histórica de siete valores OAuth/Mongo y no contiene
`NIA_BITRIX_REVIEW_TOKEN`. Ampliarlo o reinterpretarlo violaría su formato
exacto. El runbook P1-B sólo documenta que la persona conservó el Review token
en un gestor seguro; no identifica almacén ni target local.

Por ello no se inventa un origen ni se usa `.env` por inferencia. La persona
debe identificar literalmente una fuente protegida accesible y, si es
Credential Manager, el target exacto que contiene exclusivamente ese valor.
Esa decisión permite después preparar el adaptador nominal; todavía no
autoriza abrirlo, leer el token ni invocar la ruta.

## Barrera

El preflight puro devuelve `source_binding_ready=false`,
`transport_binding_ready=true`, `execution_ready=false`, cero fuentes abiertas,
cero tokens materializados y cero llamadas externas. La próxima operación se
detiene hasta recibir la identidad de la fuente; no existe rollback porque no
hubo efecto real.

## Resultado V1

Un lote posterior autorizó `.env` como única fuente. El preflight remoto
aprobó 9/9, pero el owner terminó saneadamente
`NO-GO-PROTECTED-SOURCE-UNAVAILABLE`, `protected_source_opened=false`, cero
lecturas y cero GET. No se hizo fallback, inspección o reintento. Continúa siendo necesaria una
intervención humana que asegure la fuente exacta sin comunicar el valor.
