# H13 — verificación incremental

H13 está implementado con **aceptación final EN CURSO**. Este informe distingue
incrementos observados de la aceptación completa: todavía no acredita el
recorrido GPUI integrado ni sesión prolongada. Las regresiones H1–H12 reúnen
23/23 PASS en sus últimas ejecuciones G, con metrología H10 revisada y fallos
anteriores conservados. A/V tiene evidencia acotada a condiciones visibles;
la exclusión propia final no pasó y su causa sigue sin atribuir. El [índice de evidencia](h13-evidence-index.md)
separa bundles, resultados confirmados y fallos conservados.

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

## Incremento 6: sello de cierre e importaciones en curso

La auditoría encontró que `shutdown` legacy no establecía el guard de cierre y
que las mutaciones tempranas de overlays lo omitían. El núcleo ahora bloquea
nuevos trabajos tanto en la fase pendiente como cuando ya está listo para salir.
El cierre también espera una importación existente sin entrar prematuramente
en el `join` de su destructor en el hilo de UI. No cambia el parche RTMP H8.

Bundle SHA-256
`d9b8d7026e301330d62f2f541af90c1dd245a86f79ad1fd8a35e81b08e0e2d93`:
71 tests, Clippy y formato PASS (`h13-build/shutdown-gate-*.log`). La prueba
de ventana estrecha por sockets no reprodujo un rechazo observable: primer
ensayo conserva un fallo del chequeo de PID del harness, segundo INCONCLUSIVE
por cierre antes de la admisión. No se declara reproducción multimedia de esa
carrera ni se acepta EOF como prueba del guard.

Prueba determinista H8 en
`var/evidence/h13-regressions-1794937943048758000/manifest.json`: PASS, 14 ciclos
y 47,6 s. Con conexión silenciosa y cierre pendiente, los dos arranques dirigidos,
ambos preflights e importación se rechazan con `SHUTDOWN_PENDING`; consultas de
overlays, assets y outputs siguen funcionando, sin incrementar intentos. El
owner sale después de liberar el peer; restauración completa sin errores.

Importación real de clip 1080p/20,27 s mientras se cierra, en
`var/evidence/h13-import-shutdown-1794938158330488000/report.json`: PASS.
29 consultas posteriores observan el mismo worker activo; máximo 88,9 ms,
petición de cierre 30,7 ms. Se observa el resultado `completed` antes de salir
en 3,271 s. Stores intactos y copia propia del inbox eliminada después del cierre.
El primer informe conserva un falso fallo del harness al recibir `TIMEOUT` tras
haber observado el resultado terminal: el servidor usa ese código también al
cerrarse el canal de respuesta. Solo se admite ese límite si ya se vio el final
real y la consulta tardó menos de 1 s; no se usa para inferir un worker terminado.

Al cierre de ese incremento, la aceptación GPUI y el resto de regresiones
seguían pendientes. Las repeticiones siguientes actualizan esa cobertura.

## Incremento 7: repetición en G y regresiones H1–H12

Todas las ejecuciones de esta sección identifican el mismo bundle **G**,
SHA-256 `d9b8d7026e301330d62f2f541af90c1dd245a86f79ad1fd8a35e81b08e0e2d93`.
Son lecturas de los informes reales ya conservados; no se generaron medios
nuevos ni se modificaron resultados para actualizar la documentación.

### Regresiones H1–H12: 23/23 últimas ejecuciones PASS

El conteo combina suites distintas ejecutadas en G, no presenta los manifiestos
interrumpidos como aprobados. H8 dirigido aporta una; control/control_delivery,
dos; la reanudación desde H1, catorce; H11/H12 restantes, cuatro; el piloto H10
con referencias y la repetición final de mixer, dos. H10 usa la
[metrología revisada](h13-h10-metrology.md): el conteo declara ese cambio de
procedimiento, sin modificar umbrales ni convertir archivos anteriores en PASS.
La matriz de audio SCK descrita debajo es otra suite y no sustituye H10.

