# H17 — Production reliability

Inicio: 18 de noviembre de 2026, America/Lima. Worktree independiente
`/Users/luisfarfan/Developer/products/motive-h17`, rama
`codex/h17-production-reliability`. `git fetch origin main` confirmó
`15ffbad307c5439270130979dae0e9d66d92d700`. El checkout local de main estaba
en `6019ad0`; no se modificó. H18 y sus laboratorios quedan fuera del scope.

Estado de trabajo: **PARTIAL**. Aceptación de beta: **FAIL** mientras permanezcan
los P0 de captura sin cierre. Este informe es propio de H17; los históricos
H13–H15 permanecen intactos y sus PASS no certifican una nueva candidata.

## Identidad y auditoría

Se leyeron AGENTS, README, plan, decisiones, aceptación nativa H13, beta H14,
collection-b3-followup, capture-investigation, output-matrix-b3, memory-b3-soak,
beta H15, resume H15 y native-ux H15. Se inspeccionaron fuente fijada OBS 33.0.1,
parches de captura y H8, graph/health, owner Show Control, heartbeat/preview,
verificadores y bundler. `.deps` es una copia APFS independiente, sin enlace
escribible a otro worktree ni cambios al entorno global.

B6 existente: `/Users/luisfarfan/Developer/motive-h15-portable/b6/Motive.app`.
El hash calculado de `Contents/MacOS/motive` es
`fe58dc5ca406eb0427d40c5b5a47473aad5d251a75f9d87e170eae9b51cd7d47`, igual al
informe H15. Runtime `08004138d1f3586e133f78175d8a1528c5fb7b06`; `git diff`
de ese commit a origin/main está vacío para src/native/Cargo/build.rs.
Es debug ARM64 firmado Apple Development, no release ni notarizado.
Recibo: `var/evidence/h17-audit/baseline.json`.

## Matriz de problemas

Estados exclusivamente PASS / PARTIAL / FAIL / BLOCKED / NOT_EVALUATED.
La columna anterior conserva el gate B6 pertinente; las causas no demostradas
se marcan como hipótesis. «Prueba» especifica qué falta para cerrar el alcance.

