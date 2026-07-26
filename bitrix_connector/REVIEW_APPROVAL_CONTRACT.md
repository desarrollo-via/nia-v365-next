# Contrato objetivo de aprobación humana del Review Lab

Estado: **diseño de solo lectura**. Este documento no habilita botones, no
activa el runtime y no autoriza conexiones con NIA o Bitrix.

## Resultado buscado

Una aprobación debe demostrar de forma auditable quién decidió, qué artefacto
exacto vio, qué efecto autorizó y si la misma operación ya había sido aplicada.
Una aprobación de entrada solo habilita la cola hacia NIA. Una aprobación de
salida solo habilita la cola hacia Bitrix; nunca realiza la llamada HTTP dentro
de la petición del panel.

## Base existente confirmada

Ya existen cuatro rutas bajo `/bitrix-connector/review`:

| Etapa | Decisión | Ruta actual | Transición atómica |
| --- | --- | --- | --- |
| Entrada | Aprobar | `POST /{event_key}/approve-input` | `needs_input_review → ready_for_nia` |
| Entrada | Rechazar | `POST /{event_key}/reject-input` | `needs_input_review → input_rejected` |
| Salida | Aprobar | `POST /{event_key}/approve-output` | `needs_output_review → ready_for_bitrix` |
| Salida | Rechazar | `POST /{event_key}/reject-output` | `needs_output_review → output_rejected` |

El almacén ya compara estado, hash y ausencia de decisión en una única
actualización. También distingue repetición idéntica, hash obsoleto, artefacto
bloqueado, decisión previa y evento no revisable.

La superficie todavía **no está lista para conectarse a la UI**:

- usa un único Bearer administrativo;
- acepta `actor` enviado por el cliente, por lo que no prueba la identidad real;
- considera idempotente una repetición solo si coinciden decisión, hash, actor y
  motivo, sin una clave propia de operación;
- el Review Lab es un archivo local y no debe almacenar el Bearer ni llamar las
  rutas actuales;
- con la configuración real `off`, el runtime no construye el almacén y las
  rutas fallan cerradas con `connector_runtime_not_ready`.

## Principal autenticado

Antes de validar el cuerpo, un `ReviewAuthenticator` inyectable debe convertir
la credencial en un principal calculado por el servidor:

```text
ReviewPrincipal
  actor: identificador humano allowlisted
  credential_id: identificador no secreto de la credencial
  authenticated_at: fecha UTC
```

El cuerpo objetivo no admite `actor`. Para el primer piloto controlado puede
existir un adaptador de un solo operador que compare el Bearer en tiempo
constante y obtenga el actor de configuración separada. El token no se guarda en
HTML, `localStorage`, respuestas, logs ni documentos de auditoría.

Una credencial ausente o incorrecta se rechaza antes de validar el JSON y antes
de abrir el almacén. Una configuración incompleta devuelve `503` sin degradarse
a acceso anónimo.

## Solicitud objetivo

Se conservan las cuatro rutas para que el verbo de negocio siga siendo
explícito. Todas reciben el mismo contrato:

```json
{
  "content_hash": "64 caracteres hexadecimales",
  "decision_id": "UUID v4 generado una sola vez al confirmar",
  "expected_status": "needs_input_review o needs_output_review",
  "confirmation": "APROBAR ENVIO A NIA o APROBAR ENVIO A BITRIX",
  "reason": "motivo opcional al aprobar y obligatorio al rechazar"
}
```

Reglas:

1. `event_key` pertenece exclusivamente a la ruta y debe tener 64 caracteres
   hexadecimales.
2. `content_hash` debe ser el valor obtenido en el último GET de detalle.
3. `expected_status` debe corresponder a la etapa de la ruta.
4. `confirmation` debe coincidir literalmente con la acción. Su función es
   impedir clics accidentales; no sustituye la autenticación.
5. `decision_id` identifica una intención humana, no un intento HTTP.
6. `reason` se normaliza, tiene longitud limitada y nunca acepta secretos.
7. Campos adicionales son rechazados.

Para rechazos se usan `RECHAZAR ENTRADA` y `RECHAZAR SALIDA`. El panel debe
mostrar la frase y el efecto antes de permitir confirmarla.

## Alcance exacto de los hashes

- Entrada: `content_hash` es SHA-256 canónico de
  `{"kind":"nia_payload","payload":{...}}`. Liga la decisión al `session_id`
  y `mensaje` exactos que recibiría NIA.
- Salida: `content_hash` es SHA-256 canónico de
  `{"kind":"bitrix_message","payload":{...}}`. Liga la decisión al `botId`,
  `dialogId` y mensaje exactos que recibiría Bitrix.