| Evidencia | Resultado conservado |
| --- | --- |
| [H8 dirigido](../var/evidence/h13-regressions-1794937943048758000/manifest.json) | PASS, según incremento 6. |
| [Primera tanda](../var/evidence/h13-regressions-1794938214930619000/manifest.json) | Control y entrega PASS; H1 FAIL antes de grabar por `SOURCE_AMBIGUOUS`. |
| [Reanudación desde H1](../var/evidence/h13-regressions-1794938328448756000/manifest.json) | Catorce suites PASS hasta H9; se detiene con H10 audio FAIL. |
| [Intento H10 mixer](../var/evidence/h13-regressions-1794939220662892000/manifest.json) | FAIL antes de continuar las otras cuatro suites planificadas. |
| [H11/H12 restantes](../var/evidence/h13-regressions-1794939397028955000/manifest.json) | H11 runtime/visuals/lifecycle y H12 performance PASS. |
| [H10 con referencias](../var/evidence/h13-regressions-1794940354925977000/manifest.json) | Piloto PASS en 32,9 s; mixer FAIL en 50,7 s por mute mezclado, conservando FAIL global. |
| [Mixer H10 final](../var/evidence/h13-regressions-1794940880710737000/manifest.json) | PASS en 110,0 s; MKV, RTMP, clipping intencional separado y persistencia. |

Los siete manifiestos verifican el mismo hash al inicio/final, restauración
de bytes/modos de stores y cleanup sin errores. H1 falló por una fixture propia
de un intento interrumpido que duplicaba bundle/título bajo LaunchServices;
se retiró solo su PID verificado, según la
[evidencia de limpieza](../var/evidence/h13-regressions-1794938214930619000/owned-fixture-cleanup.json).
La reanudación pasó H1 en 22,2 s y scenes en 33,5 s; el rechazo por ambigüedad y
el informe original se conservan. No se cambió el núcleo para admitir una
selección ambigua. RTMPS continúa probando rechazo de confianza, no entrega
positiva con certificado confiable.

El [pilot H10 original](../var/evidence/h13-regressions-1794938328448756000/reports/verify_h10_audio.py/h10-pilot.json)
falló al comparar muted/lower: 0,517758 dB supera el límite <0,5 dB. El
[mixer H10 original](../var/evidence/h13-regressions-1794939220662892000/reports/verify_h10_mixer.py/h10-mixer.json)
midió −9,621392 dB en la comparación de ganancia del tono, fuera de (−13, −11)
dB. Sus grabaciones y reportes permanecen FAIL.

Los diagnósticos offline de [pilot](../var/evidence/h13-h10-pilot-audio-diagnosis-1794939269396896000/report.json)
y [mixer](../var/evidence/h13-h10-mixer-audio-diagnosis-1794939476988910000/report.json)
reproducen el estimador original y muestran energía variable próxima a 440 Hz
cuando el micrófono está abierto. Otra proyección da resultados distintos,
pero no reemplaza el gate ni prueba la causa acústica/DSP/AAC. El primer
[diagnóstico mixer](../var/evidence/h13-h10-mixer-audio-diagnosis-1794939451029840000/report.json)
tenía un helper sin `return`; sus derivados dB nulos quedan identificados como
`INVALID_DIAGNOSTIC_HARNESS`, sin usarse como evidencia numérica.
La repetición usa referencias mic-muted dentro del mismo archivo, con el
estimador Hann y márgenes originales. El [checker offline](../var/evidence/h13-h10-reference-checker-1794940054296064000/report.json)
rechaza el hueco real histórico de 1024 muestras mediante ventanas RMS de
20 ms cada 10 ms; esa comprobación no cierra por sí sola H10 ni afirma
continuidad de un tono oculto bajo una mezcla más intensa.

La primera repetición cierra el piloto: ganancia aislada −11,990455 dB y errores
RMS máximos de las referencias 0,110634/0,168425 dB. El mixer de esa misma
tanda conserva otro [FAIL físico](../var/evidence/h13-regressions-1794940354925977000/reports/verify_h10_mixer.py/h10-mixer.json):
ratio de mute 440 Hz 0,033069 frente al límite <0,03 con micrófono abierto.
No se atribuye todo el residuo de esa banda al generador silenciado. El
procedimiento final acredita supresión cuantitativa con `both_muted` frente a
una referencia aislada del mismo nivel; conserva el límite 0,03, RMS de ambas
entradas muteadas <−100 dBFS y la etapa independiente de micrófono audible con
tono muteado. Esta última conserva su espectro mixto como diagnóstico, no como
identificación de una única fuente. Para continuidad posterior el tono se
declara a 0 dB con micrófono abierto, contra referencia del mismo nivel.
El [documento de metrología](h13-h10-metrology.md) detalla estímulos, controles,
ventanas, negativos del checker y límites de atribución.

