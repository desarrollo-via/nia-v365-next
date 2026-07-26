# Topología propuesta para G0 — supersedida

> **Documento histórico.** La decisión de crear un Web App separado fue
> reemplazada por el requisito de costo incremental cero: `bitrix_connector`
> vivirá como módulo independiente y apagable dentro de `nia-v365-next-api`.
> La arquitectura vigente está en
> `docs/bitrix_connector_embedded_topology.md`. Ninguna instrucción de creación
> o despliegue separado de este documento debe ejecutarse.

## Alcance

Este documento diseña el alojamiento del ingreso inerte G0. No autoriza crear
recursos, desplegar, modificar DNS, registrar el bot ni cambiar el modo `off`.

## Evidencia local

- El único manifiesto de despliegue versionado es
  `.github/workflows/desarrollo_nia-v365.yml`.
- Ese workflow se dispara por `push` a `desarrollo` o manualmente, instala
  Python 3.12 y `requirements.txt`, empaqueta la raíz completa y despliega al
  Azure Web App existente `nia-v365`, slot `Production`.
- La rama local activa es `feature/aislamiento-entorno-experimental`; no existe
  un disparador automático del workflow desde esta rama.
- No hay Dockerfile, compose, Procfile, manifiesto de proxy, servicio, runtime
  cloud ni comando de startup versionado.
- `requirements.txt` ya fija FastAPI, Uvicorn y Gunicorn, pero la configuración
  real de startup de `nia-v365` vive fuera del repositorio y no fue consultada.
- Los launchers existentes son ensayos locales: OAuth usa un `trycloudflare`
  temporal y Review Admin usa TLS autofirmado en `localhost`. Ninguno sirve
  como host persistente para el webhook.

## Preflight Azure de solo lectura

La suscripción activa `viaindustrial-core` contiene cuatro Web Apps Linux,
HTTPS-only y en ejecución: `nia-api-productos`, `ventas-api-viaindustrial`,
`nia-v365` y `nia-v365-next-api`. Ninguna es un servicio G0 dedicado; por ello
no existe todavía un hostname real que pueda usarse como
`NIA_BITRIX_G0_PUBLIC_ORIGIN`.

Hay dos planes Linux B1/Basic, ambos con capacidad declarada `1`. El plan
`microsoft_asp_1003` de Canadá Central aloja tres aplicaciones. Un Web App G0
nuevo dentro de ese plan conservaría separación de aplicación, configuración y
despliegue con menor costo incremental, pero compartiría cómputo. Un plan nuevo
mejoraría el aislamiento de capacidad y fallo a cambio de costo adicional.

El preflight no leyó app settings, variables, logs, identidades ni secretos y
no creó o modificó infraestructura.

## Decisión propuesta

G0 debe vivir en una unidad de despliegue separada de `nia-v365`. Azure App
Service es el candidato con evidencia local, pero la topología se conserva
portable:

```text
Bitrix24
  -> HTTPS estable del servicio G0
  -> terminación TLS administrada por la plataforma
  -> un proceso ASGI / una instancia / un worker
  -> create_g0_entrypoint(...)
       -> GET  /healthz
       -> POST /bitrix-connector/webhook
       -> sin runtime, Mongo, NIA, OAuth, Review Admin o instalación
```

Para el primer R0 puede usarse el hostname HTTPS estable asignado por el
servicio separado. Un dominio personalizado es opcional y queda fuera de este
corte. El hostname definitivo debe introducirse literalmente como origen
público y coincidir con el encabezado `Host` que reciba ASGI.

No se debe reutilizar el App Service `nia-v365`, su slot `Production` ni el
workflow actual. Tampoco se recomienda un slot de `nia-v365`: mantendría
acoplamiento de configuración, ciclo de vida y capacidad con NIA Next.

## Implementación local del proceso G0

`bitrix_connector.g0_deployment` implementa el contrato y deja como comando
versionado futuro:

```text
python -m bitrix_connector.g0_deployment
```

El módulo:

1. leer únicamente `NIA_BITRIX_G0_PUBLIC_ORIGIN` para construir el host;
2. componer `create_g0_entrypoint` sin importar `main.py`;
3. iniciar exactamente un worker y exigir una sola instancia;
4. enlazar en la interfaz interna que entregue la plataforma y en su puerto
   asignado, sin terminar TLS dentro de Python;
5. deshabilitar autoreload, documentación, CORS y access logs con cuerpos;
6. conservar 256 KiB, 5 segundos y 60 solicitudes/60 segundos hasta obtener
   evidencia real que justifique cambiarlos;
7. fallar antes de construir la aplicación o Uvicorn si el origen, `PORT`, la
   identidad Bitrix o el estado `off/locked/no-external` no son válidos;
