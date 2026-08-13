## Objetivo

Agregar una segunda sonda protegida, one-shot e independiente para obtener el
baseline fresco de `NIA_BITRIX_KEY_VAULT_URL` antes de la provisión R1, sin
enumerar App Settings ni reutilizar la sonda histórica consumida.

## Alcance

- tres rutas exactas;
- cero workflows y cero dependencias;
- misma autenticación Bearer y esquema saneado;
- owner distinto para la nueva ruta;
- R1 permanece apagado y el conector sigue inerte.

## Evidencia

- candidato `1b4c2be1ce68e889a19dd9c92c91a51c857ab0c4`;
- padre `2631f8483ca5e565b4ca53874e32f4d6035c09f8`;
- árbol `9e743a9bdde1ac5c1bb8786000c50e94ff9ac597`;
- extracción aislada `1702/1702`.

No invoca la ruta, abre secretos, consulta Azure o Bitrix, activa R1 ni envía
mensajes.