La [corrida mixer final](../var/evidence/h13-regressions-1794940880710737000/reports/verify_h10_mixer.py/h10-mixer.json)
sí ejecuta y aprueba toda la secuencia MKV/RTMP y persistencia. Duraciones PCM:
47,339/47,424 s; ganancia aislada del tono −12,002393/−12,010617 dB; ganancia
del micrófono −11,628350/−12,046635 dB. Error RMS aislado absoluto máximo
0,172369 dB, frente a tolerancia 2 dB; mute aislado del tono mide ratio cero
en ambos medios. Picos −13,272/−17,744 dBFS, gaps AAC ≤22 ms y video ≤34 ms.
El ensayo de saturación deliberada queda separado. Los FAIL anteriores y sus
hashes no se sustituyen por estos nuevos medios ni por reanálisis offline.

### Canvas G: siete casos reales PASS

[Matriz G](../var/evidence/h13-video-1794939774901717000/report.json): mismo
alcance controlado de patrón, texto, PNG, círculo, Cut/Fade y tono; persistencia
v5 y rechazo de reconfiguración durante salida. Los siete casos pasan con
3019 frames decodificados y cero render lag, video skips y output drops.

| Canvas / encoder | Frames | CPU mediana (%) | RSS mediana (MiB) | Máximo gap video (ms) |
| --- | ---: | ---: | ---: | ---: |
| 1280×720 30 / VT | 333 | 49,9 | 221,7 | 67 |
| 720×1280 30 / VT | 333 | 49,4 | 223,0 | 67 |
| 1920×1080 30 / VT | 336 | 52,1 | 297,8 | 67 |
| 1080×1920 30 / VT | 336 | 57,7 | 298,3 | 67 |
| 1920×1080 60 / VT | 672 | 54,2 | 298,3 | 34 |
| 1080×1920 60 / VT | 672 | 70,7 | 298,5 | 34 |
| 1920×1080 30 / x264 | 337 | 65,6 | 973,5 | 34 |

Interiores ≤34 ms a 30 FPS y ≤17 ms a 60 FPS; las colas superiores se conservan.
El objeto avanza en 29/29 y 59/59 comparaciones respectivamente. Cada Fade
contiene múltiples frames mezclados. AAC mantiene gaps ≤22 ms. CPU/RSS siguen
describiendo Motive debug con GPUI/preview y observador, no los helpers ni una
comparación ABBA. No acredita cadencia de una webcam/ventana ni operación GPUI.

### Audio SCK G: siete etapas PASS

[Matriz G](../var/evidence/h13-system-audio-1794940056194848000/report.json):
pilot, RTMP, recovery, silence, transitions, persistence y microphone pasan en
una misma ejecución con 4080 frames. La selección física explícita usa
`BuiltInMicrophoneDevice`; la recaptura acústica del fixture sigue siendo
intencional y controlada.

| Etapa | Frames | PCM (s) | Pico (dBFS) | Máximo gap video (ms) |
| --- | ---: | ---: | ---: | ---: |
| Pilot MKV | 734 | 24,405 | −23,923 | 133 |
| RTMP local | 761 | 25,323 | −23,866 | 66 |
| Recuperación de aplicación | 443 | 14,720 | −20,234 | 67 |
| Silencio/pausa | 1056 | 35,136 | −23,660 | 134 |
| Cut/Fade | 437 | 14,507 | −23,810 | 133 |
| Persistencia mixer v2 | 107 | 3,520 | −23,952 | 133 |
| Micrófono físico | 542 | 18,005 | −12,622 | 34 |

Los pasos −12 dB del pilot miden −11,987714 dB en tono y −11,994891 dB en
aplicación; RTMP mide −11,995843/−11,996329 dB. En los cuatro intervalos
aislados, el error RMS absoluto máximo es 0,022856 dB y el error peak máximo
0,029779 dB. Mute conserva la otra entrada y la recuperación exige acción
explícita tras cambiar el PID de la aplicación. Cut/Fade conserva audio y
registra 258 frames menta, 144 rojos y 37 colores mezclados distintos.
Persistencia conserva proyecto/perfiles y restaura mixer v2.

Sin clipping, render lag, video skips ni output drops observados; AAC ≤22 ms,
interior de video ≤34 ms. No se ocultan las colas de hasta 134 ms ni se presentan
PTS continuos como medida perceptual de sincronía. SCK entregó ceros durante
silencio/pausa: 22 observaciones de ceros y ninguna `awaiting_audio`. Esta
ejecución no incluye etapa A/V ni emisor propio de Motive; las evidencias de
exclusión/A/V visible del bundle C siguen separadas. Tampoco prueba hot-unplug,
revocación de permisos, ventana oculta o sleep/wake.

