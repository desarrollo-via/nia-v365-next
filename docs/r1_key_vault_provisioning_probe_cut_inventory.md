# Inventario del corte de sonda de preflight de provisión R1

Estado: `MERGED-DEPLOYED-STABLE-NOT-INVOKED`.

Este inventario no autoriza GitHub, Actions, despliegue, invocación de la
sonda, secretos, Azure, activación, Bitrix ni mensajes.

## Identidad Git exacta

- Candidato local sin rama: `1b4c2be1ce68e889a19dd9c92c91a51c857ab0c4`.
- Padre desplegado: `2631f8483ca5e565b4ca53874e32f4d6035c09f8`.
- Árbol candidato: `9e743a9bdde1ac5c1bb8786000c50e94ff9ac597`.
- Árbol padre: `765126e381380e2a5525669a6cafb93391eaf957`.
- Mensaje: `Add protected R1 provisioning preflight`.
- Rutas: 3; workflows: 0.

## Rutas y huellas

1. `bitrix_connector/review_router.py`: 11525 bytes; SHA-256
   `56AF66610611D670C6FC3BF520715EE2898555F95C8A06D55419452A583404C4`;
   blob Git `1fe545b0e33c9a23cb5682e9ffbf66ff0aaa6b0d`.
2. `bitrix_connector/router.py`: 4369 bytes; SHA-256
   `E13437937C4132B60FADFB839106860C3404BD7FA42F19BD1578F6BF29090BB1`;
   blob Git `54513e13fbcb3d00d576072fa51ecf8a393a0ef5`.
3. `tests/test_r1_key_vault_provisioning_preflight_route.py`: 4194 bytes;
   SHA-256
   `A4AB54772CD29D214E333D99484B97C5757B2CDF78E0196C022E17507A317933`;
   blob Git `83ad70ae0d0fd1eac2ef65e0813bc6559640f8a3`.

El delta sobre el padre contiene 28 inserciones productivas y una prueba nueva;
no modifica dependencias, workflows, configuración, secretos ni defaults.

## Validación aislada

- Extracción literal del padre y superposición exclusiva de las tres rutas.
- Resultado: `1702/1702` pruebas herméticas, cero fallos, errores o skips.
- La extracción y el ZIP temporales fueron eliminados; el índice temporal del
  commit también fue retirado.
- La rama activa, el índice ordinario y los demás cambios locales no fueron
  modificados.

## Propiedad funcional

La ruta nueva
`/bitrix-connector/review/r1-key-vault-provisioning-preflight` reutiliza el
esquema saneado y la autenticación Bearer existentes, pero posee un owner
one-shot distinto de `/r1-key-vault-host-probe`. Una llamada a la ruta nueva no
repite ni rearma la sonda histórica consumida. R1 sigue apagado.

## Evidencia remota del 2026-08-11

La rama exacta se publicó una vez; PR `#16` quedó fusionado en
`641331c63253536ea2531f091b933af4380c95b3`, con padres base/candidato y este
árbol exacto. Action automática `31518711951` terminó `completed/success` y la
salud posterior aprobó 2/2 bajo `off/locked/no-external/inert`. La sonda nueva
no fue invocada y rollback no fue necesario.
