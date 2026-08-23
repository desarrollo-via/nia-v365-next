# Opciones de invocación del owner OAuth R1

Estado: `ENTRA_IDENTITY_READY_LOCAL_ENDPOINT_UNMOUNTED`. Este documento no monta rutas, no crea jobs y no
autoriza publicación, Azure, Key Vault, OAuth, Bitrix ni mensajes.

## Invariantes comunes

- Host objetivo: `nia-v365-next-api`, con identidad administrada confirmada.
- Artefacto exacto y preflight de identidad antes de una única invocación.
- Máximos: una lectura del secreto Key Vault exacto, una renovación OAuth, una
  persistencia condicional y una verificación interna saneada.
- Cero reintentos, Bitrix REST, activación R1, participantes, mensajes, rutas
  auxiliares, jobs adicionales o despliegues implícitos.
- Cierre, identidad, salida o persistencia ambiguos terminan `NO-GO`.

## Opción A: job one-shot de Web App — descartada por ahora

El mecanismo de plataforma inicia el módulo exacto en un proceso de una sola
vez del host. La autenticación es la identidad administrada del proceso. Antes
de materializarlo en la plataforma hay que confirmar que el mecanismo existe y no crea un job
recurrente ni usa consola interactiva.

El adaptador local `bitrix_connector/r1_oauth_refresh_webapp_job.py` fija el
nombre, el gate, los máximos y la delegación inyectada. Es inerte: no construye
el owner real, no crea jobs y no contiene una llamada Azure.

La consulta única a la colección de jobs devolvió `Conflict` sin detalle. No
demuestra incompatibilidad, pero tampoco permite usar esta opción.

## Opción B: endpoint interno autenticado — elegida

Una sola ruta interna propuesta: `/bitrix-connector/r1/oauth-refresh`. Como
App Service Auth está deshabilitado, la alternativa seleccionada es validar en
la aplicación una identidad de carga de trabajo. No reutiliza el Bearer de
Review ni recibe tokens, secretos o parámetros OAuth.

El gate local `bitrix_connector/r1_oauth_refresh_workload_identity_auth.py`
exige, después de una validación criptográfica hecha en el borde servidor,
emisor, audiencia y cliente autorizado exactos, firma atestiguada y una ventana
máxima de cinco minutos. No carga configuración ni recibe JWT desde una ruta
montada. El adaptador de endpoint sólo delega al owner tras ese gate y
responde el snapshot saneado.

`r1_oauth_refresh_workload_identity_jwt.py` completa el verificador local
RS256: rechaza algoritmo distinto, firma inválida, clave no resuelta, claims
distintos, token futuro, vencido o con antigüedad mayor al máximo. Recibe un
JWKS ya resuelto por inyección; no descarga claves ni trata los valores fixture
de las pruebas como configuración real.

## Capacidad pendiente

La fase local dejó el autenticador, el verificador RS256 y la composición con
el endpoint probados. La identidad Entra ya quedó materializada; publicación y
ejecución continúan separadas.

## Preflight externo de identidad (2026-08-21)

Las tres lecturas saneadas confirmaron presencia de tenant, principal asignado
al sistema de `nia-v365-next-api` y cliente asociado a ese principal. No se
mostraron ni persistieron identificadores. Esto permite usar Entra como fuente
futura de issuer/JWKS, pero no configura una audiencia de recurso ni una lista
de clientes permitidos. La fuente local confirma que el router FastAPI del
conector ya se monta de forma opcional; la ruta R1 sigue sin montar.

## Materialización de identidad (2026-08-23)

La EAOR `R1-IDENTIDAD-ENDPOINT` creó y postleyó la API Entra
`nia-v365-next-api-r1-internal`, su audiencia derivada, el rol
`r1.oauth.refresh.invoke` y una única asignación a la identidad administrada
del host. Los identificadores no se registran aquí. La fábrica FastAPI R1 se
prueba por inyección y sigue sin incluirse en el router productivo; no hubo
OAuth, Bitrix, mensajes, despliegue ni activación.
