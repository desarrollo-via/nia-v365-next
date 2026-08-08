# Runbook P1-B protegido — diseño no ejecutable

Fecha de evidencia: 27 de julio de 2026.

Este documento prepara P1-B, pero no autoriza abrir `.env`, mostrar secretos,
modificar Azure, consultar Bitrix, habilitar R0 ni enviar mensajes.

## Objetivo y alcance exacto

P1-B agregará en una única operación únicamente estos cuatro App Settings de
`nia-v365-next-api`:

- `NIA_BITRIX_DOMAIN`;
- `NIA_BITRIX_MEMBER_ID`;
- `NIA_BITRIX_APPLICATION_TOKEN`;
- `NIA_BITRIX_REVIEW_TOKEN`.

P1-A debe permanecer intacto y
`NIA_BITRIX_R0_BRIDGE_ENABLED` debe continuar exactamente en `false`.

## Estado previo comprobado

- Una consulta Azure proyectada solo a los nombres P1-B devolvió `[]`.
- El health público publica en `false` los cuatro indicadores de presencia.
- El conector continúa en `off/locked/no-external`, runtime inerte y sin rutas
  R0.
- No se solicitaron valores, no se abrió `.env` y no se consultó Bitrix.

## Carga protegida propuesta

La carga se realizará manualmente en Azure Portal para evitar secretos en el
chat, comandos, historial de terminal, documentos, Agenda o salida de Codex.

1. Abrir la Web App `nia-v365-next-api` y su sección de variables de entorno.
2. La persona autorizada obtiene localmente los tres valores de identidad desde
   su fuente protegida, sin pegarlos en el chat ni compartir capturas.
3. La persona genera y conserva en su gestor seguro un token de revisión nuevo,
   exclusivo y aleatorio. Debe tener al menos 24 caracteres; se recomiendan
   256 bits de entropía y formato URL-safe.
4. Agregar los cuatro nombres anteriores y sus valores directamente en el
   formulario de Azure. No modificar ningún otro nombre.
5. Antes de guardar, comprobar visualmente que el puente R0 sigue en `false`,
   que el modo sigue `off` y que la lista contiene exactamente cuatro altas.
6. El guardado y reinicio requieren una autorización específica posterior. No
   deben ejecutarse como parte de este diseño.

La intervención humana en los pasos 2 a 5 es de atención especial. Codex no
debe observar, transcribir, validar ni repetir los valores.

## Verificación posterior prevista

Después de un guardado autorizado y de la sustitución de la instancia:

1. consultar por Azure únicamente los cuatro nombres, nunca sus valores;
2. exigir Web App `Running` y NIA HTTP 200;
3. exigir que el health muestre los cuatro indicadores de presencia en `true`;
4. exigir `requested_mode=off`, `effective_mode=off`,
   `activation_locked=true`, `external_calls_enabled=false`, runtime inerte,
   piloto apagado y parada de emergencia activa;
5. exigir 18 rutas totales, 14 Bitrix, cero R0 y `404` en la ruta interna;
6. detenerse sin habilitar R0, consultar Bitrix o pedir el primer mensaje.

Los valores nunca se verifican imprimiéndolos. La aceptación usa solamente
nombres, booleanos seguros y estado operativo público.

## Rollback exacto

Si la Web App no recupera la línea base dentro de la ventana aprobada, eliminar
únicamente los cuatro nombres P1-B, guardar y esperar el segundo reinicio.
Después deben volver a aparecer los cuatro indicadores en `false`, mientras
P1-A permanece configurado y la línea base sigue 18/14/0.

El rollback no modifica Canales Abiertos, Línea 13, bots, Wazzup ni ninguna
estructura de Bitrix. Una desviación respecto de estos cuatro nombres detiene
la operación y exige una nueva autorización.

## Sustitución correctiva de `NIA_BITRIX_REVIEW_TOKEN` después de P2

