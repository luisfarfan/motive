# H11 — Contrato de integración de overlays para GPUI

Contrato de implementación del núcleo compartido, revisado contra el código H11.
Este documento no es evidencia de aceptación visual: las grabaciones, métricas y
regresiones pertenecen al informe de verificación. Browser Source permanece
bloqueado; no hay capacidad HTML/JavaScript habilitada.

## Un solo propietario de producción

El adaptador `SharedProduction` de la nueva GPUI debe conservar su instancia
existente de `Production`. H11 no introduce otro singleton, renderer, mixer ni
servicio de producción. Despachar en el hilo propietario existente:

```rust
use crate::core::{Command, overlays::OverlayCommand};
let reply = production.apply(
    Command::Overlay(OverlayCommand::OverlayState),
    "UI",
);
```

`SharedProduction` es el punto de integración de la UI, no un tipo nuevo definido
por H11 en `core`. Para formularios se usan `core::overlays::{Definition, Widget,
WidgetKind, Font, Alignment, Shape, Event, Animation, AnimationKind, Easing,
Preset, PresetParameters}`. Las acciones de escena siguen usando `Command`.
No llamar FFI/libobs desde componentes GPUI, crear hijos OBS en la vista, escribir
JSON de proyecto desde la UI ni calcular timers/animaciones con tareas de GPUI.

Mantener el `poll_health()` del propietario en su cadencia existente. Este recoge
operaciones y publica cambios de ciclo de vida; OBS avanza los frames, fades y
medios aunque no haya clientes CLI/MCP conectados. Un contador local de GPUI puede
servir para refrescar la presentación, pero nunca para decidir que terminó una
operación, enviar eventos por frame o modificar `remaining_ms`.

CLI, MCP y UI llegan al mismo `Production::apply`. CLI usa
`motive ctl '{"op":"overlay_state"}'`; MCP usa la herramienta `overlay_state`
con `{}`. Consultar `overlay_capabilities` y `tools/list` para capacidades y schemas.
Los objetos son estrictos: campos extra, ausentes, tipos incorrectos y enums no
admitidos fallan. `update_overlay` recibe una **definición completa**, no un patch;
los campos opcionales representados por `null` también deben estar presentes.

## Respuestas, identidad y revisión

Las consultas H11 devuelven `{ok:true,pid,revision,result}`. Las mutaciones aceptadas
incluyen además `state`, el snapshot completo de producción. Los fallos H11 llevan
`{ok:false,error:{code,message},revision,overlays}`; errores de transporte/parser
pueden tener solo `ok` y `error`. `status` conserva su envelope histórico
`{ok:true,state:{pid,revision,...}}`. No asumir que todos los comandos antiguos
usan el envelope H11.

Unir fuentes por `source_id`/`id` y capas por `scene_id` + `layer_id`, nunca por
posición en arrays. Usar IDs devueltos; `source-2` y `layer-3` en ejemplos son
ilustrativos. `instance_id` y `child_instances_created` son diagnósticos de recursos
nativos de este proceso; no son IDs persistentes ni números para construir URLs.

`revision` cambia por controles y cambios observados de ciclo de vida; no es un
reloj ni aumenta en cada muestra de progreso, fade, audio o countdown. Refrescar
los valores de runtime aun si la revisión no cambió. Combinar `pid` con la revisión
para distinguir un estudio reiniciado. No hay parámetro público `expected_revision`
ni transacción de edición optimista: leer el estado actual antes de reemplazar una
definición editada desde otra superficie.

Una respuesta `ok:true` a una animación o importación significa aceptación. Guardar
su `operation_id` y observar el estado terminal. Importación y animación tienen
contadores independientes: no pasar un token de importación a cancelación de
animación. No hay comando para cancelar una importación; su worker tiene límites
y timeout. Si se pierde la respuesta, consultar
estado antes de decidir la siguiente acción: nunca reintentar automáticamente una
mutación. La capa de transporte solo reintenta consultas. `TIMEOUT` no demuestra
que la operación no haya ocurrido.

## Definiciones, capas, runtime y assets

