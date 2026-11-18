# H14 — B3: verificaciones H13 adicionales

Consolidación final de nueve ejecuciones sobre el portable B3: **seis PASS,
un FAIL y dos INCONCLUSIVE**. Pasan importación durante cierre, video 7/7,
outputs 4/4, micrófono + sistema en una toma separada, A/V y autoexclusión. La secuencia de audio sigue
FAIL y conserva seis subtrials `ok=true` de alcance parcial: la captura de
aplicación ya falla durante el sexto, `silence`, antes del rechazo del siguiente
start. La cola de cierre conserva sus dos INCONCLUSIVE. No se declara la beta
ni toda H13 aceptadas.

Esta revisión es offline: JSON, metadatos y copias de evidencia. No abrió
Motive, consultó un owner, capturó dispositivos, compiló ni volvió a decodificar
medios. Los originales permanecen sin modificaciones. El
[índice de evidencia retenida](../var/evidence/h14-b3-h13-additional-index-01/index.json)
registra hashes completos de cada primario y contexto, además de comprobaciones
de identidad, estado final y stores. Sus copias se verifican contra los bytes
de los originales; las respuestas negativas dentro de los ensayos no se
reinterpretan automáticamente como errores del runner.
Se verificaron **32 pares original/copia**. SHA-256 del índice final:
`2e569b6520fecdec4e87a6e39fbaca6f4ca323d83b1b6b79b1de7db5f8007bfa`.

## Identidad y alcance

Bundle: `/Users/luisfarfan/Developer/motive-h14-portable/b3/Motive.app`.
Ejecutable/cliente único: `Contents/MacOS/motive`, SHA-256
`797b9722b0fe4725b13d5ccd1d2868c21d8f2cfa7ca3db784fee6297504549dc`.
Fuente compilada: `d0deeb57e3526eb4f7d6fe00718a56f2b5516e1d`.
Los contextos de cada owner coinciden con su PID, ejecutable y hash del
primario. El coordinador mantuvo el lock físico canónico H14. Los tres ensayos
de cierre comenzaron con proyecto v3, canvas 960×540@30, mixer vacío y ambas
salidas idle sin workers ni attempts anteriores.

Las primeras tres invocaciones fueron directas. Sus primarios conservan la
clasificación y el estado observado, pero no un campo de exit code del proceso
Python. El coordinador observó las salidas correspondientes 0/2/2; no se
presenta un hash de script tomado posteriormente como recibo histórico de su
ejecución. La matriz de video usó el wrapper de evidencia
`var/evidence/h14-b3-h13-adapter-01/run_case.py`, congelado SHA-256
`0f284f7c8f37d12d965fdb065fa3f9e7dc80e6e77160792128d86c9221102c79`.
Los casos posteriores identifican su propia versión del wrapper; no se
atribuye retroactivamente una revisión posterior al caso de video.

## Resultados recibidos

| Ensayo | PID | Resultado primario | Evidencia |
|---|---:|---|---|
| Importación durante cierre | 99622 | PASS | [1794962426301978000](../var/evidence/h13-import-shutdown-1794962426301978000/report.json) |
| Cola de cierre, intento 1 | 482 | INCONCLUSIVE / TIMEOUT | [1794962472652645000](../var/evidence/h13-shutdown-queue-1794962472652645000/report.json) |
| Cola de cierre, intento 2 | 920 | INCONCLUSIVE / TIMEOUT | [1794962486972039000](../var/evidence/h13-shutdown-queue-1794962486972039000/report.json) |
| Matriz de video, siete casos | 1131 | PASS; wrapper CASE_PASSED | [1794962576072148000](../var/evidence/h13-video-1794962576072148000/report.json) |
| Outputs, cuatro casos | 3748 | PASS; wrapper CASE_PASSED | [1794962758123624000](../var/evidence/h13-outputs-1794962758123624000/report.json) |
| Audio, secuencia de siete stages | 6438 | FAIL; seis subtrials parciales `ok=true` | [1794962952647193000](../var/evidence/h13-system-audio-1794962952647193000/report.json) |
| Micrófono + sistema, owner separado | 8140 | PASS; wrapper CASE_PASSED | [1794963108797859000](../var/evidence/h13-system-audio-1794963108797859000/report.json) |
| A/V con ventana propia, owner separado | 8850 | PASS; wrapper CASE_PASSED | [1794963171025778000](../var/evidence/h13-system-audio-1794963171025778000/report.json) |
| Exclusión del audio del propio proceso | 9569 | PASS; wrapper CASE_PASSED | [1794963244134535000](../var/evidence/h13-self-audio-exclusion-1794963244134535000/report.json) |

