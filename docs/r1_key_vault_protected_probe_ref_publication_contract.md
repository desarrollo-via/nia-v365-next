# Contrato de publicación de ref para sonda protegida R1 Key Vault

Estado: `FAILED-RESTORED-ATTEMPT-CONSUMED`.

Este contrato no autoriza crear refs locales o remotas, usar red, hacer push,
abrir PR, ejecutar Actions, fusionar, desplegar, iniciar servicios, leer el
entorno real, acceder a Azure o Bitrix ni enviar mensajes.

## Identidad congelada

- Repositorio remoto esperado: `desarrollo-via/nia-v365-next`, vía `origin`.
- Base remota obligatoria: `main=d5b2325a7025fb00b9d5dde0f20e45ab8217f43b`.
- Ref nueva exclusiva:
  `refs/heads/codex/r1-keyvault-protected-probe-v0576`.
- Commit: `d037031bba10d5dc21f81c5f7ec9aa647c07884e`.
- Padre único: `d5b2325a7025fb00b9d5dde0f20e45ab8217f43b`.
- Árbol: `765126e381380e2a5525669a6cafb93391eaf957`.
- Asunto: `feat(bitrix): add protected R1 host probe`.
- Alcance: seis rutas, 30932 bytes, cero workflows.
- Huella del manifiesto:
  `FBA332D8A981BCA5419EC651B9BF815B5C81F618C9260F09598330F06D8DF7EE`.

La reauditoría local aprobó 8/8: objeto, padre, árbol, asunto, alcance, cero
workflows, cero refs apuntando al commit y ausencia de la ref local congelada.
La publicación futura debe usar el SHA explícito; no necesita crear una ref
local ni consultar el worktree para construir contenido.

## Preflight público futuro

Una autorización separada de red deberá terminar íntegramente en `GO` y
detenerse sin publicar:

1. revalidar las ocho condiciones locales y el manifiesto;
2. confirmar por Git directo y REST público que la ref remota está ausente;
3. confirmar `main` exactamente en la base y que REST compare responda 404
   mientras el commit siga exclusivamente local; padre/árbol/diff locales
   prueban un commit, seis rutas y cero workflows;
4. confirmar cero PR y cero Actions asociados al SHA o nombre de ref;
5. confirmar workflows esperados, última ejecución productiva exitosa sobre
   `main` y dos lecturas de salud
   `ok/v0.267/off/off/locked/no-external/inert`;
6. fotografiar `HEAD`, refs, índice y worktree locales, y repetir la ausencia
   pública de la ref inmediatamente antes de una eventual publicación.

Cualquier SHA, base, workflow, Action, salud, identidad o transporte ambiguo
termina `NO-GO` sin reintento. No se consultan credenciales, secretos, App
Settings, Azure o Bitrix.

## Única operación futura posible

Sólo otra autorización específica, posterior al preflight fresco, podrá
ejecutar una vez:

```text
git push --porcelain --force-with-lease=refs/heads/codex/r1-keyvault-protected-probe-v0576: origin d037031bba10d5dc21f81c5f7ec9aa647c07884e:refs/heads/codex/r1-keyvault-protected-probe-v0576
```

La lease vacía exige ausencia remota. Rechazo, timeout o respuesta ambigua
consume la tentativa y prohíbe repetir el push.

## Postlectura y rollback

Git directo y REST público deben converger en el SHA exacto con la política
acotada de `candidate_ref_postread_policy.py`: observaciones máximas en segundos
0, 2, 5, 10, 20 y 30, sin repetir la mutación. Después se confirman base,
comparación, alcance, cero PR/Actions, workflows, salud y estado local intactos.
Sólo entonces el resultado es `REF-PUBLISHED`; no autoriza PR.

Si la ref exacta fue creada pero falla la postlectura, el rollback puede borrar
exclusivamente esa ref después de comprobar que continúa en el SHA candidato y
que `main` sigue en la base:

```text
git push --porcelain --force-with-lease=refs/heads/codex/r1-keyvault-protected-probe-v0576:d037031bba10d5dc21f81c5f7ec9aa647c07884e origin :refs/heads/codex/r1-keyvault-protected-probe-v0576
```

Debe terminar con ref ausente en ambos transportes, `main`, salud y estado local
intactos. Si la ref o base cambió, no se fuerza ni se compensa. Todo remanente
queda visible y requiere intervención humana.

## Preflight público del 2026-08-11

La auditoría pública y no autenticada terminó `PASS` sin escrituras:

- REST y Git directo: `main=d5b2325a…`;
- ref candidata: REST 404 y Git directo ausente;
- comparación REST: 404, coherente con el commit aún no alcanzable remotamente;
- PR asociados: 0; Actions por SHA y rama: 0;
- tres workflows esperados activos;
- última ejecución de `main`: `31449006990`, `completed/success`, SHA exacto;
- salud 2/2: NIA `200/ok` y conector
  `200/v0.267/off/off/locked/no-external/inert`.

La exigencia anterior de comparación pública `ahead=1` antes de publicar era
imposible para un commit exclusivamente local y quedó corregida. Después de la
publicación sí se exige comparación pública `ahead=1`, `behind=0`, un commit,
seis rutas y cero workflows. La ref no fue creada y el preflight debe repetir
su ausencia inmediatamente antes de cualquier push autorizado.

## Tentativa única y rollback del 2026-08-11

El primer evaluador compacto produjo un falso `immediate_preflight_no_go`; la
lectura diagnóstica probó las cinco condiciones exactas y `PUSH_ATTEMPTS=0`.
Después, un evaluador con comprobaciones nominadas confirmó nuevamente la
ausencia y ejecutó la primera y única tentativa de push.

Git directo confirmó la ref en
`d037031bba10d5dc21f81c5f7ec9aa647c07884e`, `main` intacto, y REST convergió.
La comparación aprobó `ahead=1`, `behind=0`, un commit, seis rutas y cero
workflows; PR/Actions permanecieron en cero, workflows/run estables y salud
2/2. La comprobación local posterior usó `for-each-ref --points-at` sin
distinguir refs propias de refs de seguimiento creadas por el push, informó
`local_ref_created` y activó el rollback contractual.

El borrado único con lease restauró la ausencia. Git directo la confirmó de
inmediato; REST convergió después a 404. `main`, `HEAD`, índice y worktree
quedaron intactos y cero refs locales apuntan al commit. Resultado:
`FAILED-RESTORED`, un push, un rollback y cero reintentos. La autorización fue
consumida; este contrato no puede reutilizarse.

Antes de una nueva propuesta debe existir un evaluador hermético que distinga
ref local propia de ref remota de seguimiento exacta, permita sólo la creada
por esta publicación y pruebe su estado tras éxito y rollback. Toda publicación
futura requiere contrato y autorización nuevos.

La corrección local posterior quedó en
`bitrix_connector/r1_protected_probe_local_ref_policy.py`: 9/9 pruebas nuevas y
22/22 con regresión. El contrato sucesor es
`docs/r1_key_vault_protected_probe_ref_publication_v2_contract.md`, usa una ref
nueva y todavía no autoriza red. Tras alinear las expectativas documentales
Azure, aprobaron 31/31 pruebas focales y la suite completa 1781/1781; este
contrato v1 permanece consumido.
