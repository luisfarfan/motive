# H13 — investigación de intervalos PTS al finalizar

Investigación de código, 2026-11-17. Incluye un verificador nuevo preparado,
todavía sin ejecutar por su autor. No se ha modificado producción, módulos OBS,
encoders ni la semántica de reproducción para esta investigación.

## Evidencia disponible

La matriz `var/evidence/h13-video-1794931993726668000/report.json` tiene siete
casos PASS, binario firmado SHA-256
`914aa8e98371127ed1fef43b0a0497dd558c8d7326b5dae6fb3c92cee785911e`.
Todos solicitaron H.264, 2500 kb/s CBR, GOP objetivo 2 s,
`frame_reordering: true` y AAC 160 kb/s, 48 kHz estéreo. La escena contiene
patrón propio, texto/PNG/forma, Cut/Fade y tono; no captura física.

| Encoder / canvas | Frames decodificados | Máximo interior | Últimos cuatro intervalos PTS | Stop → idle |
| --- | ---: | ---: | --- | ---: |
| VT 720p30 horizontal | 334 | 34 ms | 33, 33, 34, 33 ms | 389 ms |
| VT 720p30 vertical | 336 | 34 ms | 34, 33, 67, 66 ms | 343 ms |
| VT 1080p30 horizontal | 337 | 34 ms | 33, 33, 34, 66 ms | 326 ms |
| VT 1080p30 vertical | 333 | 34 ms | 34, 33, 33, 34 ms | 345 ms |
| VT 1080p60 horizontal | 667 | 17 ms | 17, 17, 16, 67 ms | 207 ms |
| VT 1080p60 vertical | 651 | 17 ms | 16, 17, 17, 66 ms | 207 ms |
| x264 1080p30 horizontal | 336 | 34 ms | 34, 33, 33, 34 ms | 1605 ms |

Lag de render, skips de video y drops de salida observados: cero en los siete.
El verificador conserva los cuatro intervalos finales por separado: PASS no
significa que todos los intervalos sean uniformes. `has_b_frames=2` describe
reordenamiento en el stream; no es el conteo de cuadros B decodificados.
La diferencia entre los últimos PTS AAC/video es −38…−118 ms. No es por sí sola
una medida de drift ni del final audible: hay que añadir la duración del último
paquete/frame y comprobar muestras decodificadas.

H12 conservó una cola de 133 ms en su grabación adicional y 67 ms en RTMP
(`docs/h12-creative-studio-verification.md`, tabla final). H7 ya observó saltos
finales en VT y x264 con reordenamiento, y ninguna separación superior a 50 ms
al desactivarlo en cuatro tomas (`docs/h7-output-verification.md`, experimento
`verify_vt_stop.py`). Son antecedentes con otras tomas, no un control pareado
que permita atribuir la diferencia H12/H13 a este cambio de canvas.

## Ruta oficial y límites de la inferencia

- `native/encoding.inc` transmite `frame_reordering` al ajuste oficial `bframes`
  de VT; en x264 desactivado establece `bf=0`. No modifica timestamps ni drena
  sesiones privadas. El default continúa activado.