### Importación y cierre: PASS

Comando: `verify_h13_import_shutdown.py --lock-held --clip
var/evidence/h12-performance-1794960760985746000/owned-1080p.mp4
--timeout-seconds 90`, con ruta absoluta y entorno portable explícito.
El clip propio H12 es H.264 1920×1080@30, 6 s/180 frames y 10,979,077 bytes;
SHA-256 `4360a3700b88afa0d7b3b7493b292e243832d40b7c7ae122368d4118ae171b92`.
No se generó una carga artificial ni se añadió demora al worker.

- Enqueue de importación: **42,37 ms**; respuesta a shutdown: **31,25 ms**.
- La operación 1 seguía `running` al responder shutdown y en **cinco** status
  posteriores; esas respuestas tardaron **34,41–49,13 ms**, todas por debajo
  del gate original de 1 s.
- Se observó después el receipt `completed`, con asset de video 1080p/6 s,
  sin audio. La siguiente consulta devolvió TIMEOUT en **65,87 ms** durante
  el límite de cierre. Aquí el contrato permite ese límite solo después del
  receipt terminal observado; no se usa TIMEOUT como prueba de finalización.
- El PID salió **0,752976 s** después de solicitar shutdown. Ambas salidas
  permanecieron idle sin workers ni attempts. `ok=true`, `outcome=PASS`,
  `cleanup_errors=[]`; el inbox privado propio fue eliminado.
- Proyecto y mixer conservaron exactamente sus hashes, tamaños y modos
  `0644`; perfiles permaneció ausente. El hash final de B3 es el inicial.
  El catálogo cambió de 34 a 362 bytes por el asset importado y se conserva;
  esto no se presenta como igualdad del catálogo ni eliminación del asset.

Hash del primario retenido:
`a7a722bfd9d9bd3ff56fe3b4d69698ffe12df1f2087c8f3218954acd5df703d5`.
Esta aceptación cubre solapamiento real, capacidad de respuesta del owner y
cierre después del worker; no demuestra por sí sola reproducción del asset,
integridad de outputs o ausencia de toda condición de carrera posible.

### Cola de cierre: dos INCONCLUSIVE preservados

Comandos: `verify_h13_shutdown_queue.py --lock-held --attempt 1` y `--attempt 2`,
en owners nuevos y distintos. Ambos preflights de grabación eran válidos;
se envió shutdown y, por otro socket, un start de grabación encolado.

En ambos se observó `shutdown_pending=true`, salida del PID y **cero MKV
nuevo**. El start encolado respondió `ok=false`, `error.code=TIMEOUT`.
No se observó el rechazo específico `SHUTDOWN_PENDING` exigido para PASS;
tampoco una respuesta suficiente para demostrar el gate de attempts
invariantes en esa solicitud. El resultado se mantiene **INCONCLUSIVE**,
aunque los outputs del shutdown observado estuvieran idle y la app saliera.
No se ejecutarán más intentos del mismo fallo.

El [recibo nativo del segundo cierre](../var/evidence/h13-shutdown-queue-1794962486972039000/normal-shutdown.json)
identifica PID 920, ambos slots idle/`native_busy=false`, attempts null y cero
paquetes observados. Apoya el cierre sin salida, pero no contiene el rechazo
de admisión que falta y no cambia la clasificación.

Hashes de primarios retenidos, en orden:

- Intento 1: `b62cc22e29588e8223a60c19480df8a923a63ecb35037cb234cd633a495c6a1a`.
- Intento 2: `630f495298417a60958c59e05a2cde16c4777fc72adb9cb1d8fc3e64683b3729`.

### Matriz de video: siete PASS

