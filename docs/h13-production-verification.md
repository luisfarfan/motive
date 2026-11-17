# H13 — verificación incremental

H13 está en desarrollo. Este informe distingue incrementos observados de la
aceptación completa: todavía no acredita producción GPUI integrada, sincronía
A/V de captura SCK, sesión prolongada ni regresiones del bundle final.

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

## Incremento 2: audio del sistema y micrófono

Bundle firmado SHA-256
`be13f8555e1e06087be0d443e4040b23acf497337f43f5f363150119cb3ffd3d`.
El inventario inicial detectó un error real de serialización: un booleano ObjC
se emitía como número JSON. Se corrigió el tipo explícito, conservando
`var/evidence/h13-build/system-inventory-failure.json`. Las pruebas siguientes
usan la aplicación propia `local.motive.audiofixture`, con AVAudioEngine y tono
997 Hz; el segundo tono de Motive es 440 Hz. No se cambió volumen ni ruteo global.

Piloto MKV PASS: `var/evidence/h13-system-audio-1794932404437443000/report.json`.
24,64 s de PCM decodificado, 741 frames, pico −23,72 dBFS. Cambios solicitados
de −12 dB producen −11,993 dB en el tono y −11,992 dB en audio de aplicación.
Mute/unmute de cada canal conserva el otro. Mediana RMS de bloques de 20 ms:
error −0,068 dB en tono aislado y −0,006 dB en sistema aislado; error peak
respectivo +0,027/+0,014 dB. Sin clipping, render lag, skips ni drops.

Matriz `h13-system-audio-1794932515805158000/report.json`:

- RTMP local PASS: 751 frames, audio presente con ganancia/mute y medidores
  independientes; gaps AAC ≤22 ms e interior de video ≤34 ms.
- Recuperación PASS: cerrar y reabrir la aplicación cambia PID; el canal queda
  bloqueado hasta reconexión explícita, mientras el tono y la salida continúan.
- Silencio PASS: ceros digitales y AVAudioEngine pausado no se confunden con
  desconexión. SCK siguió entregando paquetes de ceros; este ensayo **no** ejercita
  físicamente `awaiting_audio` por falta de paquetes.
- El primer analizador de transiciones midió toda la placa en vez de su franja
  de color. Corrección geométrica, mismo medio y mismos gates: PASS en
  `transitions-reanalysis.json`; 258 frames menta, 148 rojos, 37 mezclados.

Nueva ejecución `h13-system-audio-1794932730872027000/report.json`:
Cut/Fade y persistencia PASS. Mixer v2 conserva identidades y reutilización sin
modificar proyecto ni perfiles. Las colas finales VT de hasta 133 ms permanecen
registradas; no se presentan como cadencia constante hasta el último frame.

Micrófono físico PASS: `h13-system-audio-1794932987734593000/report.json`.
Selección explícita `BuiltInMicrophoneDevice`, cinco intervalos mezclado/aislado/
mute/restaurado, 547 frames, 18,176 s de PCM, pico −18,75 dBFS, cero lag/skips/drops.
La recaptura acústica del fixture por el micrófono fue intencional y controlada;
no equivale a demostrar ausencia de realimentación del propio proceso.

**Gate A/V abierto:** los PTS continuos no bastan para probar sincronía perceptual.
La prueba de pulsos conserva dos fallos de contenido: la primera captura quedó
congelada; la segunda avanzó 491 veces y se congeló a los 21,233 s durante
12,934 s, aunque el audio y `drawRect` seguían avanzando. Evidencia:
`h13-system-audio-1794933205287443000/report.json` y `offline-av-diagnosis/audit.json`.
Se corrigió previamente el `vsync` del analizador para comparar frames originales,
sin ocultar el fallo real posterior. La causa no está atribuida a SCK, WindowServer
ni App Nap; siguen pendientes comparación con snapshots locales y visibilidad.
Los ensayos siguientes acotan ese gate a las condiciones visibles probadas;
no explican ni borran los congelamientos previos.

