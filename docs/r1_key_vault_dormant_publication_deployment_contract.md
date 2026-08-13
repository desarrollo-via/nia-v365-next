# Contrato reversible de publicación y despliegue dormido R1 Key Vault

Estado: `MERGED-DEPLOYED-STABLE`.

Este documento no autoriza índice, commit, refs, red, push, PR, Actions, merge,
instalación, despliegue, Azure, identidad, RBAC, Key Vault, App Settings,
secretos, activación, Bitrix ni mensajes.

## Identidad del corte

- Base obligatoria: `41ab2d5435cadf22db60574166d7eb29dd1dd57e` / árbol
  `370a5b4e5b2b55420e0c918fa8dfc12c6bd42b30`.
- Inventario: `docs/r1_key_vault_dormant_cut_inventory.md`.
- Payload: 17 rutas, 114575 bytes canónicos Git, cero workflows.
- Huella canónica:
  `AC8B7F74EAF961E3393BE258404B94728609B34B9B4FCE25C036BACCAFE33151`.
- Árbol candidato aislado esperado:
  `7214bbb08ded045d59b6eb7ea0710b6fc68c18f8`.
- Commit candidato local, aún sin ref:
  `e6af8b390f401dd3f2934faf2ced3ed70002e7bf`.
- Ref candidata futura: `refs/heads/codex/r1-keyvault-dormant-v0551`.
- R1 permanece apagado; el backend no importa SDK ni lee configuración durante
  importación o construcción.

El HEAD local antiguo y el árbol de trabajo mixto no pueden usarse como base.
El candidato debe construirse en un índice/checkout aislado desde el commit base
y superponer sólo las 17 rutas con hashes exactos. Cualquier ruta 18 termina
`NO-GO-SCOPE`.

## Barreras locales antes de red

1. comprobar existencia y árbol de la base;
2. recalcular las 17 huellas y la huella agregada;
3. extraer la base en temporal nuevo y superponer sólo el payload;
4. ejecutar allí las ocho pruebas focales y la regresión hermética completa con
   Python 3.12 existente, sin instalar dependencias;
5. demostrar cero workflows, import perezoso de Azure, diff exacto e índice y
   worktree originales sin cambios atribuibles a la validación.

La validación aislada aprobó base/árbol, focales 48/48 + 21/21 y suite
1685/1685. Después se creó sólo el commit candidato y su postlectura confirmó
padre, árbol, 17 rutas y cero workflows; no existe ref local o remota creada por
esta fase.

La auditoría pública sin autenticación del 2026-08-10 terminó 3/3: `main`
conservó `41ab2d5435cadf22db60574166d7eb29dd1dd57e`, la ref candidata continuó
ausente, el commit candidato tuvo cero Actions y la última ejecución de `main`,
`31405325991`, permaneció `completed/success` sobre el SHA exacto. Hubo cero
escrituras y cero reintentos. Resultado: `READY-BEFORE-REF-PUBLICATION`.

La publicación autorizada ejecutó un solo push atómico. Git y REST convergieron
en la primera observación: ref exacta en
`e6af8b390f401dd3f2934faf2ced3ed70002e7bf`, árbol/padre y 17 rutas exactos,
cero workflows, cero Actions y `main` intacto. Rollback 0; no se creó PR ni se
ejecutó Action. Resultado: `REF-PUBLISHED-VERIFIED`.

## Publicación futura, en fases separadas

1. Completado: una autorización específica creó localmente el commit candidato
   de un padre sobre la base exacta, sin ref ni red.
2. Completado: una autorización publicó la ref exacta con push atómico y
   postlectura convergente, sin rollback.
3. Otra autorización permite crear un PR borrador con base `main`, un commit,
   cuerpo ligado a la huella y 17 rutas exactas. No permite ready ni merge.
4. Ready, merge y despliegue son autorizaciones posteriores independientes.
   Antes del merge se revalida que `main` siga en la base prevista y que el
   workflow de producción no haya derivado.

## Despliegue dormido y éxito

El merge futuro dispara el workflow existente; no se ejecuta manualmente. El
artefacto instala las dependencias fijadas, pero no configura identidad, vault,
RBAC, secretos ni `NIA_BITRIX_KEY_VAULT_URL`. Éxito exige workflow
`completed/success`, SHA/árbol exactos y dos lecturas de salud
`v0.267/off/locked/no-external/inert`, R0 desmontado y R1 apagado. La mera
instalación de SDK no autoriza construir credenciales ni clientes.

## Rollback

- Antes de push: descartar sólo el checkout/índice temporal; no tocar el árbol
  de trabajo compartido.
- Ref publicada sin PR: eliminar sólo la ref candidata si su SHA es exacto.
- PR borrador: cerrarlo y después eliminar únicamente la ref exacta; verificar
  `merged=false`, `main` intacto y cero Actions atribuibles.
- Merge/despliegue: crear un revert normal del único merge exacto, nunca reset,
  force push ni reescritura; desplegar el revert y exigir dos lecturas de salud
  dormida.
- Si identidad, RBAC, vault, secreto o App Setting aparecen modificados, este
  contrato no intenta compensarlos: termina `NO-GO-EXTERNAL-DRIFT` porque esas
  superficies no pertenecen al corte.

Cero reintentos automáticos. Toda identidad, conteo o postlectura ambigua deja
el remanente visible y requiere intervención humana.

## Resultado final del corte dormido

PR `#14` fue fusionado una vez en
`d5b2325a7025fb00b9d5dde0f20e45ab8217f43b`; padres y árbol coincidieron. El
workflow automático `31449006990` terminó `completed/success` y dos lecturas de
salud conservaron `ok/v0.267/off/off/locked/no-external/inert`. Cero Actions
manuales y rollback 0. El artefacto contiene los tres pines, pero la instalación
runtime aún no está demostrada. Esto no autoriza ni demuestra identidad, RBAC,
vault, secreto, App Setting o activación.