Comando: `verify_h13_video.py --matrix`, sin cambiar los defaults del primer
caso. [Wrapper final](../var/evidence/h14-h13-video-b3-adapter-01/manifest.json):
`CASE_PASSED`, exit 0, assessment sin errores, grupo hijo vacío,
`QUIESCENT_OBSERVED`, `cleanup_errors=[]` y lease liberado. Duración completa
del wrapper: **93,802 s**. Los contextos del primario, wrapper y owner apuntan
al mismo PID 1131 y B3; el binding de insumos de producto coincide con el commit
compilado, sin entradas extra. SHA-256 del primario original, la copia del
wrapper y la nueva copia del índice:
`d64f350edeb38d6165e74cd44b978987e655269a4096dbdb28237b26e82ac24b`.

| Encoder / canvas | Frames decodificados | Gap máximo video | Avances en 1 s | CPU mediana¹ | RSS pico¹ |
|---|---:|---:|---:|---:|---:|
| VT 1280×720@30 | 335 | 34 ms | 29/29 | 37,13% | 208,52 MiB |
| VT 720×1280@30 | 334 | 34 ms | 29/29 | 37,16% | 209,86 MiB |
| VT 1920×1080@30 | 338 | 34 ms | 29/29 | 37,29% | 278,75 MiB |
| VT 1080×1920@30 | 333 | 34 ms | 29/29 | 35,99% | 276,55 MiB |
| VT 1920×1080@60 | 682 | 17 ms | 59/59 | 42,34% | 268,77 MiB |
| VT 1080×1920@60 | 677 | 17 ms | 59/59 | 48,43% | 277,28 MiB |
| x264 1920×1080@30 | 339 | 34 ms | 29/29 | 44,85% | 883,64 MiB |

¹ Muestras `ps` del owner durante cada toma: CPU relativa a un núcleo y RSS
del proceso completo. Los casos comparten owner, en ese orden; no son un
benchmark aislado por encoder, ni physical footprint, ni una prueba de fuga.
Las métricas se derivan de los JSON retenidos, sin un segundo decode aquí.

Todos los MKV contienen H.264 y AAC estéreo 48 kHz con full decode del runner.
Cada caso cumple **lagged=0, video_skipped=0 y output_dropped=0**. Los máximos
gaps AAC son 22 ms. RMS por ventanas de 100 ms del tono queda entre
**0,062963 y 0,063141**; pico máximo **0,098985**, dentro del gate original
sin saturación inesperada. No se excluyó un caso fallido ni se amplió ninguna
tolerancia.

En cada toma se conservaron dos Cut y dos Fade, con la mezcla continua,
geometría/alpha de PNG, texto, círculo y marcador de escena comprobados por
decodificación. Las regiones intermedias de Fade registran 17–20 frames por
transición a 30 FPS y 36–37 a 60 FPS; no se confunden esos umbrales de color
con duración completa del Fade. El patrón móvil avanza en todos los pares
de la ventana de un segundo, incluidos 59/59 a 60 FPS. Esto prueba la fuente
propia generada del ensayo; no certifica captura de otra app ni frescura de
webcam. Los deltas de timestamps A/V de principio/final tampoco prueban
sincronía perceptual sin un evento audiovisual común.

Los hashes/tamaños/modos de proyecto, mixer y perfiles quedaron exactamente
restaurados, y Show Control, destinos y reconciliación permanecieron iguales.
Los backups originales conservaron sus hashes. El catálogo pasó de 362 a
679 bytes por el PNG propio y se retuvo. El wrapper registra honestamente
`runtime_restored=false`: antes de restaurar stores había dos escenas, seis
fuentes y un tono vivo, con ambas salidas idle. El coordinador cerró después
normalmente PID 1131; el
[recibo nativo](../var/evidence/h14-h13-video-b3-close-01/normal-shutdown.json)
corresponde a ese PID. El siguiente caso usa un owner nuevo; no reutiliza ese
runtime alterado.

El runner conserva tolerancias históricas de tail y no cuenta entrega
encoder→plugin→archivo. Los siete medios/hash están enumerados en el índice;
esta consolidación verificó hashes de JSON y backups, no volvió a rehashear
ni decodificar los archivos multimedia.

### Outputs: cuatro PASS y dos parciales intencionales separados