| ID | P | Evidencia original / anterior | Causa o hipótesis; área | Corrección / riesgo | Prueba necesaria | Actual / evidencia H17 |
|---|---|---|---|---|---|---|
| CAP-01 | P0 | H15 B4 default, congelamiento ~15,4 s; FAIL. B6 foco BLOCKED | Productor dibuja, SCK suspended, OBS conserva textura; causa de suspensión no demostrada | Mantener aviso/rechazo de start; no forzar flags de otras apps. Riesgo de confundir estático con fallo | Foco independiente completo y píxeles MKV/RTMP default | FAIL; B7 default-02 foco PASS, freeze MKV15,4s/RTMP15,6s; h17-capture-verification |
| CAP-02 | P0 | B6 capture-b6-media; FAIL | B7 nueva identidad falla start SCK InvalidParameter (-3812); dimensiones de configuración no observadas | Recuperación explícita; sin bucle de reconnect. Riesgo de sesión solapada SCK no demostrado | Cierre/reapertura/ID nuevo/idle/outputs y píxeles posteriores | FAIL; h17-capture-b7, fuente rechazada y cierre limpio; sin medio posterior |
| CAP-03 | P0 | Detectado por lectura H17; NOT_EVALUATED | Producto: release_capture_source elimina scene items pero conserva préstamos en cache cuando reemplazo falla | Invalidar préstamos antes del remove; preservar máscara lógica de fuente ausente. Riesgo de ocultar fallo de salud | Contrato real libobs y regresión de recuperación fallida/cierre | PARTIAL; legacy FAIL/fixed PASS en h17-scene-items-03; salud inspeccionada |
| CAP-04 | P0 | Detectado en OBS33; NOT_EVALUATED | OBS: missing window/addStreamOutput fallido retornan true; lookup solo Window ID | Rechazo de creación y comprobación PID exacto. Riesgo de cambiar rutas upstream de cleanup | Contrato de admisión + captura propia física | PASS en contrato: upstream6 admisiones inválidas/corregido0; captura propia admitida y error real start rechazado. No cierra CAP-01/02 |
| OUT-01 | P1 | Matriz B6 9 funcionales, 14 medios; PARTIAL | Observer anterior al plugin no prueba entrega. H14 conserva AAC pre-stop con reordering | Mantener false y cutoff/H8; riesgo de alterar finalización sin causa | Matriz VT/x264 MKV/RTMP/dual/cancel/shutdown/receiver-loss | PARTIAL; B7 9 funcionales PASS/14 medios decodificados; 13 paquetes normales ausentes post-stop y 3 de receptor perdido sin bracket; ningún pre-stop observado |
| OUT-02 | P1 | Detectado H17; NOT_EVALUATED | Verificador: una última observación perdida podía dar TRACED_TAIL_PRESENT | Exigir extremos, quiescencia y matching 1:1. Riesgo de informes con evidencia insuficiente | Reproducer negativo y replay de todos los B6 | PASS; 10 tests y h17-output-audio-audit-01 |
| AUD-01 | P1 | B6 continuidad/A/V PASS | Jitter frente al margen del mixer; corrección 128 ms conservada | Sin cambiar mixer/reloj/buffering. Riesgo de heredar PASS a B7 | Pilot/RTMP/recovery/transitions/persistence/silence/resumed/tail/mix/gain/mute/pulsos | NOT_EVALUATED para candidata nueva |
| AUD-02 | P1 | H14 APPLICATION_UNAVAILABLE, B6 PARTIAL | Identidad histórica no reproducida; falta subcausa en H14 | Instrumentación B6 exact PID/count/reason; no seleccionar otra app | Pérdida/reinicio autorizado + observación de proceso y diagnóstico | PARTIAL; auditoría sin reparación inventada |
| SHOW-01 | P1 | B6 reconcile+load BUSY; PARTIAL | Producto: revisión externa impide recibo contiguo aun con terminal nativo durable | Recibo terminal independiente, solo reconcile; sin rebase/replay. Riesgo: admisión prematura o recibo falso | Contratos adversariales y sesión real reconcile→load desarmado | PASS; h17-show-b7: carrera450 real por CLI, recibo nativo durable, counter0, reconcile→load desarmado→arm explícito; sin atribuirlo a GPUI |
| SHOW-02 | P1 | B6 stock450/pre-tick; PARTIAL | Cobertura humana/carrera, no defecto demostrado | Mantener duración stock; no atribuir CLI a GPUI | Edición GPUI durante running, cancel antes/después tick | BLOCKED hasta fase supervisada; contratos disponibles |
| PERF-01 | P1 | B6 dual120s 1117,95 MiB / 83,16% CPU / RPC p95 17,51 ms; PARTIAL | Reservas y malloc vivo distintos; sin ownership concluyente de fuga | Medir misma carga y release; no purgar allocator ni cambiar umbrales | Idle/4 videos/720p60/1080p60/dual/3 ciclos/shutdown | NOT_EVALUATED para candidata nueva |
| PERF-02 | P1 | Preview copia CPU→GPU y 11 drops B6; PARTIAL | Coste heartbeat/RenderImage aún por medir | Instrumentación GPUI opt-in separada de libobs. Riesgo de perturbar medida | Tiempos UI, preview_age/drops, CPU y buffers | PARTIAL; backends compilan, benchmark pendiente |
| GPUI-01 | P1 | Fast desactivado; NOT_EVALUATED | Kit0.10 admite Fast; lock wgpu30.0.2 incompatible con exact30.0.1 Fast | Features opt-in, pin compatible; no adoptar sin visual/foco/a11y | A/B/BA misma carga/hardware, scrolling/editor/deck/dialogs | PARTIAL; release A/B compilan; defaults conservados |
| UX-01 | P2 | B6 recorrido parcial/recibos; PARTIAL | VoiceOver, Tab completo y stock450 sin observar | Corregir solo defectos demostrados; respetar Claude Design | Flujo 14 pasos nativo, labels/foco/disabled/recibos | BLOCKED hasta fase supervisada |
| PKG-01 | P2 | B6 portable debug PASS, distribución PARTIAL | Release optimizada y nueva identidad necesarias | Candidata B7 distinta, ad-hoc local sin Keychain. Riesgo de permisos por identidad nueva | Audit ARM64/rpaths/plugins/tools/licencias/runtime externo/stores | PASS para auditoría estática y runtime local fuera checkout; h17-portable-beta. Segunda Mac y distribución separadas |
| PKG-02 | P2 | B6 fuentes PARTIAL | Reconstrucción fuente→binario y revisión distribución no completas | Snapshot/hashes/fuentes correspondientes sin publicación | Verificar inventario y rebuild; autorización para distribución | PARTIAL; material25native/463Rust y avisos PASS, reconstrucción no certificada |
| HW-01 | P2 | Cámara/mic/USB/permisos/sleep; BLOCKED | Requiere persona y contenido controlado | Dispositivos explícitos y permisos normales; sin ajustes globales | Protocolo supervisado separado por dispositivo/evento | BLOCKED hasta coordinación concreta |
| MAC-02 | P2 | Segunda Mac ARM64 macOS15+; BLOCKED | Hardware externo no disponible en herramienta | Entregar procedimiento local con hashes | Ejecución fuera checkout en segunda Mac | BLOCKED |
| SIGN-01 | P2 | Distribución/notaría; BLOCKED | Falta autorización específica de Developer ID/servicios | Solo firma ad-hoc del build local | Firma distribución/notarización autorizadas por separado | BLOCKED |

