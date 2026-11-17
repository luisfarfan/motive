# H11 — Informe de verificación del Overlay Engine

Estado: **17 de noviembre de 2026**. La tanda H11 verificó texto, imágenes, formas, video local, seis acciones por capa, widgets y presets mediante medios reales decodificados. Incluye grabación, RTMP loopback, CLI/MCP y restauración. **La aceptación de H11 está condicionada al cierre de regresiones H1–H10**, detallado al final. No se declara una release ni cobertura de escenarios no ejecutados.

Worktree `motive-h11`, rama `codex/h11-overlays`, base `main` `0370ca4` con H10; macOS ARM64, libobs 33.0.1. Pruebas sobre el bundle de desarrollo firmado, con contenido controlado y uso exclusivo coordinado del bundle/dispositivos. Sin emisión pública, push, merge ni release. No se modificaron GPUI ni diseños para esta implementación.

SHA-256 del ejecutable B7 usado por la tanda H11 final descrita abajo:

`bd748f125085db734d2ff0015e8b05453b198e5b1085c7e4c3b25e3b6e9dced6`

La tanda reúne subinformes aprobados de dos ejecuciones runtime y la cohorte `h11-final-build7-remaining-1794897709260434000/manifest.json`. El primer informe runtime padre conserva `ok:false` por la métrica BRB descrita abajo; sus subinformes de animaciones/widgets pasan. No se reescribió ese fallo como éxito global.

## Evidencia y alcance

Rutas relativas al worktree. JSON, clips, fixtures y PNG permanecen privados bajo `var/evidence/` y `var/recordings/`.

| Informe en `var/evidence/` | Cobertura | Resultado |
|---|---|---|
| `h11-runtime-1794897372277649000/animations/report.json` | Seis animaciones por capa; Cut/Fade; grabación y RTMP | `ok:true`, 2 clips, 66 probes |
| `h11-runtime-1794897372277649000/widgets/report.json` | Countdown, lower third y alert; grabación y RTMP | `ok:true`, 2 clips, 24 probes |
| `h11-runtime-1794897711314448000/report.json` | Tres presets y receta BRB, dos variantes | `ok:true`, 6 clips, 10 probes |
| `h11-visuals-1794897748243741000/report.json` | Texto/alpha/formas/video; encoder x264 | `ok:true`, 1 clip de 29,066 s |
| `h11-lifecycle-1794897788620046000/report.json` | Reapertura, persistencia, pérdida/recuperación de asset, documento grande | `ok:true`, 2 clips de 3,133 s |
| `h11-build7-tests.log` | Rust, parser, assets, tracking y framing | 49 tests; 0 fallos |
| `h11-build7-clippy.log` / `h11-build7-format.log` | Análisis estático y formato | Finalizan sin diagnósticos |

Son **13 clips finales B7**: 11 grabaciones y 2 recepciones RTMP, aproximadamente 115,062 segundos sumados. Los diez clips de runtime usan VideoToolbox hardware H.264; visuales usa x264 y lifecycle vuelve a VideoToolbox. Todos contienen H.264 y AAC estéreo a 48 kHz. Horizontal es 960×540 y vertical 540×960, a 30 fps.

`var/evidence/h11-delivery/widgets-recording.mp4` ofrece una vista reproducible del clip de widgets: remux de los paquetes originales H.264/AAC, sin recodificación. `preview.json` relaciona ambos hashes; la evidencia y los análisis siguen referidos al MKV original. La app finalizó idle, sin entradas del mixer, y se liberó el lock físico al terminar.

## Pruebas visuales y audio

| Comprobación | Observación final |
|---|---|
| UTF-8 latino, saltos y actualización en vivo | 7.320 píxeles cambiados; conserva instancias y salida |
| Texto vacío | 0 píxeles de foreground restantes en su caja |
| Alineación de bloque | Centro x241–356; derecha x481–596 en caja de 600 px |
| PNG transparente/semitransparente | Transparencia conserva fondo; error encoded-RGB máximo 1,38/255 |
| Rectángulo, círculo y bordes | Colores y aro presentes en salida decodificada |
| Pausa | Cuatro muestras identifican el mismo frame original 47; posición nativa estable |
| Reproducción/loop | 8.679 píxeles cambian al reproducir; 8.702 tras seis segundos de loop |
| Aislamiento del audio del video | Amplitud 997 Hz: `4,79e-8`; tono H10 de 440 Hz: `0,03160` |
| Audio visual decodificado | RMS `0,02235`, peak `0,03528`; sin saturación del fixture |

