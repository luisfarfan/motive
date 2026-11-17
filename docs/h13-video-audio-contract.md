# H13 — contrato de canvas y audio del sistema

Implementado en el propietario compartido `Production`. La evidencia por
incremento y sus límites están en [verificación](h13-production-verification.md);
la aceptación del bundle GPUI final sigue pendiente. Las salidas se describen en
su [contrato independiente](h13-output-contract.md).

## Canvas

`video_capabilities` devuelve PID y capacidades; `status.video` es la observación
real del motor, con disponibilidad, dimensiones base/salida, FPS, espacio lógico
y error. No inferir configuración efectiva únicamente de un borrador UI.

```json
{"op":"configure_video","video":{"version":1,"resolution":"full_hd1080","fps":30,"coordinate_space":"design960"}}
```

`resolution`: `legacy540` (960×540), `hd720` (1280×720), `full_hd1080`
(1920×1080). `fps`: 30 o 60. La variante vertical intercambia dimensiones;
`set_variant` conserva su contrato. El núcleo rechaza campos desconocidos,
FPS/versiones fuera del conjunto y cambios con salidas, transiciones,
animaciones o importaciones pendientes. La UI presenta el mismo bloqueo y
envía `ConfigureVideo`; no invoca OBS ni reconstruye capturas por su cuenta.

Las coordenadas de capas continúan siendo 960×540/540×960. Cambiar resolución
escala uniformemente al componer, sin reescribir transforms ni usar dimensiones
físicas para hit-testing. Proyecto v5 exige `video`; v1–v4 cargan como 540p30
y rechazan una extensión `video` silenciosa. Guardar configuración explícita
migra a v5. Mixer y perfiles permanecen en almacenes separados.

El cambio nativo reserva memoria, desconecta preview y libera encoders
quiescentes antes de `obs_reset_video`; un fallo intenta restablecer el video
anterior. Si esa recuperación falla, `VIDEO_RECOVERY_REQUIRED` impide iniciar
salidas. La UI debe mostrar el error y permitir reconfigurar con salidas paradas.

El compositor a 60 FPS no garantiza 60 frames de la cámara o ventana. Cámara
solicita preset 720p; ventana renueva su fuente OBS al cambiar FPS. El módulo SCK
detiene SCStream de manera asíncrona: no se acredita ausencia de solapamiento
transitorio. El preview actual copia BGRA a resolución de salida y GPUI consulta
cada 33 ms. Texto/imagen/widget conservan resolución intrínseca de su definición.

## Descubrimiento y selección de audio

`system_audio_sources` es una consulta explícita, de solo lectura. No pide
permisos ni enumera aplicaciones en cada frame UI. Devuelve `SystemAudioSources`:
`available`, `permission`, `issue`, `applications`, `displays`, política de
exclusión y solapamiento. GPUI conserva el resultado para presentar el selector;
Actualizar vuelve a consultar. Un inventario viejo no autoriza una captura:
el núcleo revalida al crear/reconectar.

```json
{"op":"add_audio_input","name":"Aplicación seleccionada","source":{"kind":"system_application","bundle_id":"local.motive.audiofixture"}}
{"op":"add_audio_input","name":"Escritorio seleccionado","source":{"kind":"system_desktop","display_uuid":"UUID_CANONICO_DEL_INVENTARIO"}}
```

Estos ejemplos son alternativas: escritorio y aplicación se solapan. El UUID
real debe ser el del display principal devuelto como `selectable`; el texto de
ejemplo no es un UUID válido. Se reutiliza `sck_audio_capture` oficial, cuya
implementación actual usa el display principal. Bundle ID identifica la
aplicación, no un PID persistido. Un bundle con varias instancias no es
seleccionable; tampoco lo es Motive. Un display secundario no se selecciona
silenciosamente como principal.

`AudioSource` añade `SystemApplication { bundle_id }` y
`SystemDesktop { display_uuid }` a Tone/Microphone. El mismo destino reutiliza
su canal, ID y controles. El almacén rechaza escritorio junto a cualquier otra
captura de sistema, incluso si está silenciada/desconectada. Esto evita duplicar
sonido después de un unmute/recovery. Diferentes aplicaciones pueden coexistir.

