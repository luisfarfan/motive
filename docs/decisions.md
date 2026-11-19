# Decisiones y evidencia

Estado vigente, 2026-11-17: **H13 implementado; aceptación final EN CURSO**.
La decisión D11 amplía el canvas fijo, el único output y el mixer v1 de fases
anteriores. Las entradas D1–D10 conservan su contexto histórico; no son una
lista de límites actuales. Contratos vigentes: [canvas/audio](h13-video-audio-contract.md)
y [salidas](h13-output-contract.md). Resultados y gates pendientes:
[verificación H13](h13-production-verification.md). Las últimas ejecuciones
G pasan las 23 suites H1–H12. Producción GPUI y más de 30 minutos de salidas
duales ya se ejecutaron; la aceptación es parcial por ventana congelada,
contabilidad terminal y límites de memoria. La alerta corregida y la última
exclusión propia G pasan con sus fallos anteriores conservados. [Índice de evidencia](h13-evidence-index.md).

## Inspección inicial — 2026-11-16

- Directorio vacío, sin Git ni trabajo previo.
- Mac ARM64, macOS 27.2 (26B123), Rust/Cargo 1.99.1; Xcode y Metal presentes.
- OBS y Meld no encontrados en /Applications ni ~/Applications. Búsqueda
  acotada: no demuestra ausencia en otros directorios.
- No se instalarán dependencias globales. Los binarios y fuentes de OBS de
  desarrollo se conservan completos y versionados en .deps, fuera de Git.

## D1 — Stack inicial

