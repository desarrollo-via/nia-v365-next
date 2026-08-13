# Contrato ejecutable EAOR R1

Identificador: `NIA-NEXT-R1-EAOR-2026-08-13-V1`.

Estado: runner compuesto, auditado e inerte; envolvente productiva todavía no
aceptada. Este documento, el launcher, el runner, el coordinador y su puerto no
autorizan ni ejecutan efectos externos por construcción.

## Resultado terminal

Demostrar `mensaje humano en Chat Test → Bot Next → respuesta al mismo chat` y
restaurar la sesión y la activación, con Bot NIA todavía retirado. Sólo esa
evidencia permite registrar 100%.

## Recursos y fuentes exactos

- Proyecto `nia-next`; suscripción, Web App, vault, roles y setting definidos
  por el manifiesto Key Vault de SHA-256
  `16EDAC107B1B8041952D8ED324C0542ECAADDB0AA7EC316C2B557F135864AA49`.
- Fuente protegida `nia-next/bitrix-r1/protected-settings/v1`; únicamente siete
  campos allowlisted. Nunca se muestran, enumeran ni persisten sus valores.
- Chat Test `78733`/`chat78733`; Bot Next `373259`; Bot NIA `245339` permanece
  ausente; evento `ONIMBOTV2MESSAGEADD`.

## Recorrido autónomo

Una aceptación `sp` ligada al SP que identifique este contrato permite al
coordinador suministrar internamente los literales congelados de los owners y
encadenar, sin nuevas pausas conversacionales:

1. preflight fresco y provisión Key Vault dormida;
2. preflight y activación exacta de los tres switches;
3. preflight de participantes, montaje temporal de Bot Next y armado de sesión;
4. monitoreo hasta `ATTENTION-REQUIRED`;
5. después del único mensaje humano, observación de evento, recibo y respuesta;
6. rollback de participantes, sesión y Fase A, más salud dormida final.

Los literales internos son gates técnicos y no autorizaciones nuevas. Una
deriva invalida la etapa antes de su efecto. El coordinador no envía mensajes.

## Presupuestos máximos

- Ocho ciclos diagnósticos; doce lecturas allowlisted y una pareja de salud por
  ciclo; tres intentos sólo para lecturas recuperables.
- Una apertura de fuente y siete lecturas protegidas durante provisión; una
  escritura del secreto exacto.
- Una mutación por superficie: vault, identidad, RBAC lector, RBAC escritor
  temporal, secreto, URL del vault, tres switches y participante Bot Next.
- Una postlectura y un rollback exacto por superficie; dos lecturas de salud
  final. Cero reintentos de mutación salvo autorización literal y prueba previa
  de ausencia de efecto.
- Monitoreo máximo 30 minutos, intervalos de 15–30 segundos y sesión/lease de
  máximo 600 segundos. Cero mensajes automatizados.

## Única participación humana prevista

La persona envía manualmente un único tercer mensaje sólo cuando coincidan
`ATTENTION-REQUIRED`, `pre_event_lease_state=AWAITING-EVENT` y
`human_message_required_now=true`. Login o MFA sólo se solicitan si la
plataforma invalida realmente la sesión autenticada; no son permisos nuevos.

## Éxito y detención

- Éxito: evento exacto, recibo auténtico, respuesta de Bot Next en Chat Test,
  participante restaurado, Fase A restaurada y salud
  `v0.267/off/locked/no-external/inert`.
- Detención: vencimiento, presupuesto agotado, deriva de cuenta/recurso/destino,
  secreto ausente, autorización de plataforma denegada, salida no saneable,
  rollback incierto, riesgo nuevo o revocación.
- Un `NO-GO` recuperable no cierra la EAOR mientras queden diagnóstico,
  postlecturas o recuperación seguros y presupuestados.
- Un resultado ambiguo consume la operación iniciada; nunca habilita repetir
  una mutación por inferencia.

## Ejecutabilidad actual

`bitrix_connector/r1_result_eaor_coordinator.py` materializa el recorrido y la
única pausa humana mediante puertos inyectados, sin binding externo. Provisión
posee owner y binding reales. Preflight de activación y sesión poseen bindings
dormidos. Fase A posee ahora binding Azure CLI exacto, verificador HTTP anónimo
sin secretos y adaptador explícito al coordinador. La composición está probada
con dobles herméticos y permanece inerte.

`bitrix_connector/r1_result_eaor_product_port.py` completa el puerto único:
adapta el owner real de provisión, el owner real de Fase A y el owner de sesión
R1; construye cada uno perezosamente sólo al comenzar su etapa. Suministra los
literales congelados internamente, monitorea la sesión cada 15–30 segundos hasta
un máximo de 600 segundos y exige rollback verificado de participante y Fase A.
El supervisor vive fuera de la Web App, porque la activación reinicia ese host,
y controla por las cuatro rutas HTTP autenticadas el owner realmente montado.
No construye otro owner local. El constructor superior no invoca ninguna
factory. La auditoría hermética cubre
éxito, aceptación inválida, cierre durante espera, expiración restaurada y fallo
de activación ya restaurado sin doble rollback. Falta únicamente enlazar estas
factories con sus dependencias productivas exactas en un lanzador inerte y
auditar su preflight, antes de proponer cualquier ejecución externa.

El lanzador `bitrix_connector/r1_result_eaor_product_launcher.py` conserva el
preflight local one-shot y añade un gate de ejecución exacto. Sólo con
aceptación `sp`, día 2026-08-13, bindings sin deriva y un objeto de factories
tipado construye el runner; todavía no invoca ninguna factory. El preflight
actual devuelve `READY-EXTERNAL-PREFLIGHT` y declara disponible el runner, pero
no acepta ni inicia la envolvente productiva.

`bitrix_connector/r1_result_eaor_product_runner.py` posee dos fases one-shot:
avanza autónomamente hasta `ATTENTION-REQUIRED` y luego permite exactamente una
reanudación tras el mensaje humano o un cierre seguro. El cierre restaura
participante/sesión antes de Fase A. La auditoría integral atraviesa launcher →
runner → puerto → coordinador con owners reales y dobles de sus I/O: éxito,
pausa humana, reanudación, cierres, rollback, aceptación inválida, vencimiento y
reuso. Cero superficies externas reales.

`bitrix_connector/r1_result_eaor_product_real_binding.py` produce ahora el plan
de factories desde builders productivos exactos y lo entrega al launcher sin
invocar ninguna factory. Provisión enlaza owner/binding real; activación enlaza
owner, runner Azure CLI y verificador anónimo; sesión exige un cliente remoto
autenticado hacia el owner pre-evento ya montado. Construir binding, plan,
runner y coordinador mantiene cero cargas de settings, aperturas protegidas, red,
mutaciones o mensajes. Deriva de identidad falla antes del plan.

La auditoría con dobles recorre además el binding completo hasta
`VERIFIED-RESTORED`. El supplier asíncrono de Fase A ya compone gate, collector
y operaciones diferidas y falla cerrado antes de invocarlas si su readiness no
es exacto. Persisten barreras externas/protegidas, no pasos de coordinación
local: fuente exacta del review token para el supervisor; builders reales de
las cuatro evidencias; verificación de SDK/identidad; publicación y despliegue.
Esta unidad no ejecuta la EAOR productiva.
