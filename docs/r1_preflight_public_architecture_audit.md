# Auditoría pública de arquitectura del preflight R1

Estado: `KEYVAULT-BACKEND-DORMANT-READY-EXTERNAL-BLOCKED`.

Esta auditoría usa documentación oficial pública y contratos locales. No
consulta Azure, Credential Manager, Key Vault, OAuth o Bitrix reales y no
autoriza despliegue, configuración, secretos, participantes ni activación.

## Hallazgos oficiales

1. App Service para Python usa Linux; la documentación actual indica que Python
   sobre Windows ya no está soportado salvo contenedor Windows propio. El estado
   local documentado de `nia-v365-next-api` coincide: Linux, Python 3.12 y
   Gunicorn.
2. `CredReadW` pertenece a Win32, exige `Advapi32.dll`, un token con sesión de
   logon y declara `Target Platform: Windows`. El builder desplegado basado en
   Windows Credential Manager no puede ser la fuente productiva del Web App
   Linux.
3. App Service inyecta los App Settings como variables de entorno. El proceso
   Python puede consultar una clave por nombre exacto. En cambio, la API de
   administración `List Application Settings` devuelve un `StringDictionary`
   del conjunto de settings; no ofrece lectura administrativa de una sola clave.
4. Key Vault y la identidad administrada de App Service permiten obtener un
   secreto exacto mediante `SecretClient.get_secret(name)` sin enumerar el
   vault. Un nombre físico compatible propuesto es
   `nia-next-bitrix-r1-protected-settings-v1`; el identificador lógico local
   continúa siendo `nia-next/bitrix-r1/protected-settings/v1`.
5. Bitrix documenta `im.dialog.users.list` para un usuario con acceso al chat,
   acepta OAuth y `DIALOG_ID=chatXXX`, y permite hasta 200 participantes por
   página. Chat Test puede verificarse con una solicitud exacta y fail-closed;
   una respuesta paginada o ambigua no autoriza continuar.

Fuentes oficiales:

- https://learn.microsoft.com/en-us/azure/app-service/configure-language-python
- https://learn.microsoft.com/en-us/azure/app-service/configure-common
- https://learn.microsoft.com/en-us/rest/api/appservice/web-apps/list-application-settings
- https://learn.microsoft.com/en-us/windows/win32/api/wincred/nf-wincred-credreadw
- https://learn.microsoft.com/en-us/azure/key-vault/secrets/quick-create-python
- https://learn.microsoft.com/en-us/azure/app-service/overview-managed-identity
- https://apidocs.bitrix24.com/api-reference/chats/chat-users/im-dialog-users-list.html

## Decisión recomendada

### Switches no secretos

Añadir un lector host-side inyectable que reciba exclusivamente los tres nombres
congelados, conserve presencia/ausencia y acepte sólo los valores basales
esperados. Devuelve `SanitizedSwitchBaseline`; nunca enumera el entorno. Debe
vivir detrás de autenticación del revisor y no montarse con R1 apagado.

La administración futura puede usar `set`/`delete` sólo sobre esos nombres y
con salida suprimida, pero requiere autorización independiente porque cualquier
cambio de App Settings reinicia la aplicación.

### Fuente protegida Linux

Reemplazar el backend Windows únicamente para el binding productivo Linux por
un backend Key Vault one-shot: identidad administrada, un `get_secret` al nombre
físico exacto, cero listado, refresh, retry, escritura o salida privada. El blob
mantiene las siete claves allowlisted y se borra de memoria al cerrar. La
migración/provisión del secreto, identidad y RBAC es una fase separada aún no
autorizada.

### Ownership OAuth y participantes

Sustituir las operaciones protegida y participantes independientes por un owner
compuesto: abre la fuente una vez, carga OAuth almacenado una vez, obtiene token
una vez sin refresh, ejecuta una sola lectura exacta de participantes, produce
ambas evidencias saneadas y cierra token, HTTP, OAuth y fuente en un único
`finally`. El colector recibe las dos evidencias después del cierre verificado;
nunca recibe el recurso privado.

## Alternativas descartadas

- Ejecutar el preflight local en Windows: no demuestra que el Web App Linux
  pueda abrir la fuente durante la sesión productiva.
- Usar `az webapp config appsettings list`: abre el diccionario completo y rompe
  la allowlist de tres nombres.
- Leer OAuth dos veces: rompe el presupuesto `1/0/0` y duplica superficie.
- Transferir token u OAuth al colector: mezcla evidencia pública con ownership
  privado y dificulta garantizar el cierre.
- Activar R1 para descubrir compatibilidad por fallo: contradice el fail-closed.

## Puertas restantes

1. Aprobar la arquitectura objetivo sin autorizar todavía Azure.
2. Implementar y probar herméticamente el lector exacto y el owner compuesto.
3. Preparar contrato independiente para Key Vault, identidad, RBAC, migración y
   rollback; cualquier creación o configuración exige autorización específica.
4. Publicar/desplegar dormido y sólo entonces ejecutar un preflight real
   one-shot autorizado. Activación R1 continúa siendo una fase posterior.

## Implementación hermética aprobada

El lector `r1_pre_event_activation_exact_switch_reader.py` hace únicamente tres
lookups exactos sobre un mapping inyectado, conserva presencia/ausencia y nunca
enumera. El owner `r1_pre_event_activation_compound_owner.py` mantiene la sesión
privada hasta completar una lectura de participantes, cierra en `finally` y sólo
después entrega dos evidencias saneadas mediante probes compatibles con el
colector. El esquema exige ahora `azure-key-vault-exact-secret` y ya no afirma
compatibilidad con Windows Credential Manager. El conjunto R1 aprobó 48/48.

El backend portable `r1_key_vault_exact_secret_backend.py` implementa un único
`get_secret` al nombre físico exacto, decodifica un blob ordenado de siete claves
en buffers mutables y no expone listado, escritura o CLI. Su binding carga Azure
SDK sólo después de un permiso futuro; construirlo no requiere que la dependencia
esté instalada. Aprobó 12/12 y la regresión completa 1716/1716.

El gate permanece `NO-GO` por `azure_sdk_dependencies_missing` y
`managed_identity_configuration_unverified`. No se instaló Azure SDK ni se creó,
consultó o configuró identidad, RBAC, vault, secreto, despliegue o ejecución.
