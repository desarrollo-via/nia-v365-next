# Topología integrada y apagable de bitrix_connector

## Decisión vigente

`bitrix_connector` será un módulo independiente dentro del mismo artefacto y
Azure Web App de `nia-v365-next-api`. No se creará otro Web App, plan, slot,
dominio ni servicio de pago para el conector.

La independencia será lógica, de configuración, persistencia y proceso; no de
infraestructura:

```text
Azure Web App existente: nia-v365-next-api
│
├─ proceso web NIA Next
│  ├─ rutas normales de NIA
│  └─ /bitrix-connector/* solo si el switch maestro está habilitado
│
└─ proceso worker bitrix_connector, separado del proceso web
   ├─ cola y colecciones propias
   ├─ NiaClient -> contrato HTTP público de la misma NIA Next
   └─ BitrixClient -> bloqueado hasta autorización de activación
```

Esto busca costo incremental de infraestructura igual a cero. Sí consume CPU,
memoria, conexiones y almacenamiento del servicio existente cuando se habilite;
esa capacidad deberá observarse durante el piloto.

## Estado de implementación

El switch maestro, el montaje condicional, el núcleo inyectable del supervisor
y su adaptador/CLI Linux ya están implementados localmente. El conjunto se
probó exclusivamente con dobles: no está integrado con el startup de Azure y no
se inició ningún proceso.

## Switch maestro

`NIA_BITRIX_MODULE_ENABLED` usa interpretación estricta y valor predeterminado
`false`. Solo el valor literal `true`, ignorando espacios y mayúsculas, lo
habilita; cualquier otro valor falla cerrado.

Con `false` o valor inválido:

- `main.py` no importa ni monta routers de `bitrix_connector`;
- el launcher no inicia `python -m bitrix_connector.worker_cli`;
- no se crean índices, clientes, tareas, conexiones o procesos del conector;
- las rutas normales y el startup de NIA permanecen iguales;
- retirar físicamente el paquete no impide iniciar NIA Next.

Con `true`, el módulo puede cargarse, pero continúa sujeto a las barreras
operativas existentes:

- `effective_mode=off`;
- `activation_locked=true`;
- `external_calls_enabled=false`;
- `NIA_BITRIX_PILOT_ENABLED=false`;
- `NIA_BITRIX_PILOT_EMERGENCY_STOP=true`.

El switch maestro no activa `review`, `shadow` o `active`; solo permite que el
módulo exista en runtime. Cambiar cualquiera de las barreras posteriores exige
otra autorización.

## Montaje condicional

`main.py` ya no importa `bitrix_connector`. Importa únicamente
`optional_bitrix_connector`, un puente estándar sin FastAPI, Mongo o clientes
externos, y le entrega la aplicación una vez creada. La función:

1. lee únicamente el switch maestro;
2. no importa el paquete cuando está apagado;
3. monta el router una sola vez cuando está habilitado;
4. trata un valor inválido como `false`;
5. preserva el arranque normal de NIA si el paquete está ausente o falla su
   import, dejando solo una razón segura en logs;
6. no lee cuerpos, tokens ni `.env` para decidir el montaje.

Las pruebas deberán demostrar que las rutas de NIA son idénticas con el switch
apagado y con el paquete simulado como ausente. Cuando el switch esté encendido,
el conector todavía debe responder bajo `off/locked/no-external`.

## Worker separado dentro del mismo servicio

El worker durable no se ejecutará mediante `BackgroundTasks`, startup de
FastAPI o una coroutine residente dentro del proceso web. Ya existe el comando:

```text
python -m bitrix_connector.worker_cli
```

El diseño objetivo usa un único launcher propietario para el Web App:

- siempre inicia el comando web existente de NIA;
- solo inicia la CLI del worker si `NIA_BITRIX_MODULE_ENABLED=true`;
- mantiene web y worker como procesos del sistema operativo distintos;
- propaga `SIGTERM` a ambos y espera un cierre acotado;
- si el worker falla, conserva NIA activa, registra una razón segura y limita
  cualquier reinicio con backoff y máximo explícito;
