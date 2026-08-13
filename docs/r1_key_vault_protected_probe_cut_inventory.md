# Inventario exacto del corte de sonda protegida R1 Key Vault

Estado: `LOCAL-COMMIT-CREATED-VERIFIED-NO-REF`.

Fecha: 2026-08-11. Este inventario no autoriza índice compartido, commit, ref,
red, publicación, PR, Action, despliegue, servicio, entorno real, Azure, Bitrix
o mensajes.

## Base y árbol candidato

- Base desplegada: `d5b2325a7025fb00b9d5dde0f20e45ab8217f43b`.
- Árbol base: `7214bbb08ded045d59b6eb7ea0710b6fc68c18f8`.
- Árbol candidato canónico: `765126e381380e2a5525669a6cafb93391eaf957`.
- Alcance: 6 rutas, 30932 bytes canónicos Git, cero workflows.
- SHA-256 del manifiesto canónico `ruta|bytes|SHA-256`, UTF-8, LF y salto final:
  `FBA332D8A981BCA5419EC651B9BF815B5C81F618C9260F09598330F06D8DF7EE`.

```text
bitrix_connector/review_router.py|10500|8C510086A9CE2349FCECBC6FF15DFA5AC2BE404CC49B4C91CCFF9637BA82A29B
bitrix_connector/router.py|4252|BB1C51E0D2E36DE91C1946F28387ED33AB7EB0E00E5094C5AF9987AF36126AC1
bitrix_connector/r1_key_vault_protected_host_probe.py|3731|6A3A6518811847E03DC751148254C1F90033AE73B3AE340904EBEB0DA4BF0CC1
bitrix_connector/r1_key_vault_protected_host_probe_binding.py|532|880EC1472EC7137FA7CA280C09364616A8A87C326AA0699581A61CC75362A298
tests/test_r1_key_vault_protected_host_probe.py|7237|6F882436BD9788CC9995CD0B22D64B0796A95010E9E56ECC3EBD89A3E6A81881
tests/test_r1_key_vault_protected_host_probe_binding.py|4680|5AE78C68E65798D3983BA202EC0014788F6A476D7A5348829B73B4CF978B5E82
```

Toda ruta adicional, archivo ausente, cambio de byte/huella, workflow o base
distinta termina `NO-GO-SCOPE` sin compensación automática.

## Validación aislada inicial — método luego invalidado

Una extracción ZIP local de la base exacta recibió únicamente las seis rutas.
Un repositorio Git creado dentro del temporal calculó el árbol candidato sin
usar el índice, objetos o refs compartidos. Resultados:

- owner, binding y ruta: 12/12;
- regresión Review: 16/16;
- regresión del conector: 26/26;
- suite hermética completa: 1697/1697.

No se instaló nada, no se leyó el entorno real y no hubo servicio o red. El ZIP
y el directorio temporal fueron eliminados después de verificar su contención;
`git status --porcelain=v1` fue idéntico antes y después. No se creó commit.

## Intento de commit detenido del 2026-08-11

La revalidación de las seis huellas y de la base aprobó. Un índice temporal
creado con `read-tree` sobre la base y los seis blobs exactos produjo el árbol
`765126e381380e2a5525669a6cafb93391eaf957`, distinto del árbol aislado
contractual `ca584b0c27c0ae94a07cd9bbd282d7e84b886676`. La barrera actuó antes de
`commit-tree`; no se creó commit ni ref y no hubo reintento.

La postlectura del árbol discrepante mostró exactamente las seis rutas, cero
workflows y los blobs esperados. La base y ese árbol conservan cero entradas
ejecutables, por lo que esa hipótesis no explica la divergencia. El árbol
contractual no existe en el object database compartido y no se lo sustituye por
inferencia. El índice temporal fue eliminado; `HEAD`, refs, índice y worktree
compartidos quedaron preservados. Se requiere auditar el método ZIP/reindexado
antes de corregir cualquier identidad.

## Auditoría y corrección del árbol

Dos repositorios temporales independientes reprodujeron ambos métodos. La única
diferencia entre sus bases y candidatos fue
`.github/workflows/main_nia-v365-next-api.yml`, fuera del payload. El blob base
es `8861d91a27250cfef93d606bfd8a4414a5fb024c`; ZIP más `git add -A` lo convirtió
en `bd5718ad98b7125c1013fc9cf0016a91bae84966`.

La causa exacta es normalización involuntaria: el workflow base tiene finales
mixtos, 80 LF de los cuales 63 son CRLF, y el Git del host declara
`core.autocrlf=true`. Reindexar el archivo completo alteró esa ruta ajena. El
método válido usa `read-tree` sobre la base y actualiza sólo los seis paths, por
lo que preserva el blob del workflow y produce `765126e3…`.

Un clon local nuevo con checkout de la base y únicamente las seis rutas
revalidó el árbol corregido, seis rutas, cero workflows, focales 12/12 y suite
1697/1697. El temporal fue eliminado y el estado compartido quedó idéntico. No
se creó commit, ref o red. El antiguo `ca584b0c…` queda sólo como evidencia del
método ZIP inválido y no puede usarse como candidato.

## Commit candidato local

Una autorización posterior revalidó base y seis huellas, construyó un índice
temporal con `read-tree` y creó exactamente un commit mediante `commit-tree`:

- commit: `d037031bba10d5dc21f81c5f7ec9aa647c07884e`;
- padre único: `d5b2325a7025fb00b9d5dde0f20e45ab8217f43b`;
- árbol: `765126e381380e2a5525669a6cafb93391eaf957`;
- asunto: `feat(bitrix): add protected R1 host probe`;
- alcance: seis rutas y cero workflows.

La postlectura confirmó cero refs apuntando al commit. El índice temporal fue
eliminado y `HEAD`, refs, índice y worktree compartidos quedaron idénticos. No
hubo hooks, firma, red, publicación, PR, Action o despliegue.
