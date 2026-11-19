# H17 — audio de aplicación y finalización de outputs

Fecha: 2026-11-18. Estado de este alcance: **PARTIAL**. La auditoría corrigió
un defecto reproducible del verificador de colas. No demuestra una corrección
de `APPLICATION_UNAVAILABLE` ni un drain completo de OBS. La matriz real B7
y las grabaciones nativas B7/B8/B9 y suite de audio B9 se distinguen de la
evidencia histórica;
ninguna aceptación de un binario se hereda a otro.

Se conserva el baseline `15ffbad307c5439270130979dae0e9d66d92d700` y toda la
evidencia H14/H15. B6 ensayado tiene SHA-256
`fe58dc5ca406eb0427d40c5b5a47473aad5d251a75f9d87e170eae9b51cd7d47`, procedente
del código runtime `08004138d1f3586e133f78175d8a1528c5fb7b06`. Los resultados
históricos citados son de B6. La auditoría inicial fue offline; las pruebas
posteriores se ejecutan bajo el lock físico canónico, con owner y binario
identificados. El trabajo de colas/audio no modifica OBS ni el mixer.

## Corrección del verificador

El callback `output_packet_observed` incrementa secuencia y contadores antes
de intentar el lock de la traza. Si el último intento no obtiene ese lock,
la traza conservada puede ser contigua pero carecer del último paquete. El
correlador anterior comprobaba continuidad interior, sin exigir alcanzar el
último contador. El reproductor elimina ese último registro y el paquete del
contenedor: el código baseline devolvía una cola presente. No se trata de
evidencia de pérdida de medios en una ejecución; es un fallo del instrumento
demostrado con entradas construidas.

`scripts/verify_h14_output_integrity.py` exige ahora:

- Quiescencia terminal observada antes de comparar el extremo de la traza.
- Comienzo completo desde secuencia 1 para establecer el origen.
- Continuidad de la cola y última secuencia igual a la suma original de
  paquetes observados de video y audio.
- Correspondencia de cada paquete del contenedor con un único despacho.

La pérdida de metadata fuera de una cola retenida completa no se transforma
en una pérdida de medios ficticia. Se conservan todos los contadores, el
umbral de cuantización de 1,1 ms y los brackets originales de stop. Una
observación incompleta sigue sin acreditar la entrega. Las categorías técnicas
históricas del correlador se mantienen para compatibilidad; el estado H17 de
esa cobertura incompleta es **PARTIAL**.

Diez tests del clasificador pasan, incluidos pérdida final de callback,
snapshot activo, origen incompleto, matching duplicado, pérdida pre-stop y
frontera incierta. Los tres reproductores antes/después están en
`var/evidence/h17-output-audio-audit-01/report.json`; el baseline se carga desde
su revisión Git exacta. `tests.log` conserva la ejecución. Estos tests no son
pruebas audiovisuales.

## Reanálisis B6 sin alterar evidencia

Se releyeron los nueve casos de `h15-resume-01/output-matrix-b6/report.json`
y los timelines de los 14 medios. La auditoría verifica los hashes completos
de medios y timelines contra los informes originales, y vuelve a verificar
todos los inputs al terminar. **PASS** de integridad de artefactos y de
reclasificación equivalente; no se ejecutó un nuevo decode.

| Cobertura retenida | Resultado H17 de auditoría | Límite |
|---|---|---|
| Nueve casos funcionales B6 y 14 medios | PASS | Confirma metadata y hashes de la ejecución histórica. |
| Cola normal B6 | PARTIAL | Faltan 14 paquetes trazados: 11 AAC y tres video, todos posteriores/al bracket de stop. |
| Receptor terminado deliberadamente | PARTIAL | Un video y dos AAC ausentes sin bracket normal, mantenidos por separado. |
| Ausencia pre-stop B6 | PASS | No se observa en estas trazas; no absuelve los dos AAC pre-stop H14. |
| Encoder → observador | PARTIAL | No hay identidad temporal de cada unidad pendiente antes del callback público. |
| Matriz física sobre nuevo binario H17 | NOT_EVALUATED | El reanálisis B6 no la sustituye. |

