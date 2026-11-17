# H13 — hueco inicial del tono

Estado: defecto reproducido y localizado entre entrada y mezcla; corrección
limitada al tono verificada en tres vidas instrumentadas, tres MKV y seis
salidas RTMP locales. La repetición normal sin instrumentación está en curso.
No se amplía la tolerancia del verificador.

La matriz `var/evidence/h13-outputs-1794933990447407000/report.json` conserva un
FAIL real: MKV tiene 1024 muestras casi silenciosas, aunque sus paquetes AAC
mantienen PTS continuos. La salida aún era solo grabación. El tono antes y
después conserva amplitud y la fase posterior se retrasa 1024 muestras.
El [informe offline](../var/evidence/h13-outputs-1794933990447407000/offline-audio-diagnosis-1794934472450720000/report.json)
conserva datos y compara el smoke anterior del mismo bundle. El intervalo mínimo
de 1024 muestras ocupa 0,311083–0,332417 s, RMS −72,05 dBFS; el salto de fase
es −139,249°, frente a −139,2° para retrasar 1024 muestras a 440 Hz.

Para localizarlo se añadió instrumentación opt-in, desactivada normalmente:

```sh
MOTIVE_TEST_AUDIO_TRACE=1 target/Motive.app/Contents/MacOS/motive
```

No habilitarla para comparar CPU/RSS de producción. Escribe JSONL a stderr
desde el owner, sin PCM, rutas ni IDs de dispositivos. Los callbacks solo copian
metadatos y calculan métricas acotadas. Ring de 2048 registros, máximo 384 KiB,
presupuesto de 65536 registros por proceso; contención/overflow son explícitos.
Se drena al consultar el mixer y al destruirlo. No hay I/O ni asignaciones en
callbacks. `event=motive_test_audio_trace`, `version=1`:

- `tone_schedule`: posición de muestras, PTS programado, despertar real y
  regreso de `obs_source_output_audio`. `deadline_ns` es el instante previsto de
  entrega; `schedule_lateness_ns = seen_ns - deadline_ns`. `lateness_ns` conserva
  su significado original, `seen_ns - pts_ns`, normalmente negativo con la
  anticipación. El tiempo de entrega no sustituye el timestamp de las muestras.
- `source_pre_fader_pre_mute`: PTS/frames recibidos y energía/RMS/peak por canal.
- `mix_post_fader_post_mute_pre_clamp`: bloques mezclados antes de AAC, sin
  modificar las muestras ni añadir otra mezcla.

Los tiempos usan `os_gettime_ns`. Orden de encolado no equivale a orden temporal:
el tono publica su registro después de ejecutar sincrónicamente el callback
de fuente. Tras restaurar IDs, el registro del tono conserva el nombre original;
no correlacionar solo por ID. El drenaje de teardown precede a la cola de
destrucción OBS y puede omitir registros tardíos; no demuestra EOF completo.
Un registro diagnóstico descartado nunca demuestra pérdida PCM.

Bundle instrumentado integrado:
`dc1188bcffe943b51813311996f84e06684da024bb65d6916c1aeeccf5bba408`;
69 tests/Clippy/formato PASS. Runtime `var/evidence/h13-build/audio-trace-runtime.log`,
tres smoke seriales `audio-trace-smoke-{1,2,3}.log`. En las tres vidas del tono
aparece un bloque mezclado de 1024 muestras exactamente en cero, con fuente
energética y PTS continuos. Despertar máximo observado: 2,514/3,526/3,847 ms.
El primer hueco ocurre dentro del MKV y falla; los otros dos preceden al arranque
de la grabación y esos medios pasan. Pasar el archivo no implica que no ocurrió.
El [análisis de las tres vidas anteriores](../var/evidence/h13-audio-trace-analysis-1794935248189182000/report.json)
conserva los bloques fuente y mezcla vecinos, los PTS y la cobertura temporal.

Esta traza descarta AAC como origen del hueco observado. Todavía no identifica
por sí sola la rama interna de libobs. El código fijado marca `audio_pending`
cuando la fuente no tiene un bloque completo; conserva datos parciales y puede
avanzar su timestamp. En dos huecos, el último callback de fuente observado al
recibir el bloque de mezcla no cubría aún su intervalo completo: faltaban
0,111667 y 0,864583 ms; el siguiente callback apareció 3,125 y 11,916 µs después.
En el primer hueco ese callback ya se había observado 860 µs antes de recibir
la mezcla. Son observaciones de entrada y salida: el callback de fuente ocurre
después de encolar y el de mezcla después de mezclar; ninguno mide exactamente
el instante interno de consumo. No se afirma haber medido la ocupación privada
del búfer ni leído sus campos desde otro hilo.

