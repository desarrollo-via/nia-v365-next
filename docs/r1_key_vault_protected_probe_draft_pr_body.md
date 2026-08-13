## Alcance

Añade una sonda host-side protegida y one-shot para cerrar únicamente la
evidencia pendiente de R1 Key Vault en Linux. El corte contiene seis rutas y
cero cambios bajo `.github/workflows/`.

## Identidad y evidencia

- Base: `main@d5b2325a7025fb00b9d5dde0f20e45ab8217f43b`.
- Cabeza: `codex/r1-keyvault-protected-probe-v0580` en
  `d037031bba10d5dc21f81c5f7ec9aa647c07884e`.
- Árbol: `765126e381380e2a5525669a6cafb93391eaf957`.
- Manifiesto: seis rutas, 30932 bytes y SHA-256
  `FBA332D8A981BCA5419EC651B9BF815B5C81F618C9260F09598330F06D8DF7EE`.
- Pruebas focales 31/31 y suite completa 1781/1781.
- Ref publicada con convergencia Git/REST, cero PR/Actions y `main` intacto.

## Contenido funcional

- Expone una ruta GET bajo el Bearer Review existente; no crea autenticación
  nueva ni permite llamadas arbitrarias.
- Comprueba exactamente las versiones runtime fijadas de los SDK y la presencia
  y forma de `NIA_BITRIX_KEY_VAULT_URL`, sin enumerar el entorno ni revelar el
  valor.
- Es perezosa, consumible una sola vez, sanea errores y permanece inaccesible
  sin autorización Review válida.

## Límites

El PR debe permanecer borrador. No invoca la sonda productiva, no lee App
Settings o secretos durante el despliegue, no crea identidad, RBAC o Key Vault,
no activa R1 y no modifica Bitrix, bots, participantes, chats o mensajes. No
autoriza ready, merge, Actions manuales ni despliegue.

Si la postlectura no confirma identidad, cuerpo, alcance y ausencia de efectos,
se cierra únicamente el PR nuevo cuando siga `OPEN/DRAFT`, no fusionado y con
base/cabeza exactas. La ref publicada no se mueve ni elimina.