El video importado contiene deliberadamente 997 Hz. Su ausencia en la salida respalda mixers `0`, mute y monitoreo desactivado; no incorpora un canal H10. En runtime el tono global continúa: RMS por ventanas de 100 ms entre `0,02229` y `0,02239`, peak máximo `0,03644`. Son señales controladas, no una nueva prueba de micrófono físico.

## Animaciones, widgets y presets

Ambos transportes verifican fade in/out, slide in/out y scale in/out mediante píxeles intermedios y geometría final. Slide out grabado produce x372/326/276 frente a x368/320/272 esperados. Cancelar restaura la caja `[400,220,160,100]`. Se prueban duplicados ocupados, cancelación repetida, distancia firmada y fuente reutilizada en dos capas sin mover la segunda. Cut cambia fondo sin frames mezclados; Fade entre escenas presenta colores intermedios con audio continuo.

La aceptación devuelve `operation_id`. El resultado terminal conserva `pending_ack` hasta reconciliar generación, variante y capa; no puede desalojarse antes. Rust cubre entrega repetida, generaciones antiguas, identidad y finalizaciones independientes.

Countdown, lower third y alert ejecutan eventos tipados y modificaciones por CLI/MCP. El contador muestra glyphs distintos y termina en `00:00`: error de máscara 0,042–0,048 frente a 0,156–0,169 con referencias equivocadas. Timer y alert continúan **al menos 4,29 segundos sin cliente MCP conectado** en ambos transportes. El reloj permanece en nativo.

`professional_lower_third`, `starting_soon` y `be_right_back` se grabaron horizontal y verticalmente: seis layouts. BRB anima solamente el acento mediante `scale_in`, `ease_in_out`, 1.200 ms y escala inicial 0,7; diámetro observado aproximadamente 46→64 px. El texto permanece estable, con error de máscara en caja fija 0,019/0,040. Guardado/carga conserva definiciones y perfiles independientes.

## Rendimiento y timestamps

CPU/RSS corresponden solo al **proceso debug de Motive**, bajo sondeo del verificador; excluyen Python y procesos auxiliares. El sondeo añade trabajo al núcleo. La sesión B7 estaba bloqueada: no comparar causalmente su CPU con tandas anteriores. Nueve clips de runtime registran delta render lag 0; **widgets-grabación registra 4**, ya presentes en la primera muestra a 0,169 s, todavía con 0 frames de salida, sin aumento posterior. Los diez tienen output drops 0 y encoder skips 0; visuales x264 también tiene delta lag 0. `preview_busy_drops` es independiente. Estos PASS funcionales no satisfacen por sí solos la regresión estricta de cero lag.

| Clip | Duración s | CPU mediana % | RSS máximo MiB | Gap video máximo ms | SHA-256, primeros 12 |
|---|---:|---:|---:|---:|---|
| Animaciones, grabación | 18,766 | 26,9 | 167,3 | 34 | `99011c22d4b2` |
| Animaciones, RTMP | 19,099 | 27,6 | 169,8 | 67 | `e816beee56c1` |
| Widgets, grabación | 9,800 | 28,1 | 233,6 | 67 | `af4325f6f37b` |
| Widgets, RTMP | 10,065 | 28,9 | 234,2 | 67 | `a412ea2f1fe3` |
| Lower third horizontal | 3,800 | 27,7 | 217,8 | 34 | `75bcd7413d83` |
| Lower third vertical | 3,800 | 34,0 | 231,3 | 67 | `cbe3f23b1b16` |
| Starting soon horizontal | 3,800 | 27,0 | 231,2 | 67 | `f4e46d9d9f27` |
| Starting soon vertical | 3,800 | 33,8 | 231,6 | 67 | `c588930238f5` |
| BRB horizontal | 3,400 | 28,1 | 231,6 | 67 | `0d93a247be9d` |
| BRB vertical | 3,400 | 35,3 | 231,8 | 34 | `bdf14f6a620c` |
| Visuales x264 | 29,066 | 44,3 | 315,7 | 66 | `70ecd173247a` |
| Pérdida de asset | 3,133 | — | — | 67 | `aac4d3956e33` |
| Recuperación de asset | 3,133 | — | — | 67 | `a4e61409e6ab` |

