# Contrato de commit local para sonda protegida R1 Key Vault

Estado: `COMMIT-CREATED-VERIFIED-NO-REF`.

Este contrato documenta el objeto commit local ya creado. No autoriza modificar
el índice compartido, crear refs, usar red, publicar, abrir PR, ejecutar Actions,
desplegar, iniciar servicios, leer el entorno real, acceder a Azure o Bitrix ni
enviar mensajes.

## Identidad obligatoria

- Base y padre único: `d5b2325a7025fb00b9d5dde0f20e45ab8217f43b`.
- Árbol base: `7214bbb08ded045d59b6eb7ea0710b6fc68c18f8`.
- Árbol candidato: `765126e381380e2a5525669a6cafb93391eaf957`.
- Inventario: `docs/r1_key_vault_protected_probe_cut_inventory.md`.
- Payload: seis rutas, 30932 bytes, cero workflows.
- Huella agregada:
  `FBA332D8A981BCA5419EC651B9BF815B5C81F618C9260F09598330F06D8DF7EE`.
- Mensaje propuesto: `feat(bitrix): add protected R1 host probe`.

Los documentos de evidencia no pertenecen al payload del commit. Cualquier
séptima ruta, cambio de base, árbol o huella termina `NO-GO-SCOPE`.

## Operación futura separada

Una autorización específica podrá construir un índice temporal desde la base,
superponer sólo los seis blobs exactos, exigir el árbol candidato y crear un
único commit de un padre mediante plumbing Git. No deberá ejecutar `git add`
sobre el índice compartido ni mover HEAD o rama alguna.

La postlectura deberá demostrar:

1. padre, árbol, mensaje y seis rutas exactos;
2. cero workflows y cero refs apuntando al commit;
3. índice, HEAD, refs y `git status --porcelain=v1` compartidos preservados;
4. cero red, hooks, firma, publicación o reintento.

El SHA del commit se registra sólo después de crearlo y reconsultarlo; no se
infieren autor, fechas o identidad. Si falla antes de `commit-tree`, se elimina
únicamente el índice temporal. Si el objeto fue creado pero la postlectura
falla, no se crea ref: queda inalcanzable y el resultado es
`NO-GO-UNREFERENCED-COMMIT`, sin borrado destructivo ni reintento automático.

Commit, ref, publicación, PR, merge y despliegue son barreras independientes.

## Resultado del intento autorizado

Las seis huellas y la base coincidieron, pero el índice temporal produjo
`765126e381380e2a5525669a6cafb93391eaf957` en vez de
`ca584b0c27c0ae94a07cd9bbd282d7e84b886676`. La operación terminó antes de
`commit-tree`. No existe commit con el mensaje propuesto, no se creó ref, el
índice temporal fue eliminado y el estado compartido quedó inmóvil. El árbol
discrepante contiene sólo las seis rutas esperadas, pero no se adopta sin una
auditoría independiente del método de extracción y reindexado. Queda prohibido
reintentar el commit con cualquiera de los dos árboles por continuidad.

## Corrección auditada

La comparación independiente probó que ZIP más reindexado normalizó, por
`core.autocrlf=true`, los finales mixtos del workflow productivo fuera del
payload. `read-tree` preservó el blob base y produjo el árbol canónico
`765126e381380e2a5525669a6cafb93391eaf957`. Un clon local nuevo revalidó seis
rutas, cero workflows, focales 12/12 y suite 1697/1697; fue eliminado sin tocar
el estado compartido.

El `NO-GO` anterior quedó cerrado documentalmente, sin reintento histórico. Una
autorización posterior aplicó la operación exclusivamente al árbol corregido;
`ca584b0c…` permanece prohibido.

## Commit creado y postleído

La operación corregida creó
`d037031bba10d5dc21f81c5f7ec9aa647c07884e` con un padre exacto, árbol
`765126e381380e2a5525669a6cafb93391eaf957`, asunto acordado, seis rutas y cero
workflows. La postlectura demostró cero refs; eliminó el índice temporal y
preservó `HEAD`, refs, índice y worktree compartidos. No hubo hooks, firma, red,
publicación o reintento. Crear una ref exige otra autorización y contrato.