El endurecimiento no cambia ninguna de las 14 clasificaciones históricas. El
JSON conserva cada paquete ausente y los deltas originales encoder/output/
decoded. No se restaron las ausencias para producir igualdad ni se confundió
un archivo del receptor interrumpido con una parada normal.

## Matriz real B7

El propietario del lock ejecutó `var/evidence/h17-output-matrix-b7/` con B7,
SHA-256 `d5b702d8b245a143575a6dd77cc80dc047425139f0ebc16db8c1f8451eb0ad31`.
La revisión `metadata-review.json` lee y fija hashes de sus nueve informes
primarios; no vuelve a decodificar ni modifica los medios. Los nueve casos
funcionales pasan y sus 14 medios tienen decode, cadencia, AAC y clipping
PASS. La entrega completa permanece **PARTIAL** en todos los casos.

En la tabla, cada flecha conserva **observado antes del plugin → presente en
medio**; para video se muestra el número de frames decodificados. Cada celda
separa MKV / RTMP. `packet-count-review.json` conserva también los brackets.

| Caso | Video MKV / RTMP | AAC MKV / RTMP | Paquetes trazados ausentes |
|---|---|---|---|
| VT MKV, stop | 251→251 / — | 394→393 / — | Un AAC post-stop. |
| VT RTMP, stop | — / 249→249 | — / 390→389 | Un AAC post-stop. |
| VT dual, stop independiente | 262→262 / 264→263 | 411→410 / 412→412 | AAC MKV y video RTMP post-stop. |
| x264 MKV, stop | 286→285 / — | 447→447 / — | Un video post-stop. |
| x264 RTMP, stop | — / 285→285 | — / 447→446 | Un AAC post-stop. |
| x264 dual, stop independiente | 326→326 / 329→329 | 511→510 / 515→514 | Un AAC post-stop en cada destino. |
| VT dual, cancel | 262→262 / 253→253 | 411→410 / 397→396 | Un AAC post-stop en cada destino. |
| VT dual, receiver-loss | 266→266 / 247→246 | 417→416 / 387→385 | AAC MKV post-stop; video y dos AAC RTMP sin bracket normal. |
| VT dual, shutdown | 258→258 / 249→249 | 404→403 / 390→389 | Un AAC post-stop en cada destino. |

Son **13 ausencias trazadas normales: 11 AAC y dos video**, todas posteriores
al bracket de stop. El RTMP deliberadamente interrumpido conserva otras tres
ausencias sin bracket y su clasificación separada. No hay ausencia trazada
pre-stop en B7; los FAIL pre-stop H14 permanecen intactos. Todos los casos
conservan `cleanup_errors=[]`.

Las diferencias encoder→decoded son cinco o seis en VT, y una o dos en x264.
Output OBS→decoded es uno en VT dual RTMP, x264 MKV y el receptor interrumpido,
y cero en los demás medios. La igualdad de ese último contador no acredita
entrega de AAC ni vaciado del backlog anterior al observador. No se cambia
OBS, H8, bitrate, reordering ni el bracket para mejorar la clasificación.

El defecto del verificador de metadata tiene **PASS** en su scope offline;
la entrega final es **PARTIAL** por semántica de cutoff observada y backlog
sin identidad. La desconexión deliberada es cobertura de fallo/recuperación,
no un medio completo fallido presentado como stop normal. Son problemas y
gates distintos.

## Grabaciones de los recorridos nativos B7/B8/B9

Los medios originales se decodificaron completos sin modificarlos. Los
comandos, hashes, snapshots y revisiones visuales están en
`var/evidence/h17-native-b7/media-analysis/`,
`var/evidence/h17-native-b8/media-analysis/` y
`var/evidence/h17-native-b9/media-analysis/`. Todos tienen H.264 1280×720 a
30 fps sin B frames, AAC estéreo a 48 kHz, PTS/DTS válidos y gaps máximos de
34 ms en video y 22 ms en AAC. No hay muestras digitales recortadas en
ninguno de los canales. La integridad estructural es **PASS**; la entrega
permanece **PARTIAL**.

