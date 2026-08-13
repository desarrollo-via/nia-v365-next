# Contrato reversible para marcar ready el PR #14

Estado: `PR14-READY-VERIFIED-MERGE-NOT-AUTHORIZED`.

Este contrato cubre únicamente retirar una vez el estado borrador del PR `#14`.
No autoriza ready por sí mismo, aprobación, merge, Actions manuales, despliegue,
Azure, identidad, RBAC, Key Vault, App Settings, secretos, activación, Bitrix,
participantes, chats o mensajes.

## Identidad inmutable

- Repositorio: `desarrollo-via/nia-v365-next`.
- PR: `#14`, esperado `OPEN/DRAFT` y no fusionado.
- Base: `main@41ab2d5435cadf22db60574166d7eb29dd1dd57e`.
- Cabeza: `codex/r1-keyvault-dormant-v0551` en
  `e6af8b390f401dd3f2934faf2ced3ed70002e7bf`.
- Árbol: `7214bbb08ded045d59b6eb7ea0710b6fc68c18f8`.
- Alcance: un commit, 17 rutas, cero workflows; manifiesto SHA-256
  `AC8B7F74EAF961E3393BE258404B94728609B34B9B4FCE25C036BACCAFE33151`.
- Título y cuerpo: los literales y la huella fijados por
  `docs/r1_key_vault_dormant_draft_pr_contract.md`.

## Preflight fresco obligatorio

Una autorización posterior debe volver a observar una sola fotografía completa
inmediatamente antes de mutar. Sólo nueve barreras simultáneas permiten seguir:

1. PR `#14 OPEN/DRAFT`, no fusionado, base/cabeza/SHA y cuerpo exactos;
2. `MERGEABLE/CLEAN`;
3. un commit, 17 rutas allowlisted y cero workflows;
4. exactamente un PR para la cabeza, el propio `#14`;
5. cero revisiones, checks, statuses y Actions del candidato;
6. `main` y ref candidata en los SHA fijados;
7. run `31405325991 completed/success` sobre `main` exacto;
8. salud con campos literales `status=ok`, `version=v0.267`,
   `requested_mode=off`, `effective_mode=off`, `activation_locked=true`,
   `external_calls_enabled=false` y `runtime_state=inert`;
9. índice y worktree locales preservados.

Error, dato pendiente o transporte ambiguo termina `NO-GO` sin ready y sin
reintento automático.

## Única mutación futura

Requiere otro SP específico y permite una sola tentativa:

```text
gh pr ready 14 --repo desarrollo-via/nia-v365-next
```

Código no cero o respuesta ambigua no permite repetir. Se pasa únicamente a la
postlectura y al rollback condicionado.

## Postlectura convergente

Se permiten hasta seis observaciones a los segundos `0, 2, 5, 10, 20, 30`, con
cierre temprano. Éxito exige `OPEN`, `draft=false`, no fusionado y las mismas
nueve barreras, salvo el estado borrador. No autoriza merge ni despliegue.

## Rollback condicionado

Ante fallo, puede restaurarse el borrador una sola vez sólo si una lectura
inequívoca confirma `#14 OPEN`, `draft=false`, no fusionado y base/cabeza/SHA
exactos:

```text
gh pr ready 14 --undo --repo desarrollo-via/nia-v365-next
```

Después se exige nuevamente `OPEN/DRAFT` con identidad exacta y cero efectos.
Si estado, identidad o merge son ambiguos, no se fuerza rollback: termina
`NO-GO-REMAINDER`. Nunca se mueve o elimina la ref.

## Auditoría del 2026-08-10

La fotografía autorizada aprobó 8/9: PR `#14 OPEN/DRAFT`, no fusionado,
`MERGEABLE/CLEAN`, identidad, cuerpo, un commit, 17 rutas, único PR, cero
workflows/revisiones/checks/statuses/Actions, refs, run y estado local exactos.
La barrera de salud quedó inconclusa porque el colector consultó propiedades
locales inexistentes (`connector_version`, `locked`, `external_effects` y
`runtime`) en vez de los nombres literales del contrato. No hubo deriva remota,
ready, rollback, reintento ni otra mutación. Resultado:
`NO-GO-COLLECTOR-GAP`; una nueva lectura exige autorización separada.

La relectura pública separadamente autorizada usó los siete nombres literales
y terminó `HEALTH-BARRIER-VERIFIED`: `ok`, `v0.267`, modos `off/off`, bloqueo
activo, llamadas externas deshabilitadas y runtime `inert`. Hubo una request,
cero reintentos y cero escrituras. Junto con las ocho barreras todavía vigentes,
el preflight queda consolidado 9/9 como
`READY-BEFORE-PR14-READY-NOT-AUTHORIZED`; no se ejecutó ready.

## Ejecución ready del 2026-08-10

El preflight fresco volvió a aprobar 9/9. La única llamada a `gh pr ready 14`
convergió en la primera observación: `#14 OPEN`, `draft=false`, no fusionado,
`MERGEABLE/CLEAN`, identidad, cuerpo, un commit y 17 rutas exactos, con cero
workflows, revisiones, checks, statuses o Actions. `main`, la ref, el run, la
salud dormida y el estado local se preservaron. Hubo una llamada ready y cero
rollback. Resultado: `PR14-READY-VERIFIED-MERGE-NOT-AUTHORIZED`; no se ejecutó
merge, Action manual ni despliegue.
