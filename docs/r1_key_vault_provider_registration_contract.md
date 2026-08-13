# Contrato R1 — registro de proveedor Microsoft.KeyVault

Estado: preparado e inerte. Este documento no autoriza Azure.

## Evidencia causal

La lectura histórica exacta del intento de creación del vault devolvió
`MissingSubscriptionRegistration`. El reporte sanitario conserva una lectura,
cero mutaciones, cero secretos, cero reintentos y estado local preservado.

## Objeto exacto

- Suscripción: `0c4b9ea3-f35d-4a11-bfe7-794d40cf1ec9`.
- Namespace: `Microsoft.KeyVault`.
- No incluye otros proveedores, recursos, regiones, secretos, App Settings,
  identidades, RBAC, Bitrix, bots ni mensajes.

## Preflight separado

Una autorización `sp` ligada a este contrato permite una sola ejecución de
`az provider show` para el namespace y la suscripción exactos, consultando sólo
`registrationState`. Presupuesto: una lectura, cero mutaciones y cero
reintentos. `Registered` y `NotRegistered` son evidencia terminal;
`Registering`, `Unregistering`, autenticación, autorización o evidencia inválida
terminan `NO-GO`.

## Mutación protegida

Sólo después de un preflight fresco `NotRegistered`, la siguiente frase literal
autoriza la ejecución inmediata:

```text
REGISTRAR MICROSOFT.KEYVAULT SUSCRIPCION 0C4B9EA3-F35D-4A11-BFE7-794D40CF1EC9 R1-KV-PROVIDER-2026-08-12-V1 EJECUCION INMEDIATA
```

La envolvente hace una prelectura defensiva. Si ya está `Registered`, termina
sin mutación. Si continúa `NotRegistered`, ejecuta una sola llamada exacta a
`az provider register --wait`, con máximo 600 segundos, y una postlectura
exacta. No hay reintento.

## Éxito, detención y recuperación

- Éxito: postlectura exacta `Registered`.
- Detención: estado transitorio, deriva, fallo de autenticación/autorización,
  timeout, salida inválida o postlectura distinta de `Registered`.
- La inscripción es una mutación aditiva de alcance suscripción. No crea el
  vault ni habilita la provisión por sí sola.
- `unregister` está prohibido como rollback automático: podría afectar recursos
  ajenos. Ante resultado ambiguo se conserva el estado visible y se exige una
  comprobación de solo lectura posterior específicamente autorizada.
- La frase vence al cambiar fecha de Bogotá, suscripción, namespace, comandos,
  presupuesto, riesgo o criterio de recuperación.
