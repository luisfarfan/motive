# H21/C8 — causas, límites de atribución y decisiones

Consulta upstream: 2026-11-20 05:03 UTC. OBS fijado: **33.0.1**. Comparación
con master **`1a44b7f40140ec202da2658ba74068da8adb5a7e`**. Fuentes, respuestas
GitHub, comentarios, diferencias y SHA-256 se conservan privadamente en
`var/evidence/H21-C8-research/manifest.json`. El [informe C8](h21-c8-verification.md)
identifica el binario y las repeticiones; este documento no convierte una
explicación de código en una prueba física.

## Captura

En CAP-01 de H17, la aplicación de prueba siguió dibujando: 510 → 960 dibujos,
171 → 321 ticks. Durante aproximadamente 15 segundos la captura conservó
468 callbacks y 467 superficies, mientras OBS continuó renderizando la textura
anterior (452 → 905 renders). Se observaron 29 muestras de diagnóstico
`suspended`; los medios conservaron congelamientos de 15,4/15,6 s. La ausencia
de nuevas superficies está localizada **antes de su consumo por OBS**. Eso
descarta que un contador de renders pruebe imagen nueva; no identifica por sí
solo el motivo interno de WindowServer/SCK, ni demuestra un UAF.

El primer Podcast C7 falló a los 474,782 s, durante una animación de escritorio.
La identidad admitida conservaba ID/PID; sus bounds cambiaron durante la
animación. El contador de suspensión aumentó una vez y la siguiente consulta
ya mostraba `complete`. El respaldo preservó audio y outputs; el verificador
rechazó el cambio no previsto. Es diferente del falso rechazo de identidad C6
por nivel/título corregido en C7. No se atribuyen ambos síntomas al mismo bug.

La consulta de control una vez por segundo no reconstruye una transición más
corta. C8 añade únicamente última hora observada por estado, hora del último
cambio y contador de cambios. Los campos son atómicos individualmente; el JSON
**no** es un snapshot coherente de todos ellos. Son observaciones de callback,
no un nuevo reloj, confirmación de píxeles, duración exacta de suspensión ni
autorización de reinicio. Un ensayo nativo con CMSampleBuffers sintéticos prueba
el contrato de esas observaciones; su alcance es instrumental.

