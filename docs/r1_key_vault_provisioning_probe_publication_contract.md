# Contrato reversible de publicación y despliegue de la sonda R1

Estado: `MERGED-DEPLOYED-STABLE`.

Este contrato preparó una única envolvente GitHub y conserva su ejecución
verificada; por sí mismo no autoriza efectos adicionales.

## Identidad fija

- Repositorio: `desarrollo-via/nia-v365-next`.
- Base: `main` en
  `2631f8483ca5e565b4ca53874e32f4d6035c09f8`.
- Candidato: `1b4c2be1ce68e889a19dd9c92c91a51c857ab0c4`.
- Árbol: `9e743a9bdde1ac5c1bb8786000c50e94ff9ac597`.
- Rama futura: `codex/r1-keyvault-provisioning-preflight-v0602`.
- Título: `Add protected R1 provisioning preflight`.
- Cuerpo:
  `docs/r1_key_vault_provisioning_probe_draft_pr_body.md`.
- Alcance: las tres rutas del inventario y cero workflows.

## Envolvente ejecutada

La autorización específica cubrió como máximo:

1. preflight público fresco de main, rama ausente, candidato local, tres rutas,
   cero workflows, salud dormida y estado local;
2. publicación única del candidato como la rama exacta con lease de ausencia;
3. postlectura Git y API hasta convergencia acotada, sin re-push;
4. creación única del PR borrador exacto;
5. validación de identidad, diff, efectos y checks automáticos;
6. marcar `ready`, fusionar una vez sólo si todo permanece exacto y observar el
   workflow/despliegue automático;
7. exigir dos lecturas de salud estables y postlectura de main/PR/ref.

Se detiene ante cualquier deriva, check fallido, conflicto, transporte ambiguo,
ruta adicional, workflow modificado o salud inestable. No hay Actions manuales,
admin, auto-merge, force, eliminación automática de rama ni reintentos.

## Rollback contractual

- Antes del merge: cerrar sólo el PR creado y eliminar sólo la rama exacta si
  sus identidades coinciden; main permanece intacto.
- Después del merge: crear un revert normal del merge exacto, publicarlo por
  fast-forward normal y observar el despliegue de reversión; nunca reset o
  force-push.
- Si una identidad o postlectura no converge, terminar `NO-GO-REMAINDER` sin
  compensaciones inferidas.

La envolvente termina antes de invocar la nueva sonda, abrir `.env` o
Credential Manager, leer secretos, autenticar Azure, aprovisionar recursos,
activar R1, consultar Bitrix o enviar mensajes.

## Ejecución del 2026-08-11

El preflight público confirmó `main` en `2631f8483ca5e565b4ca53874e32f4d6035c09f8`, rama ausente, cero PR y Actions, tres workflows activos, última ejecución productiva exitosa y salud dormida 2/2. La publicación única creó la rama exacta en `1b4c2be1ce68e889a19dd9c92c91a51c857ab0c4`; Git y REST convergieron con `ahead=1`, `behind=0`, un commit, tres rutas y cero workflows.

El PR borrador `#16` se creó con título, cuerpo, base y cabeza exactos; quedó `ready/clean` y fue fusionado una sola vez. `main` avanzó al merge `641331c63253536ea2531f091b933af4380c95b3`, con padres base/candidato y árbol `9e743a9bdde1ac5c1bb8786000c50e94ff9ac597`. La rama permaneció intacta.

El único workflow automático `31518711951` terminó `completed/success`; dos lecturas posteriores confirmaron `ok/v0.267/off/off/locked/no-external/inert`. Resultado: `MERGED-DEPLOYED-STABLE`; un push, un PR, un ready, un merge, cero Actions manuales y rollback 0. No se invocó la sonda ni se abrieron secretos, Azure, Bitrix o mensajes.
