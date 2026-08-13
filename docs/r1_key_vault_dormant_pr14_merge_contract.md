# Contrato reversible de merge para PR #14

Estado: `MERGED-DEPLOYED-STABLE`.

Este contrato cubre un único merge normal del PR `#14`, la observación del
workflow automático, el despliegue dormido y un rollback Git condicionado. No
autoriza `--admin`, auto-merge, squash, rebase, eliminación de rama,
`workflow_dispatch`, reintentos, cambios de Azure, identidad, RBAC, Key Vault,
App Settings, secretos, activación, Bitrix, participantes, bots o mensajes.

## Identidad y efecto esperado

- Repositorio: `desarrollo-via/nia-v365-next`.
- Base: `main@41ab2d5435cadf22db60574166d7eb29dd1dd57e`, árbol
  `370a5b4e5b2b55420e0c918fa8dfc12c6bd42b30`.
- Cabeza: `codex/r1-keyvault-dormant-v0551` en
  `e6af8b390f401dd3f2934faf2ced3ed70002e7bf`, árbol
  `7214bbb08ded045d59b6eb7ea0710b6fc68c18f8`.
- La cabeza tiene como único padre y merge-base la base.
- Alcance: un commit, 17 rutas, 114575 bytes canónicos, cero workflows y
  manifiesto SHA-256
  `AC8B7F74EAF961E3393BE258404B94728609B34B9B4FCE25C036BACCAFE33151`.
- Workflow automático: `.github/workflows/main_nia-v365-next-api.yml`, activo,
  blob Git `8861d91a27250cfef93d606bfd8a4414a5fb024c`.
- El merge instala dependencias, pero no configura identidad, RBAC, vault,
  secretos o App Settings y no activa R1.

## Preflight fresco obligatorio

Inmediatamente antes de fusionar deben aprobar nuevamente:

1. PR `#14 OPEN/READY`, no fusionado, `MERGEABLE/CLEAN`, identidad y cuerpo;
2. un commit, 17 rutas allowlisted y cero workflows modificados;
3. exactamente un PR para la cabeza y cero revisiones, checks, statuses o
   Actions del candidato;
4. `main`, ref, padre, merge-base y árboles exactos;
5. workflow productivo activo con ruta y blob exactos;
6. run `31405325991 completed/success` sobre la base;
7. salud `ok/v0.267/off/off/locked/no-external/inert`;
8. índice y worktree locales preservados.

Cualquier deriva, cálculo pendiente o transporte ambiguo termina `NO-GO` sin
merge y sin reintento automático.

## Única operación futura

Requiere otro SP específico y permite una sola llamada:

```text
gh pr merge 14 --repo desarrollo-via/nia-v365-next --merge --match-head-commit e6af8b390f401dd3f2934faf2ced3ed70002e7bf
```

No se añaden `--admin`, `--auto` o `--delete-branch`. Código no cero o respuesta
ambigua no permite repetir; primero se postlee el estado real.

## Postlectura y despliegue

Éxito exige un merge commit nuevo con padres exactos base/cabeza y árbol
`7214bbb08ded045d59b6eb7ea0710b6fc68c18f8`; PR `MERGED`, ref candidata intacta
y `main` en ese merge. En máximo 120 segundos debe aparecer un único workflow
automático `push` para el SHA. Se observa cada 10 segundos hasta 15 minutos, sin
reintentar ni despachar Actions, y debe terminar `completed/success`.

Después se exigen dos lecturas de salud separadas por 10 segundos con
`ok/v0.267/off/off/locked/no-external/inert`. No se invocan rutas R1, Azure o
Bitrix. Sólo entonces el resultado es `MERGED-DEPLOYED-STABLE`.

## Rollback exacto y condicionado

Si el merge no ocurrió, no existe rollback. Si ocurrió pero workflow,
despliegue o salud falla, sólo puede crearse un revert normal cuando `main`
continúa exactamente en el merge verificado. El revert debe tener como único
padre ese merge y como árbol literal el árbol base
`370a5b4e5b2b55420e0c918fa8dfc12c6bd42b30`; su publicación debe ser un avance
fast-forward normal sobre `main`, sin reset, force-push o edición de Azure.

El rollback produce su propio workflow automático y exige el mismo límite y dos
lecturas finales de salud dormida. Si `main` derivó o la identidad es ambigua,
no se sobrescribe: termina `NO-GO-REMAINDER`.

## Criterios terminales

- Éxito: `MERGED-DEPLOYED-STABLE`.
- Fallo restaurado: `FAILED-MERGE-RESTORED`.
- Fallo no reversible con seguridad: `NO-GO-REMAINDER`.

## Auditoría del 2026-08-10

La fotografía autorizada aprobó 8/8: PR `#14 OPEN/READY`, no fusionado,
`MERGEABLE/CLEAN`, identidad, cuerpo, un commit y 17 rutas exactos; cero
workflows modificados, revisiones, checks, statuses o Actions; `main`, ref,
padre, merge-base y árboles exactos. El workflow productivo permaneció activo
con ruta/blob exactos, run `31405325991 completed/success`, salud dormida y
estado local preservado. Hubo cero escrituras. Resultado:
`READY-BEFORE-PR14-MERGE-NOT-AUTHORIZED`; no se ejecutó merge ni despliegue.

## Ejecución del 2026-08-10

El preflight fresco volvió a aprobar 8/8. La única llamada de merge creó
`d5b2325a7025fb00b9d5dde0f20e45ab8217f43b`, con padres base/cabeza y árbol
candidato exactos; PR `#14` quedó `MERGED`, `main` avanzó al merge y la ref
candidata permaneció intacta. El workflow automático `31449006990` terminó
`completed/success`. Dos lecturas de salud confirmaron
`ok/v0.267/off/off/locked/no-external/inert`. Hubo un merge, cero Actions
manuales y rollback 0; el estado local se preservó. Resultado:
`MERGED-DEPLOYED-STABLE`.