| Ubicación | Qué contiene | Uso en GPUI |
|---|---|---|
| `state.project.graph.sources[].overlay` | `Definition` deseada, persistente; `null`/ausente distingue fuentes anteriores | Formulario editable de propiedades |
| `state.project.graph.scenes[].layers[]` | `source_id`, layouts horizontal/vertical, geometría, visibilidad y orden de cada instancia | Árbol y canvas de escena |
| `state.overlays.definitions[]` | Las fuentes completas con `overlay`, incluido `id`, `name`, `spec` | Índice de overlays; misma definición que el proyecto |
| `state.overlays.runtime.sources[]` | Estado nativo por `id`, salud, fase, relojes, instancia | Indicadores de ejecución |
| `state.overlays.runtime.animations` | Disponibilidad, ocupación y últimas operaciones por capa | Progreso/cancelación |
| `state.overlays.import` | Última importación, `null` o `{operation_id,phase,...}` | Progreso y resultado de biblioteca |
| `state.overlays.completion_error` | `null` o error de reconciliación/ack interno de animación | Diagnóstico; no declarar la escena disponible hasta que `busy` sea false |
| `list_assets.result.assets[]` | Metadatos administrados y verificados, sin bytes ni ruta de origen | Selector de recursos |

`overlay_state.result` equivale a `state.overlays`, y declara `definition_version:1`.
Una definición es compartida: añadir otra capa con `add_layer` reutiliza la misma
fuente y sus hijos, incluso en otras escenas. Cambiar su texto, opacidad, timer o
estado de video afecta todas sus capas. Para dos contenidos/timers independientes,
crear dos fuentes. El mismo `asset_id` deduplica el archivo administrado, pero dos
fuentes de video independientes pueden tener dos decoders y relojes propios.

Crear un overlay también crea una capa con `Layouts::secondary()`. El resultado
contiene `source_id`; recuperar su `layer_id` desde el grafo devuelto antes de
posicionarla. No adivinar el ID ni dar por hecho que la caja inicial llena la escena.
Los layouts usan coordenadas de canvas: horizontal 960×540, vertical 540×960.
Cada variante tiene su transform completo `{x,y,width,height,visible,order}`;
posiciones finitas ±4096, tamaños 1..4096, orden entero 0..31. Por ejemplo:

```json
{"op":"set_transform","scene_id":"scene-1","layer_id":"layer-3","variant":"horizontal","transform":{"x":32.0,"y":368.0,"width":640.0,"height":140.0,"visible":true,"order":4}}
```

Cambiar ese layout no cambia el vertical ni el tamaño intrínseco de la definición.
Para reusar: `add_layer {scene_id,source_id}`. Para eliminar: quitar todas las capas,
`remove_source {source_id}` y, solo si ya no está referenciado, `remove_asset`.
No existe un comando separado `remove_overlay`.

El antiguo `spec:{kind:"overlay",color:...}` sin `overlay:Definition` sigue siendo
el patrón H1–H9. No usar `set_overlay_color` para H11: devuelve
`USE_OVERLAY_PROPERTIES`. H11 conserva ese `spec` por compatibilidad del grafo, pero
la fuente de verdad de sus propiedades es `overlay`.

## Comandos y precondiciones

En esta tabla, **idle** exige salida nativa detenida, importación terminada y ausencia
de animación por capa o Cut/Fade pendiente. **Escena estable** exige ausencia de
animación por capa y Cut/Fade; permite grabación/RTMP. Todas las mutaciones H11 se
rechazan durante apagado pendiente (`SHUTDOWN_PENDING`). La UI puede deshabilitar
controles, pero la validación definitiva siempre es del núcleo.

| Comando | Argumentos | Cuándo / resultado |
|---|---|---|
| `overlay_capabilities` | ninguno | Consulta schemas, límites, fuentes registradas y exclusiones |
| `overlay_state` | ninguno | Consulta definiciones y runtime |
| `overlay_presets` | ninguno | Catálogo original v1 con parámetros iniciales |
| `list_assets` | ninguno | No durante importación; verifica archivos, no consultar por frame |
| `import_asset` | `file_name` | Idle; devuelve `result.import`, inicialmente `running` |
| `remove_asset` | `asset_id` | Idle; requiere ausencia de referencias en todas las definiciones |
| `create_overlay` | `scene_id`, `name`, `definition` | Idle; devuelve `result.source_id` |
| `update_overlay` | `source_id`, `definition` | Escena estable; video exige además idle; `result:null` |
| `overlay_event` | `source_id`, `event` | Live o idle; acciones de fuente independientes de Cut/Fade y de animaciones de capa |
| `animate_overlay` | `scene_id`, `layer_id`, `animation` | Solo escena activa, sin Cut/Fade en curso; live o idle; devuelve `result.operation_id` |
| `cancel_overlay_animation` | `operation_id` | Solicita cancelación; comprobar fase terminal |
| `instantiate_overlay_preset` | `scene_id`, `preset`, `parameters` | Idle; devuelve `preset_version:1`, `source_ids` |