| Binario/toma | Video observado → decodificado | AAC observado → contenedor | Peak L/R | Stop → quiescencia |
|---|---:|---:|---:|---:|
| B7 UI, MKV | 3689→3689 | 5766→5765 | −23,924 dBFS | 240 ms |
| B7 UI, RTMP | 3874→3873 | 6053→6053 | −23,895 dBFS | 251 ms |
| B8 hardware, MKV | 2706→2705 | 4228→4228 | −26,826 dBFS | 250 ms |
| B9 UI, MKV | 5716→5715 | 8931→8931 | −23,934 dBFS | 262 ms |

B7 tiene el hash indicado en la matriz anterior; B8 tiene SHA-256
`5cc0fe08c54f7f4d5e166bce18dbe515a31c92ab92793f3c406e94a42fdc3059`.
B9 tiene SHA-256
`7ecf6b28288fed4cc7121d755b435310a59d80ced8268475e8c884e8d0576e24`.
Los anillos de 256 registros sobrescribieron el origen en estas tomas largas.
Las diferencias de contadores no se asignan a pre-stop/post-stop y no prueban
un vaciado completo, aunque drops=0. Encoder−decoded es 5/6 en B7, 6 en B8
y 5 en B9. B9 decodifica 190,467 s de PTS de video desde cero; no presenta
huecos interiores de cadencia.

Los contact sheets B7 muestran patrón→MATCHDAY y la alerta GOOOAL! antes,
durante y después en ambas salidas. Es presencia visual muestreada, no
geometría por frame ni sincronía exacta. La carrera stock450 conserva gate
`NOT_OBSERVED`, clasificada **PARTIAL**: la edición de gain ocurrió después
de completar la operación nativa de 450 ms.
El gol también aparece y se retira en la grabación B9, con la misma limitación
de muestreo. Su propio gate stock450 vuelve a ser `NOT_OBSERVED`; no se
combina con la toma B7 para inventar cobertura concurrente.

B8 usó cámara y micrófono integrados con autorización y escena controlada,
bajo supervisión del propietario. El análisis fue sólo numérico y visual:
sin escucha, transcripción ni identificación de personas. El interior de
mute, sample-time 54–64 s, contiene 500 bloques estéreo de 20 ms al piso
numérico de −300 dBFS; el intervalo bajo −95 dBFS abarca 51,48–66,52 s.
RMS antes (40–49 s) fue −55,029 dBFS y después (70–80 s), −59,509 dBFS.
Los snapshots registran mute, gain −6→−12 y unmute. Sin referencia acústica
calibrada ni reloj alineado, estos datos prueban silencio interior y retorno
de señal, no una atenuación exacta ni latencia de mute.

La botella grande aparece en el preview anterior B8 y ya está retirada al
inicio de la grabación y en los 18 tiles reales de cámara; la botella pequeña
del fondo permanece. Es un cambio preview→grabación, no una retirada dentro
del clip ni una prueba de cámara a 30 fps. El aviso del usuario «Listo» sobre
movimiento y palmadas llegó después del cierre B8: no se atribuyen esos
pulsos a este medio. Sincronía física cámara/micrófono: **NOT_EVALUATED**.
No se publican UIDs físicos ni inventarios; los reportes crudos permanecen
locales en `var/evidence`.

## Causalidad y ownership en OBS 33.0.1

Los archivos exactos inspeccionados y sus SHA-256 se conservan en
`source-identity.json`, junto con los adaptadores nativos de Motive.

1. `libobs/obs-output.c:send_interleaved` incrementa el contador OBS de video
   y llama al observador público antes del callback del plugin. Ese contador
   no confirma escritura ni recepción.
2. `count_streamable_frames` exige un timestamp mayor del medio opuesto.
   Encoder e interleaver pueden ir por delante del observador. Los contadores
   activos no son snapshots atómicos de todas esas etapas.
3. `plugins/obs-ffmpeg/obs-ffmpeg-mux.c:ffmpeg_mux_data` puede desactivar la
   salida al primer `sys_dts_usec >= stop_ts`, antes de escribir el paquete.