La corrección modifica únicamente la entrega del tono determinista de H10 en
`tone_run`: `deadline = max(start, timestamp - 20 ms)`. Conserva bloques de 480
muestras por canal, estéreo float planar a 48 kHz, la misma fórmula de fase y
amplitud y `timestamp = start + (frames / 480) * 10 ms`. Al iniciar publica
3 × 480 = 1440 muestras, equivalentes a 30 ms de contenido conocido, con PTS
iniciales separados por 10 ms; después entrega un bloque cada 10 ms con 20 ms
de anticipación respecto a su PTS. Conserva el salto de bloques tras un stall
superior a un segundo. Libobs sigue administrando la cola, la mezcla y el reloj
de salida: no se añade DSP ni se modifica su buffering global. Esto proporciona
margen al consumidor de 1024 muestras, sin desplazar el tiempo de las muestras.

Bundle posterior:
`0444029860e28e53b7e74fc0ab836fa790cc8a691f2f7cfc95702cd9e6ac3952`,
69 tests/Clippy/formato PASS. Runtime `var/evidence/h13-build/tone-lead-runtime.log`.
La comparación completa está en el
[informe A/B](../var/evidence/h13-tone-lead-analysis-1794935516851025000/report.json).

| Vida | Bloques fuente | Bloques mezcla observados | Ceros antes → después | Retraso máximo al deadline | Medio |
| --- | ---: | ---: | ---: | ---: | --- |
| audio-1 | 2528 | 1184 | 1 → 0 | 2,507 ms | [Smoke 1 PASS](../var/evidence/h13-outputs-1794935350685930000/report.json) |
| audio-2 | 2514 | 1178 | 1 → 0 | 3,495 ms | [Smoke 2 PASS](../var/evidence/h13-outputs-1794935380060511000/report.json) |
| audio-3 | 2534 | 1186 | 1 → 0 | 2,510 ms | [Smoke 3 PASS](../var/evidence/h13-outputs-1794935409349223000/report.json) |

Cada smoke incluye una grabación MKV y dos archivos recibidos por RTMP local:
los nueve medios pasan los criterios existentes. En las tres vidas se observaron
7576 bloques fuente y 3548 bloques de mezcla; todos los PTS fuente avanzan
exactamente 10 ms y cada bloque fuente contiene 480 muestras. La anticipación
efectiva posterior a la precarga fue 16,505–19,989 ms. El RMS de mezcla estable
fue −33,0587…−32,9624 dBFS, coherente con el tono de pico −24 dBFS y ganancia −6 dB.

El conteo de ceros incluye todos los callbacks de mezcla entre el primer y el
último callback observado de cada fuente, también antes de grabar; no aplica
la guarda de 100 ms usada únicamente para describir el RMS estable. El primer
bloque de audio-3 es parcial por el arranque y queda conservado en el mínimo de
vida completa del informe. No hubo contención, overflow ni agotamiento del
presupuesto en estas trazas. El cierre normal y su último drenaje tampoco
convierten el último callback de fuente en un EOF garantizado: la adhesión del
callback puede omitir la precarga inicial y la destrucción diferida puede dejar
registros tardíos. El resultado se limita a esos intervalos observados.

La mejora A/B respalda la hipótesis de margen insuficiente de entrega del tono
frente a la lectura de 1024 muestras. No acredita una corrección general de
micrófono o ScreenCaptureKit ni inmunidad frente a cualquier stall. La traza
puede influir en la planificación; por ello se repite la matriz normal con la
misma versión y `MOTIVE_TEST_AUDIO_TRACE` ausente antes de declarar estabilidad
de producción. Las pruebas de A/V y demás regresiones conservan sus propios
resultados, independientes de esta corrección.

No se cambia el buffering global por intuición. `obs_audio_info2` permite
`max_buffering_ms` y `fixed_buffering`; el frontend oficial normalmente usa
buffering dinámico. El modo de baja latencia pide 20 ms, redondeado a un bloque
de 21,33 ms. Esa API no es evidencia de que fijarla solucione este defecto ni
justifica reiniciar audio con salidas activas. La corrección aplicada conserva
esa política y se evalúa en mezcla **y** medios nuevos.

Código oficial contrastado: OBS 33.0.1 `libobs/obs-source.c`
(`process_audio_source_tick`), `libobs/obs-audio.c` (`discard_audio`),
`libobs/obs.c` (configuración de audio) y `frontend/widgets/OBSBasic.cpp`.