Comando: `verify_h13_outputs.py --lock-held --stage all --recording-encoder
videotoolbox --streaming-encoder videotoolbox`; holds 3 s, steady 8 s y soak 0.
Los samples activos confirman VideoToolbox hardware en ambos slots, canvas
1920×1080@30 y perfiles sin reordering. Se mantiene la grabación a 6 Mbps y
streaming local a 4 Mbps. No se contactó un destino público.

El [wrapper final](../var/evidence/h14-h13-outputs-b3-adapter-01/manifest.json)
es `CASE_PASSED`, exit 0, barrera `QUIESCENT_OBSERVED`, grupo vacío,
`cleanup_errors=[]` y lease liberado; duración **149,460 s**. Usó la revisión
de wrapper SHA-256
`7a90c39634dfcb009464b0fa2e17807d59d1a109dbc0de05d7a27cce236c4ff9`.
Primario original, copia del wrapper y copia nueva tienen SHA-256
`f08f8c2f3ec9999c6c86685a8db48f321ac35314d52b0ba5a137b59ac9330a2e`.
Todos declaran el mismo PID 3748 y B3; el primario conserva `ok=true`,
`cleanup_errors=[]`, `analysis_errors=[]` y hash final del ejecutable igual.

| Caso | Comportamiento observado | CPU mediana¹ | RSS máximo¹ |
|---|---|---:|---:|
| smoke | Grabación sola, dual, RTMP detenido/reabierto y streaming que sobrevive al stop de grabación | 39,27% | 320,28 MiB |
| production | Lo anterior más Cut/Fade, lower third, countdown, alert y ganancia/mute/unmute | 39,58% | 321,09 MiB |
| receiver-loss | SIGTERM solo al receptor propio; grabación continúa, RTMP se recupera y vuelve a detenerse | 39,52% | 261,56 MiB |
| muxer-loss | SIGTERM al muxer propio validado; streaming continúa, grabación se recupera y vuelve a detenerse | 39,33% | 252,17 MiB |

¹ Métricas `ps` del proceso, con el mismo alcance limitado de la tabla de
video. Los cuatro casos registran lagged/skipped/dropped **cero**. Los fallos
intencionales afectan solo el target previsto; no se interpretan como cierre
limpio de ese archivo.

Se analizaron **12 archivos**, 6.358 frames y 2.126 ventanas PCM de 100 ms en
total: diez archivos sanos y dos `expected_partial_file`. Todos los decodes
salieron con código 0; el MKV del muxer terminado prematuramente conserva su
aviso `File ended prematurely`. Ese aviso está permitido únicamente para el
caso parcial intencional, no normalizado ni borrado. Los medios sanos no
registraron stderr de decode. El gap máximo video es 34 ms, AAC 22 ms y el
pico de audio mayor, **−29,23 dBFS**. No se detectó clipping ni dropout en las
ventanas no silenciadas exigidas por el runner; se mantienen sus guardas de
200 ms alrededor de ganancia/mute y sus límites históricos del tail.

En producción, el RMS pasa de aproximadamente **−33,02 a −45,01 dBFS** con
el cambio de ganancia −6→−18 dB; vuelve a −33,02 dBFS al restaurarla. El mute
decodifica ceros (reportados como −240 dBFS por el piso numérico del helper).
Ocho comparaciones de intervalos compartidos MKV/RTMP registran diferencia RMS
absoluta máxima **0,00322 dB** y deriva máxima de sus offsets de video **1 ms**.
Esto compara etapas comunes y no demuestra entrega del tail ni sincronía
perceptual A/V.

El runner eliminó fuentes, escenas, tono y perfiles propios, dejó ambos slots
idle y mantuvo stores y catálogo iguales; se comprobaron también los hashes
de los backups. Conservó un endpoint RTMP loopback y promovió el canvas a v5
al restaurar su configuración, por lo que `runtime_restored=false` sigue
siendo correcto. El coordinador cerró normalmente PID 3748, conservando
[el recibo nativo](../var/evidence/h14-h13-outputs-b3-close-01/normal-shutdown.json),
y abrió un owner nuevo para audio. Ninguna de estas aceptaciones transforma
`complete_healthy_file`, el nombre usado por el runner para los medios sanos,
en prueba de entrega completa encoder→archivo/receptor.

### Audio del sistema: secuencia FAIL, seis subtrials parciales preservados