`update_overlay` conserva `kind`, `asset_id`, tipo de widget y tipo de shape.
Cambiar de rectángulo a círculo, imagen a video, recurso o widget requiere otra
fuente (`OVERLAY_RESOURCE_IMMUTABLE`). Texto/colores/opacidad/dimensiones y contenido
admitido reutilizan fuentes e hijos. La definición se acepta antes de que OBS
aplique su actualización diferida; confirmar salud y resultado visual en runtime.

Los comandos existentes `set_transform` y `rename_scene` permiten cambios con
salida activa si la escena está estable. `set_transform` requiere idle si cambia
`visible`; los cambios de geometría/orden no. `add_layer`, `remove_layer`,
`remove_source`, cambios estructurales, `set_variant` y `load_project` requieren
idle. `save_project` requiere escena estable, pero puede guardar durante una salida.
Cut/Fade de escena y animaciones por capa se excluyen mutuamente en H11.

## Schemas y ejemplos completos

Colores son enteros RGB24 `0..16777215`, no strings CSS ni RGBA. `opacity` y
`background_opacity` son finitos `0..1`. Dimensiones de la caja fuente:
`width=1..1920`, `height=1..1080`; no sustituyen el transform de la capa. UTF-8 se
limita a 4096 **bytes** por texto; solo `\n` y `\t` se permiten entre caracteres de
control. El `maxLength` del schema no sustituye las validaciones de bytes/geometría.

Texto completo para crear una fuente:

```json
{"op":"create_overlay","scene_id":"scene-1","name":"Título","definition":{"kind":"text","text":"Motive\nEn vivo","font":"Helvetica","size":48,"color":16777215,"opacity":1.0,"align":"center","width":720,"height":180,"background":null,"background_opacity":0.0,"outline":false}}
```

Fuentes: `Helvetica`, `Arial`, `Menlo`; tamaño `8..192`; `align` es `left`, `center`
o `right`. Máximo 16 líneas y `cantidad_de_caracteres × size <= 24576`. El texto usa
FreeType oficial de OBS: saltos de línea explícitos, **sin ajuste automático de
líneas**. Se escala el bloque completo para caber, sin ampliarlo, y luego se alinea
ese bloque dentro de la caja. No es alineación independiente de cada párrafo,
editor de texto enriquecido, selección de fuentes arbitrarias ni promesa de
cobertura para todos los glifos. No hay fallback tipográfico garantizado: en el
piloto, Helvetica mostró un cuadro de glifo faltante para `✓`. No anunciar soporte
universal de Unicode/emoji por aceptar UTF-8. Texto vacío es válido y saludable.
`outline` usa el contorno fijo del hijo oficial, sin ancho configurable.

Las siguientes son definiciones completas para `create_overlay.definition` o
`update_overlay.definition`; sustituir el ID de ceros por el devuelto por importación:

```json
{"kind":"image","asset_id":"asset-0000000000000000000000000000000000000000000000000000000000000000","opacity":0.8}
```

```json
{"kind":"video","asset_id":"asset-0000000000000000000000000000000000000000000000000000000000000000","opacity":1.0,"looping":true}
```

```json
{"kind":"shape","shape":"rectangle","width":640,"height":140,"color":1121833,"opacity":0.9,"border_color":3401909,"border_width":2}
```

Shape admite `rectangle` o `circle`. El círculo se inscribe en la caja; no es una
elipse arbitraria. `border_color:null` elimina borde; `border_width` es entero
`0..32` y como máximo la mitad del lado menor. Los rectángulos pueden estirarse
mediante el layout; otros contenidos conservan proporción. Imágenes mayores que
la caja nativa se reducen proporcionalmente a un máximo de 1920×1080, conservando
sus dimensiones intrínsecas en metadatos/runtime.

