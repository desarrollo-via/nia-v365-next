# Contrato M86-CF/CG de despliegue dormido — no ejecutable

Estado: `LOCAL-DORMANT-VERIFIED / DO-NOT-DEPLOY`.

Este documento no autoriza `stage`, commit, push, PR, merge, Actions, Azure,
App Settings, Bitrix, NIA, OAuth, mensajes ni activación.

## Evidencia local congelada

- Base Git local observada: `0c0614df9aa7b663a313db3c66cbfb255c8ba523`.
- `router.py` entrega al webhook integrado el campo
  `protected_oauth_observer`, pero el montaje M86-CF siempre devuelve
  `observer=None`, `enabled=false` y `activation_surface_available=false`.
- No existe switch, endpoint, App Setting o fábrica real que pueda activar
  M86-CE desde configuración.
- Solicitar el montaje o inyectar un observador produce `UNAVAILABLE` y conserva
  cero NIA, Bitrix, OAuth o persistencia.
- La regresión integrada exige que un evento con token privado continúe
  respondiendo `connector_locked_off`, sin exponer el token.

La base local no se presenta como base productiva actual. Esa identidad debe
verificarse nuevamente justo antes de cualquier publicación futura.

## Corte futuro obligatorio

M86-CI conserva el corte local autocontenido en `284` rutas exactas: `143` de
implementación, `137` pruebas, `3` documentos y `1` script. La resolución está limitada por
patrones acotados y por una huella SHA-256 fija del conjunto ordenado; cualquier
ruta nueva, ausente o extra invalida `dependency_cut_frozen`. El manifiesto vive
en `bitrix_connector/bitrix_event_scoped_r1_cut_manifest.py` y no ejecuta
`stage`, red ni servicios.

El plan M86-CI queda representado únicamente como un `argv` inerte con prefijo
exacto `git add --` seguido por las 284 rutas literales ordenadas. Una segunda
huella fija cubre el `argv` completo. No contiene comodines, `.`, `-A`, CLI,
`subprocess` ni superficie de ejecución; `stage_authorized=false`,
`executable=false` y `git_calls=0`.

Antes de pedir autorización de despliegue deben existir simultáneamente:

1. la allowlist M53–M86 continúa resolviendo exactamente las 284 rutas
   congeladas, sin faltantes, extras o rutas prohibidas;
2. índice Git exacto, sin archivos ajenos, secretos ni faltantes;
3. regresión completa fresca y compilación del corte;
4. SHA productivo previo verificado contra `origin/main` y Azure;
5. un único commit candidato de 40 caracteres derivado de ese SHA;
6. dos lecturas públicas estables de NIA y del conector antes del merge.

Mientras falte cualquiera, `deployment_ready=false` y no se muestra una
autorización de despliegue.

## Despliegue dormido futuro

El único despliegue inicialmente admisible publica código con M86-CF dormido.
No añade ni cambia App Settings y no habilita M86-CE. El merge a `main` debe
considerarse despliegue productivo porque el workflow local se activa con cada
push a esa rama.

Éxito mínimo después del workflow:

- build y deploy terminan `success` para el SHA candidato exacto;
- NIA responde dos veces `200`;
- el conector responde dos veces `200`, `off/locked/no-external`;
- el montaje M86-CF continúa sin superficie HTTP ni activación configurable;
- no se llamó Bitrix, NIA funcional, OAuth o Mongo por este montaje.

Cualquier fallo, deriva de SHA, cambio de rutas, reinicio no convergente o
salud distinta detiene el proceso. No hay reintento automático.

## Rollback exacto congelado

El despliegue candidato deberá ser un único commit `DEPLOY_SHA` cuyo padre sea
el SHA productivo previo `BASE_SHA`, ambos verificados inmediatamente antes del
merge. El rollback autorizado para ese futuro corte se limita a:

1. crear `git revert DEPLOY_SHA` sin `reset --hard` ni tocar otros commits;
2. verificar que el árbol resultante coincide con `BASE_SHA` para todas las
   rutas del corte;
3. publicar únicamente ese revert en `main` para disparar el redeploy;
4. verificar dos veces NIA y conector `200` en la línea base previa.

`DEPLOY_SHA` y `BASE_SHA` aún no existen como pareja verificada; por eso
`exact_rollback_target_available=false` y el despliegue permanece bloqueado.
No existe rollback operativo de configuración porque M86-CF no incorpora un
switch ni modifica App Settings.

## Activación posterior, separada

Publicar el montaje dormido nunca autoriza activar M86-CE. Una futura
activación requerirá otro diseño, preflight, rollback, dos confirmaciones
textuales separadas y evidencia del retiro manual de Nia actual. Sólo después
podrá aparecer **ATENCIÓN REQUERIDA** para enviar el mensaje controlado.