La corrida `pilot → rtmp → recovery → transitions → persistence → silence →
microphone`, con `--microphone-id BuiltInMicrophoneDevice`, terminó con
**`ok=false`, exit 1 y wrapper CASE_FAILED** tras 128,196 s. Hash del primario,
la copia del wrapper y la copia del índice:
`fb87f2cd197ddc45a30b6247c696b8f4c9cd09f54778e307a06bfc0983ae0779`.
El wrapper es la revisión `7a90c396…c4ff9`; la fixture H13 firmada conserva
SHA-256 `ef87bc704a404a834e0cf3590903e1ec6f11b06debbd7fddd0785a89c7f3f5c2`.
La adaptación portable del observador se hizo antes de la corrida, en
`2026279`; el runner ejecutado registra SHA-256
`8f6307a870a7c425a46c93ebc0f4978be278160d7a7bd86a72fd18a4f62d3e83`.
No se cambió el producto B3 ni se retocaron asserts durante la toma.

Los primeros seis trials tienen `ok=true` y sus medios/análisis completos
retenidos. Se informan como cobertura parcial dentro de la corrida fallida,
sin cambiar su resultado global:

| Trial | Frames | Duración de audio decodificado | Alcance que pasó |
|---|---:|---:|---|
| pilot | 719 | 23,936 s | Tono 440 Hz + aplicación 997 Hz, ganancia, mute/unmute y medidores |
| rtmp | 740 | 24,683 s | Los mismos controles y niveles en el receptor loopback |
| recovery | 441 | 14,677 s | Fixture termina/reabre; tono continúa y aplicación requiere reconexión explícita |
| transitions | 423 | 14,101 s | Dos Cut y dos Fade con las dos señales continuas |
| persistence | 107 | 3,563 s | Mixer v2, IDs/reutilización y restauración sin cambiar proyecto/perfiles |
| silence | 1071 | 35,691 s | Ceros/pausa y ventana temprana de reanudación; tono interno continuo. No prueba continuidad completa de la aplicación |

En estos seis medios los gaps máximos fueron 34 ms video y 22 ms AAC; los
contadores lagged/skipped/dropped fueron cero. Pilot/RTMP midieron el cambio
de −12 dB independiente con errores ≤0,004 dB; los medidores aislados difieren
del decode como máximo **0,01965 dB RMS y 0,03006 dB peak**. En recovery,
997 Hz desaparece al cerrar la fixture, continúa ausente tras reabrirla y
vuelve solo con reconexión; 440 Hz permanece audible durante esos intervalos.
Esto cubre pérdida de aplicación, no desconexión física de un cable.

Silence retiene 25 observaciones de buffers medidos a cero, pero **ninguna
observación `awaiting_audio`**. El propio reporte deja esa cobertura pendiente;
`silence.ok=true` no significa que se probaran todos los estados de ausencia
de paquetes ni que toda la secuencia larga quedara sana después.

El intento siguiente de `start_recording` fue rechazado con
**`AUDIO_NOT_READY`**: `audio-2` (`system_application`) estaba `failed`, con
`APPLICATION_UNAVAILABLE`, medidor stale y edad **16,989 s**. El micrófono
`audio-3` estaba ready. El trial microphone conserva solo su estado anterior
y listas vacías de etapas/eventos: no llegó a tener start, path ni medio.
El [diagnóstico posterior independiente](../var/evidence/h14-system-audio-b3-failure-audit-01/findings.md)
sitúa el primer fallo antes de este rechazo, durante `tone_resumed` del trial
`silence`: MCP 570 aún estaba ready; MCP 571 ya devuelve
`APPLICATION_UNAVAILABLE`, con edad de buffers **161 ms** y `stale=false`.
El chequeo de identidad fija el error y separa la captura antes de evaluar
antigüedad. Los frames quedan en 978.240 y las 70 muestras posteriores del
trial están failed. La edad de 16,989 s al iniciar el micrófono es posterior
a esa separación; no demuestra el disparador inicial.