Añadir/quitar/restaurar requiere salidas detenidas; gain, mute y reconexión de
una entrada existente conservan las operaciones H10 en vivo. Ocho entradas
máximo, ganancia finita −60…+24 dB. No hay otro mezclador, audio por escena,
efectos ni monitorización. SCK entrega timestamps originales a libobs.

## Estados, niveles y recuperación

`AudioInputRuntime` conserva ID/instance ID, fase, issue y niveles del mismo
canal. `ready` significa paquetes observados, no sonido audible. `awaiting_audio`
informa ausencia reciente de muestras sin retirar automáticamente la captura;
no se presenta como silencio. SCK puede entregar paquetes de ceros cuando una
aplicación deja de reproducir: esos paquetes mantienen `ready`.

Pérdida de aplicación, cambio de PID, display principal incompatible, permiso
perdido o señal de parada del stream aíslan la entrada y retienen el fallo.
`reconnect_audio_input` revalida y reabre explícitamente solo esa entrada. La
captura restante y ambas salidas continúan. La señal pública del módulo no
entrega NSError al adaptador: `SYSTEM_AUDIO_STREAM_STOPPED` no inventa una causa.

Medidores por entrada: post-fader/pre-mute manual; master: post-mute/pre-clamp.
La UI muestra los niveles observados, edad de muestras y clipping, sin generar
animaciones que aparenten señal. Silenciar no borra el medidor de entrada.
`SYSTEM_AUDIO_NO_SAMPLES` es informativo; fallos latched requieren recuperación.
Los demás códigos tipados están en `AudioIssueCode` (`src/audio.rs`).

Mixer v1 sigue cargando y rechaza fuentes de sistema. Añadirlas promueve el
almacén a v2; `save_audio_mixer`/`load_audio_mixer` conservan identidad y no cambian
escenas ni perfiles. Ningún inventario PID o estado de ejecución se persiste.

Los IDs persistidos tienen la forma canónica `audio-N`: `N` es un entero
decimal positivo, menor que `next_id`, sin signo ni ceros iniciales. El ID debe
ocupar menos de 64 bytes; los IDs generados incluso cerca del límite de `u64`
cumplen ese tamaño. Esta validación se aplica al documento completo antes de
renombrar o retirar capturas durante la restauración. Rechaza, por ejemplo,
`audio-01`, `audio-+1`, cadenas alargadas con ceros, dígitos Unicode y NUL
embebido, con `INVALID_AUDIO_STORE: input id`.

No se renumeran IDs válidos ni cambia la versión del mixer: los documentos v1/v2
generados por Motive conservan sus identidades y su formato. La restricción
repara un caso de documento malformado que podía pasar el parseo numérico,
truncarse en el registro nativo y dejar desalineados sus nombres y el almacén
Rust. El renombrado nativo ahora rechaza nombres vacíos, nulos, demasiado largos
o fuera del alfabeto ASCII alfanumérico/guion antes de modificar la captura;
`INVALID_AUDIO_ID` distingue ese rechazo. Mantiene los nombres privados
`restore-N` usados para permutar canales sin duplicar dispositivos. El puente
`CString` también rechaza NUL embebido antes de llamar C.

La prueba de modelo cubre esos documentos malformados y el round-trip de IDs
ordinarios y del mayor ID asignable. Esa prueba y la defensa de código no
sustituyen una prueba física de restauración del bundle final.

## Adaptador GPUI y límites de prueba

`studio/configuration.rs` presenta canvas/FPS y accesos a perfiles/encoder.
`studio/audio.rs` añade selección explícita aplicación/escritorio al mixer H10;
usa los mismos comandos, medidores y recuperación. No mantiene otra instancia
del núcleo ni copia reglas de mezcla. CLI y MCP usan los mismos nombres de
operación, validación estricta y PID/revisión observables.

Probado por medios reales: presets de canvas, tonos/aplicación, micrófono,
ganancia/mute, recuperación de aplicación, Cut/Fade y persistencia. Exclusión
de Motive comprobada mediante emisor diagnóstico opt-in y control positivo de
igual frecuencia desde otra aplicación. Sincronía A/V pasó con ventana visible;
los congelamientos anteriores quedan conservados y su causa sigue abierta.
Permisos revocados, USB hot-unplug, cambio físico de display, sleep/wake y
`awaiting_audio` por falta real de paquetes no se simulan como aceptación.
