# Contrato v2 de publicación de ref — sonda protegida R1 Key Vault

Estado: `PUBLISHED-VERIFIED-AWAITING-PR-PHASE`.

Este contrato no autoriza red, creación de refs, push, PR, Actions, merge,
despliegue, servicios, Azure, Bitrix o mensajes. Sustituye sólo para una futura
propuesta al contrato v1 consumido; no reutiliza su autorización ni su nombre de
ref.

## Identidad exacta

- Remoto esperado: `origin` → `desarrollo-via/nia-v365-next`.
- Base obligatoria: `main=d5b2325a7025fb00b9d5dde0f20e45ab8217f43b`.
- Ref nueva: `refs/heads/codex/r1-keyvault-protected-probe-v0580`.
- Commit: `d037031bba10d5dc21f81c5f7ec9aa647c07884e`.
- Padre: `d5b2325a7025fb00b9d5dde0f20e45ab8217f43b`.
- Árbol: `765126e381380e2a5525669a6cafb93391eaf957`.
- Alcance: seis rutas, 30932 bytes y cero workflows.
- Huella:
  `FBA332D8A981BCA5419EC651B9BF815B5C81F618C9260F09598330F06D8DF7EE`.

La ref local propia y su tracking están ausentes. La ausencia remota no se
infiere: debe demostrarse en un preflight público futuro.

## Evaluador local obligatorio

`r1_protected_probe_local_ref_policy.py` compara fotografías completas
`refname → objectname` tomadas antes y después. Aprobó 9/9 pruebas; junto con la
política de convergencia Git/REST, 22/22.

- Baseline inválido si ya existe la ref propia o de seguimiento candidata.
- Tras push acepta sólo baseline literal o la adición exacta
  `refs/remotes/origin/codex/r1-keyvault-protected-probe-v0580` en el SHA
  candidato.
- `refs/heads/...`, SHA distinto o cualquier alta, baja o cambio ajeno es
  `REF_DRIFT`.
- Tras rollback exige igualdad literal con el baseline pre-push.

Las cinco condiciones del preflight se evalúan por nombres independientes; no
se usa una expresión compacta ni `for-each-ref --points-at` como criterio de
preservación.

## Fases futuras separadas

1. Otra autorización permite sólo auditoría pública no autenticada: `main`
   exacto, ref v2 ausente por Git/REST, PR/Actions 0, workflows/run y salud
   estables; debe detenerse sin publicar.
2. Una autorización crítica posterior permite repetir inmediatamente el
   preflight y ejecutar una única vez:

```text
git push --porcelain --force-with-lease=refs/heads/codex/r1-keyvault-protected-probe-v0580: origin d037031bba10d5dc21f81c5f7ec9aa647c07884e:refs/heads/codex/r1-keyvault-protected-probe-v0580
```

3. Git directo y REST convergen con observaciones máximas en 0, 2, 5, 10, 20 y
   30 segundos. Después se exigen comparación `ahead=1/behind=0`, un commit,
   seis rutas, cero workflows/PR/Actions, run y salud estables, y decisión local
   `EXACT_WITHOUT_TRACKING` o `EXACT_WITH_TRACKING`.

No se crea PR. Un push rechazado o ambiguo consume la tentativa sin reintento.

## Rollback futuro

Sólo si Git directo conserva ref=candidato y `main`=base puede ejecutarse una
eliminación con lease exacta. Después Git/REST deben converger a ausencia y el
evaluador local debe devolver `EXACT_RESTORED` contra el baseline original.
Cualquier ref, SHA, base o transporte distinto deja `NO-GO-REMAINDER`; no se
fuerza ni se compensa automáticamente.

## Validación local vigente

La política nueva aprobó 9/9 y 22/22 junto a la regresión de convergencia. La
auditoría focal confirmó que el contrato Azure vigente era coherente. Se
alinearon sólo tres literales documentales del mismo archivo de pruebas: los dos
fallos iniciales y una expectativa posterior oculta por el primero. Aprobaron
31/31 pruebas focales y la suite completa 1781/1781.

El contrato v2 queda listo únicamente para una auditoría pública no autenticada
bajo autorización separada. No hubo red, creación de refs ni publicación.

## Auditoría pública del 2026-08-11

La observación autorizada aprobó 9/9 barreras no relacionadas con salud: `main`
exacto por Git/REST, ref v0580 ausente por Git/REST, PR y Actions cero, tres
workflows activos, run `31449006990 completed/success` y estado local idéntico.
Las dos respuestas de salud confirmaron `status=ok`, modos `off/off`, bloqueo,
cero llamadas externas y runtime `inert`, pero el colector consultó la propiedad
inexistente `connector_version` en vez del nombre literal `version`; por ello no
conservó evidencia del valor `v0.267`.

El código y el contrato local confirman que el campo correcto es `version`, pero
esa evidencia no reemplaza la respuesta remota descartada. Resultado:
`NO-GO-COLLECTOR-GAP`, cero refs, publicación, PR, Actions, despliegue o cambios
locales ajenos a esta evidencia. No hubo reintento. Una nueva autorización puede
permitir únicamente dos lecturas de salud con los siete nombres literales y
detención inmediata.

La relectura separadamente autorizada ejecutó exactamente dos consultas y ambas
aprobaron los siete campos: `status=ok`, `version=v0.267`, modos `off/off`,
`activation_locked=true`, `external_calls_enabled=false` y
`runtime_state=inert`. Resultado: `HEALTH-BARRIER-VERIFIED`. No consultó GitHub,
no reintentó y no creó ref, PR, Action, despliegue ni otro estado externo. El
contrato queda listo sólo para la autorización crítica de la fase 2.

El preflight crítico posterior aprobó 13/13 barreras y terminó
`GO-BEFORE-PUSH`. La unidad de publicación fue rechazada por la barrera de
ejecución antes de iniciar el comando: no hubo push, rollback ni nueva red en
esa unidad. La tentativa permanece sin consumir. Continuar exige una
confirmación humana literal con repositorio, ref, commit, tentativa única,
lease y rollback contractual.

La confirmación literal posterior autorizó una sola tentativa. El preflight
fresco aprobó 13/13 y el push con lease creó exactamente la ref v0580 sobre
`d037031bba10d5dc21f81c5f7ec9aa647c07884e`. Git directo y REST convergieron en
la primera observación. La postlectura aprobó comparación `ahead=1/behind=0`, un
commit, seis rutas, cero workflows/PR/Actions, tres workflows activos, run y
salud estables, `main` intacto y estado compartido preservado. El evaluador
local devolvió `EXACT_WITH_TRACKING`. Resultado: `PUBLISHED-VERIFIED`, un push,
cero rollback y cero reintentos. No se creó PR, merge ni despliegue.