```json
{"kind":"widget","widget":{"kind":"lower_third","title":"Alex Rivera","subtitle":"Creative producer","width":640,"height":140,"background":1121833,"accent":3401909,"color":15988730,"opacity":1.0,"duration_ms":0}}
```

Widgets requieren al menos 240×100, máximo 1920×1080. Título: hasta 160 caracteres
y 3 líneas; subtítulo: 256 y 4 líneas, además del límite UTF-8 general. Duración:
`lower_third=0`, `countdown=1000..3600000`, `alert=100..60000` ms. No admiten CSS,
JS, filtros de voz ni referencias a datos externos. Countdown muestra título y
contador grande centrados; conserva `subtitle` en la definición pero no lo dibuja
en esta versión. Lower third y alert usan título/subtítulo alineados a la izquierda.

## Eventos globales de fuente

```json
{"op":"overlay_event","source_id":"source-2","event":"show"}
```

| Fuente | Eventos | Semántica |
|---|---|---|
| Cualquier overlay | `show`, `hide` | Visibilidad interna de la fuente; compartida por todas sus capas |
| `lower_third` | `show`, `trigger`, `hide` | Inicialmente oculto; entrada/salida nativa de 300ms, desde la opacidad actual |
| `alert` | `show`, `trigger`, `hide` | Inicialmente oculto; trigger reinicia deadline; entrada/salida de hasta 300ms dentro de duración; hide inmediato |
| `countdown` | `timer_start`, `timer_stop`, `timer_reset` | Visible e idle al crear; start inicia/reanuda, stop pausa, reset vuelve al valor configurado sin arrancar |
| `video` | `play`, `pause`, `restart`, `stop` | APIs oficiales de media; observar estado real del decoder |

Start después de countdown completado inicia otro ciclo con la duración deseada.
Editar `duration_ms` no altera el tiempo en curso ni pausado: se adopta en reset
o en un start posterior a completar. Cambiar texto/estilo preserva el reloj.
Ocultar una fuente o cambiar de escena no pausa su countdown ni reinicia video.
Un evento no admitido para esa fuente devuelve `INVALID_OVERLAY_ACTION`.

`visible` en runtime representa la apariencia interna de la fuente, no si hay
una capa visible en la escena activa. Para explicar lo que se ve, combinar
visibilidad de la capa, fuente, opacidad y animación de capa. El valor
`effective_opacity` nativo es opacidad de definición × apariencia del widget;
no incluye la transición de la capa. Una entrada de capa no muestra mágicamente
un lower third cuyo estado global sigue oculto: enviar `show`/`trigger` cuando
esa sea la intención.

El countdown conserva tiempo monotónico y solo cambia el texto nativo cuando
cambia el segundo mostrado (`MM:SS`, redondeado hacia arriba). `remaining_ms` no es
un mandato para regenerar texto desde la UI. Alert expira sin sondeos MCP.

## Animación por capa y operaciones

```json
{"op":"animate_overlay","scene_id":"scene-1","layer_id":"layer-3","animation":{"kind":"slide_in","easing":"ease_out","duration_ms":600,"distance":160.0,"scale_from":0.8}}
```

Todos los campos de `animation` son obligatorios aunque alguno no se use por ese
kind. Duración `100..10000` ms; distancia finita `-1920..1920`; escala `0.1..2.0`.
Kinds: `fade_in`, `fade_out`, `slide_in`, `slide_out`, `scale_in`, `scale_out`.
Fade usa el `fade_transition` oficial por item y solo `linear`; slide/scale admiten
`linear`, `ease_in`, `ease_out`, `ease_in_out`. Slide mueve horizontalmente desde/hacia
`baseline.x - distance`; distancia negativa mueve el extremo hacia la derecha.

La animación actúa sobre un item de escena, sin modificar otras capas de la misma
fuente. El reloj es `obs_video_time`; la aceptación puede preceder al primer tick
(`started:false`, `start_ns:null`). En el terminal se restaura la geometría base:
entradas dejan la capa visible, salidas oculta; cancelación/fallo restaura visibilidad
y geometría previas. Solo la visibilidad terminal completada se reconcilia al
layout persistente. No guardar posiciones intermedias ni reconstruir escenas para
avanzar una animación.

