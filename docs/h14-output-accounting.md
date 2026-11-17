# H14 — contabilidad de paquetes y finalización

Estado inicial: **PARTIAL**. Instrumentación y experimento implementados;
las pruebas unitarias del clasificador no sustituyen una ejecución multimedia.
Los informes H13 y sus diferencias de uno/dos frames permanecen intactos.

## Semántica revisada en OBS 33.0.1

| Medida | Punto observado | Lo que no demuestra |
|---|---|---|
| `stats.rendered_frames` de producción | Contador global del compositor OBS | Frames propios de un destino ni contenido fresco de una captura |
| `stats.encoded_frames` por slot | Paquetes de video que el encoder entregó a sus callbacks; OBS incrementa después de invocarlos | Que el interleaver o el output haya conservado todos esos paquetes |
| `stats.output_frames` por slot | Máximo observado de `obs_output_get_total_frames`; en la ruta A/V intercalada incrementa antes del plugin | Escritura MKV o recepción RTMP confirmadas |
| `diagnostics.observed_video_packets` | Callback oficial justo antes del plugin | Aceptación por muxer, socket o receptor |
| `diagnostics.observed_audio_packets` | Mismo punto para AAC | Audio finalmente escrito o decodificado |
| `frames_written`, `frames_received`, `frames_decoded` | No disponibles en el contrato nativo actual: `null` | No se sustituyen por contadores cercanos ni por cero |
| FFprobe/FFmpeg sobre el archivo cerrado | Paquetes y frames realmente recibidos/decodificados | Que el total de OBS tenga la misma definición |

El [callback público](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs.h)
se ejecuta en `send_interleaved` antes de `output->info.encoded_packet`.
Su contador no es un acuse de recibo. En
[obs-output.c](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs-output.c),
el contador de video se incrementa antes de ese punto. La ruta raw heredada no
ofrece este callback intercalado y anuncia que el observador no está disponible.

[ffmpeg_mux_data](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/obs-ffmpeg/obs-ffmpeg-mux.c)
puede recibir un paquete ya contado, comparar `sys_dts_usec` con `stop_ts` y
terminar sin escribirlo. Su contador de bytes mide escritura al pipe del helper,
no confirmación de cada frame en disco. `deactivate` espera el helper y devuelve
su estado; el camino normal de cutoff descarta ese retorno, mientras que
`signal_failure` sí lo convierte en un error tras una escritura fallida.
Por eso un stop nativo sin error no certifica por sí solo integridad del archivo.

En [RTMP](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/obs-outputs/rtmp-stream.c),
el callback encola y un hilo distinto envía. Ese hilo descarta el paquete que
cruza el cutoff o cuando vence el timeout de cierre. Un write del socket tampoco
certifica recepción/decodificación remota. El parche H8 conserva la barrera de
workers y no fue ampliado para esta instrumentación.

[VideoToolbox](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/mac-videotoolbox/encoder.c)
encola resultados asíncronos y el método de encode retira una muestra de la cola.
Su destrucción invalida la sesión. No existe aquí una garantía pública de que
todos los frames entregados a VT se convertirán en paquetes antes del cutoff.
El experimento separa reordering activado/desactivado y x264 como control;
no modifica el encoder ni presupone cuál causó cada diferencia H13.

## Instrumentación sin cambiar medios

`output_diagnostics {target}` devuelve PID, revisión, snapshot del destino y
`packet_trace`. La traza versión 1 conserva únicamente metadata: secuencia,
instante monotónico del callback, tipo/track, tamaño, keyframe, PTS, DTS,
timebase, `dts_usec` y `sys_dts_usec`. No retiene bytes multimedia ni secretos.
Capacidad fija: **256 registros por slot**. Es una cola de diagnóstico final,
no un log de duración ilimitada ni un segundo reloj multimedia.

El callback no asigna memoria, no realiza I/O, no modifica el paquete y nunca
espera al owner: si el flag de copia está ocupado, aumenta
`trace_missed_records`. `trace_overwritten_records` cuenta registros antiguos
desplazados por la capacidad, no pérdidas de medios. La consulta copia el array
fuera de la serialización JSON; si coincide con el callback devuelve
`snapshot_busy=true` sin esperar. Los contadores del resumen son observaciones
atómicas individuales, no una transacción con toda la traza; después de la
barrera terminal dejan de avanzar. El estado ordinario incluye solo el resumen.

`stop_requested_ns` y `stop_call_returned_ns` acotan la llamada a
`obs_output_stop`; no inventan el timestamp interno exacto del plugin.
`stop_signal_ns` identifica la señal de OBS; `quiescent_observed_ns` la primera
observación del owner que también satisface las barreras OBS/H8. El delta de
quiescencia incluye la frecuencia de polling. Una cancelación diferida puede
haberse solicitado antes: este bracket mide el stop nativo efectivo.

La información permanece al recuperar un error y se reinicia al crear el
siguiente intento. Debe leerse junto a `(pid,target,attempt_id)`. En cierre
normal, el owner conserva sus snapshots/trazas terminales en el diagnóstico
privado `last-shutdown.json` antes de destruir el engine. Ese registro no
certifica la decodificación de ningún archivo.

## Experimento A/B reproducible

`python3 scripts/verify_h14_output_integrity.py --plan` imprime 15 casos:
dos encoders × reordering on/off × MKV/RTMP/dual con stop normal, más cancelación,
pérdida del receptor y shutdown dual con VT sin reordering. No abre Motive.
Cada caso se ejecuta por separado y serialmente en el bundle firmado del owner:

```sh
python3 scripts/verify_h14_output_integrity.py --lock-held \
  --encoder videotoolbox --mode dual --ending stop --seconds 8
```

Para shutdown añadir `--shutdown-report` con la ruta privada exacta de ese
owner. `--app` y `--store-root` permiten el bundle portable y su directorio de
datos aislado. El harness comprueba PID/ejecutable, exige patrón y mixer vacío,
añade solo un tono, perfiles propios y receptor loopback sin credenciales.
No guarda stores, verifica hashes/modos y restaura ajustes runtime cuando el
owner continúa. El endpoint inicial ausente no tiene operación unset: se
declara explícitamente el loopback retenido. No se fuerza la salida de Motive.

Los medios se decodifican completos; se guardan todos los PTS/DTS, número de
paquetes y cuadros, AAC, PCM, hashes, estado nativo y trazas inicial/final. La
referencia inicial requiere conservar el comienzo completo para medir el origen
de cada timeline; el match usa 1,1 ms exclusivamente por la cuantización de
timestamps de MKV/FLV, no como tolerancia a frames ausentes.

Un paquete ausente anterior al bracket de stop es **FAIL de contabilidad de
cola**. Ausencias posteriores se etiquetan como compatibles con el cutoff
documentado y permanecen enumeradas, con los contadores originales. Ausencias
dentro del bracket, origen perdido o metadata incompleta son INCONCLUSIVE.
El script no resta paquetes ni recorta medios para crear igualdad. Decode/
cadencia PASS y contabilidad de entrega se reportan por separado; un déficit
terminal impide el PASS agregado aunque sea compatible con el cutoff.

Las pruebas en `scripts/test_h14_output_accounting.py` verifican que una pérdida
pre-stop, una frontera incierta y una traza incompleta no se conviertan en PASS.
Son tests del analizador con datos construidos, no pruebas audiovisuales.

Pendiente de ejecución física serial: matriz, medidas reales y conclusiones
sobre el binario final. No se declara cerrada la aceptación P0 por la revisión
de código ni por que un archivo pueda decodificarse.