Hashes completos en `media.sha256` o lifecycle. Runtime suma 79,730 s. Máximos interiores: video 34 ms, audio 22 ms; timestamps crecientes. **Persisten gaps de cierre de 66–67 ms**; ambos clips lifecycle tienen gaps finales en índices 90/91. El gate interior excluye los últimos cuatro intervalos y conserva el máximo total. MKV runtime tiene dos paquetes de video sin DTS; FLV, ninguno. La tanda anterior conserva gaps de 67–134 ms en `h11-runtime-1794895559315733000`. Decodificación completa no equivale a cadencia de cierre perfecta.

## Fallos conservados y correcciones

Los informes originales fallidos no se reescribieron:

- El aro del círculo desaparecía por escrituras al buffer inmediato que sobrescribían geometría Metal pendiente. Se corrigió con vertices inmutables y un probe del borde.
- `play_pause(false)` después de stop no reiniciaba FFmpeg. `play` usa restart oficial para stopped/ended; pause/resume conserva su API. Fallo: `h11-visuals-1794894023544054000/report.json`.
- El baseline de animaciones registró 457 frames retrasados; otro piloto visual, 214. Se añadió actividad `NSProcessInfo` para preparación/salida/finalización. El bundle ya usa `LSAppNapIsDisabled:true`; no se atribuye el lag a App Nap. La tanda anterior tuvo diez outputs con delta cero, pero B7 widgets registra 4 antes de su primera muestra (0,169 s, todavía 0 frames de salida), sin aumento posterior. No hay mejora causal demostrada ni cambios globales. [API oficial Apple](https://developer.apple.com/documentation/foundation/processinfo).
- El análisis temporal inicial mezclaba offset de comando con origen multimedia y normalización de seek FLV. `h11-runtime-timeline-analysis.py/.json` conserva el diagnóstico privado. El verificador calibra una vez mediante marcador independiente, selecciona PTS absoluto y contrasta un marcador inverso: deriva B7 entre −20,79 y +12,09 ms, sin ajustar individualmente cada curva.
- Una pausa parecía moverse por recuantización H.264 en un I-frame: 983 píxeles distintos, pero idéntico frame fuente. `h11-visuals-1794894936346635000/pause-analysis/findings.md` conserva imágenes, rankings y controles negativos. El gate exige cuatro coincidencias inequívocas con el fixture, posición nativa constante y frames diferentes al reproducir. Movimiento real y región vacía fallan. No se añadió blur ni se ocultó la diferencia RGB.
- B7 falló BRB con error de máscara 0,188. `h11-runtime-1794897372277649000/presets/brb-glyph-offline-analysis.json` demuestra que un píxel de borde cambió la altura del recorte de 106 a 105: reescalarlo deformaba toda la comparación. La caja fija mide 0,017945, bajo el mismo límite 0,05; controles negativos con desplazamiento de 1 px producen 0,384/0,296 y texto vacío, 1,0. Se corrigió solo el verificador para comparar esa caja sin reescalado; el informe fallido y los píxeles originales permanecen.

## Persistencia y recuperación

Lifecycle cerró/reabrió el bundle, restauró v4 y cambió subtipo de widget recreando solamente ese recurso. Conservó imagen administrada, mezclador H10 y perfiles; restauró después v3. El arranque hasta control disponible fue 0,450 s. Eliminar el asset activo finalizó la grabación, bloqueó reinicio y permitió recuperación mediante reimportación idéntica y reconnect explícito; ambos clips decodifican.

El documento grande contiene 16 fuentes: **74.693 bytes persistidos y respuesta CLI de 139.319 bytes**, preservando identidad y acuerdo CLI/MCP. Solicitudes siguen limitadas a 64 KiB; respuestas, 1 MiB. Rust verifica límites exactos, fragmentación y frames incompletos/consecutivos, evitando un falso fallo tras una mutación aplicada.

## Reproducción

Adquirir primero el lock exclusivo coordinado entre worktrees para dispositivos/bundle. Usar el bundle firmado correspondiente, idle; no ejecutar drivers simultáneamente ni reemplazar el bundle durante la tanda. Requiere FFmpeg/ffprobe y Python. Pillow queda fijado en venv local, sin modificar paquetes globales:

```sh
python3 -m venv var/h11-verify-venv
var/h11-verify-venv/bin/python -m pip install -r scripts/requirements-h11.txt
target/debug/motive ctl '{"op":"set_encoder","encoder":"auto"}'
var/h11-verify-venv/bin/python scripts/verify_h11_runtime.py --transport both
target/debug/motive ctl '{"op":"set_encoder","encoder":"x264"}'
var/h11-verify-venv/bin/python scripts/verify_h11_visuals.py --with-video
target/debug/motive ctl '{"op":"set_encoder","encoder":"auto"}'
var/h11-verify-venv/bin/python scripts/verify_h11_lifecycle.py
```

Runtime presupone la app abierta; lifecycle la cierra/reabre y respalda/restaura documentos. Conservar JSON, logs, clips y hash de app, incluidos fallos. Comparar `shasum -a 256 <archivo>` con el hash completo y revisar frames/PTS mediante FFmpeg/ffprobe. Los fixtures permiten repetir identidad visual y separación espectral.

## Regresiones H1–H10 — pendiente de cierre

Los tres manifests siguientes corresponden al SHA anterior `a423dee423d80be48a1e153c153708a41958cfced2efd3d9aff702c814a20b3d`. Conservan exit codes, informes y hashes; **los tres tienen `ok:false`**. Se cuentan suites individuales, sin contar el driver legacy como otra prueba ni duplicar repeticiones: **14 distintas PASS y 5 todavía fallidas, de 19 ejecutadas**.

| Manifest bajo `var/evidence/` | Resultado observado |
|---|---|
| `h11-regressions-1794895818941003000/manifest.json` | Driver legacy: control y delivery PASS; H1 falla en cámara |
| `h11-regressions-1794895981427538000/manifest.json` | 14 suites independientes: 12 PASS; encoding y H9 faults fallan |
| `h11-regressions-1794896604624466000/manifest.json` | Repite encoding/H9 faults y ejecuta scenes/H9 transitions: las cuatro fallan |

PASS: `verify_control.py`, `verify_control_delivery.py`, `verify.py`, `verify_encoding_fallback.py`, `verify_output_recovery.py`, `verify_rtmp.py`, `verify_rtmps.py`, `verify_connect_stop.py`, `verify_vt_stop.py`, `verify_profiles_restart.py`, `verify_h8_lifecycle.py`, `verify_h8_keychain.py`, `verify_h10_audio.py` y `verify_h10_mixer.py`. RTMPS conserva su alcance anterior de rechazo TLS; no certifica una emisión TLS positiva.

El bundle final B7 repitió **13 de esas suites, todas PASS**, en `h11-regressions-1794897825446170000/manifest.json` (`ok:true`, SHA `bd748f…dced6`). Incluye todas las anteriores salvo `verify.py`, cuyo fixture de ventana requiere la sesión desbloqueada; su PASS pertenece solamente al bundle anterior. No se repitieron las otras cuatro suites físicas pendientes mientras seguía bloqueada la sesión. Encoding tiene el diagnóstico B7 fallido descrito abajo. Así, el manifest verde de 13 suites no representa aceptación completa de H1–H10.

Ambas suites H10 pasan en B7: micrófono y tono, ganancia/mute, medición, recuperación controlada, Cut/Fade, persistencia y RTMP local. El piloto de ganancia mide −12,039 dB para la orden de −12 dB, peak decodificado 0,07529. `h10-pilot.json` y `h10-mixer.json` conservan mediciones y eventos; hot-unplug físico USB sigue explícitamente sin probar.

| Suite pendiente | Fallo reproducido / alcance todavía sin validar |
|---|---|
| H1 | Solo 3.740 píxeles de fuente sobre el umbral luminoso, frente a 10.000 exigidos; imagen de cámara casi negra. Antes pasaron selección, pérdida de ventana, finalización y recuperación. El driver no completó toda su aceptación física |
| Encoding | VideoToolbox acumula 9 y 13 `lagged_frames` en dos intentos; `video_skipped_frames:0`. El primer trial x264 de cada intento tiene lag 0. El criterio de cero lag no pasa; la comparación completa queda interrumpida |
| H9 faults | En ambos intentos la ventana activa tiene `width:0`, `CAPTURE_NOT_READY`; no alcanza la preparación necesaria para completar la prueba de fallos |
| Scenes | Timeout con ventana sin dimensiones de video (`width:0`, `CAPTURE_NOT_READY`); la webcam sí reporta 215 frames y ancho 1.280. Composición/persistencia completas siguen pendientes en esta tanda |
| H9 transitions | Ventana destino sin dimensiones de video (`width:0`); `SCENE_PREPARATION_TIMEOUT` bloquea el Cut. La webcam tiene frames; la aceptación completa Cut/Fade de esta suite no termina |

El contador `sources[].frames` se instrumenta para cámara, no para ScreenCaptureKit: su cero no demuestra ausencia de buffers de ventana. Son fallos observados contra criterios conservados, no PASS ni exclusiones. Todavía no se ha establecido si son regresiones introducidas por H11. La aceptación funcional H11 no elimina estos 9/13 frames de lag.

El diagnóstico B7 de 15 segundos por trial, `h11-startup-activity-1794897235846510000`, cubre con `NSProcessInfo` la inicialización del encoder. Pasan el primer x264 y VideoToolbox; el siguiente VideoToolbox falla con 6 frames de lag. Se sitúan en el arranque, sin aumento durante el tramo estable, pero **no prueba una corrección** ni sustituye los trials originales de 60 segundos.

`h11-regressions-1794896604624466000/startup-diagnosis.json` localiza los seis antes del baseline de captura OBS, con 0 frames de salida al responder start. El archivo contiene 473 frames H.264 y gaps PTS de 33–34 ms, ninguno superior a 50 ms. El criterio original incluye el intervalo de preparación y sigue fallando; no se ocultan ni restan esos contadores.

`var/evidence/h11-session-state.json` registra una consulta de solo lectura a `CGSessionCopyCurrentDictionary`: sesión bloqueada desde **2026-11-17T06:15:46Z**, observada a las 06:32:34Z; `h11-session-final.json` confirma que seguía bloqueada al cierre. Los fallos posteriores de ventanas coinciden con ese bloqueo. Es una hipótesis que requiere repetir las mismas suites tras desbloqueo normal del usuario; no demuestra causalidad ni explica por sí sola la cámara oscura o el lag. No se cambiaron ajustes globales ni permisos. Preparar contenido de cámara controlado, repetir los cinco grupos y revisar sus resultados siguen siendo puertas de aceptación abiertas.

## Límites pendientes

Browser/CEF permanece bloqueado por aislamiento/lifecycle; audio de video, deshabilitado. Helvetica mostró glyph faltante para un checkmark: no se promete fallback universal, emoji ni shaping complejo. HDR y video alpha no están verificados. Faltan long-run, presión de memoria, revocación de permisos y hotplug prolongado; no se heredan esas garantías de pruebas históricas. Los 256 MiB son estimados, no RSS: decoders ocultos siguen abiertos y reconciliar puede duplicar recursos. No se verificó streaming público ni release autocontenida.

Detalles: [contrato UI](h11-overlay-ui-contract.md), [arquitectura](h11-architecture-review.md), [animaciones](h11-animation-notes.md), [comparación](h11-comparison.md) y [bloqueo Browser](h11-browser-spike.md).