- si el proceso web falla, el launcher termina para que Azure aplique su ciclo
  normal de recuperación.

`nia_process_supervisor.py` implementa ya el núcleo puro e inyectable de ese
contrato. Inicia primero el web, crea el worker únicamente con el switch maestro
habilitado, limita sus reinicios con backoff, preserva el web cuando el worker
falla o agota sus intentos y aplica terminación seguida de kill solo al vencer
el plazo de cierre. El módulo no importa `subprocess`, no ofrece CLI y no conoce
un mecanismo real para crear procesos.

La consulta de solo lectura del startup real y la implementación local del
adaptador ya quedaron completadas. `python -m nia_process_launcher` todavía no
forma parte del startup ni de un workflow de despliegue.

## Evidencia real de Azure y diseño del adaptador

La consulta de solo lectura del 25 de julio de 2026 confirmó para
`nia-v365-next-api`:

- Web App Linux en ejecución con `PYTHON|3.12` y HTTPS obligatorio;
- startup exacto: `gunicorn -w 1 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 main:app --timeout 600 --access-logfile - --error-logfile -`;
- `numberOfWorkers=1`;
- plan Linux Basic B1 con capacidad actual de una instancia;
- `alwaysOn=false`, `healthCheckPath=null` y `autoHealEnabled=false`;
- despliegue identificado como `GitHubAction`.

No se solicitaron App Settings, credenciales de publicación, logs, archivos de
la aplicación ni valores secretos.

El adaptador local implementado es pequeño y explícito:

1. usar una fábrica basada en `asyncio.create_subprocess_exec` únicamente en el
   módulo launcher, nunca en el núcleo probado;
2. entregar como proceso web el comando Gunicorn existente sin alterar sus
   argumentos;
3. entregar como worker `python -m bitrix_connector.worker_cli` únicamente
   cuando `NIA_BITRIX_MODULE_ENABLED=true`;
4. capturar `SIGTERM` y `SIGINT`, pedir cierre al núcleo y conservar sus límites
   de espera y kill;
5. devolver el código del proceso web para mantener el contrato de recuperación
   del host;
6. no registrar entorno, argumentos sensibles ni salida que pueda contener
   secretos.

La capacidad actual de una instancia evita duplicación inmediata, pero no debe
tratarse como invariante. Si Azure escala horizontalmente, cada instancia
iniciará su propio worker; las leases de la cola deben seguir siendo la barrera
de concurrencia y el piloto debe permanecer limitado a una instancia.

`alwaysOn=false` impide afirmar que un proceso residente permanecerá disponible
de forma durable durante periodos sin tráfico. Antes de producción habrá que
decidir y autorizar por separado `Always On`, además de una señal de salud del
conector. Este hallazgo no modifica la configuración actual.

## Frontera HTTP y persistencia

- `bitrix_connector` no importará módulos internos de NIA.
- `NIA_BASE_URL` apuntará al origen HTTPS público existente de
  `nia-v365-next-api` y `NiaClient` usará `/nia/chat`.
- La llamada seguirá siendo HTTP aunque origen y destino compartan Web App.
- El conector puede reutilizar la infraestructura Mongo ya pagada, pero solo
  mediante sus colecciones `nia_bitrix_*` y sus modelos propios.
- No compartirá ni modificará documentos de sesión internos de NIA.
- La cola conservará leases, reintentos e idempotencia; el proceso web solo
  valida y persiste el ingreso cuando el módulo y el modo lo permitan.

## Despliegue y costo

El paquete se incluirá en el mismo artefacto completo de NIA Next. La plantilla
`deploy/templates/g0-azure-webapp.yml.example`, diseñada para un Web App G0
separado, queda supersedida y no debe activarse.

No se requiere:

- otro App Service Plan;
- otro Web App o slot;
- otro hostname o certificado;
- otro MongoDB;
- un servicio de cola adicional.

