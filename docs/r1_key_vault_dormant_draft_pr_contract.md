# Contrato de PR borrador — R1 Key Vault dormido

Estado: `DRAFT-PR-CREATED-VERIFIED-READY-NOT-AUTHORIZED`.

Este contrato no autoriza crear el PR. Tampoco autoriza ready, revisión, merge,
Actions manuales, despliegue, Azure, identidad, RBAC, Key Vault, App Settings,
secretos, activación, Bitrix, participantes, chats o mensajes.

## Identidad inmutable

- Repositorio: `desarrollo-via/nia-v365-next`.
- Base: `main@41ab2d5435cadf22db60574166d7eb29dd1dd57e`.
- Cabeza: `codex/r1-keyvault-dormant-v0551` en
  `e6af8b390f401dd3f2934faf2ced3ed70002e7bf`.
- Árbol: `7214bbb08ded045d59b6eb7ea0710b6fc68c18f8`.
- Alcance: un commit, `ahead=1`, `behind=0`, 17 rutas, 114575 bytes
  canónicos, cero workflows.
- Manifiesto: SHA-256
  `AC8B7F74EAF961E3393BE258404B94728609B34B9B4FCE25C036BACCAFE33151`.
- Título: `Add dormant R1 Key Vault preflight`.
- Cuerpo literal: `docs/r1_key_vault_dormant_draft_pr_body.md`, 1671 bytes,
  SHA-256 `91DF7F01FB006E0181014958581E772775AEAF0A44CA7D18DBB4F09698C9CB15`.
- Modo obligatorio: `draft=true`.

## Preflight fresco

Inmediatamente antes de crear el PR deben aprobar simultáneamente:

1. `main`, ref, commit, padre, árbol y manifiesto exactos;
2. comparación de un commit, `ahead=1`, `behind=0`, las 17 rutas allowlisted y
   cero workflows;
3. cuerpo con tamaño/hash exactos y pruebas aisladas 48/48, 21/21 y 1685/1685;
4. cero PR abiertos o históricos asociados a esta cabeza y cero Actions,
   checks o estados para el SHA candidato;
5. última ejecución de `main` aún `31405325991`, `completed/success`, y salud
   pública dormida sin deriva;
6. índice/worktree locales preservados y autenticación GitHub disponible sin
   abrir ni mostrar credenciales.

Error, dato pendiente o colección ambigua termina `NO-GO` sin crear el PR. El
preflight sólo lee y no se reintenta automáticamente.

## Única creación preparada

Con autorización posterior específica se permite una tentativa:

```text
gh pr create --repo desarrollo-via/nia-v365-next --base main --head codex/r1-keyvault-dormant-v0551 --draft --title "Add dormant R1 Key Vault preflight" --body-file docs/r1_key_vault_dormant_draft_pr_body.md
```

Sólo el número devuelto por esa llamada puede postleerse o cerrarse. Un error no
autoriza repetir `gh pr create`.

## Postlectura convergente

Se permiten hasta seis observaciones a los segundos `0, 2, 5, 10, 20, 30`, con
cierre temprano. Deben coincidir simultáneamente:

- número nuevo, `OPEN/DRAFT`, `merged=false`, base/cabeza/SHA exactos;
- título y cuerpo literal exactos;
- un commit, `ahead=1`, `behind=0`, 17 rutas allowlisted y cero workflows;
- cero revisiones, checks, estados y Actions;
- `main`, ref, última ejecución, salud, índice y worktree sin deriva.

Los únicos campos temporalmente pendientes permitidos son cálculos nativos de
mergeability dentro de la ventana. Identidad distinta, estado ready, merge,
efecto inesperado o transporte inconcluso termina `NO-GO`; nunca repite la
creación. Sólo la fotografía completa produce `DRAFT-PR-CREATED-VERIFIED`.

## Rollback exacto

Ante `NO-GO`, puede cerrarse una vez únicamente el número nuevo cuando una
lectura inequívoca confirme `OPEN/DRAFT`, `merged=false` y base/cabeza/SHA
exactos. Después se exige `CLOSED/DRAFT`, no fusionado, ref y `main` intactos y
cero efectos adicionales. La ref no se mueve ni elimina.

Si la identidad es ambigua, el PR ya no es borrador o fue fusionado, no se
fuerza el cierre: termina `NO-GO-REMAINDER`. El cierre no borra historial,
checks o Actions inesperados. Cero reintentos y detención antes de ready o merge.

## Preflight autorizado del 2026-08-10

El bloque 1 confirmó `main`, ref, commit, padre, árbol, comparación y 17 rutas
exactas con cero workflows. En el bloque 2, al menos uno de los conteos de PR,
Actions, checks o estados resultó no cero; el manejador PowerShell concatenó
incorrectamente `throw` con el motivo y terminó antes de emitir los contadores
saneados. El bloque 3 —workflow, salud, cuerpo y auth— no se ejecutó. No se creó
PR ni hubo escritura externa o reintento. Resultado:
`PREFLIGHT-NO-GO-INCONCLUSIVE`; una nueva lectura diagnóstica exige autorización.

La corrección persistente
`bitrix_connector/r1_key_vault_draft_pr_effects_audit.py` aprobó 9/9 fixtures:
deduplica PR por número, exige identidad exacta y reduce cinco GET allowlisted a
cuatro conteos. Su única ejecución pública terminó `EFFECTS-ABSENT`: PR 0,
Actions 0, checks 0 y estados 0, con cero reintentos/escrituras. El hallazgo
anterior era del colector PowerShell; bloque 2 queda resuelto. Bloque 3 y la
creación del PR continúan pendientes y no autorizados.

El bloque 3 autorizado confirmó run `31405325991` en `completed/success`, salud
`ok` y conector `v0.267/off/off/locked/no-external/inert`, cuerpo de 1671 bytes
con SHA exacto, autenticación GitHub disponible y estado local preservado. La
consolidación de los tres bloques terminó `READY-BEFORE-DRAFT-PR-CREATE`, con
cero escrituras/reintentos y ningún PR creado. La creación continúa requiriendo
autorización separada.

## Creación verificada del 2026-08-10

La única creación autorizada produjo el PR `#14`. Dos observaciones convergentes
confirmaron `OPEN/DRAFT`, no fusionado, base `main`, cabeza y SHA exactos, un
commit, 17 rutas y cero workflows, revisiones, checks o Actions. `main`, la ref,
el run `31405325991 completed/success`, la salud dormida y el estado local se
preservaron. Resultado: `DRAFT-PR-CREATED-VERIFIED-READY-NOT-AUTHORIZED`;
creados 1, cerrados 0. No se ejecutó ready, merge, Action manual ni despliegue.