La fixture 7496 continúa dibujando y aumentando su contador de audio al menos
**16,73 s después** de la primera respuesta fallida, aplicando los límites
causales de relojes conservados por la auditoría. Su temporizador no termina
a los 36 s. El código de salud puede devolver ese error por count cero,
aplicación marcada terminada o PID distinto; no registró cuál condición ocurrió.
No hay causa demostrada de SCK, caché, run loop, autorelease ni salida de la
fixture. En las mediciones ya decodificadas, el tono externo de 997 Hz cae
aproximadamente a 4e−8 en `pulses`/`tail`, mientras continúa el tono interno de
440 Hz. Por ello `silence.ok=true` solo acredita sus aserciones parciales y no
continuidad completa ni un fallo exclusivo del micrófono.

El [derivado de diagnóstico](../var/evidence/h14-system-audio-b3-failure-audit-01/audit.json)
tiene SHA-256 `ecc2502eabc1598c649fe23068b338f567f96479afffb2cdbef060e0a9d12fb3`.
Se añadió después del índice de 32 pares citado arriba; no cambia ningún
primario ni sus valores `ok`, ni volvió a decodificar medios.

La limpieza del runner retiró sus recursos; el
[wrapper final](../var/evidence/h14-h13-system-b3-adapter-01/manifest.json)
registra grupo vacío, `QUIESCENT_OBSERVED`, `cleanup_errors=[]`, lease liberado,
stores restaurados exactamente y catálogo sin cambio. PID 6438 se cerró
normalmente después, con
[recibo nativo conservado](../var/evidence/h14-h13-system-b3-close-01/normal-shutdown.json).
Cleanup satisfactorio no convierte la corrida fallida en PASS.

### Micrófono + sistema en owner nuevo: PASS independiente

La repetición ejecuta solo `--stage microphone --microphone-id
BuiltInMicrophoneDevice` sobre PID 8140 nuevo, con los mismos runner, fixture
y B3. Dura **21,528 s** en el wrapper y conserva `ok=true`, exit 0,
`CASE_PASSED`, grupo vacío, barrera nativa quiescente y cleanup sin errores.
Hash del primario/copia:
`eb59b7acd6d1d720aa2daa4b341cdbe943c555a6bdd34986f43c414faec8d454`.

El MKV contiene **526 frames**, 17,515 s de PCM, gap máximo video/AAC
34/22 ms y pico **−18,65 dBFS**, sin clipping inesperado ni lag/skips/drops.
La prueba recaptura intencionalmente la fixture propia por el micrófono físico
con ganancia +6 dB; no habilita monitoreo. Los cinco intervalos decoded muestran
mezcla, micrófono aislado, ambos caminos de captura muted, sistema aislado y
mezcla restaurada. La amplitud de 997 Hz en el micrófono aislado es 0,03942,
en sistema aislado 0,03159 y con ambos muted cae a **4,98×10⁻⁸**; el tono
interno 440 Hz continúa en todas las ventanas exigidas. No se exige que la
recaptura acústica sume linealmente en amplitud, porque conserva su propia fase.

Stores y catálogo permanecieron iguales; se retiene el
[wrapper](../var/evidence/h14-h13-microphone-b3-adapter-01/manifest.json) y el
[cierre normal de PID 8140](../var/evidence/h14-h13-microphone-b3-close-01/normal-shutdown.json).
Este PASS valida la toma independiente, **no sustituye ni borra** el fallo
al encadenar los siete stages en el owner anterior.

### A/V: PASS en esta toma de ventana propia

`verify_h13_system_audio.py --stage av` se ejecutó en PID 8850 nuevo, sin
`--fixture-snapshots`, redraw diagnóstico ni intervención CUA del coordinador.
El [wrapper](../var/evidence/h14-h13-av-b3-adapter-01/manifest.json) termina
`CASE_PASSED`, exit 0, en **40,752 s**, con la revisión `7a90c396…c4ff9`.
Hash del primario y sus copias:
`8f76c4b72c3b789af9de3f2d34582ff433a9dbdffa9c301f006b683f8655c6fb`.

El MKV retiene **1.051 frames**, 35,029 s de PCM, pico −23,53 dBFS y gaps
máximos video/AAC 34/22 ms. Lagged/skipped/dropped son cero. El análisis
detectó ocho onsets de audio y siete de video, emparejando los siete visuales;
el primero de audio no tiene pareja visual en la lista retenida. La mediana
de audio−video es **−2,75 ms**, con offsets entre −35,75 y −2,75 ms y rango
**33 ms**. Son alineaciones de pulsos comunes observadas en el medio, con la
latencia real de redraw y salida de hardware de la fixture; no una referencia
de latencia cero ni una medida de deriva de reloj durante 30 minutos.