8. rechazar `WEB_CONCURRENCY` o `NIA_BITRIX_G0_WORKERS` si su valor no es `1`;
9. construir Uvicorn con un worker, sin reload, access log, proxy headers ni
   cabeceras de servidor, y con concurrencia, backlog y cierre acotados.

La fábrica y el adaptador Uvicorn reales fueron construidos en pruebas sin
llamar a `serve()` ni abrir sockets. El runner posee `SIGINT/SIGTERM`, impide
que Uvicorn los sustituya, activa primero `G0StopController`, solicita cierre y
fuerza/cancela después de diez segundos. También limpia servidor y señales si
su propia tarea es cancelada.

## Configuración mínima

La configuración debe vivir en el almacén seguro de la plataforma, nunca en un
`.env` desplegado:

- `NIA_BITRIX_G0_PUBLIC_ORIGIN`: nuevo nombre propuesto, sin secretos.
- `PORT`: puerto interno asignado por la plataforma; es obligatorio y debe
  estar entre 1 y 65535.
- `NIA_BITRIX_MODE=off`.
- `NIA_BITRIX_PILOT_ENABLED=false`.
- `NIA_BITRIX_PILOT_EMERGENCY_STOP=true`.
- `NIA_BITRIX_DOMAIN`, `NIA_BITRIX_MEMBER_ID` y
  `NIA_BITRIX_APPLICATION_TOKEN`: identidad del evento, suministrada por el
  almacén seguro sin exponer valores.

G0 no necesita `MONGO_URI`, `NIA_BASE_URL`, credenciales OAuth, OpenAI,
ViaIndustrial o WhatsApp. `activation_locked=true` y
`external_calls_enabled=false` continúan siendo barreras de código.

## Salud y operación

- La plataforma consulta `GET /healthz`.
- Salud aceptable para R0: HTTP 200, `effective_mode=off`,
  `activation_locked=true`, `external_calls_enabled=false`,
  `pilot_enabled=false`, `pilot_emergency_stop=true` y
  `accepting_webhooks=true`.
- El webhook auténtico debe terminar `connector_locked_off` y conservar
  `persisted=false`, `nia_called=false` y `bitrix_written=false`.
- No se habilita afinidad, autoscale ni una segunda instancia durante el
  piloto; la tasa y la parada actuales son memoria de proceso.
- Los logs permiten solo estado HTTP, razón segura, duración y un identificador
  no secreto. No registran formulario, texto, tokens o cabeceras de
  autenticación.

## Parada propietaria

No se añadirá una ruta HTTP de parada. El propietario será el proceso de
arranque:

1. crea un único `G0StopController` y lo inyecta en la aplicación;
2. ante `SIGTERM` o `SIGINT`, llama primero `request_stop()`;
3. G0 cancela solicitudes en curso y rechaza nuevas;
4. el servidor ASGI inicia después su cierre con un plazo acotado;
5. la plataforma puede detener la única instancia como segunda barrera.

La parada es terminal: volver a aceptar webhooks requiere un proceso nuevo. El
control de detener o reiniciar la plataforma es una acción externa separada y
requiere autorización expresa.

## Secuencia futura y autorizaciones

1. Completado localmente: `deploy/templates/g0-azure-webapp.yml.example`
   permanece fuera de `.github/workflows`, no tiene destino literal ni trigger
   por `push`, exige confirmación manual y rechaza explícitamente `nia-v365`.
2. Completado en solo lectura: no existe un servicio G0 separado. Falta definir
   localmente el nombre, región y si compartirá el plan B1 o tendrá plan propio.
3. **ATENCIÓN ESPECIAL:** crear el servicio separado y confirmar el hostname
   público. Esto modifica infraestructura externa.
4. Completar el workflow exclusivo; commit, push y
   ejecución requieren autorizaciones independientes.
5. Desplegar todavía en `off` y verificar desde Internet solo `/healthz` y un
   POST sintético sin secretos.
6. Solo después continuar G1/G2; registrar el bot permanece bloqueado por una
   autorización diferente.

## Rollback

Antes del registro del bot, el rollback es detener o eliminar exclusivamente el
servicio G0 separado. No se toca `nia-v365`, NIA Next, Mongo, Bitrix, DNS
personalizado ni el Canal Abierto. Después de registrar el bot, el rollback
necesitará además el procedimiento explícito de desvinculación y
`imbot.v2.Bot.unregister`, que no forma parte de G0.

## Incertidumbres pendientes

- No se verificó la configuración actual del App Service `nia-v365`, sus
  dominios, plan, slots, variables, startup, escala o permisos.
- Se comprobó que no existe actualmente un App Service dedicado a G0.
- No se eligió nombre de servicio, región, plan, hostname o repositorio de
  despliegue.
- No se ha probado todavía cómo preserva la plataforma el encabezado `Host` ni
  su secuencia exacta de `SIGTERM`.
