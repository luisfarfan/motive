# H14 — emisión privada RTMPS y grabación local B2

La prueba real transmitió por RTMPS a YouTube durante **104,837 s activos**.
El usuario confirmó en la vista privada de YouTube Studio el patrón controlado
en movimiento y el tono continuo. La grabación local simultánea decodifica
sin errores y continúa **21,698 s después de que streaming llegó a idle**.
Ambas salidas terminaron idle, sin workers nativos pendientes ni fallos.

El resultado agregado sigue **PARTIAL**: la copia del proveedor no se descargó
ni se decodificó independientemente, y persisten diferencias entre contadores
de encoder/dispatch y los paquetes del archivo local. No se declara reparado
el cierre de cola por esta toma.

## Contexto y alcance observado

El propietario autorizó expresamente una prueba privada de hasta dos minutos,
solo con patrón generado y tono. La app B2 firmada estaba fuera del checkout,
con owner PID 75663. El destino aprobado fue
`rtmps://a.rtmps.youtube.com:443/live2`; el inicio requirió la confirmación
local GPUI. Este informe no contiene credenciales.

La configuración compartida fue 1920×1080, 30 fps, VideoToolbox H.264 hardware,
CBR solicitado de 6000 kbps, keyframe de dos segundos y frame reordering
desactivado. El mixer tenía una entrada de tono a −6 dB de ganancia, sin mute
y con monitoreo desactivado. Esta toma no verifica webcam, captura de ventana,
micrófono físico ni Cut/Fade.

Se conservan **216 muestras estructuradas** del runtime. Streaming pasó por
connecting, active, stopping e idle; grabación permaneció active durante esa
observación. Ambos contadores OBS de dropped frames permanecieron en cero.
Esto describe OBS; no es un contador de cuadros recibidos por YouTube.

La observación del proveedor está en `provider-observation.json`, marcada
explícitamente como observación del usuario. No es una captura ni una descarga
independiente del proveedor. El runtime conserva `delivery_verified=false`.

## Archivo local y análisis independiente

Archivo: `/Users/luisfarfan/Movies/Motive/motive-1794954591283454.mkv`.
Tamaño: **105.444.073 bytes**. SHA-256:
`e02bf69d8e044a9068a6bd3e746537d58d75929567532c67a9d266268f50f8ae`.

El análisis utilizó los ejecutables FFmpeg/ffprobe incluidos en B2, con dos
threads para decodificar. Las cinco invocaciones terminaron con código cero y
stderr vacío. Se decodificaron todos los cuadros de video y el PCM estéreo;
el análisis completo tardó 4,09 s y terminó antes de las mediciones de memoria.

| Medida | Resultado |
|---|---|
| Formato real | H.264 1920×1080 a 30 fps; AAC 48.000 Hz, dos canales |
| Duración reportada por el contenedor | 138,431 s, con primer PTS AAC −0,021 s |
| Cuadros de video decodificados | 4.152; cero B-frames |
| PTS video | 0,000 → 138,367 s; incrementos de 33–34 ms; cero huecos >50 ms |
| PTS AAC | −0,021 → 138,389 s; incrementos de 21–22 ms |
| DTS | Presentes y estrictamente crecientes en todos los paquetes de ambos streams |
| Movimiento del patrón | Centroide diferente en 4.151/4.151 pares de cuadros; ningún cuadro sin el cuadrado esperado |
| PCM | 6.643.712 muestras por canal; 138,410667 s |
| RMS decodificado | −33,0145 dBFS en ambos canales |
| Peak decodificado | −29,3507 dBFS izquierdo; −29,3434 dBFS derecho |
| Saturación | Cero muestras con valor absoluto ≥0,999; cero bloques nativos de clipping |
| Silencio por ventanas de 100 ms | Ninguna ventana por debajo de −80 dBFS |
| Finales de medios | Video 138,400 s; audio 138,410 s; diferencia de 10 ms |

Para verificar contenido fresco se midió la posición del cuadrado blanco en
una fila central del patrón en **cada cuadro decodificado**, con umbral de
luminancia 180/255. El desplazamiento normal fue de 3,5–4 píxeles por cuadro
en la escala de diseño, con 19 vueltas del patrón. El criterio usa movimiento
del objeto, no hashes que puedan variar por ruido de compresión.

El RMS de ventanas interiores de 100 ms quedó entre −33,0275 y −33,0004 dBFS.
Los medidores nativos del tono estuvieron entre −33,1035 y −32,9332 dBFS RMS,
con peak cercano a −30 dBFS; son coherentes con el PCM. El pequeño aumento del
peak después de AAC conserva más de 29 dB de margen hasta saturación.
Una comprobación Goertzel de 220, 440 y 880 Hz, en ventanas de un segundo cerca
del inicio y del final, identifica claramente el componente esperado de 440 Hz.
La diferencia de los finales A/V no constituye por sí sola una medición de
sincronía perceptual ni de latencia del proveedor.

## Cola, contadores y finalización

| Contador final | Grabación | Streaming |
|---|---:|---:|
| Frames del encoder | 4.154 | 3.144 |
| Frames de output / callback de dispatch | 4.153 | 3.142 |
| Paquetes de audio observados antes del plugin | 6.490 | 4.911 |
| Dropped frames OBS | 0 | 0 |
| Stop → quiescence observado | 140 ms | 139 ms |

El MKV contiene **4.152 paquetes/cuadros de video y 6.489 paquetes AAC**. Por
tanto, se mantienen explícitamente los deltas: un frame menos que output /
dispatch, dos menos que el encoder y un paquete AAC menos que dispatch.
El callback ocurre antes del plugin; no confirma escritura ni entrega.
Los contadores del streaming tampoco prueban recepción del proveedor.

El correlador estricto de cola devuelve **INCONCLUSIVE** con razón
`beginning_of_trace_not_complete`: la primera traza guardada ya había
sobrescrito 6.169 registros del comienzo. La traza final conserva 256 registros,
10.387 sobrescritos y cero registros perdidos por contención. No se inventa
un origen de timestamps ni se modifica la tolerancia para convertir el
resultado en PASS. La continuidad del archivo decodificado no resuelve qué
paquetes de la frontera de stop quedaron fuera del contenedor.

La grabación pasó de 116.819 ms activos al observar streaming idle a 138.517 ms
activos al finalizar: esos **21.698 ms adicionales** y el contenido continuo
hasta el final verifican la detención independiente en esta toma.

## Evidencia

La evidencia de ejecución original queda intacta en
`var/evidence/h14-rtmps-youtube-b2-1794954163260835000/`: autorización/contexto,
observación del proveedor, muestras, estados finales y trazas de paquetes.

El análisis derivado está separado en
`var/evidence/h14-rtmps-b2-media-analysis/`: `analyze.py`, `report.json`,
`acceptance.json`, `probe.json`, `frames.json`, `packets.json`, posiciones del
patrón, ventanas PCM y `levels-crosscheck.json`. Incluye comandos, tiempos y
hashes para repetir la revisión. No altera medios ni registros originales.

Gates locales de decode, cadencia, movimiento, continuidad AAC, ausencia de
clipping y parada independiente: **PASS**. Vista privada del proveedor:
**USER_OBSERVED_PASS**. Decode externo: **NOT_EVALUATED**. Contabilidad completa
de salida: **PARTIAL**; entrega estricta de cola: **INCONCLUSIVE**.