El panel debe llamarlos respectivamente **Hash del payload NIA** y **Hash del
payload Bitrix**. No debe afirmar que esos hashes cubren todo el evento original
o toda la respuesta de NIA.

El servidor recalcula el hash desde el documento persistido y lo compara con el
solicitado dentro de la misma precondición atómica. Si el detalle cambió desde
que la persona lo abrió, responde `409 review_hash_mismatch`; nunca aplica la
decisión a la versión nueva.

## Idempotencia y concurrencia

El documento de decisión objetivo conserva:

```text
decision_id, stage, decision, content_hash, actor, credential_id,
reason, decided_at, request_id
```

- La primera aplicación de un `decision_id` devuelve `200`, `idempotent=false`.
- Una repetición con el mismo `decision_id` y contenido semántico idéntico
  devuelve la decisión original con `idempotent=true`.
- Reutilizar el mismo `decision_id` con otro evento, etapa, decisión, hash o
  motivo devuelve `409 review_idempotency_conflict`.
- Una decisión diferente sobre un artefacto ya decidido devuelve
  `409 review_already_decided`.
- La hora y el actor siempre proceden del servidor.

No se reabre una decisión mediante estas rutas. Corregir una decisión exige un
flujo administrativo futuro, separado y explícitamente auditado.

## Confirmación visual

El panel ejecuta dos pasos locales antes del POST:

1. Muestra nuevamente el artefacto exacto, su hash, evento, diálogo, etapa,
   identidad piloto y estado observado.
2. Abre una confirmación que nombra el efecto:
   - aprobar entrada: `Habilitar el worker para consultar NIA`;
   - aprobar salida: `Habilitar el worker para responder en Bitrix`;
   - rechazar: `Cerrar esta etapa sin envío`.

No existe una acción manual independiente llamada **Enviar a Bitrix**. Aprobar
la salida cambia a `ready_for_bitrix`; el worker separado reclama después el
evento y vuelve a comprobar modo, bloqueo de activación, llamadas externas,
identidad piloto, ventana y parada de emergencia justo antes del cliente.

Mientras `effective_mode=off`, `activation_locked=true` o
`external_calls_enabled=false`, todos los controles permanecen deshabilitados.
El panel debe refrescar el detalle después de cada respuesta y deshabilitar la
acción inmediatamente para evitar dobles clics.

## Respuestas seguras

| HTTP | Significado para la UI |
| --- | --- |
| `200` | aplicada o repetición idempotente; refrescar detalle |
| `401` | credencial ausente o inválida; no revelar cuál parte falló |
| `403` | principal autenticado sin permiso para esa etapa |
| `404` | clave inválida, inexistente o no visible para el principal |
| `409` | hash obsoleto, artefacto bloqueado, decisión previa o conflicto idempotente |
| `422` | contrato mal formado; no tocar el almacén |
| `503` | autenticación, runtime o almacén no configurados; permanecer inerte |

Las respuestas nunca incluyen Bearer, credenciales OAuth, `application_token`,
payload original sin redacción ni detalles internos de Mongo.

## Auditoría mínima

Cada intento autenticado genera una entrada propia, aun si termina en conflicto:

- `request_id`, `decision_id`, evento, etapa y acción;
- actor y `credential_id` no secreto;
- hash solicitado y resultado estable;
- fecha UTC del servidor;
- estado anterior y posterior cuando hubo aplicación;
- razón normalizada;
- jamás el token ni secretos del evento.

La auditoría no sustituye la transición atómica del documento del evento.

## Criterios antes de conectar botones

- Actor derivado del servidor y pruebas que demuestren que un `actor` enviado
  por el cliente se rechaza.
- Autenticación ejecutada antes de validar el cuerpo y antes de abrir recursos.
- Hash, estado, etapa y `decision_id` comprobados atómicamente.
- Repetición idéntica y conflicto idempotente cubiertos para las cuatro rutas.
- Motivo obligatorio en ambos rechazos.
- Cero llamadas a NIA o Bitrix dentro de las rutas de revisión.
- Revalidación piloto conservada en ambos workers.
- UI servida desde un origen administrativo controlado; ningún secreto embebido
  en el HTML o almacenamiento del navegador.
- Pruebas herméticas de clic doble, pestaña obsoleta, dos revisores simultáneos,
  parada de emergencia posterior a la aprobación y runtime real `off`.

Solo después de cumplir estos criterios podrá proponerse, mediante un SP nuevo,
conectar los controles. Producción, OAuth, bot, Canal Abierto, credenciales y
activación siguen fuera de alcance.