4. `plugins/obs-outputs/rtmp-stream.c` tiene cola y sender propios: el cutoff
   se evalúa allí. Escribir el socket no confirma recepción o decode.
5. `plugins/mac-videotoolbox/encoder.c` conserva su salida asíncrona. Los
   deltas anteriores al observador no localizan por sí solos un defecto VT,
   del interleaver o del muxer.

Los dos AAC pre-stop H14 llegaron después de un video que ya cruzaba el
cutoff. La secuencia y el código son compatibles con desactivación al primer
paquete posterior. Permanecen **FAIL** históricos; no se ha demostrado un
drain completo ni se habilita reordering. Los 14 ausentes normales B6 están
del otro lado de la frontera. Ese comportamiento acota la causa a una parada
compatible con los plugins, pero no autoriza declarar entrega completa.

Se conserva `frame_reordering=false`, el rechazo de perfiles con reordering
y la barrera de workers H8. No hay sleeps añadidos, force-stop, cambios de PTS,
flush inventado o reemplazo del reloj audiovisual. Modificar el interleaver
necesita antes una reproducción que identifique los paquetes retenidos y su
relación con el cutoff; estas trazas no aportan esa identidad.

## Audio: qué está demostrado

`native/engine.m` mantiene `obs_reset_audio2`, 48 kHz estéreo y buffering fijo
de 128 ms. La corrección B6 tiene continuidad y siete pulsos A/V históricos.
El reanálisis JSON verifica los reportes B6 de pilot, RTMP, recovery,
transitions, persistence y silence, además de A/V; sus hashes, binario y
resultados por etapa se retienen. No vuelve a decodificar su PCM ni atribuye
esos resultados a H17.

`system_audio_resolve` exige una sola instancia SCK y una sola instancia
AppKit del bundle seleccionado, con PID coincidente. El módulo oficial OBS
elige por bundle en su enumeración propia; Motive vuelve a comprobar el PID
autorizado inmediatamente después de crearlo y antes de conectarlo al mixer.
La falta de objeto válido se rechaza con `obs_obj_invalid`. No se persiste ni
se autoriza silenciosamente un nuevo PID.

`system_audio_target_health` separa pérdida de identidad, instancias múltiples,
permiso, display y stream detenido. Sus diagnósticos B6 conservan PID esperado,
count/PID enumerados, flags `terminated`, presencia del PID fijado, coincidencia
del bundle y subrama exacta. El primer fallo queda fijado y detiene solo esa
entrada. El resto de la mezcla continúa; reconnect es explícito.

La salud de identidad se comprueba antes que la edad de paquetes. Ausencia de
paquetes SCK produce espera y no prueba pérdida de identidad; ceros con
paquetes son silencio observado. Se conserva esa diferencia.

El FAIL H14 de `APPLICATION_UNAVAILABLE` tuvo muestras recientes y la fixture
siguió dibujando y produciendo audio al menos 16,73 s después. Su registro no
contiene qué subrama rechazó la identidad. El diagnóstico añadido en B6 no
puede reconstruir retroactivamente ese dato. La hipótesis de una observación
transitoria de AppKit sigue sin demostrarse; cambiar a otra instancia,
reintentar automáticamente o ignorar el rechazo sería injustificado.

## Suite real B9 de audio propio

Se ejecutaron secuencialmente pilot, RTMP, recovery, transitions, persistence
y silence bajo `h15_run_owned.py`; A/V tuvo otro owner nuevo. B9 tiene el hash
indicado arriba. Los wrappers están en `h17-system-audio-b9/` y `h17-av-b9/`;
los informes primarios son
`h13-system-audio-1795046880324315000/report.json` y
`h13-system-audio-1795047030422033000/report.json`, dentro de `var/evidence`.
`h17-system-audio-b9/review.json` fija sus hashes y los de los siete medios.

Las siete etapas funcionales tienen **PASS**. La suite usa su configuración
real 960×540 a 30 fps, H.264 sin reordering y AAC estéreo a 48 kHz; no se
presenta como una ejecución a 720p. Usa únicamente la fixture de audio propia
y tono de Motive, con ventana propia para A/V, sin micrófono/cámara, cambios
de volumen o routing, ni snapshots que fuercen redraw. No hubo pruebas de
rendimiento, builds o decodes ajenos concurrentes.

