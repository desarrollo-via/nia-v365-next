# Inventario del corte Git de bitrix_connector

## Estado base

- Rama: `feature/aislamiento-entorno-experimental`.
- Upstream local: `origin/feature/aislamiento-entorno-experimental`.
- HEAD: `ad9260568ffbf40e49ea67c88571ef380bbf532e`.
- Índice inicial: 0 rutas en staging; índice preparado: 148 rutas exactas.
- Se ejecutaron únicamente los dos `git add` allowlisted de este documento. No
  se ejecutaron `fetch`, `pull`, `commit`, `push`, merge o workflow.

## Candidato técnico exacto

Después de incluir este inventario existen 148 rutas candidatas: 3 archivos
versionados modificados y 145 archivos nuevos.

### Corte A — integración funcional, 140 rutas

Archivos versionados modificados:

- `.env.example`: añade exclusivamente nombres y valores predeterminados seguros
  del conector;
- `.gitignore`: excluye los dos directorios de runtime efímero;
- `main.py`: añade únicamente el puente opcional, montaje y estado seguro.

Archivos nuevos:

- `bitrix_connector/`: 72 archivos, incluidos 67 Python y 5 contratos/HTML;
- `optional_bitrix_connector.py`;
- `nia_process_supervisor.py`;
- `nia_process_launcher.py`;
- `scripts/lanzar_bitrix_oauth_installation.ps1`;
- `scripts/lanzar_review_admin_https.ps1`;
- 60 pruebas de `tests/`, excluyendo únicamente
  `tests/test_nia_deployment_patch_template.py`.

Allowlist del corte A, ejecutada y verificada en 140 rutas:

```text
git add -- .env.example .gitignore main.py bitrix_connector optional_bitrix_connector.py nia_process_supervisor.py nia_process_launcher.py scripts/lanzar_bitrix_oauth_installation.ps1 scripts/lanzar_review_admin_https.ps1 tests/test_bitrix*.py tests/test_nia_chat_isolated.py tests/test_nia_process_launcher.py tests/test_nia_process_supervisor.py tests/test_optional_bitrix_connector.py
```

Antes de usarla se debe confirmar nuevamente que el índice está vacío y que el
pathspec `tests/test_bitrix*.py` resuelve exactamente las 56 pruebas previstas.

### Corte B — diseño y despliegue inerte, 8 rutas

- `deploy/templates/`: 3 archivos;
- `docs/`: 4 archivos, incluido este inventario;
- `tests/test_nia_deployment_patch_template.py`.

Allowlist del corte B, ejecutada y verificada en 8 rutas:

```text
git add -- deploy/templates docs tests/test_nia_deployment_patch_template.py
```

La plantilla de workflow permanece fuera de `.github/workflows`; este corte no
puede ejecutar Actions ni cambiar Azure.

## Exclusión local aplicada — 12 rutas

Integración Codex local, 8 rutas:

- `AGENTS.md`;
- `CONTINUIDAD_PROYECTO.md`;
- `PROTOCOLO_CODEX_AGENDA.md`;
- `PROTOCOLO_PROPIO_NIA_NEXT.md`;
- `nia_next.md`;
- `scripts/CodexAgendaInteractiveNotifier.cs`;
- `scripts/CodexAgendaInteractiveNotifier.exe`;
- `scripts/lanzar_notificacion_codex.ps1`.

Evidencia visual generada, 4 rutas:

- `logs/review_admin_off_demo.png`;
- `logs/review_lab_decision_demo.png`;
- `logs/review_lab_demo.png`;
- `logs/review_lab_dynamic_demo.png`.

Estas rutas están ancladas a la raíz en `.git/info/exclude`, permanecen locales
y nunca deben agregarse mediante `git add .` o `git add -A`.

La verificación posterior resolvió las 12 rutas contra sus patrones exactos y
conservó visibles las 148 candidatas: 3 modificadas y 145 nuevas. El índice
continuó con 0 rutas en staging.

## Elementos ignorados y fuera del corte

- `.env` continúa ignorado y no fue leído;
- `.venv/`, caches Python y logs de texto permanecen ignorados;
- `/.review-admin-runtime/` y `/.oauth-install-runtime/` permanecen ignorados;
- no hay symlinks o reparse points entre los candidatos;
- no cambian `requirements.txt`, el workflow activo local ni el remoto.

## Barreras de stage satisfechas

1. comprobar nuevamente índice vacío y conteos 140 + 8;
2. ejecutar revisión de secretos sobre la allowlist sin imprimir coincidencias;
3. repetir pruebas aisladas y compilación en memoria;
4. revisar el diff de `main.py`, `.env.example` y `.gitignore`;
5. los cortes A y B se prepararon por separado y cada conteo fue verificado
   antes de continuar.

## Resultado de la auditoría pre-stage

- La revisión de secretos sobre las 148 rutas candidatas produjo cero hallazgos
  de alta confianza. Las 26 asignaciones genéricas quedaron limitadas a siete
  archivos de pruebas con dobles, dominios seguros y credenciales ficticias.
- Una prueba conservaba el contrato anterior de montaje directo en `main.py`;
  se actualizó para exigir la delegación al puente opcional y la ausencia de
  importación directa del paquete.
- Pasan 469 de 469 pruebas herméticas y la compilación en memoria aprobó los
  132 archivos Python del corte, incluido `main.py`.
- `git diff --check` no encontró errores; el workflow local activo permanece sin
  cambios y el índice Git continúa vacío.
- No se leyó `.env`, no se iniciaron procesos o conexiones y no se ejecutaron
  commit, fetch, pull, push, merge, workflow o despliegue.

## Resultado del índice preparado

- Corte A: 140/140 rutas, sin faltantes o extras.
- Corte B: 8/8 rutas, sin faltantes o extras.
- Total: 148 rutas en staging, cero rutas prohibidas y cero archivos nuevos sin
  seguimiento.
- Las 12 rutas locales continúan resueltas por `.git/info/exclude` y `.env`
  permanece ignorado y fuera del índice.
- La primera revisión del diff staged detectó espacios finales en la última
  línea de contexto de la plantilla de parche. Se retiró ese contexto vacío y
  se ajustó el hunk de `6/11` a `5/10`, conservando exactamente cinco adiciones;
  sus 2/2 pruebas focales pasan y el diff staged queda sin errores de whitespace.

Commit, push, merge y despliegue permanecen como autorizaciones separadas. Un
push o merge a `main` dispararía automáticamente el workflow productivo.
