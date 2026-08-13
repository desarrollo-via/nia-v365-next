## Alcance

Añade el preflight dormido para preparar R1 sobre Linux sin activar el conector.
El corte contiene 17 rutas: `requirements.txt`, ocho módulos R1 y ocho pruebas,
con cero cambios bajo `.github/workflows/`.

## Identidad y evidencia

- Base: `main@41ab2d5435cadf22db60574166d7eb29dd1dd57e`.
- Cabeza: `codex/r1-keyvault-dormant-v0551` en
  `e6af8b390f401dd3f2934faf2ced3ed70002e7bf`.
- Árbol: `7214bbb08ded045d59b6eb7ea0710b6fc68c18f8`.
- Manifiesto canónico: 17 rutas, 114575 bytes, SHA-256
  `AC8B7F74EAF961E3393BE258404B94728609B34B9B4FCE25C036BACCAFE33151`.
- Extracción aislada: activación 48/48, Key Vault 21/21 y suite 1685/1685.
- Ref publicada con postlectura Git/REST exacta y cero Actions.

## Contenido funcional

- Fija `azure-identity==1.25.3`, `azure-keyvault-secrets==4.11.0` y
  `aiohttp==3.14.3`; el SDK sólo se importa tras un permiso futuro.
- Añade lectura exacta y no enumerante de `NIA_BITRIX_KEY_VAULT_URL`.
- Añade backend one-shot para el secreto físico
  `nia-next-bitrix-r1-protected-settings-v1`, sin listados ni escritura.
- Conserva evidencia saneada, presupuestos cerrados, owner compuesto y cierre
  previo a devolver evidencia.

## Límites

El PR debe permanecer borrador. No configura identidad administrada, RBAC,
Key Vault, App Settings o secretos; tampoco activa R1, modifica Bitrix, bots,
participantes o chats, ni envía mensajes. No autoriza ready, merge, Actions
manuales o despliegue.

Si la postlectura no confirma identidad, cuerpo, alcance y ausencia de efectos,
se cierra únicamente el PR nuevo cuando siga `OPEN/DRAFT`, no fusionado y con
base/cabeza exactas. La ref publicada no se mueve ni elimina.