- OBS `obs_output_stop` entrega `os_gettime_ns()` al módulo. El muxer MKV deja
  de escribir al alcanzar `packet->sys_dts_usec >= stop_ts`. RTMP aplica el mismo
  límite o su timeout de finalización. Es un límite temporal de salida basado
  en DTS; no es una comprobación de haber emitido cada PTS previo al cierre.
  [Core OBS33.0.1](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs-output.c#L472),
  [muxer](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/obs-ffmpeg/obs-ffmpeg-mux.c#L823),
  [RTMP](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/obs-outputs/rtmp-stream.c#L492).
- VT configura `AllowFrameReordering`, publica muestras asíncronas a una cola
  y retira una muestra por llamada `vt_encode`. Ajusta DTS dos frames cuando
  corresponde, conservando PTS del sample. `vt_destroy` invalida/libera la sesión,
  sin llamada a `VTCompressionSessionCompleteFrames` ni bucle de drenaje en ese
  camino. El core detiene la conexión y destruye el encoder cuando desaparece
  su último callback. [VT fijado](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/mac-videotoolbox/encoder.c),
  [encoder core](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs-encoder.c#L848).
- Apple distingue completar cuadros pendientes de invalidar la sesión.
  [CompleteFrames](https://developer.apple.com/documentation/videotoolbox/vtcompressionsessioncompleteframes(_:untilpresentationtimestamp:))
  emite los pendientes hasta el PTS solicitado antes de retornar.
  [Invalidate](https://developer.apple.com/documentation/videotoolbox/vtcompressionsessioninvalidate(_:))
  efectúa el teardown. Motive no posee esa sesión para invocar estas APIs.

Hipótesis principal: el corte por DTS combinado con reordenamiento y cuadros
pendientes afecta el extremo de presentación. La cola asíncrona de VT puede
participar, pero no se ha aislado su contribución. Que x264 también lo reproduzca
en H7 impide presentar la ausencia de CompleteFrames como causa única. Tampoco
está demostrado que aumentar resolución/FPS haya reparado nada. No se propone
cambiar `RealTime` —el módulo lo configura a false— ni el default de reordenamiento
sin una comparación que aísle esas variables.

## Experimento acotado pendiente

Después de estabilizar los dos slots, adquirir el lock físico y usar un único
bundle firmado identificado. Primera fase: solo grabación MKV activa, sin RTMP;
misma escena controlada patrón + overlay animado y tono, sin cambios de escena
ni edición durante cada toma. No guardar proyectos/perfiles del experimento.

1. En reposo, `configure_video` con
   `{"version":1,"resolution":"full_hd1080","fps":30,"coordinate_space":"design960"}`
   y `set_variant` horizontal. Capturar estado/IDs y configuración inicial para
   restaurarla después. Confirmar selección real VT sin fallback.
2. Crear/seleccionar perfil temporal `h13-tail-probe`: `encoder=videotoolbox`,
   `bitrate_kbps=2500`, `rate_control=cbr`, `keyframe_seconds=2`.
3. Ejecutar A/B/B/A, donde A=`frame_reordering:true` y B=`false`.
   Las primeras dos tomas duran 6,10 s desde confirmación de arranque; las otras
   dos 6,33 s, como las dos fases temporales de H7. Usar plazos monotónicos,
   conservar tiempo real de solicitud y medir por separado respuesta stop y
   finalización. En cada par solo cambia reordenamiento.
4. Repetir las cuatro tomas con `encoder=x264` como control. Detener siempre con
   `stop_output` normal, válido al haber una sola salida, y esperar su barrera
   idle; nunca force-stop, sleep fijo para simular finalización ni release directo.
5. Conservar cada MKV y SHA, todo PTS/DTS/duración de paquetes, tipo de cada frame,
   mensajes de decodificación completa, contador de B-frames, último segundo de
   video, final AAC/PCM, tiempos de stop y deltas lag/skips/drops/CPU/RSS.
   Usar todos los intervalos al informar; separar interior y últimos cuatro
   únicamente para localizar el fallo, sin borrarlos del informe.
6. En B exigir cero cuadros B. Para comparar cadencia a 30 FPS, el interior debe
   seguir dentro de 50 ms; informar si algún intervalo final también supera
   50 ms. Un resultado positivo prueba mitigación bajo estas condiciones, no
   garantía universal. Si el efecto se reproduce, repetir el par relevante a
   1080p60 con umbral interior 25 ms. Solo después añadir RTMP concurrente como
   una segunda variable y comparar ambos archivos por separado.

El script H7 contiene la secuencia ABBA, pero asume 540p30 y alias de una salida:
no ejecutarlo sin adaptar/verificar geometría y contrato H13. Las fuentes con
60 imágenes únicas ya verificadas no sustituyen este experimento de cierre.

## Ownership y lifecycle

No se encontró en esta lectura una razón para que Motive acceda a la cola o
sesión privada de VT. Añadir un drenaje desde GPUI, imponer una espera fija o
liberar encoders al recibir la primera señal stop rompería las barreras de
lifecycle. Mantener el `RequestShutdown` del owner, los workers RTMP fijados y
la finalización OBS por slot. Cero gaps finales tampoco acredita que esos
workers hayan terminado: es una condición distinta que debe verificarse.

## Instrumento H13 preparado: rendimiento y cola

`scripts/verify_h13_performance.py` reutiliza `process_sample`/`profile` de H7,
el `Sampler` libproc de H12 y `Client`/`Receiver`/contratos de
`verify_h13_outputs.py`. No modifica esos verificadores. **Estado: preparado,
sin ejecución física todavía**; ni una lectura estática ni su futura salida
`--help` acreditan medios reales.

Requiere que el operador ya posea el lock compartido de dispositivos/bundle y
que la aplicación firmada de este checkout esté abierta. `--lock-held` declara
esa posesión; no crea un lock independiente que dé una falsa exclusión entre
worktrees. Verifica `codesign --verify --verbose=2`, identidad de PID/ruta y SHA
antes/después. Registra `--strict` sin usarlo como gate: el bundle de desarrollo
conserva un symlink absoluto de Frameworks a `.deps/OBS.app`, incompatible con
esa comprobación de portabilidad. No reconstruye, firma, abre aplicaciones ni
cambia permisos. Solo configura RTMP en `127.0.0.1`, sin credenciales.

Ejecutar serialmente, con el estudio visible y el mismo entorno térmico/carga
externa durante cada bloque. Los decodificadores de análisis se ejecutan después
del muestreo, para no contaminar los intervalos comparados:

```sh
# Variable única: un output frente a dos, mismo encoder/perfil/fixture.
python3 scripts/verify_h13_performance.py --lock-held --fps 30 --mode performance
python3 scripts/verify_h13_performance.py --lock-held --fps 60 --mode performance

# Reproducción H11: un video generado de 1080p60, looping y sin audio.
# Se genera/importa antes de medir. No sustituye el baseline de patrón.
python3 scripts/verify_h13_performance.py --lock-held --fps 60 --fixture video

# Variable única: reordenamiento, sin RTMP, VT y x264 como control separado.
python3 scripts/verify_h13_performance.py --lock-held --fps 30 --mode tail
python3 scripts/verify_h13_performance.py --lock-held --fps 60 --mode tail
```

También acepta `--fps 30 60` para bloques seriales, `--encoder x264`,
`--reordering off` y duración de carga `--seconds 6..120`. Los defaults son
12 s de carga, 4 s de reposo anterior/posterior, CBR 2500 kb/s, GOP 2 s y
reordenamiento activo. Cada bloque performance es A/B/B/A = MKV / MKV+RTMP /
MKV+RTMP / MKV. Los dos destinos usan el mismo perfil: no comparar un preset
barato para una salida contra otro costoso para dos. VT explícito exige encoder
hardware efectivo sin fallback; un fallo de la segunda sesión es evidencia de
fallo, no una sustitución silenciosa por x264. Cada bloque tail es on/off/off/on,
6,10/6,10/6,33/6,33 s, primero VT y después x264. Ambos experimentos conservan
tiempos monotónicos reales de arranque, solicitud, respuesta y barrera de stop.

Muestreo y resultados:

- CPU/RSS/threads por libproc a 20 Hz, independientes de consultas MCP a 2 Hz;
  CPU 100% corresponde a un núcleo. CPU acumulada contrastada con `ps TIME`
  dentro de 0,3 s. Se exige cobertura observada de al menos 15 Hz y ninguna
  separación de muestreo ≥250 ms; quedan visibles p95/máximo del intervalo.
- Mediana, media/p95/máximo de CPU, mediana/p95/pico de RSS y muestras completas;
  fase completa, estado estable después de 2 s, picos de arranque/drenaje y
  reposo posterior. RSS incluye GPUI/OBS en Motive; **no** incluye el receptor
  ffmpeg, helper muxer ni verificador. Picos <50 ms pueden no observarse.
- Deltas globales render/lag/skips y copias/drops de preview; por slot se guardan
  intentos, perfil efectivo, frames codificados/emitidos, bytes, drops y duración.
  `preview_copies × 1920 × 1080 × 4 / segundos` estima solo la copia BGRA que
  cuenta `motive_copy_frame` hacia Rust. No representa todo el tráfico CPU/GPU,
  presentación, latencia ni una ruta zero-copy. No se impone una tasa de preview
  igual a FPS: GPUI puede consumir a su propia cadencia.
- Comparaciones descriptivas B1−A1 y B2−A2 y media dual−single. Dos observaciones
  por rama no acreditan significación estadística ni una mejora de rendimiento.
  No se inventan presupuestos de CPU/RSS o una prueba de ausencia de fugas.
- Decodificación completa H264/AAC, PTS de todos los frames, tipo/keyframe,
  PTS/DTS/duración de todos los paquetes, conteo B, gaps completos y últimos
  cuatro, metadatos del último segundo y sus checksums de frames. El MKV y SHA
  se retienen incluso en fallos. Se comprueba movimiento propio real para
  distinguir 60 frames nuevos de duplicados a 30 FPS.
- AAC continuo (gaps ≤23 ms), tono interior en bloques de 20 ms dentro de 1 dB
  del nivel esperado y sin clipping; se conserva el final PCM de 100 ms y el
  desfase final de presentación incorporando duraciones de paquetes. Si falta
  una duración se declara la inferencia. No se presenta ese desfase como drift.

Los gates son distintos y aparecen por archivo en el informe:

| Gate | Criterio |
| --- | --- |
| Integridad funcional | Decode sin error; geometría/FPS/audio correctos; PTS/DTS positivos/monótonos; cero lag/skips/drops observados; tono continuo. |
| Cadencia interior | Todos los intervalos salvo los últimos cuatro ≤1,5/FPS: 50 ms a 30; 25 ms a 60. |
| Límite final histórico | Todos los intervalos, incluidos los finales, <150 ms. Conserva el antecedente H12, no lo llama continuidad perfecta. |
| Cadencia estricta | **Todos** los intervalos ≤1,5/FPS. `strict_cadence_ok` se informa aparte. |
| Reordenamiento desactivado | Cero cuadros B decodificados. |

`ok:true` expresa gates funcionales y limpieza; puede ir acompañado de
`result:functional_pass_with_tail_gaps` y `strict_cadence_ok:false`.
Solo comparar una mitigación de cola cuando las tomas off cumplan también el
gate estricto y los perfiles/fixture sean equivalentes. No atribuirla al canvas
ni a VT sin ese control. El script no cambia defaults de encoders.

La limpieza espera barreras por slot antes de mutar recursos, elimina sus
escenas/fuentes/tono/perfiles/asset propio y restaura selección, canvas, variante
y transición. No guarda ni sobrescribe stores; compara hashes de proyecto,
mixer y perfiles antes/después. Los contadores de IDs y migración runtime a v5
permanecen. Si el endpoint inicial era nulo, el loopback queda seleccionado por
falta de operación para borrarlo; se declara en el informe. Un timeout de
limpieza no autoriza liberar un slot vivo ni salir forzosamente de Motive.

## Matriz mínima adicional tras este benchmark

H12 ya midió cuatro videos 1080p visibles/ocultos, reemplazo de cuatro IDs y tres
ciclos de reapertura/liberación: 633,4 MiB / 64,4% visibles; 662,1 MiB / 60,4%
ocultos; pico de reconciliación 910,25 MiB; mediana posterior 263,1 MiB tras
20 s. Son evidencia H12 con su canvas original, no mediciones H13 equivalentes.
Ocultar conserva reproducción: no proponer pausa automática como optimización.

Después de ABBA patrón y ABBA con un video H11 a 1080p60, bastan tres controles
adicionales acotados antes de ampliar:

1. **Preview:** con el mismo fixture y single MKV, 1080p30/60, observar una fase
   de estudio visible y otra de ventana minimizada por acción nativa explícita.
   Registrar copias/s, CPU/RSS y lag. No modificar ventanas mediante este script
   ni asumir que el preview se detiene al ocultar. La interacción GPUI es otro
   gate bajo el mismo lock.
2. **Visibilidad H11:** 1080p60, un video y luego cuatro; visible/oculto/visible,
   mismo perfil y single MKV. Exigir reloj media continuo y un hijo por fuente,
   audio de video desactivado; medir costo sin cambiar la semántica. Si cuatro
   no caben en el presupuesto de producción observado, reportar ese límite.
3. **Reconcile/liberación:** en reposo, reemplazar cuatro IDs una vez, medir la
   operación y 20 s posteriores a liberar; solo repetir tres ciclos si el pico
   o retención difieren de H12. No reconciliar IDs durante outputs activos:
   sus guards existentes deben seguir rechazándolo. No hace falta repetir toda
   la matriz H12 ni introducir un nuevo mecanismo de caché para medirlo.

Estas tres filas son propuestas pendientes, no están implementadas por el
benchmark ni se contabilizan como PASS. Si el benchmark muestra una regresión,
primero repetir su par bajo condiciones iguales y conservar ambos informes;
optimizar únicamente después de aislar la causa.