P2 sobre `v0.111` confirmó públicamente
`r0_bridge_review_auth_missing` sin retirar el conector. Esta evidencia demuestra
que la autenticación de revisión no es válida para montar R0, pero no identifica
ni autoriza leer el valor responsable. La sustitución se limita a un solo App
Setting y mantiene `NIA_BITRIX_R0_BRIDGE_ENABLED=false` en todo momento.

### Requisitos del nuevo token

- Debe ser exclusivo para revisión R0; no se reutiliza el application token,
  OAuth access token, refresh token, client secret ni otra credencial.
- El código exige al menos 24 caracteres después de retirar espacios exteriores.
- Se recomiendan 256 bits aleatorios, codificación URL-safe sin espacios,
  comillas, saltos de línea ni caracteres de control. Un gestor de secretos
  confiable puede generarlo y conservarlo fuera del chat.
- Codex no lo genera, lee, recibe, copia, valida, cuenta, transcribe ni ve en una
  captura. La persona comprueba localmente estos requisitos sin comunicar el
  valor ni una parte del valor.

### Precondiciones obligatorias

1. Web App `nia-v365-next-api` en `Running`, NIA `ok`, conector `v0.111`,
   barreras `off/locked/no-external`, runtime inerte y línea base `18/14/0`.
2. `r0_bridge` público en `requested=false`, `mounted=false`,
   `status=disabled`, `reason=r0_bridge_disabled`.
3. La persona conserva en un gestor seguro el valor anterior exacto como
   rollback. Si no puede recuperarlo sin compartirlo, la operación no comienza.
4. El nuevo token ya está generado y guardado por la persona en el gestor
   seguro. No se pega primero en notas, terminal, chat, Agenda o documentos.
5. No hay ninguna otra edición pendiente en Variables de entorno de Azure.

### Preparación manual, sin Aplicar

1. Abrir la Web App exacta `nia-v365-next-api` y Variables de entorno.
2. Localizar únicamente `NIA_BITRIX_REVIEW_TOKEN`.
3. Reemplazar su valor directamente desde el gestor seguro, sin comillas simples
   o dobles; las comillas formarían parte de la credencial.
4. No modificar `NIA_BITRIX_R0_BRIDGE_ENABLED`; debe seguir en `false`.
5. No agregar, eliminar o editar ningún otro App Setting.
6. Detenerse antes de pulsar Aplicar. La preparación no autoriza guardar ni
   reiniciar la Web App productiva.

### Aplicación y verificación separadas

Aplicar requiere una autorización textual posterior que mencione el reinicio
productivo y el rollback literal. Tras Aplicar:

1. esperar la sustitución real de la instancia; una primera lectura con el
   proceso anterior no determina éxito o fallo;
2. exigir Web App `Running`, NIA `ok` y conector `v0.111`;
3. exigir `requested_mode=off`, `effective_mode=off`, bloqueo activo, llamadas
   externas deshabilitadas, runtime inerte y sin recursos, piloto apagado y
   parada activa;
4. exigir `review_token=true`, `r0_bridge_disabled`, `18/14/0`, ambas rutas NIA
   y ruta interna R0 en `404` durante dos lecturas separadas por diez segundos;
5. detenerse sin habilitar R0. El booleano público confirma presencia, no
   longitud ni entropía; la validez funcional solo se comprobará en otro P2 con
   autorización independiente.

### Rollback exacto de la sustitución

Si la instancia convergente no recupera cualquiera de las invariantes
anteriores, la persona restaura exclusivamente el valor anterior de
`NIA_BITRIX_REVIEW_TOKEN` desde su gestor seguro y vuelve a pulsar Aplicar. No
se muestra el valor ni se toca otro ajuste. Después se exigen dos lecturas
restauradas en `v0.111 · 18/14/0`, con R0 deshabilitado y todas las barreras
intactas.

Solo después de verificar la sustitución se retira el valor anterior del gestor
seguro. No se modifica Bitrix, no se inicia el worker y no se pide ni envía el
primer mensaje controlado.
