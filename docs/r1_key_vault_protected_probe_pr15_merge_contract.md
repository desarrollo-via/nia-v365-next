# Contrato reversible de merge para PR #15

Estado: `MERGED-DEPLOYED-STABLE`.

Este contrato cubre un único merge normal del PR `#15`, el workflow automático,
la verificación del despliegue dormido y rollback Git condicionado. No autoriza
`--admin`, auto-merge, squash, rebase, eliminación de rama,
`workflow_dispatch`, reintentos, Azure, App Settings, secretos, activación,
Bitrix, bots, participantes, chats o mensajes.

## Identidad y efecto esperado

- Repositorio: `desarrollo-via/nia-v365-next`.
- Base: `main@d5b2325a7025fb00b9d5dde0f20e45ab8217f43b`, árbol
  `7214bbb08ded045d59b6eb7ea0710b6fc68c18f8`.
- Cabeza: `codex/r1-keyvault-protected-probe-v0580` en
  `d037031bba10d5dc21f81c5f7ec9aa647c07884e`, árbol
  `765126e381380e2a5525669a6cafb93391eaf957`.
- La cabeza tiene como padre único y merge-base la base.
- Alcance: un commit, seis rutas, 30932 bytes, cero workflows y manifiesto
  `FBA332D8A981BCA5419EC651B9BF815B5C81F618C9260F09598330F06D8DF7EE`.
- Workflow automático: `.github/workflows/main_nia-v365-next-api.yml`, activo,
  blob Git `8861d91a27250cfef93d606bfd8a4414a5fb024c`.
- El merge expone la ruta protegida, pero no la invoca, no configura Azure o
  secretos y conserva R1 apagado.

## Preflight fresco obligatorio

Inmediatamente antes de fusionar deben aprobar:

1. PR `#15 OPEN/READY`, no fusionado, `true/clean`, identidad, título y cuerpo;
2. un commit, comparación `ahead=1/behind=0`, seis rutas allowlisted y cero
   workflows modificados;
3. único PR para la cabeza y cero revisiones, checks, estados o Actions;
4. `main`, ref, padre, merge-base y árboles exactos;
5. workflow productivo activo con ruta y blob exactos;
6. run `31449006990 completed/success` sobre la base;
7. dos lecturas de salud `ok/v0.267/off/off/locked/no-external/inert`;
8. HEAD, refs, índice y worktree locales preservados.

Deriva, cálculo pendiente o transporte ambiguo termina `NO-GO` sin merge.

## Único merge autorizado por la envolvente vigente

Sólo tras confirmar el estado ready exacto se permite una llamada:

```text
gh pr merge 15 --repo desarrollo-via/nia-v365-next --merge --match-head-commit d037031bba10d5dc21f81c5f7ec9aa647c07884e
```

No se añaden `--admin`, `--auto` o `--delete-branch`. Código no cero o respuesta
ambigua no permite repetir; primero se postlee el estado real.

## Postlectura y despliegue

Éxito exige un merge commit nuevo con padres exactos base/cabeza y árbol
`765126e381380e2a5525669a6cafb93391eaf957`; PR `MERGED`, ref intacta y `main`
en ese merge. En máximo 120 segundos debe aparecer un único workflow automático
`push` para el SHA. Se observa cada 10 segundos hasta 15 minutos, sin reejecutar
ni despachar Actions, y debe terminar `completed/success`.

Después se exigen dos lecturas de salud separadas por 10 segundos con
`ok/v0.267/off/off/locked/no-external/inert`. No se invoca la sonda ni se
consulta Azure o Bitrix. Sólo entonces termina `MERGED-DEPLOYED-STABLE`.

## Rollback normal condicionado

Si no hubo merge, no existe rollback. Si ocurrió pero workflow, despliegue o
salud falla, sólo puede crearse un revert normal cuando `main` continúa
exactamente en el merge verificado. El revert tendrá ese merge como padre único
y el árbol base `7214bbb08ded045d59b6eb7ea0710b6fc68c18f8`; se publica como
avance fast-forward normal, sin reset, force-push ni edición de Azure.

El rollback produce su propio workflow automático y exige el mismo límite y dos
lecturas finales de salud. Si `main` derivó o la identidad es ambigua, no se
sobrescribe y termina `NO-GO-REMAINDER`.

## Validación local

Las pruebas nuevas aprobaron 9/9; junto con el contrato ready aprobaron 18/18 y
la suite completa terminó 1808/1808. No hubo red durante esta preparación ni se
ejecutó ready, merge, Action o despliegue.

## Ejecución del 2026-08-11

El preflight fresco aprobó 8/8. La única llamada de merge creó
`2631f8483ca5e565b4ca53874e32f4d6035c09f8`, con padres base/cabeza y árbol
candidato exactos; PR `#15` quedó fusionado, `main` avanzó al merge y la ref
permaneció intacta. El workflow automático `31497045244` apareció en la primera
observación y terminó `completed/success`. La postlectura final aprobó 7/7 y dos
lecturas separadas confirmaron `ok/v0.267/off/off/locked/no-external/inert`.
Resultado: `MERGED-DEPLOYED-STABLE`; un ready, un merge, cero Actions manuales y
rollback 0. No se invocó la sonda, Azure, Bitrix ni mensajes.
