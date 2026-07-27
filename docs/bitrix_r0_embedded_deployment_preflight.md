# Preflight de despliegue R0 integrado — no ejecutable

Fecha de evidencia: 27 de julio de 2026.

Este documento no autoriza cambios en Git, GitHub, Azure, `.env`, Bitrix ni
NIA. Define el delta y el rollback que deberán aprobarse por fases.

## Resultado de la auditoría

- Producción usa `nia-v365-next-api`, Linux Python 3.12, plan B1 de una
  instancia y startup Gunicorn directo a `main:app`.
- El origen estable es
  `https://nia-v365-next-api-ekd4fza7e0fzevfd.canadacentral-01.azurewebsites.net`.
- `alwaysOn=false`, no existe health check, Auto Heal está apagado y Deployment
  Center declara `deploymentRollbackEnabled=false`.
- La fuente es `desarrollo-via/nia-v365-next`, rama `main`, con despliegue
  automático por cada `push` a `main`.
- El último despliegue observado fue el commit `df9ef0f`, exitoso. NIA responde
  `status=ok` y el conector desplegado es `v0.097`.
- Producción expone 14 plantillas OpenAPI de `/bitrix-connector/*`; no expone
  las plantillas internas R0.
- El estado publicado continúa `off/locked/no-external`, runtime `inert`,
  piloto apagado y parada de emergencia activa.
- Los booleanos públicos indican que dominio, miembro, application token,
  token de revisión y `NIA_BASE_URL` no están configurados. Actor y credential
  ID no se exponen y no fueron consultados en App Settings.
- La rama local es ancestro directo de `main` por un commit de merge, pero los
  árboles `HEAD` y `origin/main` son idénticos. El worktree conserva 36 rutas
  pendientes: 12 modificadas y 24 sin seguimiento.

No se consultaron App Settings, secretos, logs, archivos desplegados ni
credenciales de publicación.

## Contradicción encontrada

La topología vigente es integrada en `main:app`, pero el montaje R0 `v0.109`
se compuso en `bitrix_connector.g0_deployment`, entrada correspondiente a la
antigua topología G0 separada. Ese comando no es el startup desplegado.

Por ello, publicar el worktree actual no montaría las rutas R0 en producción.
El cliente CLI apuntaría al hostname correcto, pero recibiría `404` al intentar
armar el recibo. Esto bloquea R0 y debe corregirse localmente antes de publicar.

## Delta de código implementado localmente

1. Completado: `build_optional_r0_bridge_mount` recibe un prefijo de montaje.
2. Completado: `bitrix_connector/router.py` construye el montaje con
   `/internal/r0-receipts`, incluir su router solo cuando el switch exacto esté
   activo y entregar el mismo observador al webhook integrado.
3. Verificado: con switch ausente, falso o inválido, conserva las 14
   plantillas actuales y cero construcción del puente.
4. Verificado: con switch verdadero y autenticación completa, agrega tres plantillas y
   cuatro operaciones HTTP bajo
   `/bitrix-connector/internal/r0-receipts`, sin duplicar el prefijo.
5. Verificado: autenticación antes de JSON, una sola instancia compartida,
   `off/locked/no-external`, consumo único, cierre y rollback a `245339`.
6. Completado localmente: el workflow productivo ejecuta
   `python -m unittest discover -s tests` antes de empaquetar.

No se cambia `main.py`, el startup Gunicorn, el supervisor ni el worker para
R0. Tampoco se activa `NIA_BITRIX_MODULE_ENABLED` desde código.

Aprobaron 38/38 pruebas focales y 535/535 pruebas completas con dobles. El
workflow no fue ejecutado y ningún cambio fue staged, publicado o desplegado.

## Publicación segura por fases

### P0 — código inerte

1. Partir de `origin/main` en una rama nueva y preservar las 36 rutas locales.
2. Implementar y probar el delta integrado.
3. Auditar allowlist, secretos, compilación, 528+ pruebas y workflow.
4. Commit, push, PR y merge requieren autorizaciones separadas.
5. El merge a `main` dispara despliegue automático: debe conservar
   `NIA_BITRIX_R0_BRIDGE_ENABLED` ausente o en `false`.
6. Verificar NIA `200`, conector actualizado en `off` y las mismas 14
   plantillas; ninguna ruta R0 debe existir todavía.

### P1 — configuración preparada con puente apagado

En el almacén seguro de Azure, sin usar `.env` desplegado, preparar:

- `NIA_BITRIX_G0_PUBLIC_ORIGIN` con el origen HTTPS estable sin path;
- `NIA_BITRIX_DOMAIN`;
- `NIA_BITRIX_MEMBER_ID`;
- `NIA_BITRIX_APPLICATION_TOKEN`;
- `NIA_BITRIX_REVIEW_TOKEN`;
- `NIA_BITRIX_REVIEW_ACTOR`;
- `NIA_BITRIX_REVIEW_CREDENTIAL_ID`;
- `NIA_BITRIX_R0_BRIDGE_ENABLED=false`.

Los valores sensibles no se registran en documentos, comandos, consola o
Agenda. La modificación reinicia el Web App y requiere atención especial.
Después deben seguir existiendo solo 14 plantillas y el modo debe permanecer
`off/locked/no-external`.

`NIA_BASE_URL` no es necesaria para R0 inerte; se mantiene fuera de esta fase.

### P2 — habilitación breve del puente

Con autorización específica, cambiar únicamente
`NIA_BITRIX_R0_BRIDGE_ENABLED=true`. Tras el reinicio:

- NIA y `/bitrix-connector/health` deben responder `200`;
- deben existir exactamente tres plantillas internas nuevas y cuatro métodos;
- una consulta sin credencial debe devolver `401` sin leer JSON;
- no se arma una sesión y no se llama Bitrix todavía.

### P3 — R0

La ejecución R0 conserva su autorización independiente, confirmación literal,
preflight fresco, ventana de diez minutos y rollback obligatorio. Finalizado el
ensayo, el switch R0 vuelve a `false` aunque el resultado sea exitoso.

## Rollback exacto

### Rollback operativo del puente

1. Fijar `NIA_BITRIX_R0_BRIDGE_ENABLED=false`.
2. Reiniciar controladamente el Web App.
3. Confirmar NIA y conector `200`, estado `off/locked/no-external` y ausencia
   de las tres plantillas R0.
4. Conservar las demás configuraciones para auditoría; retirarlas exige una
   decisión separada.

### Rollback del código

Azure declara rollback automático deshabilitado. La base restaurable conocida
es `df9ef0fc217f5d3d1548bedfd4f5e975d15d53f6`.

Si el código nuevo afecta NIA con el switch apagado:

1. mantener o fijar el switch R0 en `false`;
2. preparar un commit de reversión que restaure el árbol funcional de
   `df9ef0f`, sin `reset --hard`;
3. publicar esa reversión en `main`, lo que dispara otro despliegue;
4. verificar NIA `200`, conector `v0.097` y las 14 plantillas previas.

Si la aplicación no inicia, el procedimiento de redeploy de un artefacto
anterior debe confirmarse antes del merge, porque Deployment Center no ofrece
rollback automático.

## Puntos de atención especial

1. El merge a `main` despliega automáticamente a producción.
2. Cualquier modificación de App Settings reinicia la misma aplicación que
   atiende NIA.
3. Habilitar el puente crea una sesión efímera en memoria; un reciclado de la
   instancia la pierde. El coordinador debe tratarlo como fallo y restaurar
   `245339`.
4. `alwaysOn=false` no impide un R0 breve, pero no permite afirmar durabilidad
   continua del proceso.
