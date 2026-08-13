# Contrato reversible para marcar ready el PR #15

Estado: `PR15-READY-VERIFIED-MERGE-COMPLETED`.

Este contrato cubre únicamente retirar una vez el estado borrador del PR `#15`.
No autoriza ready por sí mismo, aprobación, merge, Actions manuales, despliegue,
Azure, App Settings, secretos, activación, Bitrix, bots, participantes, chats o
mensajes.

## Identidad inmutable

- Repositorio: `desarrollo-via/nia-v365-next`.
- PR: `#15`, esperado `OPEN/DRAFT` y no fusionado.
- Base: `main@d5b2325a7025fb00b9d5dde0f20e45ab8217f43b`.
- Cabeza: `codex/r1-keyvault-protected-probe-v0580` en
  `d037031bba10d5dc21f81c5f7ec9aa647c07884e`.
- Árbol: `765126e381380e2a5525669a6cafb93391eaf957`.
- Alcance: un commit, seis rutas, cero workflows; manifiesto SHA-256
  `FBA332D8A981BCA5419EC651B9BF815B5C81F618C9260F09598330F06D8DF7EE`.
- Título: `Add protected R1 host probe`.
- Cuerpo: 1638 bytes, SHA-256
  `2C3DB574268C45F41BF7C51D63244CACBB7625A7F67960868DCC5941EFBCAABB`.

## Preflight fresco obligatorio

Inmediatamente antes de mutar deben aprobar simultáneamente:

1. PR `#15 OPEN/DRAFT`, `merged=false`, base/cabeza/SHA, título y cuerpo exactos;
2. `mergeable=true` y `mergeable_state=clean`;
3. un commit, comparación `ahead=1/behind=0`, seis rutas allowlisted y cero
   workflows;
4. exactamente un PR abierto para la cabeza, el propio `#15`;
5. cero revisiones, checks, estados y Actions del candidato;
6. `main` y ref candidata en los SHA fijados;
7. tres workflows activos y run `31449006990 completed/success` sobre `main`;
8. dos lecturas de salud con los siete campos exactos en
   `ok/v0.267/off/off/locked/no-external/inert`;
9. HEAD, refs, índice y worktree locales preservados.

Error, dato pendiente o transporte ambiguo termina `NO-GO` sin ready ni
reintento automático.

## Única mutación futura

Requiere autorización crítica literal y permite una sola tentativa:

```text
gh pr ready 15 --repo desarrollo-via/nia-v365-next
```

Un código no cero o respuesta ambigua consume la tentativa sin repetir. Sólo se
pasa a postlectura y rollback condicionado.

## Postlectura convergente

Se permiten hasta seis observaciones a los segundos `0, 2, 5, 10, 20, 30`, con
cierre temprano. Éxito exige `OPEN`, `draft=false`, no fusionado y las mismas
nueve barreras, salvo el estado borrador. Sólo la fotografía completa produce
`PR15-READY-VERIFIED-MERGE-NOT-AUTHORIZED`.

## Rollback condicionado

Ante fallo, puede restaurarse el borrador una sola vez sólo si una lectura
inequívoca confirma `#15 OPEN`, `draft=false`, no fusionado y
base/cabeza/SHA exactos:

```text
gh pr ready 15 --undo --repo desarrollo-via/nia-v365-next
```

Después se exige nuevamente `OPEN/DRAFT` con identidad exacta y cero efectos.
Si estado, identidad o merge son ambiguos, no se fuerza rollback y termina
`NO-GO-REMAINDER`. Nunca se mueve o elimina la ref; no se autoriza merge.

## Validación y preflight del 2026-08-11

Las pruebas nuevas aprobaron 9/9, las focales 27/27 y la suite completa
1799/1799. El preflight público posterior aprobó las nueve barreras más
autenticación disponible: PR `#15 OPEN/DRAFT`, `true/clean`, identidad, cuerpo,
un commit, seis rutas, único PR, cero efectos, refs, workflows/run, salud 2/2 y
estado local exactos. Resultado: `READY-BEFORE-PR15-READY-NOT-AUTHORIZED`. No se
ejecutó ready, rollback, merge, Action manual ni despliegue.

La repetición inmediata cubierta por la autorización envolvente se detuvo antes
de completar la fotografía porque el API público respondió `rate limit
exceeded`. No se ejecutó ready ni otra mutación y no hubo reintento. Resultado:
`NO-GO-TRANSPORT-RATE-LIMIT`. El fallback propuesto usa únicamente lecturas
autenticadas saneadas mediante `gh api`; requiere aceptación separada por el
criterio de detención vigente, pero no una nueva autorización del lote GitHub.

El fallback corregido usó `gh api` saneado y aprobó 9/9. La única llamada
`gh pr ready 15` convergió en la primera observación; la postlectura aprobó 7/7
con `OPEN`, `draft=false`, no fusionado, `true/clean`, identidad, cero efectos,
refs, salud y estado local exactos. Resultado: `PR15-READY-VERIFIED`; una llamada
ready y rollback 0. El merge posterior quedó cubierto por su contrato separado.