Probar GPUI Kit 0.10.0 publicado por longbridge y OBS 33.0.1 oficial. Kit
reexporta su snapshot compatible de GPUI; no activar el backend gpui-fast.
Fijar las versiones y Cargo.lock. Fuentes:
[instalación Kit](https://gpui-kit.com/docs/installation/),
[release OBS](https://github.com/obsproject/obs-studio/releases/tag/33.0.1),
[frontend libobs](https://docs.obsproject.com/frontends).

El preview inicial puede copiar frames a CPU y volver a subirlos a la GPU de
GPUI. No prometer zero-copy. Evaluar un display nativo después de establecer
una prueba reproducible. El engine conserva la propiedad de recursos y su
ciclo de vida; la UI recibe únicamente snapshots y frames.

## D2 — REA opcional

Primero documentación, código abierto y pruebas observables. Usar REA solo
para una incertidumbre concreta pendiente, con identidad del artefacto,
hash, versión, método, límites y distinción observación/inferencia. No
introducirlo en dependencias de Motive ni en criterios de H0/H1.


## Investigación competitiva — 2026-11-16

**Resultado:** REA no es necesario para las decisiones iniciales. La
investigación es documental y estática; no se ejecutó Meld, no se midió su
rendimiento y no se extrajeron código ni recursos propietarios.

| Área | Evidencia OBS | Evidencia Meld | Oportunidad propia |
|---|---|---|---|
| Escenas | Fuente y elemento de escena separados; orden, transformaciones, recorte y ajuste conservando aspecto | Capas, grupos y duplicadores | Reutilizar identidad de fuente y guardar una colocación por variante |
| Transiciones | Cut, Fade, Swipe, Slide, Stinger, Fade to Color, Luma Wipe en módulo abierto | Cut, Fade, Morph, Move, Stinger; Move empareja por nombre | Cut/Fade primero; identificadores estables para movimientos futuros |
| Overlays | Browser Source local/URL con tamaño, FPS y permisos | Navegador CEF y widgets con eventos de prueba | Overlay local declarativo, permisos restringidos y comprobación en grabación |
| Efectos | Filtros de color, LUT, chroma, máscara, recorte y audio | Cadena ordenable, presets, activación conservando ajustes | Pocos efectos bien probados, valores acotados y comparación antes/después |
| Configuración | Asistente y recomendación de grabación de prueba | Inspector contextual, estadísticas y ajustes previos a emitir | Preflight que explica permisos, fuente ausente, encoder, audio y almacenamiento |
| Variantes | Transformaciones y bounding boxes en libobs | Multi Canvas con pilas independientes | Anclajes, prioridades, márgenes seguros y ajustes por variante; nunca estirar |

Fuentes oficiales por área:

- Escenas: [OBS Sources](https://obsproject.com/kb/sources-guide),
  [API de escenas](https://docs.obsproject.com/reference-scenes),
  [capas Meld](https://meldstudio.co/docs/layers/).
- Transiciones: [registro OBS, commit fe1ed7955f300efd17fc59f65938388e43d8bb06](https://github.com/obsproject/obs-studio/blob/fe1ed7955f300efd17fc59f65938388e43d8bb06/plugins/obs-transitions/obs-transitions.c),
  [transiciones Meld](https://meldstudio.co/docs/settings/#scene-transition).
- Overlays: [Browser Source](https://obsproject.com/kb/browser-source),
  [Browser Meld](https://meldstudio.co/docs/layers/#browser),
  [widgets Meld](https://meldstudio.co/docs/widget/).
- Efectos: [OBS Filters](https://obsproject.com/kb/filters-guide),
  [efectos Meld](https://meldstudio.co/docs/effects/).
- Configuración: [OBS Quick Start](https://obsproject.com/kb/quick-start-guide),
  [estadísticas Meld](https://meldstudio.co/docs/layers/#capture-devices-stats-fps-graphs),
  [preferencias Meld](https://meldstudio.co/docs/settings/#user-interface).
- Variantes: [Multi Canvas Meld](https://meldstudio.co/docs/outputs/multi-canvas/).

OBS docs se identifican como 33.0.1. El código competitivo consultado corresponde
al commit anterior (2026-11-10); el prototipo usa el tag 33.0.1, no ese HEAD.
Meld docs no fijan versión de aplicación: estos hallazgos no prueban
comportamiento de una versión instalada ni ausencia de funciones no descritas.

### Control público y REA

La [API pública de Meld](https://github.com/MeldStudio/streamdeck/blob/9c84ce3a00d94b974e6d0cffbef85df09b7a3a8c/WebChannelAPI.md)
(commit 9c84ce3, 2026-11-10) ofrece QWebChannel sobre WebSocket para sesión,
escenas, capas, efectos y grabación con señales de cambios. Esto no establece
la arquitectura interna ni atomicidad de todas las operaciones. El contrato
de Motive se diseña independientemente.

[REA](https://github.com/morluto/rea) aporta análisis de paquetes, JavaScript y
binarios nativos con registros de evidencia y límites. El análisis nativo
necesita proveedores disponibles; un MCP conectado no basta. Su código propio
es MIT, con licencias separadas para herramientas y materiales ajenos.
[package.json fijado](https://github.com/morluto/rea/blob/26d88826cc36c5513ce8977346c0e4f15bb25169/package.json)
declara 6.9.0 (2026-11-16); la habilidad local cita 6.5.0. Ante una necesidad
futura hay que fijar versión y usar esquemas reales, sin instalar ni reparar
configuración por defecto.

Usar REA solo después de una reproducción y una pregunta concreta que las
fuentes públicas no resuelvan. Conservar hash/versión del artefacto, proveedor,
operación, Evidence ID, cobertura y límites. Distinguir observado, derivado e
inferido. No incorporar pseudocódigo, shaders, presets, assets o diseños
extraídos de Meld al producto. No se invocó ningún análisis REA en esta sesión.

### Preguntas abiertas y primera prueba adecuada

| Pregunta | Próxima evidencia | Prioridad |
|---|---|---|
| Nombres duplicados en Move de Meld | Proyecto desechable con dos capas propias y video del resultado | Posterior; no bloquea |
| Fuente desconectada durante transición/grabación | Desconexión controlada y logs | H1 en Motive; comparación posterior |
| Coste de efectos, CEF y dos lienzos | Escena, hardware y duración idénticos; mediciones | Posterior; REA no sustituye benchmark |
| Adaptación automática en Meld | Docs solo establecen pilas independientes; prueba observable | No afirmar ausencia universal |
| Contradicción entre comportamiento y API | Caso mínimo, versión y después análisis estático enfocado | Único candidato eventual a REA |

Las pruebas futuras usarán contenido propio, permisos normales y ninguna
emisión pública. La búsqueda inicial de apps fue limitada a nombres inmediatos
en /Applications y ~/Applications; no descarta otras rutas.

## D3 — Integración inicial y límites de esa etapa

Registro de la primera arquitectura ejecutable. D5–D11 amplían esta base;
en particular, H13 reemplaza el límite de un output y el canvas físico fijo.

- `src/core.rs`: estado autoritativo, comandos, validación y persistencia.
  `src/main.rs`: UI GPUI y cola de comandos en su hilo principal.
  `src/control.rs`: adaptadores Unix socket/CLI y MCP stdio.
  `src/engine.rs`: propietario Rust de un puente C/Objective-C; no es Send/Sync.
  `native/engine.m`: ciclo de vida de libobs y fuentes propias.
- Las operaciones nativas de control se ejecutan en el hilo principal. Libobs
  mantiene sus hilos de video, audio y outputs. Callback BGRA con mutex y
  `trylock`: si el consumidor ocupa el buffer se descarta ese preview, sin
  bloquear el video. UI actualiza a aproximadamente 30 Hz y libera imágenes
  anteriores de GPUI. No hay cola ilimitada de frames.
- Flujo de preview: composición Metal de libobs → callback de video BGRA en
  CPU → copia al buffer más reciente → copia a Rust → RenderImage de GPUI →
  presentación por su renderer. No es zero-copy. No se midió latencia de
  captura a pantalla; los timestamps internos no demuestran por sí solos esa
  latencia. Los logs informan que las texturas NV12/P010 no están disponibles
  en esta configuración, aunque la salida NV12 funciona.
- Fuentes y overlays se renderizan en libobs; el reloj de animación es
  `video_tick`, independiente de MCP. La captura usa el módulo oficial
  `mac-capture`/ScreenCaptureKit. La ventana propia de prueba es una segunda
  ventana GPUI, no un frame fabricado para aparentar captura.
- Grabación: módulo oficial `mac-videotoolbox` preferido en `auto`, con fallback
  a `obs-x264` antes de iniciar; `ffmpeg_aac` + `ffmpeg_muxer`, helper y
  bibliotecas del bundle oficial. La selección es compartida en Production,
  fuera de la persistencia v3. Ver [mediciones y límites](videotoolbox-verification.md).
  Streaming local: `ffmpeg_output`, libx264/AAC y MPEG-TS a UDP loopback fijo.
  El soporte de protocolos no prueba integración con YouTube/TikTok.
- En esa etapa, un solo output simultáneo. `stop_output` es asíncrono: observar `idle` y
  `output_code == 0` antes de cambiar formato o dar un archivo por terminado.
- Dos composiciones iniciales: 960×540 y 540×960. Captura con ajuste `contain`, anclada
  al centro y prioridad inferior; overlay de 320×72, anclaje inferior izquierdo,
  margen seguro de 32 px y prioridad superior. Es una política mínima propia,
  no un editor adaptativo completo ni un simple estiramiento.
- Socket local 0600 en directorio 0700; mensajes ≤64 KiB, cola acotada y plazos
  de espera. El cliente debe consultar estado tras un timeout porque una
  operación ya en curso puede haber terminado. Esto no es un sandbox contra
  otros procesos del mismo usuario. El overlay actual es código propio fijo:
  no carga scripts ni contenido externo y no tiene acceso a claves.
- MCP implementa un subconjunto probado de
  [stdio 2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)
  y [tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools).
  No se ha certificado contra todos los clientes MCP ni implementado HTTP.

### Problemas encontrados y correcciones

1. Los headers públicos de OBS en ARM64 necesitan SIMDe. Se añadió el árbol
   completo 0.8.2 fijado y su hash, no headers sueltos ni un paquete global.
2. `deny_unknown_fields` no rechazaba campos sobrantes de variantes unitarias
   del enum de comandos. Una prueba falló; ahora se comprueban también las
   claves requeridas/permitidas en CLI y MCP. Se mantuvo la prueba.
3. La UI inicial dejaba que la imagen desbordara su contenedor. Se fijaron
   límites explícitos y ajuste conservando aspecto; se verificó visualmente.
4. OBS 33 reajusta elementos al cambiar el lienzo. El overlay heredaba escala
   y quedaba recortado en vertical. Se restablecen escala unitaria, alineación
   y límites explícitos después del reset. La prueba comprueba movimiento en
   varias muestras y presencia de captura fuera del overlay.
5. Reabrir una captura de la misma ventana al restaurar el proyecto podía
   producir una fuente sin frames. Se conserva la identidad de la captura
   existente; se restaura la ventana si estaba minimizada. Una nueva salida
   requiere captura válida. La causa interna exacta de ScreenCaptureKit no
   se atribuye sin más evidencia; no fue necesario investigar Meld con REA.
6. El helper de muxing requiere sus frameworks. El bundle de desarrollo
   conserva un enlace al árbol completo oficial, con fuentes y licencias
   disponibles. No es empaquetado independiente.

Los primeros informes fallidos se conservaron en `var/evidence/` para no
confundir una prueba de codecs con una captura válida. Ningún criterio se
sustituyó por mocks.

## D4 — Versiones, integridad, empaquetado y licencias

| Componente | Selección | Evidencia/límite |
|---|---|---|
| GPUI Kit | 0.10.0 | Publicación oficial; Cargo.lock fija dependencias; gpui-fast desactivado |
| GPUI | gpui-pre 0.3.12 | Snapshot compatible que Kit publica; no un backend alternativo |
| libobs y módulos | OBS 33.0.1 ARM64 | Bundle oficial completo, versión confirmada en ejecución |
| SIMD headers | SIMDe 0.8.2 | Árbol completo, MIT, compilación ARM64 verificada |
| Deployment target | macOS 15.0 | Verificado en LC_BUILD_VERSION; ejecución solo comprobada en 27.2 |

Hashes SHA-256 fijados en `scripts/bootstrap.py`:

- DMG OBS: `3d6b2eedeb56416602af635adaba32327fdf11ff9d2806a4ce7d5b608de73238`.
  Coincide con el digest del asset publicado por GitHub para OBS.
- Tarball de fuentes OBS: `9174ee0e3677c92d0d060bdce4c5d44dfee9fd3afddfb6333f098fd029b8de2b`.
- SIMDe: `ed2a3268658f2f2a9b5367628a85ccd4cf9516460ed8604eed369653d49b25fb`.

Se comprobó `codesign --verify --strict .deps/OBS.app`. Los módulos cargados
están limitados a obs-x264, obs-ffmpeg, obs-outputs, mac-capture, mac-avcapture,
obs-transitions y, opcionalmente, mac-videotoolbox;
no se inicia OBS Studio, CEF, obs-websocket ni plugins de frontend Qt.

El código propio se publica bajo GPL-3.0-or-later. Los
[headers de libobs](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs.h)
permiten GPL versión 2 o posterior; Kit y GPUI declaran Apache-2.0.
[Apache confirma compatibilidad con GPLv3](https://www.apache.org/licenses/GPL-compatibility.html).
El inventario de licencias declaradas de Cargo está en
`var/evidence/cargo-licenses.json` (incluye plataformas no activas). Esto no
sustituye el inventario de todo el bundle binario, avisos, fuentes
correspondientes y revisión de redistribución antes de una release. No se
publicó ni redistribuyó un paquete en esta sesión.

Pendiente de producto: bundle autosuficiente con dependencias necesarias,
fuentes/avisos de terceros, firma Developer ID y notarización, comparación en
macOS 15/16 y otras máquinas, manejo de dispositivos físicos en producción y
medición de latencia. No se instaló ni cambió ninguna herramienta global.


### Robustez del control

Una consulta durante una prueba devolvió Broken pipe, mientras el motor seguía
renderizando y aceptó la orden posterior de detener la grabación. Se conservó
`acceptance-transport-failed.json`. Se cambió el transporte para serializar el
mensaje antes de conectar, enviarlo con `write_all`, ampliar el plazo de
lectura del servidor a 5 s y reintentar una vez solo `status`/`devices` ante un
error de transporte. Las mutaciones nunca se reintentan automáticamente. La
causa externa exacta de ese fallo transitorio no está establecida; la prueba
final debe seguir validando duración, frames, audio y contenido, no solo que
la consulta funcione.

Se comprobó además la pérdida real de la ventana de prueba: al cerrarla,
`start_recording` devuelve `SOURCE_UNAVAILABLE`. Evidencia:
`var/evidence/source-loss.json`. Los dispositivos se actualizan una vez por
segundo; la UI conserva el aviso de captura ausente y no declara video válido
por el mero hecho de haber creado un objeto obs_source_t.

La prueba de recepción local descubrió inicialmente MPEG-TS con video pero
sin pista de audio. El output `ffmpeg_output` usa una máscara de mezclas;
se añadió `obs_output_set_mixers(output, 1)` para incluir la mezcla 0, según
el código oficial de `obs-ffmpeg-output.c` de OBS 33.0.1. Se conservó
`acceptance-stream-audio-failed.json`. El criterio de H4 exige comprobar AAC
no silencioso en el receptor, además de video decodificable.

Una repetición desde arranque frío mostró una carrera adicional: restaurar el
mismo proyecto antes del primer frame recreaba una captura todavía pendiente.
La identidad se conserva también durante ese estado; pedir el formato que ya
está activo tampoco reinicia libobs. La ventana de prueba se abre enfocada
para garantizar que reciba su primer render nativo. Esto se valida desde un
proceso nuevo, manteniendo la comprobación de captura real y el timeout.


## H1 — Selección y recuperación (2026-11-16)

Se usa `macos-avcapture` oficial, cámara con audio deshabilitado y micrófono
CoreAudio por UID explícito. Se excluye el alias de audio predeterminado para
no cambiar silenciosamente de dispositivo. El callback de audio mide flujo y
pico; el silencio con paquetes sigue siendo saludable.

Production decide la salud para UI/CLI/MCP. Pérdida durante output solicita
stop, conserva el motivo y exige recuperación explícita; nunca reanuda una
salida por reconexión. Project v2 conserva identidad de cámara/audio y pareja
bundle ID/título para ventanas; coincidencias ambiguas se rechazan. V1 solo
puede resolver la ventana controlada propia.

La lista UI se congela mientras está abierta para evitar que los cambios de
orden del sistema alteren la fila pulsada. Se filtran agentes auxiliares y se
reserva altura para el selector. La firma Apple Development local existente
mantiene una identidad estable entre builds; bootstrap no crea certificados.

Resultados, pruebas reproducibles y limitaciones de hardware se conservan en
[informe H1](h1-verification.md). Hot-unplug físico y cámara conectada pero sin
frames nuevos siguen pendientes; no se sustituyeron por mocks.

## D5 — Primer Scene Graph (2026-11-16)

`src/scene.rs` define escenas, fuentes y capas con IDs persistentes; cada capa
contiene dos transformaciones independientes. El proyecto v3 migra v1/v2, valida
referencias y límites, y se guarda mediante archivo temporal, fsync y rename.
No se persisten IDs efímeros de ventanas ni PIDs. Una ventana se restaura solo
con una coincidencia única de bundle/título. La carga es explícita.

`native/graph.inc` construye escenas privadas de libobs, aplica posición y
rectángulo contain, visibilidad y orden (ascendente, desempate por ID de capa).
Reutiliza fuentes por identidad: mover una capa no recrea la captura ni reinicia
su reloj. Se reconstruyen los scene items; no hay motor de render paralelo,
jerarquías arbitrarias ni abstracción de plugins. Una fuente de cámara por UID
puede aparecer en varias capas y escenas.

La sustitución de una cámara tiene una excepción explícita al staging: el
dispositivo requiere liberar primero los items y la sesión anterior, esperando
la cola de destrucción de OBS antes de crear otra sesión. Se observó un crash
de CoreMediaIO/AVFoundation con sesiones solapadas. Si la reapertura falla,
la fuente queda sin captura y bloquea la salida; no se presenta como saludable
ni se borra su identidad del modelo. El resto de la composición se conserva.

Las transformaciones y el color del overlay se pueden editar grabando. Cambios
de recursos, visibilidad y selección de escena requieren salida detenida en
esta fase. La operación heredada de visibilidad del overlay propio mantiene
su comportamiento en vivo. No hay multistream ni dos lienzos activos.

La salud usa una lectura coherente por consulta. Un filtro async passthrough
cuenta frames reales de cámara y tiempo de llegada; no compara píxeles. Hay
4 s de gracia al activar y fallo tras 3 s sin entrega. El estado deseado del
grafo incluye fuentes todavía pendientes de activación nativa, evitando declarar
listas las cámaras frías. Ventanas conservan chequeos de permiso, existencia,
PID de propietario y dimensiones; no se afirma detección de toda congelación.

La recuperación se conserva por ID de fuente, audio y output. Un cambio de
audio no reconoce fallos visuales ni del encoder/muxer. El callback stop no
equivale a recursos liberados: se espera además `!obs_output_active` y se
desconecta la señal antes de liberar output/encoders. La ruta de preview sigue
siendo CPU; consultar la secuencia antes de reservar/copiar evita trabajo
repetido cuando no hay un frame nuevo, sin rediseñar el renderer.

Evidencia ejecutada y límites: [verificación de escenas](scene-graph-verification.md).
Fuentes públicas utilizadas: `libobs/obs-scene.c`, `libobs/obs-output.c`,
`libobs/obs-source.c`, `plugins/mac-avcapture/plugin-main.m` y
`plugins/mac-avcapture/OBSAVCapture.m` del árbol oficial OBS 33.0.1 fijado en
`.deps/`. No se utilizó REA ni contenido de Meld.


## D6 — Perfiles y RTMP local (H7)

Escenas v3 permanecen intactas. Definiciones de perfiles usan un archivo v1
separado, con guardado/carga explícitos; selección y endpoint son preferencias
runtime. Grabación y RTMP comparten creación de encoders, fallback y parámetros.
El alcance H7 admite solo CBR y canvas existentes a 30 FPS; H13 añade
resolución/FPS de producción configurables y pares de encoders por destino.

RTMP/TLS usan `rtmp_output` oficial con un adaptador mínimo de servicio local
vía API pública. No se carga el catálogo `rtmp-services` ni su actualizador.
Endpoint limitado a 127.0.0.1 y puerto, sin claves/URLs arbitrarias. Las claves
futuras deberán resolverse desde Keychain dentro del núcleo, no desde MCP ni
archivos de escena/perfil. En H7 todavía no había administrador de credenciales;
H8 añadió referencias opacas Keychain, manteniendo loopback y los límites TLS.

Un receptor silencioso reprodujo bloqueo al forzar stop durante conexión y
una carrera nativa al trasladar esa espera a un worker. Se descartó el worker:
`stop_output` devuelve `OUTPUT_CONNECTING` hasta que termine el handshake.
No se reinicia automáticamente tras rechazo o desconexión. Ver
[informe H7](h7-output-verification.md) para evidencia, límites TLS, anotaciones
MCP y experimentos de B-frames sin alterar silenciosamente la calidad.

## D7 — Transiciones oficiales y escenas nativas retenidas (H9)

Seleccionar escena deja de reconciliar el grafo. Cut/Fade son fuentes oficiales
OBS conectadas a output 0; reutilizan escenas y recursos existentes, sin reiniciar
encoder, conexión ni reloj. El propietario prepara el destino fuera de programa,
balancea activación/referencias y confirma el ID actual tras la señal nativa de
finalización. Los callbacks solo publican un contador atómico. Audio sigue global
en canal 1; no hay segundo renderer ni cambios al parche RTMP H8.

Un destino fallido conserva la escena anterior. Cancelar un Fade corta de vuelta;
destinos distintos mientras está ocupado se rechazan, sin cola implícita.
Ediciones del grafo esperan a que termine. Configuración de transición es una
preferencia de sesión separada de proyecto v3 y perfiles v1. La selección Cut
detenida conserva el recorrido de edición de escenas vacías/frías.

Contratos, evidencia de video/RTMP, carreras de control, límites de readiness y
siguiente incremento de audio: [verificación H9](h9-scene-transitions-verification.md).

## D8 — Mezcla global y persistencia de audio separada (H10)

`core::audio` modela entradas con identidad tipada, IDs estables, ganancia/mute
y store v1, sin convertir escenas v3 ni perfiles v1. Repetir un UID reutiliza
el mismo canal y conserva sus controles; no se crean capturas físicas duplicadas.
Restaurar reconcilia por identidad incluso si cambia el orden/ID del documento.
La UI debe consumir el mismo núcleo y sus snapshots; no implementar su propio
mezclador ni persistencia. Ver [contrato](h10-audio-ui-contract.md).

Libobs mezcla las fuentes globales en mix 0 mediante sus APIs de volumen, mute
y ruteo. Las transiciones de video permanecen en canal 0; las entradas de audio
usan canales 1..8. El tono propio deriva la fase y los timestamps de su posición
de muestras. Se observó
un cambio de fase al arranque también con esta fuente; su causa no está aislada
y no se atribuye al WAV anterior.
No se agregó un mezclador DSP, reloj MCP ni encoder adicional.

El medidor oficial de OBS 33.0.1 es post-fader/pre-mute manual; se declara esa
semántica y se observa también la suma nativa post-mute/pre-clamp. Clipping se
expone como advertencia estructurada; no se oculta con normalización/limitadores.
Monitoreo permanece desactivado. La recuperación nueva libera/reabre solo la
entrada afectada y conserva la mezcla restante; el selector heredado de una
sola entrada conserva su política de stop controlado. El módulo CoreAudio tiene
reconexión propia, por lo que un fallo latched libera la fuente para impedir que
vuelva al aire sin acción explícita.

La aceptación física, espectral, de timestamps y de restauración está en
[informe H10](h10-audio-verification.md). H10 pospuso la captura de audio del
sistema; H13 la implementa como adaptador del mixer mediante el módulo oficial
SCK, sin cambiar ruteo, volumen ni permisos globales. Ver D11.

## D9 — Overlays nativos, recursos administrados y proyecto v4 (H11)

`core::overlays` separa definiciones tipadas, broker de assets, presets y
adaptación del propietario. Un wrapper nativo por ID mantiene hijos oficiales
FreeType, image_source o ffmpeg_source; formas y placas usan gráficos libobs.
No hay compositor, mezclador, reloj de frames ni runtime de JavaScript paralelo.
CLI/MCP llaman a `Production::apply` sobre el mismo propietario; H12 incorpora
la UI al contrato que H11 dejó preparado.

Una definición extendida opcional en `VisualSource` evita romper los matches
GPUI de `SourceKind`. Solo los proyectos que la necesitan se guardan como v4;
v1–v3 siguen cargando y v3 rechaza extensiones silenciosas. Audio Mixer y perfiles
conservan sus archivos versionados independientes. Estado de timers, eventos y
animaciones es efímero: restaurar no dispara una alerta ni reanuda una cuenta.

La importación acepta únicamente un basename de la bandeja privada preparada
explícitamente por el usuario/UI. El broker valida contenido, cuotas y enlaces,
normaliza a PNG/MKV y devuelve IDs SHA-256; las rutas originales no llegan al
contrato MCP. No es un sandbox contra otro proceso del mismo usuario. El límite
visual de 256 MiB estima targets/atlas; no promete limitar RSS, decodificadores
ni los picos de reemplazo. Ver [auditoría](h11-architecture-review.md).

Fade de capa usa transiciones oficiales; slide/scale usan transforms oficiales
desde el tick de OBS. Ocho operaciones acotadas como máximo; no hay cola
implícita. Una finalización se retiene hasta que el propietario actualiza la
generación/variante/capa originales y reconoce su ID. Las ediciones del grafo y
Cut/Fade de escena esperan esa barrera. Eventos de fuente afectan todas sus
capas; una animación afecta solo la capa seleccionada.

Video local permanece visual: mixers 0, mute y monitoreo desactivado. Audio de
medios necesita un futuro adaptador explícito de H10. Browser Source no se carga:
el [spike CEF](h11-browser-spike.md) identifica dependencias de frontend/Qt y
ausencia de confinamiento de red/archivos. HTML, URLs y scripts arbitrarios no
son capacidades de este incremento.

La salida mantiene una actividad `NSProcessInfo` local desde el arranque hasta
que terminan los workers; evita que el trabajo multimedia solicitado se trate
como inactividad. Se libera al finalizar/fallar, sin cambiar opciones globales.
Contratos y evidencia: [UI](h11-overlay-ui-contract.md),
[verificación](h11-overlay-verification.md).

## D10 — Adaptador creativo nativo y evidencia de estabilización (H12)

`studio/creative` integra H11 por funcionalidades sin otra `Production`.
Borradores GPUI Kit capturan una revisión: una edición concurrente requiere
recarga explícita antes de aplicar. Los controles de ejecución consultan los
recibos nativos independientemente del borrador; no extrapolan relojes/progreso.
Eventos de fuente y visibilidad por capa se explican por separado. El inspector
clásico no ofrece `SetOverlayColor` para definiciones H11.

El selector nativo entrega una capacidad local Rust para copiar a inbox privado.
El guard por descriptor permanece hasta el resultado terminal del worker. La
consulta estricta `asset_inventory` expone errores por objeto para permitir
reimportación del mismo ID; no amplía MCP a rutas arbitrarias. La limpieza RAII
no promete eliminar huérfanos después de un crash. Detalle en el
[contrato H12](h12-creative-studio-contract.md).

Se conserva la semántica de video oculto: quitar visibilidad de capa no pausa el
medio. H12 lo mide y explica Pause/Stop; cambiarlo silenciosamente rompería el
reloj esperado al volver al aire. RSS, CPU y picos de reemplazo se miden en el
proceso, separados del presupuesto estimado de targets/atlas de H11.

El verificador H10 compara ahora el mismo estadístico nativo (mediana de RMS por
bloque) con PCM sobre el mismo intervalo; mantiene el margen de 2 dB. Encoding
conserva muestras del ensayo fallido sin reducir el gate de cero render lag.
Los informes históricos no se reescriben y pasar tests unitarios no sustituye
medios reales. [Evidencia y límites](h12-creative-studio-verification.md).

## D11 — Producción compartida y destinos independientes (H13)

Implementado, con aceptación final **EN CURSO**. La
[decisión previa](h13-production-architecture.md) conserva la comparación de
alternativas y fuentes oficiales fijadas en OBS 33.0.1; los contratos de
[canvas/audio](h13-video-audio-contract.md) y [salidas](h13-output-contract.md)
describen la API vigente. No se añade otra `Production`, compositor, mixer DSP
ni reloj de UI/MCP. GPUI presenta el estado del mismo propietario.

La composición OBS usa las dimensiones elegidas: `legacy540`, `hd720` o
`full_hd1080`, a 30/60 FPS y en ambas orientaciones. Las coordenadas editables
continúan siendo `design960`; posición, tamaño y animación se escalan al motor
sin reescribir las transformaciones persistidas. Un proyecto explícito v5
declara `video.version=1`; v1–v4 conservan 540p30. `configure_video` exige
salidas, transición, animaciones e importación quiescentes. Antes de resetear
video se reservan recursos y se liberan encoders detenidos; ante fallo se
intenta restaurar la configuración anterior. `VIDEO_RECOVERY_REQUIRED` impide
arrancar si esa recuperación falla. Esto no acredita 1080p60 de cada captura:
la cámara solicita 720p y SCK renueva su stream al cambiar FPS.

Cada destino estable, `recording` y `streaming`, tiene output, par H.264/AAC,
perfil efectivo por intento, métricas, duración monotónica y fallo propios.
Ambos consumen el mismo `obs_get_video()` y mix 0 de `obs_get_audio()`. Se eligen
encoders independientes porque un fallo del encoder compartido se propaga a
todos sus outputs en OBS 33.0.1, además de acoplar bitrate/GOP/reordering.
El coste de los dos pares se mide; compartirlos queda como optimización futura
con su propia aceptación. No se duplican cámaras, ventanas ni captura de audio.

La identidad de observación es `(pid, target, attempt_id)`. `outputs` expone
ambos slots; los comandos dirigidos permiten detener/recuperar uno mientras
continúa el otro. Los arranques antiguos siguen exclusivos. Stop/cancel sin
destino rechaza dos slots ocupados con `OUTPUT_TARGET_REQUIRED`; el estado
legacy puede ser `multiple` y sus campos específicos quedan `null`, sin
atribuir a toda la producción las métricas de un destino. Perfiles permanecen
v1 y su selección/endpoint son runtime; reiniciar nunca inicia una salida.

El módulo oficial `sck_audio_capture` aporta aplicación por bundle ID único
y escritorio principal por UUID. Se revalida identidad al crear/reconectar;
PIDs efímeros no se persisten. Escritorio junto a cualquier aplicación se
rechaza por solapamiento incluso si un canal está silenciado/desconectado.
El módulo OBS solicita excluir el audio del propio proceso; esa configuración
no sustituye su aceptación medida, todavía abierta. Mixer v1 sigue cargando;
las fuentes SCK requieren v2, separado de proyecto y perfiles. Ganancia, mute y recuperación
reutilizan H10; `ready` significa paquetes, `awaiting_audio` ausencia reciente
de muestras y un fallo retenido exige reconexión explícita. Medidores mantienen
post-fader/pre-mute por entrada y post-mute/pre-clamp en master. No se activa
monitoreo, audio por escena ni audio de los videos H11.

La barrera RTMP H8 `get_thread_state` se conserva por slot. Stop no demuestra
que todos los workers terminaron; no se fuerza su liberación ni se oculta la
espera del handshake. `request_shutdown` solicita la finalización conjunta y
espera también una importación existente antes de permitir el destructor del
worker. `shutdown` legacy establece el mismo sello de cierre. Tanto pendiente
como listo para salir, el núcleo rechaza nuevo trabajo, incluidas mutaciones
de overlays que antes entraban por una ruta temprana. Las consultas siguen
disponibles. Ventana, menú y Cmd+Q pasan por la confirmación/ciclo compartidos.
La producción GPUI observó cancelación de Cmd+Q, cierre confirmado y rechazo
de una confirmación obsoleta (Q5). El cierre diferido Q4 mantiene vivo el owner
con un peer RTMP incompleto y termina 0,835 s después de liberarlo. No se
forzaron señales sobre Motive. Las rutas restantes conservan su estado
individual en el [informe de aceptación](h13-native-acceptance.md).

El bundle G (`d9b8d702…e0e2d93`) tiene 71 tests, Clippy y formato PASS, y
**23/23 suites H1–H12 distintas PASS en sus últimas ejecuciones**. El
[índice de evidencia](h13-evidence-index.md) conserva los manifiestos fallidos;
H10 aporta nuevas grabaciones con [referencias aisladas](h13-h10-metrology.md),
sin borrar los resultados anteriores. El ensayo H8
comprueba rechazos `SHUTDOWN_PENDING` y cierre tras liberar el peer; otro ensayo
observa 29 consultas durante un import real y el resultado `completed` antes
de salir. En G la matriz dual pasa **4/4 casos y 12/12 medios** (diez completos
y dos parciales intencionales), con recuperación independiente; A/V visible
pasa con siete pares de pulsos, mediana audio−video **+24,27 ms** y rango
**33 ms**. Ya se ejecutó producción GPUI integrada con una sesión dual de más
de 30 minutos. Los ocho archivos pasan decodificación completa y cadencia
estricta (≤34 ms), con siete functional/integrity PASS y un RTMP parcial
intencional INCONCLUSIVE. El agregado estructural permanece INCONCLUSIVE por
ese parcial y un intento de handshake sin medio; no declara aceptación nativa.
[informe y evidencia](h13-production-verification.md),
[runner de regresiones](h13-regressions.md), [aceptación nativa](h13-native-acceptance.md).

La [revisión visual](../var/evidence/h13-native-visual-extract-1794944740966518000/visual-review.md)
aprueba los cambios Cut/Fade completos y observa edición de lower y countdown
en ambas salidas, pero conserva alerta parcialmente ocluida y congelamiento
visual tardío de la ventana en REC3. El congelamiento coincide con oclusión
mientras la fixture sigue incrementando los contadores de audio y dibujo.
Esto no distingue publicación de WindowServer, entrega de SCK o retención
posterior: causa INCONCLUSIVE.

La [revalidación compacta](../var/evidence/h13-native-visual-extract-1794946829324892000/visual-review.md)
pasa la alerta completa tras corregir su orden a 3 desde GPUI; el fallo
original permanece. La ventana sigue FAIL: once muestras repiten 193356288,
sin atribuir duración exacta ni causa. El [análisis de dos medios](../var/evidence/h13-native-analysis-1794946801711114000/report.json)
tiene funcional y cadencia estricta PASS, coverage INCONCLUSIVE y aceptación
no evaluada. RTMP conserva 5027 frames decodificados frente a 5028 del output;
MKV coincide en 13880. Ese gate terminal no estaba incluido en el PASS:
PTS regulares y cero drops no prueban entrega de cada cuadro final.

La última [exclusión propia G](h13-system-audio-exclusion-final.md), documentada
en `0573f8b`, pasa después de un control de piso PASS: **−123,174221 dB**
frente al mismo gate <−45 dB. Checker, umbrales y bundle se mantuvieron
intactos; no se atribuye el cambio a una corrección de código. La cifra cercana
al piso numérico no garantiza esa atenuación universalmente. El primer G FAIL
(−16,41 dB con fondo adicional) conserva atribución INCONCLUSIVE y no se
sustituye retrospectivamente; también permanece el PASS histórico de C.

Se conserva el fallo de audio inicial de 1024 muestras y su
[investigación](h13-audio-startup-investigation.md): adelantar 20 ms la entrega
del tono conserva fase/PTS y no modifica el buffering de micrófono/SCK.
Persisten límites de [colas de video](h13-encoder-tail-investigation.md) y
congelamientos previos de captura cuya causa no está demostrada. A/V pasó bajo
las condiciones visibles documentadas, sin acreditar latencia cero. Preview
sigue copiando BGRA por CPU; presupuestos visuales no son límites de RSS.
El probe dirigido en G observa destrucción de ocho fuentes ffmpeg y sus
wrappers, y asignaciones malloc activas próximas al baseline
(35,4M frente a 33,5M en `vmmap`), mientras permanecen páginas residentes
(835,5M en esa zona). Tras liberar videos y esperar 20 s, RSS mediana es
1141,38 MiB frente a 178,41 MiB inicialmente. Se documenta como observación,
sin PASS de presupuesto ni atribución causal de fuga o prueba de su ausencia;
el probe es más corto que H12 y `vmmap` puede alterar la residencia.
USB hot-unplug, permisos revocados, display físico, sleep/wake, otros macOS,
RTMPS positivo confiable y bundle portable siguen pendientes; la sesión dual
prolongada ejecutada no acredita esos escenarios.
No se habilitan destinos públicos, multistream, dos canvases simultáneos,
Browser/CEF ni nuevas dependencias globales.

## D12 — Autoridad local, Show Control y bundle portable (H14)

Implementación integrada; **aceptación de beta abierta**. El
[índice H14](h14-beta-verification.md) identifica cada binario y sus medios.
Los resultados anteriores de D11 siguen describiendo H13.

El adaptador de [Show Control](h14-show-control-contract.md) toma prestada la
misma `Production` en el turno del owner. El crate conserva reglas, cooldowns,
contadores y deduplicación; el owner conserva grafo, reloj nativo y autoridad
de revisión. Antes de aplicar una acción se sincroniza su intención duradera.
Los recibos solo admiten rangos contiguos de revisiones propias de esa acción
y su operación nativa. Una edición ajena no puede convertirse en revisión
propia por observar una operación completada. La incertidumbre exige
reconciliación; no reejecuta triggers ni continúa la secuencia automáticamente.

El [trigger animado B3](h14-animated-trigger.md) aplica el evento del widget y
su transformación inicial en el mismo tick nativo, con un único operation ID.
Corrige el salto inicial observado en B1 sin un reloj adicional de GPUI/MCP.
Las tres celebraciones completas B3 se verificaron en MKV y RTMP; los límites
de cancelación y concurrencia permanecen separados en su
[informe](h14-show-control-b3-verification.md). La instalación MATCHDAY presenta
un plan local y bindings reales; conserva progreso parcial y no promete rollback
atómico. Guardar/restaurar su configuración es explícito y siempre restaura
desactivada, sin trabajos ni salidas automáticas.

Los [destinos externos](h14-destination-contract.md) se registran localmente por
identidad, host, puerto, ruta y referencia opaca. La credencial se vincula a esa
tupla completa en Keychain y se introduce mediante AppKit. Cada arranque externo
consume una autorización local ligada al owner, revisión, perfil y destino;
un mensaje MCP, un origen `UI` o un booleano no pueden crear esa autoridad.
La prueba privada B2 verificó conexión real y observación del usuario; no prueba
entrega remota por decodificación independiente ni certifica B3 por herencia.

El [bundle portable](h14-portable-app.md) incorpora el cierre de dependencias
ARM64 y herramientas de importación. Un marcador versionado selecciona rutas
macOS fuera del checkout y falla si es inválido. No migra stores de desarrollo.
Licencias, fuentes correspondientes, firma, ejecución fuera del checkout,
notarización y prueba en otra Mac son gates distintos. Un build firmado local
no se anuncia como release notarizada.

Los diagnósticos de SCK distinguen callbacks, superficies, consumo OBS y edad
de buffer; ninguno demuestra por sí solo píxeles frescos. La ausencia reciente
de buffer es un aviso compatible con contenido estático. Error de sesión o
pérdida del recurso conserva la recuperación explícita existente. Los paquetes
observados antes del plugin tampoco equivalen a frames escritos o recibidos;
la [contabilidad](h14-output-accounting.md) conserva PTS, cortes de parada y
diferencias sin restarlas para producir un aprobado.

Las mediciones separan RSS, footprint y asignaciones malloc vivas. Pausar un
video oculto es una operación explícita; no cambia automáticamente el reloj
según visibilidad. Retirar la fuente y pausar su decoder tienen costes y
retenciones diferentes. La voz opcional sigue como benchmark offline, con
fiabilidad insuficiente y sin ruta de reconocimiento en vivo. Ninguna de estas
ampliaciones añade DSP paralelo, audio por escena, nube, CEF ni otro owner.

## H15 — admisión conservadora y recibos observables

Los perfiles persistidos con frame reordering=true conservan su valor al cargar,
pero preflight/start devuelven FRAME_REORDERING_UNSUPPORTED antes de reservar
recursos. La UI permite desactivarlo explícitamente. No se modifica OBS/H8 ni se
añaden esperas para simular drenaje.

Guardar Show Control devuelve un recibo después de escritura, rename y fsync
de directorio; incluye hash, bytes, owner, revisión, sesión y fingerprint. Un
guard opcional rechaza revisiones/sesiones obsoletas; el guardado no crea una
revisión de producción ni invalida trabajos. La restauración sigue desarmada
y sin replay. Configurar/guardar/activar validan los IDs del proyecto.

La cola de control despierta al owner GPUI mediante canal acotado. No traslada
Production a otro thread ni introduce un reloj multimedia externo. Suspended/
stopped observados por SCK se muestran y bloquean nuevos starts; no convierten
idle en fallo, no fuerzan reconexión y no detienen outputs activos por sí solos.
Los nuevos diagnósticos de identidad/reloj son observacionales; no cambian la
aplicación autorizada ni hacen de MCP un transporte audiovisual.

### H15 B6 — margen de mezcla acotado y observación de recuperación

El núcleo configura `obs_reset_audio2` con 48 kHz estéreo y buffering fijo de
128 ms: seis bloques de 1024 muestras. La evidencia B4 relaciona un bloque de
mezcla incompleto con callbacks SCK hasta 48,24 ms después de PTS y solo 42 ms
de margen dinámico. B6 pasa continuidad estricta sin cambiar ventanas, guards,
umbrales, timestamps de origen ni ownership del mixer. Se reserva al iniciar;
no se reconstruye el mixer, no se añade otra captura y no se simula un drain.
Ese margen no garantiza latencia cero: la medición A/V de siete pulsos conserva
−36,875 ms audio−video. No se declara reparada una pérdida de identidad por
haber corregido el jitter observado. Evidencia: [reanudación H15](h15-resume-verification.md).

Crear una fuente OBS puede devolver un objeto cuyo callback create falló.
La captura comprueba `obs_obj_invalid` y rechaza SOURCE_CREATE_FAILED. El parche
SCK añadido solo registra código/dominio tipado de error, ventana y PID propio;
no filtra ventanas ni reconecta, ni imprime userInfo o descripciones privadas.
Recibir buffers tras recrear una ventana tampoco acredita recuperación final:
el nuevo start puede observar suspensión y debe rechazarla. La prueba B6
conserva ese FAIL en lugar de aceptar el snapshot listo anterior.

El mixer no mantiene el borrador Forms y lee el estado compartido en vivo;
se excluye de ese aviso stale, conservando los guards de formularios reales.
Guardar reglas sigue produciendo un recibo durable y no incrementa revisiones
de producción. Reconciliar no elimina silenciosamente jobs ni habilita replay;
si la sesión aún rechaza cargar por BUSY, se conserva el límite y se exige una
reapertura/restauración explícita desarmada en lugar de modificar el journal.

## H17 — admisión, reconciliación y rendimiento con evidencia separada

La [matriz H17](h17-production-reliability.md) conserva el congelamiento externo
como FAIL. El productor puede seguir dibujando mientras SCK suspende superficies
y OBS renderiza la última textura. No se cambian flags de aplicaciones ajenas,
Spaces ni el estado global del sistema para presentar ese caso como resuelto.

La sustitución de una captura invalida primero los préstamos de scene items
antes de retirar el source OBS; conserva la máscara lógica y las referencias
ajenas. La creación SCK rechaza una ventana ausente, un PID distinto y un
addStreamOutput fallido. B9 mostró además una ventana nueva con geometría 0×0:
el guard B10 valida el mismo rectángulo antes de casts, filtro y SCStream.
Devuelve CAPTURE_NOT_READY y exige una reselección explícita; no inventa
dimensiones ni incorpora un bucle de reconexión. El PASS de recuperación
controlada B10 no cierra la suspensión general ni cambia el cierre asíncrono
de SCK. [Contrato y lifecycle](h17-sck-geometry-admission.md).

Show Control distingue un recibo terminal durable de un recibo de mutación.
Solo reconcile explícito puede usar el terminal validado para cerrar la acción
y cancelar los pasos restantes sin apropiarse de revisiones ajenas. La carga
permanece bloqueada mientras hay operaciones incompatibles o incertidumbre;
cuando se admite, crea una sesión nueva desarmada. No hay replay, borrado de
jobs, incremento de contador ni reescritura de journals para recuperar.
[Causa y verificación](h17-show-control-verification.md).

La contabilidad de outputs exige cobertura de extremos, quiescencia y matching
uno a uno. Un paquete observado antes del plugin no acredita escritura ni
recepción. Las diferencias post-stop y el receptor perdido conservan sus
categorías; no justifican modificar H8, flush, reordering ni introducir sleeps.
El buffering de audio de 128 ms permanece; el fallo histórico de identidad
con proceso vivo no se declara corregido porque no se reprodujo.

GPUI Fast y ui-profiler son features opt-in. El A/B real no mostró una mejora
consistente de CPU y aún falta cobertura de interacción/accesibilidad entre
backends, por lo que el producto mantiene GPUI predeterminado. El heartbeat
de 33 ms mantiene Show Control y datos externos a las entidades GPUI; no se
elimina notify para mejorar una métrica dejando estados obsoletos. La memoria
malloc viva se separa de reservas y footprint. [Evaluación A/B](h17-gpui-performance.md).

B10 es una app release ARM64 con firma ad-hoc local, fuentes inventariadas y
hashes de build. La correspondencia de archivos no prueba reconstrucción
reproducible ni distribución notarizada. Cada prueba identifica su candidato;
los PASS B7/B8/B9 no certifican automáticamente B10. No se publica la beta.

## H20 — alcance exacto de captura y respaldo acotado

Se reutiliza `screen_capture` oficial OBS para Window, Display y Application.
Display requiere UUID explícito y Application un bundle único más UUID, con PID
fijado durante la sesión; ningún target ausente se convierte en escritorio por
fallback. Window excluye child windows y Application el menú compartido. v6
transporta modos nuevos y respaldo opcional; proyectos previos conservan contrato.

Salud distingue superficie recibida de contenido fresco, `idle` de `suspended`
y stop intencional de fallo. Edad de buffer sola no reinicia ni activa respaldo.
Una escena segura debe existir, cubrir canvas con patrón y excluir capturas,
incluidas capas ocultas. Ante fallo SCK confirmado puede recibir un único Cut por
sesión de outputs, acotado a 2 s mientras persiste el fallo. No se destruyen/crean
fuentes ni se modifica audio/output. Cut puede dejar un origen fallido; Fade y el
destino conservan sus guards. La prueba C2 que motivó ese cambio se conserva.

La reconstrucción SCK en vivo sigue cerrada: `obs_wait_for_destroy_queue` no es
un barrier del stop asíncrono de Apple. Reconexión explícita requiere outputs
detenidos. C3 demuestra respaldo de Window/Application propias, no recuperación
general del productor ni ausencia de fugas. [Arquitectura](h20-capture-engine.md),
[investigación fijada](h20-obs-capture-investigation.md) y
[evidencia por candidata](h20-capture-verification.md).