| Etapa | Video frames | AAC packets | Peak PCM canal 0 | Resultado ejercido |
|---|---:|---:|---:|---|
| Pilot MKV | 744 | 1163 | −23,957 dBFS | Gain, mute y medidores aislados. |
| RTMP recibido | 751 | 1174 | −23,588 dBFS | Mismos controles y decode recibido. |
| Recovery | 451 | 705 | −20,495 dBFS | Pérdida del PID propio y reconnect explícito; tono continuo. |
| Transitions | 433 | 678 | −23,807 dBFS | Cut/fade y continuidad del tono. |
| Persistence | 110 | 172 | −23,841 dBFS | Restore reutiliza capturas; proyecto y perfiles sin cambio. |
| Silence | 1064 | 1664 | −23,900 dBFS | Ceros, pausa, resumed y tail. |
| A/V | 1024 | 1601 | −23,936 dBFS | Siete pulsos propios y continuidad. |

Todos decodifican completos, con gap máximo video/AAC 34/22 ms, counters
lagged/skipped/drops sin incremento y clipping nativo cero en cada muestra.
El análisis tonal/peak histórico selecciona el canal PCM 0; no se hace pasar
por una comprobación independiente de clipping PCM en ambos canales. La
comparación de paquetes finales tampoco forma parte de estos siete PASS.

Las variaciones esperadas de gain −12 dB se midieron en pilot como
−12,003/−11,995 dB (tono/aplicación), y en RTMP como −11,999/−11,993 dB.
En recovery la fixture PID 79980 terminó deliberadamente: la entrada quedó
`APPLICATION_UNAVAILABLE`, `no_registered_instance`, count=0 y PID fijado
ausente. El nuevo PID 80529 no recuperó silenciosamente la entrada. Sólo
reconnect explícito cambió instancia 2→3, con identidad matching. Esto es una
pérdida real esperada; **no reproduce ni corrige** el rechazo histórico con
la fixture todavía viva.

La continuidad estricta de 997 Hz, anclada al primer AAC y reloj nativo,
pasó en 68/75/35 ventanas de 100 ms (tone/resumed/tail) para silence y
56/75/35 para A/V, con guard de 200 ms y cero fallos de identidad inesperados.
El tono independiente de 440 Hz también pasó su continuidad. Se observaron
26 y 24 muestras de buffers cero, respectivamente. No apareció
`awaiting_audio`: la cobertura de ausencia de callbacks queda **PARTIAL**,
distinta del silencio efectivamente medido.

A/V emparejó siete pulsos con audio−video = −42,292 ms y rango observado
0 ms, a resolución de 20 ms de audio y 30 fps de video. Es alineación medida
de esta fixture, incluyendo redraw y latencia de salida; no prueba latencia
cero, deriva nula general ni sincronía de cámara/micrófono físicos.

Los owners 79973 y 81487 terminaron con exit 0 y cleanup vacío. Todas las
fixtures propias terminaron y se verificó ausencia de owner/socket antes de
devolver el lease. El store de audio previo se restauró por el runner. No hubo
emisor dentro de Motive para probar exclusión de audio propio.

La preparación encontró un bloqueo del instrumento: `lock_matches` sólo
aceptaba etiquetas H14/H15, rechazando el lock canónico H17. El commit
`f9a399f` admite únicamente el owner exacto `h17-root`, conservando el
worktree exacto y el comportamiento histórico. Un reproductor falló antes;
los nueve tests pasan después, incluidos owner similar y worktree distinto
rechazados. Logs: `h17-audio-lock-contract-01/`. No se relajaron las puertas
de audio ni los umbrales para esta ejecución.

## Matriz de problemas de este alcance

