# H13 — verificación incremental

H13 está en desarrollo. Este informe distingue incrementos observados de la
aceptación completa: todavía no acredita producción GPUI, audio del sistema,
dos outputs, sesión prolongada ni regresiones del bundle final.

## Incremento 1: canvas real y coordenadas persistentes

Bundle firmado local de la rama `codex/h13-live-production`, base `b52d135`:
SHA-256 `914aa8e98371127ed1fef43b0a0497dd558c8d7326b5dae6fb3c92cee785911e`.
Pruebas bajo el lock canónico de `motive/var/run/physical-test.lock`, seriales,
sin dispositivos físicos ni fuentes privadas. 62 tests Rust, Clippy
`--all-targets -- -D warnings` y rustfmt PASS antes del bundle.

`scripts/verify_h13_video.py` controla la misma instancia mediante MCP y contrasta
PID/capacidades mediante CLI. Configura canvas, guarda/carga proyecto v5, rechaza
reconfiguración durante grabación y conserva las instancias de fuentes durante
Cut/Fade. Fuentes propias: patrón animado, texto, círculo, PNG con alpha y tono.
FFmpeg decodifica íntegramente H.264/AAC; ffprobe inspecciona todos los PTS.
El centro de un objeto en movimiento distingue 60 frames nuevos de duplicar 30.

Primer piloto: `var/evidence/h13-video-1794931927017680000/report.json`.
El verificador falló porque FFmpeg no acepta `.3` como argumento de seek;
se corrigió a `0.3` sin alterar gates ni el medio. El análisis completo del
mismo archivo pasa en `h13-video-reanalysis-1794931968077763000/report.json`.
Un intento anterior empezó antes de abrirse el socket y conserva
`STUDIO_UNAVAILABLE` en `h13-video-1794931916396692000/report.json`.

Matriz completa posterior PASS:
`var/evidence/h13-video-1794931993726668000/report.json`.
Cada grabación dura aproximadamente 11 segundos; esto no es una prueba larga.

| Canvas / encoder | Frames decodificados | CPU mediana (%) | RSS mediana (MiB) | Máximo gap video (ms) |
|---|---:|---:|---:|---:|
| 1280×720 30 / VT | 334 | 50.0 | 208.1 | 34 |
| 720×1280 30 / VT | 336 | 50.3 | 209.5 | 67 |
| 1920×1080 30 / VT | 337 | 53.7 | 282.1 | 66 |
| 1080×1920 30 / VT | 333 | 61.8 | 282.7 | 34 |
| 1920×1080 60 / VT | 667 | 58.3 | 282.8 | 67 |
| 1080×1920 60 / VT | 651 | 74.5 | 260.7 | 66 |
| 1920×1080 30 / x264 | 336 | 69.8 | 942.1 | 34 |

Las siete ejecuciones conservan cero render lag, video skips y output drops.
Los huecos de 66–67 ms ocurren en la cola final; se conservan explícitamente,
con gate de interior <1,5 intervalos y cola <150 ms. Los pulsos observados del
objeto avanzan en las 59/59 comparaciones a 60 FPS y 29/29 a 30 FPS. Ambos Fade
tienen múltiples frames mezclados; los Cut no introducen un tramo mezclado.
AAC mantiene gaps ≤22 ms y tono audible continuo incluso durante transiciones.

CPU corresponde al proceso Motive debug con GPUI/preview y observador; RSS se
muestra por sondeo, no incluye todos los helpers ni garantiza capturar cada
pico. No es un ensayo ABBA ni prueba una optimización. El coste de x264 y la
comparación de cargas representativas necesitan medición posterior.

Persistencia: v1–v4 siguen representando 540p30 y los mismos números. v5 declara
`video.version=1` y `coordinate_space=design960`; las transformaciones de ambas
orientaciones permanecen independientes. Mezcla v1/v2 y perfiles v1 tienen sus
stores separados. El motor compone a resolución real; no cambia únicamente
el tamaño codificado de un compositor 540p.

Límites de este incremento:

- Cámara conserva preset 720p y cadencia propia; esta matriz no prueba webcam
  ni captura de ventana a 60 FPS.
- El raster intrínseco de texto/widget/imagen no gana densidad automáticamente
  al ampliar canvas. Se verificó ubicación/proporción y contenido decodificado.
- SCK toma FPS al crear stream. La fuente OBS se retira antes de renovarse;
  el cierre SCStream upstream es asíncrono. Solapamiento transitorio no medido.
- Preview sigue usando BGRA por CPU a resolución de salida y sondeo GPUI de
  33 ms. Un preview de 30 Hz no dirige ni limita el reloj del compositor de 60.
- La implementación inicial de entradas SCK está compilada y tipada, pero aún
  necesita sus grabaciones reales y operación GPUI antes de declararse verificada.