Exclusión propia PASS en
`h13-self-audio-exclusion-1794934285059972000/report.json`, bundle `dc9c38a…`.
Emisor AVAudioPlayer dentro de Motive, opt-in `MOTIVE_TEST_SELF_AUDIO=1`,
2011 Hz/−30 dBFS; fixture externo 997 Hz/−30 dBFS y luego 2011 Hz al mismo nivel
como control positivo. Solo escritorio principal en el mixer, sin monitoreo.
El tono propio queda por debajo del gate de −45 dB relativo al control positivo;
la estimación espectral fue −122,74 dB (limitada por el piso del análisis).
401 frames, AAC sin gaps >22 ms, sin clipping/lag/skips/drops. Motive se cerró
normalmente y volvió a abrir **sin** el emisor al terminar.

Los intentos previos de ese verificador permanecen: `1794934183628345000`
no alcanzó el estudio; el primer launcher no aislaba su grupo de procesos y
dejó un socket obsoleto. Se verificó ausencia de proceso/conexión antes de
retirarlo. `1794934251673534000` falló antes de capturar por `codesign --strict`:
el bundle local usa un symlink externo de Frameworks OBS. La firma ordinaria
sí pasa; strict se conserva como resultado y límite de portabilidad, sin
confundirlo con corrupción de firma ni modificar los gates multimedia.

A/V visible PASS, mismo bundle, dos ensayos:

- `h13-system-audio-1794934345250779000/report.json`: snapshots NSView opt-in
  y acción CUA Raise; siete pulsos, mediana audio−video −35,83 ms, rango de
  desfase 33 ms. Los snapshots redibujan y pueden influir la publicación.
- `h13-system-audio-1794934414391892000/report.json`: sin snapshots, ventana
  elevada mediante CUA; siete parejas de pulsos, mediana −67,48 ms, rango 0 ms.

Gate por pulso: |desfase| <250 ms y rango <100 ms. Mide alineación de extremo a
extremo, incluida latencia de reproducción y redraw, no latencia cero. La
visibilidad es una condición observada, **no** una causa demostrada del fallo.
Quedan los logs, snapshots y timestamps de Raise para contrastar. No se cambió
Stage Manager, permisos ni otra configuración global.

## Incremento 3: primer ensayo de salidas independientes

Bundle SHA-256
`dc9c38a82d72c86cacd668a88c25ec26f0e12cbbb7b9d0c829d3e820a20ef38f`;
67 tests Rust, Clippy y rustfmt PASS. `scripts/verify_h13_outputs.py --lock-held
--stage smoke` ejercita dos pares VT/AAC con perfiles distintos sobre el mismo
canvas 1080p30, fuentes y mezcla. Detener/reiniciar RTMP conserva grabación;
detener grabación conserva RTMP. Barreras terminales observadas por destino.

Control/lifecycle y los tres medios PASS:
`var/evidence/h13-outputs-1794933571099068000/reanalysis-1794933732548210000/report.json`.
El informe original conserva un fallo del verificador: recortaba PCM por PTS
original y luego `-t 1` descartaba muestras con PTS mayor de un segundo.
Se añadió `asetpts=PTS-STARTPTS` únicamente al sink PCM tras el recorte; se
reanalisaron los archivos originales, sin cambiar umbrales ni producción.
Matriz posterior `h13-outputs-1794933990447407000/report.json`: los cuatro casos
de control/lifecycle pasan, incluidos widgets/Cut/Fade, pérdida de receptor y
muerte del helper muxer propio. La salida superviviente conserva recursos y
continúa; recuperación por destino es explícita. Once de doce medios pasan.