El costo monetario incremental esperado de infraestructura es cero, sujeto a
que el plan actual soporte la carga. Si CPU, memoria o latencia se degradan, se
detendrá el piloto antes de proponer gasto.

## Fuente real de despliegue

La consulta proyectada de solo lectura del 25 de julio de 2026 confirmó:

- Azure Deployment Center asocia `nia-v365-next-api` con
  `https://github.com/desarrollo-via/nia-v365-next`, rama `main`;
- la asociación declara `isManualIntegration=false`;
- GitHub contiene el workflow activo
  `.github/workflows/main_nia-v365-next-api.yml`, llamado
  `Build and deploy Python app to Azure Web App - nia-v365-next-api`;
- la ejecución más reciente observada es `run_number=1`, disparada mediante
  `workflow_dispatch` sobre `main` el 7 de julio de 2026 y concluida con éxito;
- el checkout local actual solo contiene `desarrollo_nia-v365.yml`, destinado a
  otra Web App. El workflow de NIA Next no se descargó, creó ni infirió.

No se abrió el YAML remoto, no se consultaron secretos o App Settings y no se
ejecutaron `fetch`, `pull`, workflow, despliegue o cambios en Azure/GitHub.

### Inspección redactada y parche local

El YAML remoto fue leído después con toda referencia `secrets.*` sustituida
antes de su salida. La revisión confirmó:

- disparadores `push` sobre `main` y `workflow_dispatch`;
- Python 3.12, `pip install -r requirements.txt` y artefacto de toda la raíz con
  exclusión de `antenv/`;
- jobs separados `build` y `deploy`;
- login Azure mediante OIDC y `azure/webapps-deploy@v3` hacia
  `nia-v365-next-api`, slot `Production`;
- el workflow original no tenía pruebas ni instrucciones que configuraran el
  startup.

Como el artefacto ya contiene `.`, `nia_process_launcher.py` viajará sin cambiar
el empaquetado. La plantilla inerte
`deploy/templates/main_nia-v365-next-api.supervisor.patch.example` añade solo
las tres regresiones aisladas del switch, supervisor y launcher después de
instalar dependencias. Está fuera de `.github/workflows`, no contiene secretos,
no habilita el módulo y no modifica startup o despliegue.

La plantilla fue parseada por Git como un diff válido de 5 adiciones y 0
eliminaciones contra `.github/workflows/main_nia-v365-next-api.yml`; su contexto
coincide con las líneas remotas inspeccionadas. Las 29 pruebas relacionadas
aprobaron y el workflow local activo permaneció sin diferencias. No se aplicó
el parche porque el archivo objetivo no existe en la rama local actual.

El cambio futuro de startup no debe ocultarse dentro de ese diff. Requiere una
operación Azure separada y autorizada:

```text
startup propuesto: python -m nia_process_launcher
rollback exacto: gunicorn -w 1 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 main:app --timeout 600 --access-logfile - --error-logfile -
```

La transición segura será:

1. confirmar por proyección que `NIA_BITRIX_MODULE_ENABLED` está ausente o en
   `false`, sin listar los demás App Settings;
2. desplegar primero el código con el startup Gunicorn actual y comprobar la
   salud normal de NIA;
3. cambiar el startup al launcher en una autorización separada, asumiendo que
   la operación reinicia la aplicación;
4. comprobar salud de NIA y ausencia del worker con el switch apagado;
5. conservar el comando Gunicorn anterior como rollback inmediato.

La consulta proyectada del 26 de julio de 2026 devolvió `[]` para
`NIA_BITRIX_MODULE_ENABLED`: el App Setting está ausente. El parser estricto usa
por tanto su valor predeterminado `false`; el módulo no se monta y el futuro
launcher no iniciaría el worker. La salida no mostró ningún otro nombre o valor
y Azure no fue modificado.

Debido al disparador `push: main`, integrar cambios en esa rama implica un
despliegue automático y requiere atención especial. `alwaysOn=false` continúa
siendo una condición pendiente antes de afirmar durabilidad del worker.

## Salud, UI y apagado