| ID | Prioridad / tipo | Estado anterior | Causa demostrada o hipótesis | Cambio / riesgo | Prueba necesaria | Estado actual / evidencia |
|---|---|---|---|---|---|---|
| OUT-TRACE-END | P1, verificador | FAIL | Una última metadata omitida deja una cola contigua que el clasificador aceptaba. | Guards de origen/quiescencia/extremo; matching 1:1. Riesgo: cobertura antes aceptada puede quedar incompleta. | Reproductores baseline/nuevo y replay de medios conservados. | PASS, diez tests y 14 replay equivalentes. |
| OUT-TAIL | P1, OBS/aceptación | PARTIAL | Cutoff explica compatibilidad de ausencias observadas B6; backlog previo sin identidad. | Sin cambio del motor. Riesgo conservado de entrega final incompleta. | Nueva matriz VT/x264 MKV/RTMP/dual, cancel/shutdown y receiver-loss con trazas terminales. | PARTIAL, auditoría B6. |
| OUT-PRE-STOP | P1, OBS/aceptación | FAIL | Dos AAC H14 pre-stop después de video que cruza cutoff. | Reordering permanece rechazado. No reescritura de perfiles. | Reproducción con identificación temporal antes del interleaver si se busca cambiarlo. | FAIL histórico preservado; perfil inadmitido. |
| AUD-MIX | P1, producto | PASS | Jitter SCK superaba el margen dinámico observado B4. | Conservar 128 ms; sin cambio H17. | Secuencia estricta y A/V del binario ensayado. | PASS de siete etapas B9; awaiting_audio no observado, cobertura PARTIAL. B6 permanece separado. |
| AUD-ID | P1, producto/hipótesis macOS | PARTIAL | H14 rechazó identidad, pero count/terminated/PID causante no se registraron. | Conservar diagnósticos, aislamiento y reconexión explícita. Riesgo: fallo no explicado. | Secuencia propia con observación independiente del proceso; conservar primera rama fallida. | PARTIAL; no se declara reparación. |

## Reproducción offline y próximo ensayo acotado

Desde el worktree H17:

```sh
python3 -m unittest discover -s scripts -p test_h14_output_accounting.py -v
python3 scripts/h17_output_audio_audit.py \
  --matrix /Users/luisfarfan/Developer/products/motive-h15/var/evidence/h15-resume-01/output-matrix-b6/report.json \
  --audio-report /Users/luisfarfan/Developer/products/motive-h15/var/evidence/h13-system-audio-1795015727218037000/report.json \
  --audio-report /Users/luisfarfan/Developer/products/motive-h15/var/evidence/h13-system-audio-1795015870184192000/report.json \
  --output var/evidence/h17-output-audio-audit-new/report.json
```

El destino debe ser nuevo. Para nueva evidencia física, el propietario del
lock canónico inicia un owner desechable identificado por hash. Reutilizar
`verify_h15_output_matrix.py` para sus nueve casos sin reordering; el
correlador corregido se carga en cada caso. No proseguir al siguiente caso si
hay un worker, proceso o limpieza pendiente.

Para identidad, ejecutar primero la secuencia de fixture propia con los
stages pilot/RTMP/recovery/transitions/persistence/silence. Conservar el PID
del `Popen`, su retorno observado con timestamp antes/después de las consultas,
la identidad nativa y los eventos de la fixture. El verificador H13 actual
conserva PID de lanzamiento, log y `fixture_process_bracket`, que consulta
`Popen.poll()` antes y después de cada muestra nativa. Esta observación
independiente no demuestra por sí sola publicación de audio. Si aparece el
fallo, retener el
primer snapshot y las observaciones siguientes sin reconectar para borrarlo.
Después, recuperar explícitamente la misma fuente y comprobar la instancia
nueva. No extender el ensayo ni modificar los 128 ms para forzar un resultado.

Ejecutar A/V aparte con ventana propia visible y pulsos, como en B9. B8 ya
conserva la toma supervisada de cámara/micrófono descrita arriba; no sustituye
permisos, desconexión o sleep/wake. Esas coberturas siguen **NOT_EVALUATED**
en este alcance y requieren coordinación física. Dos repeticiones sin nuevo dato
no justifican una tercera; preservar el bloqueo y continuar trabajo independiente.