Hasta ocho operaciones simultáneas en capas distintas; una segunda operación en
la misma capa falla. Hay historial acotado: no es un registro permanente. Fases:
`running`, `cancel_pending`, `completed`, `cancelled`, `failed`. `running` agregado
incluye las dos primeras; `busy` incluye además terminales con `pending_ack:true`.
Cada job también expone `pending_ack`. El propietario reconcilia su resultado y
confirma por FFI internamente; **no hay comando de ack para UI/CLI/MCP**. Los
terminales sin confirmar no se expulsan del historial: ocupan slots hasta que el
propietario los procese, evitando perder completions. La UI debe esperar
`animations.busy:false`, no solo una fase terminal, para habilitar Cut/Fade o
cambios estructurales.

El núcleo captura generación del grafo, variante y las identidades de
escena/capa/fuente al aceptar. Solo aplica visibilidad completada a esa generación
y variante; una operación antigua nunca modifica un documento nuevo por coincidir
los IDs. Esos datos de reconciliación son internos y no se exponen como parámetros
ni se persisten. `completion_error` señala una reconciliación/ack pendiente que
necesita diagnóstico; la UI no debe forzar una confirmación ni editar el layout
para fingir su terminación.

Cancelar una operación terminal aún retenida es éxito idempotente; un token
desconocido/expulsado falla. Los fallos nativos incluyen
`ANIMATION_ITEM_BUSY`, `ANIMATION_LAYER_UNAVAILABLE`, `ANIMATION_INTERRUPTED`,
`ANIMATION_STALLED`; el último representa Fade aún activo después del plazo más
3 segundos, no éxito por tiempo transcurrido.

## Importación autorizada y biblioteca

La capacidad pública acepta exclusivamente un **basename de la bandeja**
`var/imports`, nunca una ruta, URL, directorio, `file://` ni HTML. La carpeta `var`
pertenece al checkout compilado (`data_dir()`), no al directorio de trabajo del
cliente. Un picker GPUI debe obtener autorización normal del usuario, copiar solo
el archivo elegido a la bandeja privada con nombre seguro y luego enviar
`import_asset`. H11 no proporciona un comando que permita a MCP explorar o copiar
rutas arbitrarias del usuario. No convertir un campo libre de MCP en acceso del
picker.

Usar nombres ASCII de 1–120 bytes, empezando por alfanumérico, con letras/números,
`.`/`-`/`_`; sin separadores ni prefijo punto. La copia debe ser archivo regular con
un solo enlace; symlinks, hardlinks, directorios y raíces sustituidas se rechazan.
No modificar permisos globales ni eliminar el archivo original tras importarlo.

```json
{"op":"import_asset","file_name":"logo-autorizado.png"}
```

Una sola importación se valida en worker acotado. Observar
`overlay_state.result.import.phase`: `running` → `completed` con `asset`, o `failed`
con `error`. La fuente se crea después de obtener un `asset.id` completado; una
importación aceptada no es aún un asset disponible. El catálogo devuelve
`{id,kind,width,height,bytes,sha256,duration_ms,has_audio}`; nunca el nombre/ruta de
origen ni los bytes. El ID es `asset-` + SHA-256 hexadecimal del archivo normalizado.
Reimportar los mismos bytes normalizados reutiliza el objeto, y permite reparar
un objeto corrupto con el mismo ID tras autorización explícita.

Formatos admitidos: PNG, JPEG, WebP, MP4, MOV, WebM. Imágenes se decodifican y
normalizan a PNG, hasta 2048×2048. Video: un stream de video, como máximo uno de
audio, H.264/VP8/VP9 y AAC/Opus/Vorbis; hasta 1920×1080, 60fps, 60s y 3600 frames.
Se valida la decodificación y se crea MKV administrado conservando solo tracks
admitidos, sin metadata/capítulos. No se ofrecen GIF, SVG, APNG animado, playlists,
URLs, archivos externos referenciados ni una biblioteca de paquetes ejecutables.