- La salud principal de NIA no dependerá de la salud del conector.
- El estado del módulo deberá ser visible por separado como `disabled`,
  `off`, `review`, `shadow` o `active`, sin secretos.
- Review Admin podrá montarse después bajo el mismo hostname y autenticación
  propia; no se habilita en este corte.
- El apagado ordinario será poner `NIA_BITRIX_MODULE_ENABLED=false` y reiniciar
  controladamente el Web App. Ese reinicio afecta a NIA y requiere atención y
  autorización explícitas.
- El apagado de emergencia previo a reinicio sigue siendo
  `NIA_BITRIX_PILOT_EMERGENCY_STOP=true`, junto con las barreras de modo.

## Rollback

1. activar la parada de emergencia;
2. fijar el switch maestro en `false`;
3. reiniciar controladamente el Web App existente;
4. verificar que las rutas normales de NIA están sanas y que las rutas del
   conector no están montadas;
5. conservar las colecciones para auditoría hasta autorizar su tratamiento.

No se elimina el Web App, el plan, MongoDB, NIA Next ni sus datos. Desregistrar
el bot o desvincular el Canal Abierto es una operación Bitrix independiente.

## Secuencia segura

1. Completado: parser estricto, import diferido y montaje condicional con
   `false` predeterminado, dobles y ausencia simulada del paquete.
2. Completado: núcleo inyectable del supervisor probado con procesos dobles,
   reinicios acotados y preservación del web, sin iniciar procesos reales.
3. Completado: startup, runtime y capacidad no secreta de
   `nia-v365-next-api` consultados en solo lectura, sin listar App Settings.
4. Completado: adaptador `create_subprocess_exec`, CLI, señales, salida segura y
   propagación del código web probados con dobles, sin iniciar procesos reales.
5. Completado: fuente `desarrollo-via/nia-v365-next`, rama `main` y workflow
   remoto activo `main_nia-v365-next-api.yml` identificados en solo lectura.
6. Completado: YAML remoto inspeccionado con referencias sensibles redactadas y
   parche local inerte limitado a regresiones previas al despliegue.
7. Completado: diff inerte validado como 5 adiciones/0 eliminaciones, contexto
   cotejado con el YAML remoto redactado y 29/29 pruebas relacionadas aprobadas.
8. Completado: proyección exclusiva confirmó que
`NIA_BITRIX_MODULE_ENABLED` está ausente y falla cerrado a `false`, sin
mostrar otras variables ni modificar Azure.

El corte R0 integrado añade ahora localmente la regresión completa
`python -m unittest discover -s tests` al workflow activo después de instalar
dependencias y antes de empaquetar. También monta el puente efímero desde
`bitrix_connector/router.py`, que sí forma parte de `main:app`, usando un
prefijo interno para evitar duplicación. Con el switch R0 apagado no añade
rutas; con configuración exacta añade tres plantillas y cuatro operaciones.
Las 38 pruebas focales y las 535 completas aprobaron con dobles. El workflow no
se ejecutó y estos cambios no fueron publicados ni desplegados.
9. Completado: inventario local separa 140 rutas funcionales, 8 de
   diseño/despliegue y 12 exclusivamente locales; el índice permanece vacío.
10. Ejecutar la auditoría pre-stage de la allowlist: secretos sin imprimir
    coincidencias, regresiones aisladas, compilación y diff final.
11. Stage y commit requieren autorizaciones independientes; push, merge y
    ejecución continúan separados.
12. Desplegar todavía con el switch maestro apagado y comprobar primero que NIA
    no cambió.
13. Cambiar el startup al launcher en una operación separada y verificar NIA
    todavía con el switch maestro apagado.
14. Habilitar el módulo bajo `off`, verificar su estado y solo después continuar
    con el piloto controlado.

## Fuera de alcance

Esta decisión no autoriza cambios en código funcional, `.env`, Azure, GitHub,
MongoDB o Bitrix; tampoco autoriza commit, push, despliegue, registro del bot,
vinculación al Canal Abierto ni llamadas reales.
