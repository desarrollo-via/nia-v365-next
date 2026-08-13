# Contrato de PR borrador — sonda protegida R1 Key Vault

Estado: `DRAFT-PR-CREATED-VERIFIED-READY-NOT-AUTHORIZED`.

Este contrato no autoriza red ni crear el PR. Tampoco autoriza ready, revisión,
merge, Actions manuales, despliegue, Azure, App Settings, secretos, activación,
Bitrix, bots, participantes, chats o mensajes.

## Identidad inmutable

- Repositorio: `desarrollo-via/nia-v365-next`.
- Base: `main@d5b2325a7025fb00b9d5dde0f20e45ab8217f43b`.
- Cabeza: `codex/r1-keyvault-protected-probe-v0580` en
  `d037031bba10d5dc21f81c5f7ec9aa647c07884e`.
- Padre: `d5b2325a7025fb00b9d5dde0f20e45ab8217f43b`.
- Árbol: `765126e381380e2a5525669a6cafb93391eaf957`.
- Alcance: un commit, `ahead=1`, `behind=0`, seis rutas, 30932 bytes y cero
  workflows.
- Manifiesto: SHA-256
  `FBA332D8A981BCA5419EC651B9BF815B5C81F618C9260F09598330F06D8DF7EE`.
- Título: `Add protected R1 host probe`.
- Cuerpo literal: `docs/r1_key_vault_protected_probe_draft_pr_body.md`, 1638
  bytes, SHA-256
  `2C3DB574268C45F41BF7C51D63244CACBB7625A7F67960868DCC5941EFBCAABB`.
- Modo obligatorio: `draft=true`.

## Preflight fresco

Inmediatamente antes de crear el PR deben aprobar simultáneamente:

1. `main`, ref, commit, padre, árbol, manifiesto y cuerpo exactos;
2. comparación de un commit, `ahead=1`, `behind=0`, seis rutas allowlisted y
   cero workflows;
3. cero PR abiertos o históricos asociados a la cabeza y cero Actions, checks
   o estados para el SHA candidato;
4. tres workflows activos, run `31449006990 completed/success` sobre `main` y
   dos lecturas de salud `ok/v0.267/off/off/locked/no-external/inert`;
5. pruebas focales 31/31, suite completa 1781/1781 y `tc 9/9` conservados;
6. HEAD, refs, índice y worktree locales preservados, permitiendo únicamente el
   tracking exacto ya creado por la publicación;
7. autenticación GitHub disponible sin abrir, mostrar ni enumerar credenciales.

Error, dato pendiente o colección ambigua termina `NO-GO` sin crear el PR ni
repetir automáticamente el preflight.

## Única creación futura

Una autorización crítica posterior puede permitir una sola tentativa:

```text
gh pr create --repo desarrollo-via/nia-v365-next --base main --head codex/r1-keyvault-protected-probe-v0580 --draft --title "Add protected R1 host probe" --body-file docs/r1_key_vault_protected_probe_draft_pr_body.md
```

Sólo el número devuelto por esa llamada puede postleerse o cerrarse. Un error o
una respuesta ambigua consume la tentativa sin repetir `gh pr create`.

## Postlectura convergente

Se permiten como máximo seis observaciones a los segundos `0, 2, 5, 10, 20,
30`, con cierre temprano. Deben coincidir simultáneamente:

- número nuevo, `OPEN/DRAFT`, `merged=false`, base, cabeza, SHA, título y cuerpo
  exactos;
- mergeability limpia cuando GitHub termine su cálculo, un commit,
  `ahead=1/behind=0`, seis rutas allowlisted y cero workflows;
- cero revisiones, checks, estados y Actions del candidato;
- `main`, ref, workflows, run, dos lecturas de salud y estado local sin deriva.

Sólo la fotografía completa produce `DRAFT-PR-CREATED-VERIFIED`. No autoriza
ready, merge, Action manual o despliegue.

## Rollback exacto

Ante `NO-GO`, puede cerrarse una vez únicamente el número nuevo cuando una
lectura inequívoca confirme `OPEN/DRAFT`, `merged=false` y base/cabeza/SHA
exactos:

```text
gh pr close <PR_NUEVO> --repo desarrollo-via/nia-v365-next
```

Después se exige `CLOSED/DRAFT`, no fusionado, ref y `main` intactos y cero
efectos adicionales. La ref no se mueve ni elimina. Si la identidad es ambigua,
el PR ya no es borrador o fue fusionado, no se fuerza el cierre y termina
`NO-GO-REMAINDER`. Cero reintentos.

## Validación local

El cuerpo quedó fijado en 1638 bytes y SHA-256
`2C3DB574268C45F41BF7C51D63244CACBB7625A7F67960868DCC5941EFBCAABB`.
Las pruebas documentales nuevas aprobaron 9/9; junto con las políticas de ref y
convergencia aprobaron 31/31, y la suite completa terminó 1790/1790. No hubo
red, PR ni otra modificación externa. El preflight público y la creación siguen
separados y no autorizados.

## Preflight público del 2026-08-11

La ejecución autorizada aprobó 16/16: `main`, ref, commit, comparación, seis
rutas, cuerpo, cero PR/Actions/checks/estados, tres workflows activos, run,
salud 2/2, autenticación disponible y estado local exactos. Resultado:
`READY-BEFORE-DRAFT-PR-CREATE`. No se creó PR ni hubo otra escritura externa;
la creación conserva su barrera crítica independiente.

## Creación verificada del 2026-08-11

El preflight crítico renovado aprobó 16/16. La única creación autorizada produjo
el PR `#15`; la mergeability convergió a `true/clean` en la observación de 20
segundos. La postlectura aprobó 16/16: `OPEN/DRAFT`, no fusionado, identidad,
título, cuerpo, un commit, seis rutas, comparación, único PR abierto, cero
revisiones/checks/estados/Actions, refs, workflows, run, salud 2/2 y estado local
exactos. Resultado: `DRAFT-PR-CREATED-VERIFIED-READY-NOT-AUTHORIZED`, creados 1,
cerrados 0 y rollback 0. No hubo ready, merge ni despliegue.
