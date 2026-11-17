# H13 — decisiones previas a la implementación

Base: `b52d135`, libobs/OBS Studio 33.0.1, macOS Apple Silicon.
Este documento registra decisiones de diseño; no es una declaración de
capacidades verificadas. La evidencia multimedia se añadirá por incremento.

## Recursos y relojes que se conservan

Una sola `Production` en el owner GPUI serializa UI, CLI y MCP. Una sola
instancia OBS compone las escenas y mezcla las entradas globales. Los callbacks
nativos publican observaciones acotadas; los comandos no producen frames ni
marcan el reloj multimedia. Las fuentes visuales se reutilizan por identidad,
las escenas poseen sus items y las transiciones Cut/Fade poseen la salida 0.
El mixer conserva canales 1–8, mezcla 0, captura física única por UID, monitoreo
desactivado, medidores post-fader/pre-mute y master post-mute/pre-clamp.

Las fuentes conservan sus timestamps. El tono usa su reloj de muestras sobre
tiempo monotónico; OBS mantiene los relojes de video/audio. No se añade DSP ni
un segundo compositor. Los fallos de una entrada H10 aíslan esa entrada;
los fallos de video compartido conservan la parada controlada y recuperación
explícita. Los perfiles de salida v1 y los proyectos v1–v4 siguen siendo legibles.

## Canvas: coordenadas estables, composición a resolución real

El primer incremento introduce configuración tipada, acotada y versionada.
Las coordenadas de edición siguen siendo 960×540 horizontal y 540×960 vertical.
El proyecto v5 declara ese espacio lógico y la configuración de video; cargar
v1–v4 conserva explícitamente 540p30 y sus transformaciones originales. Cambiar
resolución no reescribe coordenadas ni mezcla los dos layouts. La composición
base y la salida OBS usan las dimensiones elegidas; posición, bounds y distancia
de animación se escalan uniformemente al pasar al motor nativo. No se presenta
un simple reescalado de un frame 540p como composición 1080p.

`obs_reset_video` requiere todas las salidas quiescentes, sin transición ni
animación pendiente. Se desconecta el preview, liberan outputs/encoders inactivos,
reserva el buffer nuevo y se restablece explícitamente la configuración anterior
si falla: OBS puede haber destruido el contexto de video previo. La captura SCK
toma los FPS al arrancar, por lo que cambiar FPS requiere renovar esas capturas
con la producción detenida. Resolución/FPS de composición y de captura se
informan por separado: la cámara actual solicita 720p y no acredita 1080p60.
720p30 y 1080p30 se prueban antes de ampliar a 1080p60/vertical.

## Dos salidas: encoders independientes, medios compartidos

OBS admite fan-out de un encoder compatible hacia varios outputs; su frontend
lo utiliza para grabar con el encoder de streaming. Reduce trabajo cuando los
perfiles coinciden, pero también acopla bitrate, GOP, reordering y los fallos.
En OBS 33.0.1 `obs-encoder.c::full_stop` detiene todos los outputs asociados a
un encoder fallido. Por eso el primer incremento usa dos pares independientes
H.264/AAC, conectados al mismo `obs_get_video()` y `obs_get_audio()`.
No duplica fuentes, capturas, escenas ni mezcla. El coste adicional se medirá.

Cada slot estable (`recording`, `streaming`) posee output, service si aplica,
encoders, señales atómicas, actividad macOS, métricas y recuperación. Un fallo
local detiene y bloquea únicamente ese slot; un fallo compartido solicita la
parada de ambos y conserva el motivo. Auto elige VideoToolbox con fallback x264
antes del arranque; no cambia el encoder de una salida activa.

La barrera H8 `get_thread_state` sigue siendo obligatoria por instancia RTMP.
Una señal stop o `obs_output_active == false` no acredita que terminaron los
workers. Cancelar una conexión difiere la parada hasta un punto seguro. Ni el
cierre ni el recovery liberan un slot antes de su quiescencia. El parche fijado
no se amplía sin nueva evidencia. Los comandos antiguos conservarán su uso con
una única salida y rechazarán ambigüedad cuando haya dos; habrá comandos por
destino y una parada explícita de todos.

## Audio del sistema: adaptador del módulo oficial

Se reutiliza `sck_audio_capture`. El módulo fijado captura escritorio/aplicación
y excluye el propio proceso, pero usa el display principal y selecciona el
primer bundle ID coincidente. El contrato validará identidad estable y unicidad
antes de crear la fuente; nunca persistirá PID ni elegirá una aplicación ambigua.
Escritorio y aplicación no podrán coexistir en el mixer por su solapamiento.
La selección será explícita y la restauración verificará el mismo destino.

El adaptador separará silencio de ausencia de paquetes. La señal pública
`update_properties` permite observar una parada del stream en este módulo,
sin leer su struct privado ni invocar el panel de propiedades como polling.
La señal no proporciona el NSError: el fallo publicado será genérico y honesto.
Ganancia, mute, medidores y recuperación usarán el mixer existente. Un almacén
versionado nuevo permitirá cargar el v1 sin alterar escenas ni perfiles.

## Referencias oficiales revisadas

- [OBS 33.0.1: reset de video](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs.c).
- [API core: obs_reset_video](https://docs.obsproject.com/reference-core).
- [OBS 33.0.1: encoder y propagación de fallos](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs-encoder.c).
- [OBS 33.0.1: outputs](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs-output.c).
- [OBS 33.0.1: audio ScreenCaptureKit](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/mac-capture/mac-sck-audio-capture.m).
- [OBS 33.0.1: video ScreenCaptureKit](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/mac-capture/mac-sck-video-capture.m).

## Orden y gates

Canvas y archivos reales primero; después audio del sistema, dos outputs,
contratos completos y GPUI. Cada incremento estable tendrá pruebas relevantes
y commit local. Pruebas físicas seriales bajo el lock compartido, bundle firmado
identificado y fallos conservados. La aceptación final exige operación GPUI,
decodificación de ambos medios, métricas, prueba prolongada y regresiones H1–H12.
No hay autorización H13 para push, merge, release ni emisiones públicas.