Límites: 64MiB por archivo, 128 assets, 512MiB administrados. El índice v1 se guarda
en `var/assets/index.json`; los objetos usan nombres derivados del hash.
`list_assets` verifica integridad y puede leer archivos; usarlo al abrir/refrescar
la biblioteca, no en cada repaint. La protección de rutas y validación de formatos
no es un sandbox de decoders contra otro proceso del mismo usuario.

Recuperación: corregir permisos/archivo con consentimiento, reimportar una copia
válida si corresponde y usar `reconnect_source` mientras idle. No reconectar ni
reiniciar una salida automáticamente. El broker verifica hashes al resolver; la
fuente comprueba metadatos de archivo en consultas de salud, nunca desde render.

## Video visual, audio H10 y recursos

Cada video usa `ffmpeg_source` oficial, con mixers `0`, mute activado y monitoreo
`off`; incluso si `asset.has_audio` es true, no entra a H10 ni a grabación/RTMP.
`audio_mixers:0` en runtime confirma esa política. No ofrecer gain/mute del video
como si fuera otro canal H10. La mezcla global y sus controles siguen el
[contrato H10](h10-audio-ui-contract.md).

El decoder conserva instancias, timestamps y reproducción entre escenas:
`close_when_inactive=false`, `restart_on_activate=false`, `clear_on_media_end=false`.
Consultar `media_state` (`none`, `opening`, `buffering`, `playing`, `paused`,
`stopped`, `ended`, `error`), `media_time_ms` y `media_duration_ms`. Stop/EOF pueden
producir una fuente vacía saludable; no diagnosticar pérdida por ausencia de frames
tras un stop deliberado. La UI no debe asumir que pause/stop es instantáneo en la
respuesta al comando: las acciones oficiales se procesan en el reloj nativo.

Límites globales: 16 fuentes, 8 escenas, 32 capas **sumadas entre escenas**, 8
animaciones simultáneas y 4 fuentes de video. El grafo limita a 256MiB la estimación
conservadora de píxeles más atlas (`limits.estimated_visual_bytes=268435456`,
`limits.max_video_sources=4` en capabilities): `8 × ancho × alto`, más 8MiB por texto y 16MiB
por widget (hijos FreeType). No es una promesa de RSS máximo: excluye memoria del
decoder, fuentes, glyph metadata, buffers del encoder y otros recursos del proceso.
El runtime expone `framebuffer_estimate_bytes` y `text_atlas_estimate_bytes`, además
de dimensiones intrínsecas/lógicas. No convertir esos campos en un medidor de GPU
real. Los targets nativos están limitados a 1920×1080; los bloques FreeType usan
atlas fijo y guardas adicionales de 32768×8192 antes de dibujar.

## Salud, errores y persistencia

`runtime.sources[].health` es `""` cuando está saludable, o un código; no confundir
texto vacío, opacidad cero, una fuente oculta o un timer completado con fallo.
Fases de lower third/alert: `hidden`, `showing`, `visible`, `hiding`; countdown:
`idle`, `running`, `paused`, `completed`. La salud es independiente de la fase.

| Código/familia | Respuesta de UI |
|---|---|
| `INVALID_ARGUMENT`, `INVALID_OVERLAY_*`, `OVERLAY_*_LIMIT`, `WIDGET_*_LIMIT`, `INVALID_WIDGET_DURATION` | Mostrar validación junto al campo; conservar estado aceptado previo |
| `OUTPUT_BUSY`, `TRANSITION_BUSY`, `ANIMATION_BUSY`, `ASSET_IMPORT_BUSY` | Esperar al estado terminal pertinente; no reenviar en bucle |
| `SOURCE_UNAVAILABLE`, `LAYER_UNAVAILABLE`, `OVERLAY_UNAVAILABLE`, `NOT_AN_OVERLAY` | Refrescar selección/estado, pudo cambiar desde otra superficie |
| `OVERLAY_RESOURCE_IMMUTABLE`, `USE_OVERLAY_PROPERTIES` | Usar el comando/modelo indicado; no recrear silenciosamente |
| `ASSET_IN_USE`, `SOURCE_IN_USE` | Mostrar referencias existentes antes de eliminar |
| `ASSET_MISSING`, `ASSET_CHANGED`, `ASSET_CORRUPT`, `ASSET_UNAVAILABLE` | Recurso administrado perdido/modificado; recuperación explícita |
| `ASSET_NOT_READY`, `ASSET_DECODE_FAILED`, `OVERLAY_RENDER_LIMIT` | Consultar salud y operación; no declarar el overlay listo por aceptar create |
| `OVERLAY_BACKEND_UNAVAILABLE`, `OVERLAY_RENDER_UNAVAILABLE` | Backend/render no disponible; no simular éxito con una vista GPUI |
| `INVALID_IMPORT_NAME`, `UNSAFE_ASSET_*`, `ASSET_DIRECTORY_PERMISSIONS`, `ASSET_*_LIMIT`, `ASSET_QUOTA_EXCEEDED` | Explicar nombre/ruta/tamaño/formato permitido sin revelar rutas privadas |
| `ASSET_TOOL_UNAVAILABLE`, `ASSET_VALIDATION_TIMEOUT`, `ASSET_IMAGE_INVALID`, `ASSET_VIDEO_INVALID` | Importación fallida; conservar biblioteca/proyecto anterior |
| `INVALID_OVERLAY_ACTION`, `ANIMATION_BUSY_OR_INVALID`, `ANIMATION_OPERATION_UNAVAILABLE` | Acción/token no válido; inspeccionar fuente y operación actual |
| `BROWSER_ISOLATION_UNAVAILABLE` | Browser no está disponible; mostrar exclusión, no opción que lance CEF |