### Salidas duales G: cuatro casos y doce medios PASS

La [matriz final G](../var/evidence/h13-outputs-1794940477678855000/report.json)
repite smoke, producción, pérdida de receptor real y pérdida del helper muxer
propio. Pasan los cuatro casos de control/lifecycle y los doce análisis de
medios, sin errores de análisis o cleanup y con el mismo hash al terminar.
Diez archivos se clasifican como completos y dos como parciales esperados
por el fallo inducido; esos parciales no acreditan finalización limpia.

Se observan stop/restart/recovery por destino sin perder la otra salida,
recursos compartidos estables, ganancia/mute, edición/widget y Cut/Fade.
Ocho comparaciones de intervalos comunes contrastan video y RMS entre MKV y
RTMP. La fixture usa patrón y tono, perfiles independientes y compositor
1080p30. No contiene dispositivos de captura ni audio SCK; la ejecución usa
CLI/MCP y no sustituye el recorrido GPUI. El caso de producción ronda un minuto,
no una sesión prolongada.

### A/V visible G y exclusión propia final

La [toma A/V G](../var/evidence/h13-system-audio-1794941016583790000/report.json)
pasa con la fixture visible activada mediante Finder/CUA y sin snapshots
diagnósticos. Siete pares de pulsos: mediana audio−video **+24,270833 ms**,
rango **33 ms**, dentro de los gates |desfase| <250 ms y rango <100 ms.
Incluye latencia de reproducción/redraw y mide alineación de extremo a
extremo; no acredita latencia cero ni explica los congelamientos históricos.

La [exclusión propia final](h13-system-audio-exclusion-final.md) tiene resultado
distinto: **ensayo G FAIL, atribución INCONCLUSIVE**. El
[reporte original](../var/evidence/h13-self-audio-exclusion-1794940665168715000/report.json)
mide supresión 2011 Hz de −16,412088 dB frente al gate <−45 dB. El diagnóstico
encuentra fondo adicional de banda ancha y tres bloques saturados en la
entrada, aunque el contador de mezcla final es cero. No permite atribuir
el residuo exclusivamente a Motive ni confirmar una regresión concreta de
ScreenCaptureKit. Tampoco permite dar por cumplida la exclusión. Se conservan
el PASS de C y FAIL de G, sin sustituir el criterio, filtrar el fondo ni
identificar contenido ajeno. El agregado 23/23 de regresiones no cierra este
gate específico H13.

### Probe de memoria G: finalizado, sin gate de RSS

El [probe dirigido](../var/evidence/h13-video-memory-1794940705116187000/report.json),
documentado en el commit `89eed5e`, usa el mismo bundle G y un owner fresco a
540p30, sin outputs ni captura física. Baseline → cuatro videos H11 visibles →
cuatro IDs reemplazados → cero videos durante 20 s. Resultado
`PROBE_COMPLETED_NOT_A_MEMORY_BUDGET_PASS`; proyecto, bytes/modos y stores
restaurados, asset/inbox propios retirados. No es un ensayo equivalente a todo
H12 ni una aceptación de memoria limitada.

| Fase | RSS mediana (MiB) | CPU mediana (%) |
| --- | ---: | ---: |
| Baseline | 178,41 | 34,93 |
| Cuatro visibles | 673,55 | 63,59 |
| Cuatro reemplazados | 1030,91 | 61,69 |
| Cero, espera 20 s | 1141,38 | 36,32 |

Sin lag en esas fases, con avance de los videos y destrucciones nativas
balanceadas; el RSS global observado alcanza 1250,69 MiB. `vmmap` se toma
fuera de las fases y puede influir en residencia posterior. Asignaciones
activas malloc vuelven cerca del baseline mientras quedan páginas residentes
y fragmentación contable: es compatible con retención, sin demostrar una
fuga ni su ausencia. La [investigación de memoria](h13-encoder-tail-investigation.md)
conserva vmmap, métricas, logs de destrucción y límites; no se añadió purge ni
optimización del producto.

**Pendiente:** aceptación de producción GPUI dual y sus flujos de cierre,
sesión prolongada con medios/restauración y aceptación de exclusión propia en
condiciones de audio controladas. Las 23/23 últimas regresiones, matrices y
probes no declaran H13 completo.
