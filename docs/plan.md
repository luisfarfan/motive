# Plan y criterios de aceptación

Estado: 2026-11-16 (America/Lima). Base experimental ejecutable; no es una
release ni paridad con OBS/Meld. La investigación documental quedó resuelta
para esta fase y REA no bloqueó los hitos.

| Hito | Evidencia real | Estado y límite |
|---|---|---|
| 0 — Viabilidad | GPUI Kit abierto; libobs 33.0.1 Metal; patrón propio y captura ScreenCaptureKit de otra ventana GPUI; preview inspeccionado | Verificado en esta Mac; copia CPU, sin zero-copy |
| 1 — Producción | Selección de ventana externa, cámara y micrófono integrados; grabación real; guardar/restaurar; pérdida de ventana y reconexión explícita | Verificado en esta Mac; hot-unplug físico USB, sesiones largas y cámara congelada pendientes |
| 2 — Agentes | MCP/CLI comparten PID y revisión con UI; cambio visible del overlay; desconexión conserva el motor; errores estructurados | Conjunto mínimo verificado; no certificación de todos los clientes MCP |
| 3 — Diferenciador | Overlay animado dentro de archivos; 960×540 y 540×960 con contain, margen seguro y anclaje inferior; vertical 4.166000 s/123 frames | Política mínima verificada; editor libre y salidas simultáneas pendientes |
| 4 — Streaming | libobs → MPEG-TS UDP loopback → FFmpeg, 5.021333 s/150 frames, H.264/AAC y overlay | Receptor local verificado; plataformas públicas y RTMP/SRT pendientes |
| 5 — Primer editor | Ventana + webcam + overlay; transformaciones y orden por MCP; persistencia v3 y reapertura; UI refleja el núcleo | Ver [verificación de escenas](scene-graph-verification.md); una composición/output activo, cambios de recursos solo detenido |

## Reproducir y consultar evidencia

Seguir README.md para bootstrap/bundle. Abrir Motive y su fuente de prueba,
mantenerla disponible y comenzar sin una salida activa:

```sh
cargo test --locked
cargo clippy --locked -- -D warnings
cargo fmt -- --check
python3 scripts/verify_control.py
python3 scripts/verify.py
```

La ejecución original de ambos scripts terminó con éxito. Seis pruebas unitarias
pasaron; Clippy sin advertencias y formato comprobado. La integración usa el
motor y hardware reales, sin mocks. Se conservaron las pruebas fallidas.

- `var/evidence/acceptance.json`: archivos, duración, frames, audio, overlay y
  muestras de CPU/RSS; `ok: true`.
- `var/evidence/control-integration.json`: intercambio MCP, PID/revisión y
  continuidad tras desconexión.
- `var/evidence/source-loss.json`: error tras cerrar la fuente de captura.
- `var/evidence/horizontal.png` y `vertical.png`: frames reales del motor.
- `var/evidence/build-identity.json`: hashes del ejecutable, fuentes y lockfile.
- `var/evidence/final-acceptance-runtime.log`, `tests.log`, `clippy.log` y
  `bundle.log`: runtime y verificaciones.

Las rutas de videos están en acceptance.json. Son artefactos locales ignorados
por Git y reproducibles. El bundle está en `target/Motive.app`.

## Medición y límites

Durante la regresión H1, `ps` registró CPU mediana 33.3 %, máximo
39.5 %, y RSS entre 190.6 y 307.7 MiB. Build debug con UI
y ventana controlada; excluye el helper de muxing y la carga restante del
sistema. Los contadores de render, output y preview están en acceptance.json.
Son contadores distintos. No demuestran cero latencia ni ausencia de pérdidas
en todos los niveles. No hubo benchmark comparativo ni prueba prolongada de
memoria.

En la primera etapa el micrófono estaba denegado. En H1 se autorizaron cámara,
micrófono y pantalla mediante los permisos normales de macOS y se verificó
grabación física. Ver [informe H1](h1-verification.md) para evidencia, firma
de desarrollo, desconexión de ventana y límites de hot-unplug. Solo esta
Mac/macOS 27.2 fueron probados. El mínimo de build 15.0 no equivale a una matriz
de compatibilidad ejecutada.

## Siguiente hito recomendado

Sobre el editor actual, añadir campos numéricos directos y selección visual de
capas, conservando el mismo contrato del núcleo. Antes de permitir cambio de
cámara/escena durante una salida, probar hot-unplug con dispositivos removibles,
sleep/wake y sesiones de mayor duración. El monitor de entrega de frames de cámara
ya existe; el atasco físico y una ventana viva con imagen congelada no están
verificados. Preparar el bundle distribuible y optimizar preview cuando una
medición específica lo justifique.

Mantener fuera nube, pagos, marketplace, framework genérico de plugins y
emisiones públicas. REA se reconsidera solo ante una pregunta concreta que
fuentes públicas y reproducción controlada no resuelvan. Ver detalles,
problemas corregidos y fuentes en docs/decisions.md.

## Ampliación H1

Ver [informe de verificación](h1-verification.md) y ejecutar
`scripts/verify_h1.py` con los UIDs físicos solo cuando corresponda.
UI, CLI y MCP siguen controlando la misma instancia de Production.
Las grabaciones y los inventarios de dispositivos permanecen fuera de Git.

## Incremento de escenas

El formato v3 añade escenas, recursos reutilizables y capas con IDs estables y
transformaciones horizontal/vertical independientes. UI, CLI y 26 herramientas
MCP usan Production. Se conservan las pruebas anteriores y se añaden pruebas
reales de composición y recuperación del muxer. La evidencia y las limitaciones
actuales están en [scene-graph-verification.md](scene-graph-verification.md).
