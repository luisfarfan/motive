# Decisiones y evidencia

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

## D3 — Integración implementada y límites

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
- Grabación: `obs-x264` + `ffmpeg_aac` + `ffmpeg_muxer`, helper y bibliotecas del
  bundle oficial. Software x264, no una demostración de encoder hardware.
  Streaming local: `ffmpeg_output`, libx264/AAC y MPEG-TS a UDP loopback fijo.
  El soporte de protocolos no prueba integración con YouTube/TikTok.
- Un solo output simultáneo. `stop_output` es asíncrono: observar `idle` y
  `output_code == 0` antes de cambiar formato o dar un archivo por terminado.
- Dos composiciones: 960×540 y 540×960. Captura con ajuste `contain`, anclada
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
están limitados a obs-x264, obs-ffmpeg, obs-outputs, mac-capture y obs-transitions;
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
