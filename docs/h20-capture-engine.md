# Capture Engine H20

## Implementación

UI, CLI y MCP envían los mismos comandos a `Production`. El grafo mantiene
recursos con ID propio y capas que los reutilizan. `src/capture.rs` valida las
identidades y clasifica observaciones; no transporta píxeles ni lleva un reloj.
`native/capture-targets.inc` inventaría targets exactos y `native/graph.inc`
configura el `screen_capture` oficial. SCK produce IOSurface, libobs las consume,
compone y entrega al encoder/output existentes. No hay otro motor de video.

| Modo | Identidad persistida | Identidad de sesión y alcance |
|---|---|---|
| Window | bundle y título, formato existente | ID de ventana + PID exactos; sin child windows |
| Display | UUID canónico de `devices.displays` | display activo resuelto por UUID; pantalla completa explícita |
| Application | bundle y UUID de display | una única app en ejecución, PID fijado; sus ventanas en ese display, sin menú compartido |

IDs runtime no se convierten en identidad persistente. Un target ausente,
duplicado o cambiado no selecciona otro display/app/ventana. El grafo rechaza dos
recursos Display/Application idénticos; se debe añadir una capa del mismo recurso.
Crear/reconectar recursos requiere outputs detenidos. La captura visual se silencia
en OBS: audio de app/juego/micrófono se configura en el mixer existente.

Los proyectos con modos nuevos usan v6, con `video` opcional. v1–v5 conservan sus
contratos; no se permite esconder tipos v6 en un archivo de versión anterior.
La carga sigue siendo explícita y la resolución de identidad falla de forma
visible si el target no existe o es ambiguo.

## Salud y lifecycle

`capture_delivery` distingue `inactive`, `unavailable`, `unobserved`, `starting`,
`receiving`, `static_or_unobserved`, `blank`, `suspended`, `stopped`, `user_stopped`
y `failed`. `receiving` significa superficie reciente, no contenido fresco. La
propiedad `content_freshness` conserva `not_inferred_from_timestamps`.

`idle` o edad mayor de tres segundos no provoca por sí sola una reconexión. La
detención por el usuario prevalece sobre un último sample `complete`. El preflight
rechaza estados suspendidos, sin imagen y terminales. Las transiciones rechazan
un destino suspendido/sin imagen. No existe fallback implícito a escritorio.

La fuente oficial retiene el lifecycle SCStream. H17 libera los scene items que
tomaban referencias antes de destruir un recurso sustituido; el stop SCK sigue
siendo asíncrono. Esta implementación **no habilita reconstrucción automática en
vivo** ni promete ausencia de callbacks tardíos. Se conserva reconexión explícita
con las salidas detenidas.

`configure_capture_fallback` permite elegir una escena existente, con un patrón
visible que cubra el canvas y exclusivamente overlays locales. Se valida al
configurar, cargar y editar el grafo; una escena con cámara o captura, incluso
oculta, no es elegible. La selección se guarda como `capture_safe_scene` en v6.
Con outputs activos, un fallo SCK confirmado puede cancelar la transición en
curso y ejecutar un Cut al respaldo. No crea/destruye recursos SCK ni cambia el
mixer/encoder/output. El presupuesto es un intento por sesión de outputs; si
falla, no se reintenta y se aplica el cierre seguro existente. Una edad incierta
no activa el respaldo. Sin respaldo configurado se conserva la política previa.
`capture_recovery` expone intento/operación, nunca afirma que la fuente se reinició.

## Uso local y gates pendientes

Abrir el bundle candidato, elegir Añadir fuente y luego Ventana, Pantalla o
Aplicación. Leer el alcance mostrado y elegir una identidad de la lista. Reutilizar
la misma fuente en otra escena mediante Añadir capa. Guardar el proyecto solo
cuando se quiera persistir esa selección. Un permiso se concede mediante el flujo
normal de macOS; no se modifica TCC ni se reinicia una fuente detenida por el usuario.

CLI/MCP admiten estos payloads (sustituir IDs exclusivamente por `devices` y `status`):

```json
{"op":"add_source","scene_id":"SCENE_ID","name":"Juego","source":{"kind":"display","display_uuid":"UUID_FROM_DEVICES"}}
{"op":"add_source","scene_id":"SCENE_ID","name":"Aplicación","source":{"kind":"application","bundle_id":"BUNDLE_FROM_DEVICES","display_uuid":"UUID_FROM_DEVICES"}}
{"op":"add_source","scene_id":"SCENE_ID","name":"Ventana","source":{"kind":"window","window_id":123}}
{"op":"reconnect_source","source_id":"SOURCE_ID"}
{"op":"configure_capture_fallback","scene_id":"SAFE_SCENE_ID"}
```

Los payloads se pasan a `Motive.app/Contents/MacOS/motive ctl '<JSON>'`; MCP llama
las herramientas homónimas contra el mismo owner abierto. Los valores de ejemplo
no son targets válidos y nunca deben resolverse por aproximación.

| Sesión propuesta | Preparación | Aceptación todavía requerida |
|---|---|---|
| Gaming | 1080p60; display explícito; audio de juego y mic separados; VideoToolbox; escena de espera preparada | Juego real, pantalla controlada, 60 min, cambios de foco/fullscreen, audio y A/V medidos |
| Podcast | 1080p30; cámara/mic explícitos; audio de invitado/app; MKV + RTMP local | Dispositivos reales, 60 min, desconexión controlada, continuidad y decodificación |
| Charlas | 1080p30; Window/Application para limitar alcance; Display solo con escritorio controlado | 60 min; cerrar/recrear/minimizar ventana, Spaces y recuperación sin ampliar alcance |

Antes de salir en vivo, verificar preflight, movimiento real en preview y medio
local decodificado. Una imagen congelada puede coexistir con render/PTS continuos.
Ante suspensión, mostrar la fuente y comprobar avance real; si no recupera,
usar el respaldo previamente configurado, detener las salidas cuando corresponda,
esperar finalización y reseleccionar/reconectar explícitamente.
No usar reconexión repetida como sustituto de una causa medida.

La tabla describe una guía de validación, no presets certificados. Tres sesiones
de una hora, A/V, tail, Display físico y recuperación en vivo siguen siendo gates
independientes de unit tests. RTMPS externo requiere autorización específica y el
flujo seguro de destinos/credenciales existente. Browser Host H19 no se integra
en este cambio; su handoff deberá preservar estos contratos de fuente y owner.