La política de salud visual H1–H9 sigue vigente: una fuente visual activa perdida
puede detener la salida de forma controlada y requerir recuperación. No prometer
que un asset fallido solo desaparece mientras el resto sigue emitiendo. Revisar
`issues`, `last_fault`, `recovery_required`, `recovery_sources` y estado de salida.

`save_project` guarda explícitamente `var/project.json`: v4 si hay definiciones
H11; sin ellas, el grafo conserva v3. El campo nuevo `sources[].overlay` se omite en
fuentes antiguas. V1–V3 siguen admitidos; un archivo v3 con definiciones H11 se
rechaza (`PROJECT_VERSION_MISMATCH`). V4 permite hasta 256KiB; V1–V3, 64KiB.
No renombrar IDs ni reescribir layouts de la otra variante al editar una.

Persisten definiciones, referencias de assets, capas y layouts; no persisten
relojes/deadlines, posición de reproducción, fases, opacidad de fade, tokens,
generaciones, salud ni instancias nativas. Reabrir una fuente aplica su estado
inicial; no recrear un countdown en marcha desde un snapshot viejo. El catálogo de
assets v1 está separado: copiar solo `project.json` no empaqueta sus medios.
`audio-mixer.json` v1 y `output-profiles.json` v1 siguen separados y no cambian de
schema por H11. No añadir estado de UI a ninguno de esos archivos.

Los presets `professional_lower_third`, `starting_soon`, `be_right_back` v1 crean
fuentes normales editables con layouts horizontales/verticales originales. Enviar
todos los parámetros del catálogo (`title`, `subtitle`, `background`, `accent`,
`color`, `duration_ms`); no son plantillas con HTML ni fuentes del sistema externo.
Lower third/BRB empiezan ocultos; después de instanciar, mostrar la fuente widget
cuando el usuario quiera presentarla. Starting Soon no comienza el reloj hasta
`timer_start`. No editar el preset instalado para guardar personalizaciones: editar
las definiciones devueltas y guardar el proyecto.

## Mismo control por MCP

Tras el handshake normal MCP, la misma acción de fuente se expresa así:

```json
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"overlay_event","arguments":{"source_id":"source-2","event":"timer_start"}}}
```

El envelope MCP transporta la respuesta compartida como JSON en `content[].text`
y marca `isError` cuando `ok` no es true. No poner `op` dentro de `arguments`.
Ninguna herramienta devuelve frames, audio, archivos importados ni secretos.
MCP describe/solicita operaciones y consulta estado; no controla el reloj multimedia.

Implementación de referencia: `src/overlays/{mod,protocol,production,assets,presets}.rs`,
`src/core.rs`, `src/scene.rs`, `src/engine.rs` y `native/overlays/`.
Para el bloqueo de navegador y sus próximos requisitos ver
[el spike estático](h11-browser-spike.md); no convertir su fixture HTML en una
capacidad de producto sin resolver el aislamiento documentado.