**Fallo real retenido:** en el primer MKV aparece un hueco inicial de 1024
muestras, 0,311083–0,332417 s. El intervalo RMS de 100 ms incumple el margen de
1 dB (−34,076 frente a −33,010 dBFS). El centro del hueco cae a −104,2 dBFS y
la fase posterior se retrasa exactamente un bloque de audio; ocurre antes de
iniciar RTMP. PTS AAC continuos no ocultan esta pérdida. El primer smoke del
mismo binario no la presenta. Diagnóstico:
`offline-audio-diagnosis-1794934472450720000/report.json`. No se relajó el gate;
la instrumentación y corrección posterior se describen a continuación. Este
informe original permanece FAIL.

## Incremento 4: tono con margen de entrega y matriz dual completa

La traza localizó el bloque cero antes de AAC, con muestras fuente continuas.
En dos casos documentó disponibilidad insuficiente justo al deadline. Entregar
el tono determinista 20 ms por adelantado conserva PTS/fase y permite a libobs
consumir bloques completos; no cambia micrófono/SCK ni buffering global.
[Investigación, límites y A/B](h13-audio-startup-investigation.md).

Nuevo bundle firmado SHA-256
`0444029860e28e53b7e74fc0ab836fa790cc8a691f2f7cfc95702cd9e6ac3952`:
69 tests Rust, Clippy `--all-targets -- -D warnings`, rustfmt PASS. Tres vidas
instrumentadas: cero bloques silenciosos frente a uno por vida anteriormente;
7576 bloques fuente y 3548 de mezcla observados, cadencia original de 10 ms.
Tres MKV y seis RTMP pasan los gates originales.

Después de cerrar y abrir Motive **sin variables de diagnóstico**, la matriz
completa pasa en `var/evidence/h13-outputs-1794935484169154000/report.json`:
cuatro casos de control/lifecycle y los doce medios; sin errores de análisis ni
limpieza. Los fallos intencionales conservan su distinción de archivo parcial.
Cut/Fade, widgets, gain/mute, supervivencia del otro destino y recovery se
verifican por comandos y medios. No se reutiliza el PASS instrumentado como
medición de rendimiento normal.

GPUI: controles independientes compilados y panel observado visualmente a
1440 px en `var/evidence/h13-ui-increment/outputs.png`; aún no equivale al
recorrido de producción final ni a la comprobación de tamaño compacto/cierre.
Las mediciones posteriores están en la [investigación de rendimiento y colas](h13-encoder-tail-investigation.md).
Sesión prolongada y regresiones finales continúan pendientes.

## Incremento 5: rechazo de identidades de audio malformadas

La revisión encontró que un ID numérico con ceros iniciales podía superar el
buffer nativo al restaurar una captura retenida. El almacén ahora exige la forma
canónica `audio-N` antes de cualquier mutación; el puente nativo también rechaza
un renombrado truncable. Los IDs emitidos por Motive v1/v2 no cambian.

Bundle firmado SHA-256
`f9e0b2865817a08c3fb62afa43f5b4c7becddb2087b57a1902087ca20745570c`:
70 tests Rust, Clippy de todos los targets y rustfmt PASS. Logs
`var/evidence/h13-build/audio-id-*.log`. Prueba contra el núcleo real en
`var/evidence/h13-audio-id-validation-1794937378949652000/report.json`:
dos almacenes inválidos producen `INVALID_AUDIO_STORE`, conservan documento e
instancia de la fuente y permiten controlar después su ganancia. Se restaura
la ausencia original del archivo de mixer y se retira la entrada de prueba.
Los dos ensayos previos conservan errores del harness (exit code esperado y
ubicación del snapshot runtime), sin atribuirlos a fallos del producto.

La preparación GPUI anterior queda registrada como preparación, sin salidas
iniciadas, en `var/evidence/h13-native-1794936995861463000/`. No acredita la toma
dual final. La ventana compacta 1024×780, temas y cierre idle por Cmd+Q/menú sí
se observaron en `var/evidence/h13-ui-increment/`; cierre con salidas pendiente.