## Checkpoints

1. Auditoría/remoto/aislamiento: PASS. Identidad B6 verificada por bytes y Git.
2. Ownership de captura: contrato PASS, aceptación física PARTIAL.
   `h17-scene-items-01` conserva un defecto inicial del fixture (faltaban callbacks
   width/height); `02` conserva un error del instrumento: obs_wait_for_destroy_queue
   devuelve false cuando no existen threads audio/video. Se cambió la hipótesis
   y se usó la barrera real OBS_TASK_DESTROY, sin sleeps. `03` observa el fallo
   de cache legacy y el PASS corregido, dos escenas/dos referencias por captura,
   fuente ajena conservada, retry idempotente y dos destrucciones finales.
   ASan instrumenta el fixture, no el libobs precompilado; no se declara que ASan
   haya detectado un UAF ni que se capturó video en esta prueba.
3. Show Control: [causa/contratos](h17-show-control-verification.md).
4. Output/audio: [auditoría y límites](h17-output-audio-verification.md).

## Captura: límites de las APIs

El filtro usado por OBS es `initWithDesktopIndependentWindow:`. Permite capturar
una ventana identificada; no garantiza que un productor suspendido publique
contenido nuevo. Apple distingue [idle](https://developer.apple.com/documentation/screencapturekit/scframestatus/idle)
de [suspended](https://developer.apple.com/documentation/screencapturekit/scframestatus/suspended).
No se usa antigüedad de buffer para declarar una imagen estática perdida.
Reconfigurar filtro/configuración es una API soportada, pero no demuestra por
sí mismo recuperación ni habilita elegir otra identidad sin acción explícita.

La política conserva fuente afectada/estado/aviso y rechazo de nuevos outputs
con suspended/stopped. Los outputs activos no se destruyen por un simple estado
idle/suspended. La alternativa inmediata es mostrar la ventana propia y comprobar
contenido, o seleccionar explícitamente otra fuente compatible; no se captura
el escritorio automáticamente. Minimización, otros Spaces, suspensión, resize,
restauración y foco deben probarse por separado. Ninguna evidencia atribuye
causalidad a Stage Manager. El callback stop asíncrono upstream continúa siendo
un límite distinto del retiro de préstamos de escenas corregido aquí.

## Procedimientos supervisados

Siempre lock canónico, hash de candidata, owner/PID y directorio nuevo. Cerrar
normalmente y comprobar socket/procesos/barreras al terminar cada fase.

1. Foco: ventana de fixture propia → Motive → fixture, fases completas de 15 s.
   Observador independiente AppKit + PID/window/time en toda la fase; marcador
   aislado insuficiente. Decodificar MKV/RTMP y contador. Dos intentos sin progreso
   cambian hipótesis o dejan BLOCKED; no alargar para ocultar fase inválida.
2. Cámara/mic: usuario identifica dispositivo y confirma contenido controlado.
   Selección explícita GPUI; patrón visual y tono acústico sin conversaciones.
   MKV/loopback, mute/gain, detach USB, error observado y reconnect explícito.
3. Sleep/wake y permisos: solo cuenta/Mac de pruebas autorizada. UI normal del
   sistema, sin reset TCC ni cambios de SIP/Gatekeeper. Separar idle y outputs;
   preservar medios parciales intencionales y estado al reanudar.
4. UX/VoiceOver: abrir/añadir/configurar/video/grabar/transmitir/escenas/deck/
   stop/biblioteca/guardar/cerrar/reabrir desde GPUI. Tab/Shift-Tab/Enter/Escape,
   labels/foco/disabled, anuncios de error y recibos persistentes. No sustituir
   un gesto sin efecto por mutación CLI atribuida a UI.
5. Segunda Mac: ARM64 macOS15+, verificar hashes y firma, lanzar fuera del
   checkout sin `.deps`/DYLD; importar medio propio con tools embebidas, guardar
   y restaurar proyectos/reglas desarmadas, MKV+RTMP local, cierre/reapertura.
   Registrar OS/hardware y decodificar. Una firma ad-hoc/Apple Development no
   equivale a notarización ni autoriza publicación.
