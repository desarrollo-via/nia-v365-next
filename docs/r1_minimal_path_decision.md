# Decisión de ruta mínima hacia el tercer mensaje R1

Estado: `CANDIDATE-PRE-EVENT-PREFERRED`; sólo análisis, sin autorización
operativa.

## Evidencia oficial

- [`imopenlines.crm.chat.user.add`](https://apidocs.bitrix24.com/api-reference/imopenlines/openlines/chats/imopenlines-crm-chat-user-add.html)
  acepta como `USER_ID` un usuario o bot y permite fijar `CHAT_ID`; exige scope
  `imopenlines` y acceso del actor al objeto CRM.
- [`imopenlines.crm.chat.user.delete`](https://apidocs.bitrix24.com/api-reference/imopenlines/openlines/chats/imopenlines-crm-chat-user-delete.html)
  ofrece la operación inversa sobre el mismo objeto y chat.
- [`im.chat.user.list`](https://apidocs.bitrix24.com/api-reference/chats/chat-users/im-chat-user-list.html)
  devuelve los participantes, pero sólo puede ejecutarlo un participante del
  chat.
- El evento [`ONIMBOTV2MESSAGEADD`](https://apidocs.bitrix24.com/api-reference/chat-bots/chat-bots-v2/imbot.v2/events/events.html)
  se entrega cuando el usuario escribe en un chat del que el bot forma parte.
- `imbot.v2.Chat.User.add` permite que un bot administrador agregue usuarios;
  no demuestra que un bot ajeno pueda incorporarse a sí mismo a Chat Test.

## Comparación

### Incorporación directa externa

Evita PR y despliegue, pero necesita un ejecutor nuevo con OAuth protegido,
acceso CRM y participación suficiente para leer el baseline. También separa la
mutación, sesión y restauración entre procesos distintos. No existe evidencia
oficial revisada de una acción UI equivalente para incorporar Bot Next.

### Candidato pre-evento

Usa los mismos métodos oficiales y ya fija Bot Next `373259`, Chat Test
`78733/chat78733` y negocio `614949`. Lee el baseline, exige Bot NIA ausente,
agrega una sola vez, verifica exactamente `baseline + Bot Next`, autoriza un
solo mensaje, limita el lease a 600 segundos y restaura la huella inicial al
terminar, expirar o cerrar. El OAuth sólo se abre dentro del runtime protegido.

## Decisión y ruta crítica

Se prefiere desplegar el candidato pre-evento. La ruta directa no se descarta,
pero hoy crea más superficie operativa de la que elimina.

1. Sustituir las auditorías PowerShell ad hoc por un auditor Python persistido
   que consuma JSON sin coerciones de colección.
2. Auditar una vez la ref y el PR cerrado; detenerse ante deriva.
3. Con autorización separada, reutilizar el PR `#13` si sigue exacto y GitHub
   permite reabrirlo; crear otro sólo si esa opción no es segura.
4. Validar, fusionar y desplegar en fases separadas.
5. Ejecutar el preflight protegido. Sólo con acceso, baseline y rollback exactos
   abrir una sesión R1 y pedir el tercer mensaje humano.

Permanecen sin demostrar el scope/acceso del actor OAuth y su capacidad para
leer Chat Test. El preflight debe terminar `NO-GO` antes de mutar si cualquiera
falla. Este documento no autoriza red adicional, Bitrix, OAuth, participantes,
PR, fusión, despliegue, sesión o mensaje.