Se observaron 24 buffers medidos a cero, sin `awaiting_audio`; esa cobertura
continúa pendiente. Stores y catálogo son iguales, grupo vacío, barrera
quiescente, cleanup sin errores y lease liberado. Se retiene el
[cierre normal de PID 8850](../var/evidence/h14-h13-av-b3-close-01/normal-shutdown.json).
Esta toma demuestra pulsos visuales/audio de la ventana propia en esas
condiciones; no elimina los fallos o las condiciones no observadas de las
pruebas de captura/foco A/B/A, ni subsana la secuencia de audio fallida.

### Autoexclusión: PASS con controles positivo y negativo

Se abrió PID 9569 con `MOTIVE_TEST_SELF_AUDIO=1`, log stderr explícito y el
display principal selectable observado. El runner usa captura de audio del
desktop, video de patrón propio y monitoreo desactivado; no añade micrófono ni
tono al mixer. El emisor interno reproduce 2011 Hz a −30 dBFS y sus
observaciones del mismo PID muestran reproducción/reloj avanzando durante la
toma. La fixture externa usa primero 997 Hz y después 2011 Hz, a −30 dBFS.

En las cuatro ventanas de cada fase:

- Con 997 Hz externo y 2011 Hz propio, las amplitudes medianas decodificadas
  son **0,0158232** a 997 Hz y **9,63×10⁻⁹** a 2011 Hz.
- Con 2011 Hz externo como control positivo, 2011 Hz aparece con amplitud
  **0,0158233**, mientras 997 Hz cae a 2,29×10⁻⁸.

La relación espectral negativo/positivo registrada es **−124,31 dB**. Es el
contraste de esas ventanas controladas y su piso numérico, no una medición
universal del rechazo analógico. El control positivo evita atribuir la ausencia
del tono propio a incapacidad para capturar esa frecuencia.

El medio contiene **405 frames**, 13,483 s de PCM, pico −35,40 dBFS y gaps
máximos video/AAC 34/22 ms; lagged/skipped/dropped son cero. Firma estricta
registrada con código 0. El
[wrapper](../var/evidence/h14-h13-exclusion-b3-adapter-01/manifest.json) finaliza
`CASE_PASSED`, exit 0, en **16,120 s**, con grupo vacío, ambas barreras libres,
cleanup sin errores, stores/catálogo iguales y lease liberado. Hash primario:
`c9ee07f6525fb093cf1222512d25b33431191e08996a984a20f1baa6065602a3`.

El coordinador cerró normalmente el
[owner con emisor PID 9569](../var/evidence/h14-h13-exclusion-b3-close-01/normal-shutdown.json).
El [contexto del siguiente owner PID 10022](../var/evidence/h14-native-b3-owner-01/context.json)
declara `self_audio_emitter_requested=false` y el mismo hash B3; no se deja
el emisor diagnóstico habilitado para continuar las pruebas nativas.

## Límites que permanecen

- La secuencia de siete etapas de audio conserva FAIL; seis subtrials con
  aserciones parciales `ok=true` y una toma independiente posterior no la
  convierten en PASS.
- Los dos intentos de cola conservan INCONCLUSIVE por falta de rechazo
  `SHUTDOWN_PENDING` observado. No se añadieron reintentos.
- `awaiting_audio` no se observó en silence ni A/V. Desconexión de aplicación
  no equivale a desconexión física. Autoexclusión corresponde al ensayo
  controlado, display y permisos registrados.
- A/V pasó en una ventana propia durante una toma, sin certificar todos los
  escenarios de foco/publicación. Su alineación no se extrapola al soak.

Estas pruebas conservan los asserts y tolerancias H13. Integridad audiovisual,
frescura de captura, sincronía A/V, admisión durante cierre y entrega completa
de paquetes son gates separados. Las aceptaciones aquí no sustituyen la
[matriz H14 de salidas](h14-output-matrix-b3-verification.md), el análisis del
soak ni las 23 regresiones H1–H12 ya consolidadas.