Apple diferencia [`idle`](https://developer.apple.com/documentation/screencapturekit/scframestatus/idle)
(sin cambio en el display) de
[`suspended`](https://developer.apple.com/documentation/screencapturekit/scframestatus/suspended)
(actualizaciones suspendidas). Ninguno permite deducir una duración futura.
`complete` confirma la entrega observada, no que el contenido esperado de una
aplicación avance. Edad, `idle` o contenido quieto se presentan como estático/no
observado; no como prueba de salud dinámica ni fallo confirmado automático.
`stopped`, error terminal y stop intencional mantienen sus distinciones.

### OBS original y master

Los archivos oficiales
[`mac-sck-common.m`](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/mac-capture/mac-sck-common.m)
y [`mac-sck-video-capture.m`](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/mac-capture/mac-sck-video-capture.m)
conservan en el master consultado la misma relación delegate → `screen_capture`,
la parada asíncrona y la ruta de Restart Capture. Las diferencias observadas
son la selección del formato de píxel mediante un helper y una limpieza de
includes; **no aportan la barrera de callbacks pendiente**. El módulo original
puede conservar la última textura mientras no llegan superficies. Reutilizar
su botón Restart no demuestra seguridad de reconstrucción durante outputs.

Los cinco issues solicitados seguían **abiertos** al consultar:

| Issue | Señal descrita | Límite de inferencia |
|---|---|---|
| [#14175](https://github.com/obsproject/obs-studio/issues/14175) | Inicio con captura ya detenida | Motive conserva preflight y stop intencional; no hereda una solución upstream |
| [#11435](https://github.com/obsproject/obs-studio/issues/11435) | Congelamientos aleatorios macOS | Síntoma compatible, no prueba de causa común con CAP-01 |
| [#13131](https://github.com/obsproject/obs-studio/issues/13131) | Congelamiento/error 3821 | Un código de error de otro ensayo no se asigna retrospectivamente a C7 |
| [#12044](https://github.com/obsproject/obs-studio/issues/12044) | Preview y audio detenidos | Versiones/configuraciones distintas; no demuestra que C8 repita el defecto |
| [#12623](https://github.com/obsproject/obs-studio/issues/12623) | Preview fullscreen detenido | Fullscreen requiere su propia observación de identidad y contenido |

`stopCapture` informa el resultado de la parada; `removeStreamOutput` retira
un receptor. Las páginas oficiales consultadas no prometen que todo callback
ejecutándose o encolado haya liberado sus referencias:
[`stopCapture`](https://developer.apple.com/documentation/screencapturekit/scstream/stopcapture(completionhandler:)),
[`removeStreamOutput`](https://developer.apple.com/documentation/screencapturekit/scstream/removestreamoutput(_:type:)).
Tampoco `obs_wait_for_destroy_queue` demuestra esa condición en la cola SCK.
Se conserva el [bloqueo de reconstrucción live](h21-sck-lifecycle.md).

### Política de suspensión

No se añade una gracia temporal: una suspensión breve que terminó entre
consultas no prueba pérdida persistente actual; una suspensión confirmada no
se oculta durante un plazo arbitrario. Se conserva el Cut a la escena segura
elegida, sin cambiar encoders, mixer o identidad de captura. El retorno requiere
una acción explícita y superficies completas recientes de la fuente existente
en el momento de ejecutar la selección; cuando cumple esa condición, rearma
una oportunidad. Mejorar por sí sola no hace volver la escena. El primer
fullscreen C8.1 muestra el límite: una observación `complete` anterior no basta
si al retornar ya hay `idle`. El recorrido corregido espera el final real de
AppKit y observa el rearmado. Registra un transitorio `suspended` en cada
dirección, pero sólo la salida produce respaldo: al consultar la entrada ya
hay superficies `complete`. No cubre dos respaldos consecutivos. No se añade
una gracia temporal ni se provoca un respaldo retroactivo por esa historia.

En C8.2 el verificador consulta estado durante la transición AppKit y espera
también que termine cualquier transición de escena antes del retorno. Observa
dos respaldos, dos retornos explícitos y los callbacks reales de entrada/salida;
ambos medios pasan el análisis. Es una mejora de cobertura del instrumento,
no una política nueva que fuerce respaldos por un evento ya resuelto. El
recorrido usa una ventana propia de 10 Hz a 1080p30; no certifica fullscreen de
cualquier juego ni que una consulta autónoma más espaciada vea cada transitorio.

Window conserva ID/PID; Application conserva bundle/PID/display; Display exige
identidad explícita y contenido cubierto. Cambiar foco, nivel o Space no autoriza
otra ventana/pantalla. Un resultado en Window no se extiende a Display durante
un cambio de resolución. El cambio manual de Spaces C8 sí fue observado; el
período fuera del Space quedó `static_or_unobserved`/`idle`, separado del avance
decodificado antes y después. No se promete imagen nueva de una ventana oculta.

## Audio y medida física

El bloque C7 r3 alcanzó el umbral del medidor **pre-fader**; la mezcla no saturó.
Por ello bajar únicamente el fader no corrige la señal ya recibida. Sin embargo,
el medidor OBS está después de la ruta de entrada/resampling: esa observación
no identifica por sí sola clipping del ADC, procesamiento del sistema o una
etapa anterior de software. “Pre-fader” no equivale a “hardware demostrado”.

El módulo oficial CoreAudio usa `AudioConvertHostTimeToNanos(mHostTime)`;
AVFoundation convierte el presentation timestamp del sample. Libobs adapta
esas entradas a su procesamiento. Ver timestamps crecientes o una referencia
generada dentro de otra aplicación no calibra exposición de cámara, propagación
acústica, procesamiento de micrófono o latencia del dispositivo.
Fuentes: [CoreAudio](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/mac-capture/mac-audio.c)
y [AVFoundation](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/mac-avcapture/OBSAVCapture.m).

Las dos tomas breves C8 usaron temporalmente scalar 0,2 con la autorización
previa, y restauraron exactamente 0,3764705955982208. No registraron clipping
de entrada ni mezcla. La segunda eliminó tonos y cambios de escena: hay manos
visibles contactando, pero los transitorios acústicos fuertes no forman una
correspondencia inequívoca con esa serie. Las señales bajas podrían deberse
al gesto, entorno o procesamiento; no se elige una hipótesis como causa probada.
No se emparejan picos posteriores de voz/mesa con contactos anteriores para
fabricar un offset. La prueba de un minuto tampoco certifica deriva horaria.
La [calibración requerida](h21-c8-physical-calibration.md) conserva estos límites.

### Audio de aplicación y desaparición de una pantalla en C8

El primer intento prolongado de SuperTuxKart se interrumpe a **1106,020 s**
por `SYSTEM_AUDIO_STREAM_STOPPED`. El log oficial informa la rama
`SCStreamErrorNoCaptureSource`. El PID del juego seguía siendo el admitido;
la captura de video conservaba `complete`, cero errores y cero suspensiones.
Ambos destinos estaban activos hasta el cierre controlado. No fue otro crash
del juego ni una suspensión de video equivalente a CAP-01.

Al comenzar había dos pantallas; la observación posterior sólo encuentra la
integrada. La ventana cambia de 1920×1050 a 3456×2100. El módulo oficial
[`mac-sck-audio-capture.m`](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/mac-capture/mac-sck-audio-capture.m)
construye también el filtro de audio de aplicación sobre un display. Este
archivo es idéntico en el master fijado. Motive fija la pantalla principal al
admitir el canal y no sustituye esa identidad silenciosamente.

La desaparición del display es, por tanto, una explicación consistente con
las observaciones; no se conoce qué la ocasionó ni se demuestra un defecto
interno de SCK. El intento queda **FAIL**, con ambos medios decodificados,
una pausa visual de unos 0,77 s cerca del cambio y silencio al final. El
verificador no había retenido las trazas terminales de su ruta de fallo:
esa entrega queda INCONCLUSIVE; la ruta posterior conserva también esos datos.
La repetición usa la topología actual y observaciones pasivas de sus cambios,
sin modificar preferencias ni reconstruir SCStream durante outputs.

En el mismo intento, los contadores reportan 222 frames omitidos por encoding
lag, aunque el compositor no registra frames tardíos y los destinos indican
cero drops. OBS puede repetir un frame y avanzar su timestamp cuando falta
espacio en la cola de video; una cadencia codificada de 60 FPS no demuestra
60 imágenes distintas. Véanse
[`video-io.c`](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/media-io/video-io.c)
y [`obs-video-gpu-encode.c`](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs-video-gpu-encode.c).
Los contadores y medios se conservan separadamente. No se atribuye el cuello de
botella a VideoToolbox, al juego o a Motive sin una comparación que lo localice.

### Falsa desaparición de aplicación: corrección C8.1

El segundo intento prolongado C8 se detiene a **2586,611 s** con
`APPLICATION_UNAVAILABLE`. El supervisor aún posee vivo el proceso del juego
PID 39785; la ventana 21757 conserva ese PID. Hay una superficie completa de
video con edad de 7 ms y audio con edad de 16 ms, sin clipping ni suspensión
SCK. La topología permanece en la pantalla integrada. Sin embargo,
`NSRunningApplication` devuelve cero instancias del bundle y ninguna referencia
para el PID. La política anterior convertía esa ausencia de catálogo en cierre
de aplicación. Es un fallo confirmado de la integración Motive; no demuestra
por qué desapareció la entrada de LaunchServices ni un fallo de SCK.

Ambos archivos del intento fallido se decodifican completos: 155.249/155.230
frames, separación máxima 17 ms video y 22 ms audio. El análisis de medios pasa,
pero el intento conserva FAIL y no cuenta como hora completa. Los contadores
muestreados conservan 272 frames omitidos por encoding, 3 tardíos del compositor
y 1.051 descartes de preview; cero drops de destino no borra esos datos.

**C8.1 fija PID, UID, fecha de creación y ruta de ejecutable al admitir el canal.**
La admisión sigue exigiendo una aplicación única coincidente entre SCK y el
catálogo. Durante la captura, `proc_pidinfo`/`proc_pidpath` comprueban sólo ese
PID, con observaciones de nacimiento antes/después de la lectura de ruta. Un
catálogo vacío deja de bastar para declarar muerto un proceso verificado.
Muerte, cambio de generación/ejecutable, conflicto positivo de bundle/PID,
ambigüedad, permiso perdido, display perdido y stop terminal siguen fallando.
Si no se puede observar la identidad OS, se emite
`APPLICATION_IDENTITY_UNAVAILABLE`; no se autoriza una sustitución.

La ruta y fecha de nacimiento permanecen en memoria privada; los diagnósticos
exponen resultado de comparación y contador de ausencias del catálogo. No se
modifican filtros del stream admitido, relojes ni lifetime. Cada observación es
puntual: no prueba que el proceso siga vivo después ni una barrera de callbacks.
El contrato nativo prueba un hijo real que ejecuta otro binario con el mismo PID
y luego termina; los contraejemplos de UID/nacimiento se inyectan y no equivalen
a provocar reutilización real de PID. La ausencia de catálogo también se inyecta
en el contrato; la prueba prolongada informa por separado si reaparece realmente.
La regresión de la app firmada prueba cierre/reinicio real, rechazo de seguimiento
automático y reconexión explícita estando idle, con audio grabado y decodificado.
Referencias: [semántica de NSRunningApplication](https://developer.apple.com/documentation/appkit/nsrunningapplication),
[advertencia sobre comparar sólo PID](https://developer.apple.com/documentation/appkit/nsrunningapplication/processidentifier)
y [wrappers oficiales libproc](https://github.com/apple-oss-distributions/xnu/blob/main/libsyscall/wrappers/libproc/libproc.c).
El manifiesto `application-identity-review.json` conserva también los hashes de
los headers del SDK realmente compilados. El método no compara solamente PID.

### Extensión a video Application en C8.2

La revisión de `visual_health` encontró la misma condición de catálogo en la
captura de video por Application: consultaba de nuevo `capture_application` y
trataba un resultado ausente como pérdida del proceso. El fallo de los 43 minutos
usaba video Window, por lo que **no demuestra un fallo real de video Application**.
Sí aporta un contraejemplo verificable a esa premisa compartida. C8.2 aplica a
Application la misma comprobación de identidad OS, fijada durante la admisión
estricta; no cambia filtros ni selecciona otra aplicación o pantalla.

La observación se actualiza también cuando la fuente está fuera de Program,
sin activarla. Esto permite que rearmar el respaldo mediante un retorno explícito
exija identidad actual coincidente además de superficies completas recientes. Los errores de fuentes
inactivas siguen sin convertirse en fallos globales; una identidad ausente,
reemplazada o no observable impide rearmar desde metadata antigua. El test de
política cubre esos casos sin presentarse como prueba física de SCK.

La hora Window de C8.1 pasa el análisis completo con 3.291 observaciones OS
coincidentes y **cero ausencias naturales de catálogo**. Ese resultado es una
regresión prolongada del binario corregido; no demuestra haber reproducido y
superado otra desaparición real de LaunchServices. Los resultados de video
Application de C8.2 se identifican por separado en la matriz, con otro hash.

## Paquetes terminales

La traza Motive está **antes** del plugin de salida. En OBS 33.0.1,
[`obs-ffmpeg-mux.c`](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/obs-ffmpeg/obs-ffmpeg-mux.c)
comprueba `sys_dts_usec >= stop_ts` antes de escribir; el hilo
[`rtmp-stream.c`](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/obs-outputs/rtmp-stream.c)
también aplica su frontera de parada (o timeout). Ambos archivos son idénticos
en el master consultado. La observación en
[`obs-output.c`](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs-output.c)
no implica aceptación posterior por mux, red ni receptor.

| Evidencia | Interpretación C8 |
|---|---|
| Dispatch válido anterior a todo el bracket, ausente del medio | FAIL de entrega no explicado |
| Dentro del bracket de petición/retorno | Frontera indeterminada; no se inventa `stop_ts` exacto |
| Después de todo el bracket | Compatible con descarte normal OBS; ausencia no es automáticamente un bug |
| Receptor terminado deliberadamente | Entrega parcial esperada; no exonera toda otra pérdida |
| Origen vacío, snapshot busy, hueco o extremo terminal perdido | Instrumentación inconclusa |
| Correspondencia uno a uno de todo el tail retenido | PASS de ese tail, no de cada paquete de una hora |

Charlas C7 guardó una traza RTMP inicial vacía pese a que el output ya estaba
`active`. Es un defecto confirmado del verificador: conexión activa no implica
primer paquete despachado. C8 recoge cada origen inmediatamente después de
activar su destino, antes de iniciar el siguiente; espera dentro de un plazo
de diagnóstico hasta observar audio y video, secuencia desde 1, sin pérdida ni
overwrite. Si falta, falla cerrado. No retrasa stop, modifica paquetes ni cambia
clocks. Los informes históricos permanecen intactos; una nueva interpretación
semántica se conserva junto a su clasificación original.

En la matriz C8.2, la primera grabación se pidió mientras el tono tenía **cero
muestras** y fase `warming`. Motive rechazó correctamente el arranque con
`AUDIO_NOT_READY`; aún no había ninguna salida iniciada ni pérdida de paquetes.
El verificador se corrige para esperar muestras reales y fase `ready`, con
plazo acotado. La repetición observa 480 frames de audio antes de empezar y
pasa. Se conservan el FAIL original y los otros ocho casos sin repetirlos.

El agregado de esa matriz devolvía código 0 incondicionalmente, incluso con un
caso funcional FAIL. Ahora requiere nueve informes únicos, distingue PARTIAL de
PASS y devuelve fallo cuando falta cobertura o un caso falla. Tres tests
protegen esa clasificación. El agregado original de comandos no certifica por
sí solo los resultados internos; el informe resuelto liga explícitamente los
ocho casos conservados y la repetición al mismo hash de C8.2.
