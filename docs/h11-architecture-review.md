# H11 — Revisión de arquitectura

Revisión del incremento nativo al 17 de noviembre de 2026. Describe responsabilidades, límites y deuda; no declara aceptación final ni sustituye la evidencia audiovisual. El [contrato de integración](h11-overlay-ui-contract.md) define comandos y respuestas para GPUI, CLI y MCP.

## Responsabilidades y recursos

| Componente | Responsabilidad |
|---|---|
| `Production` y `src/overlays/production.rs` | Validación, documento deseado, identidad, presupuesto del grafo, importación y reconciliación de resultados. |
| `src/overlays/assets.rs` | Inbox autorizado, normalización, catálogo versionado y resolución de IDs a archivos administrados. |
| `native/overlays/sources.inc` | Fuente visual libobs, hijos oficiales de texto/imagen/video, primitivas acotadas y widgets declarativos. |
| `native/overlays/animation.inc` | Acciones por instancia de capa, referencias OBS, reloj nativo y resultados retenidos. |
| `native/graph.inc` | Reutilización de fuentes y preparación de escenas antes de publicar el grafo. |
| UI/CLI/MCP | Enviar comandos y presentar snapshots; no crear un segundo modelo ni programar frames. |

Una definición identifica una fuente reutilizable; las capas contienen posición, tamaño, orden y visibilidad por variante. Editar texto o disparar un widget compartido afecta sus capas. Animar una capa modifica solamente su item OBS. Compartir un `asset_id` deduplica almacenamiento; crear dos fuentes de video independientes puede crear dos decodificadores.

Los hijos oficiales `text_ft2_source`, `image_source` y `ffmpeg_source` conservan la composición y reproducción dentro de libobs. El wrapper añade fondo, primitivas y opacidad en un target limitado. El texto usa bloques naturales, saltos explícitos y ajuste al contenedor; no promete maquetación tipográfica avanzada. Cambios compatibles conservan recursos; cambios de identidad, incluido subtipo de widget, requieren recreación.

## Operaciones y consistencia

Las animaciones aceptadas devuelven `operation_id`. El tick OBS avanza fade, desplazamiento y escala; las consultas no son un reloj multimedia. Fade utiliza la transición oficial por item y solamente admite easing lineal. Las otras acciones admiten cuatro curvas y distancia firmada ±1920.

Un resultado terminal conserva `pending_ack` hasta que el propietario aplica su efecto al documento y reconoce exactamente ese ID. Los ocho slots no desalojan resultados pendientes: ejercen contrapresión. `running` distingue ejecución; `busy` incluye también reconocimiento pendiente. El propietario registra generación del grafo, variante, escena, capa y fuente al aceptar la operación. Una finalización antigua no modifica otro documento o variante. Cancelación restaura la línea base; solamente una finalización completada actualiza visibilidad deseada. Reconstrucciones y cambios de escena/variante permanecen bloqueados durante esa transacción. No existe un comando de ack para clientes.

El framing separa solicitudes de **64 KiB** y respuestas de **1 MiB**. Esto evita que un estado grande provoque un falso fallo de transporte después de aplicar una mutación. Las pruebas de socket fragmentado cubren ambos límites. Las mutaciones no se reintentan automáticamente.

## Persistencia y recuperación

Los proyectos sin definiciones H11 conservan v3. Los que contienen overlays usan v4; insertar overlays en v3 se rechaza. Guardado y lectura comparten límites: 64 KiB para v1–v3 y 256 KiB para v4. Los campos son tipados y estrictos. El catálogo de assets tiene versión propia; perfiles de salida y mezclador H10 conservan sus documentos independientes.

Se persisten definiciones y layouts, no timers en marcha, procesos, referencias OBS ni operaciones. Ante recurso ausente/corrupto, reimportar una copia válida puede reparar el objeto conservando ID; `reconnect_source`, estando idle, reconstruye y verifica. No se reemplaza silenciosamente el contenido ni se reinicia una salida automáticamente.

## Frontera de seguridad

La API acepta un basename de `var/imports`, nunca rutas arbitrarias, URLs o comandos. Descriptores relativos, `O_NOFOLLOW`, archivos regulares de un enlace y directorios privados restringen el acceso. El broker verifica hashes; solamente incorpora la ruta canónica administrada al JSON interno enviado a nativo. Estado público devuelve IDs/metadatos, sin ruta original ni bytes. Stderr de FFmpeg se consume y descarta; los errores nativos pueden mostrar rutas administradas.

Las imágenes se decodifican y normalizan a PNG. Videos admitidos se inspeccionan, decodifican para validación y remuxean a MKV con pistas permitidas, descartando tags originales de contenedor/streams y capítulos. La copia de codecs puede conservar metadatos embebidos en el bitstream, como SEI; no garantiza eliminar toda información auxiliar. Hay listas de protocolos, formatos y codecs; referencias externas MOV se deshabilitan. Límites: 64 MiB por archivo, 128 objetos y 512 MiB catalogados.

Esto **no es aislamiento del sistema operativo** frente a procesos del mismo UID ni frente a vulnerabilidades de decodificadores. FFmpeg/ffprobe proceden del entorno instalado. Los subprocesos tienen plazos y salida acotada; `max_alloc` limita una asignación, no RSS total. La decodificación de imágenes ocurre en el worker del proceso, sin cancelación temporal. Temporales y huérfanos tras un fallo no forman parte de la cuota catalogada; requieren política de limpieza futura.

## Memoria, audio y Browser Source

El presupuesto de 256 MiB estima píxeles y atlas de **todas** las fuentes, activas o inactivas, con máximo cuatro videos. Excluye decodificadores, colas, encoders y otros recursos: no es un límite de RSS. Videos ocultos permanecen abiertos y pueden seguir decodificando. Preparar un grafo nuevo antes de liberar el anterior puede mantener ocho decodificadores durante un reemplazo de cuatro videos, además de duplicar temporalmente recursos estimados. Faltan mediciones de esos picos y una política explícita de suspensión.

El audio de medios sigue cerrado: hijos con mixers `0`, mute y monitoreo desactivado. Conservar una pista validada en el asset no la incorpora al mezclador H10. Browser Source permanece indisponible con `BROWSER_ISOLATION_UNAVAILABLE`: el [spike](h11-browser-spike.md) documenta falta de confinamiento de archivos/red, sandbox y ciclo de vida integrado de CEF. No se admite HTML/JS arbitrario.

## Rendimiento y siguientes incrementos

El baseline de animación registró 457 frames retrasados. La actividad `NSProcessInfo`, con `UserInitiatedAllowingIdleSystemSleep` y `LatencyCritical`, cubre preparación del encoder, salida y finalización de workers; termina al finalizar o fallar. Es un alcance de lifecycle, no una corrección de rendimiento demostrada. El bundle ya declara `LSAppNapIsDisabled:true`: no se atribuye el lag a App Nap ni a throttling confirmado. La regresión estricta de encoding conserva 9/13 frames de lag y el diagnóstico B7, 6 al arranque; B7 widgets registra otros 4 antes de su primera muestra, con el contador estable después. La causa sigue pendiente. Apple contempla actividades para trabajo audiovisual sensible a latencia, sin garantizar rendimiento; no se modifican ajustes globales. [Referencia oficial Apple](https://developer.apple.com/documentation/foundation/processinfo).

Prioridades: cerrar regresiones con sesión desbloqueada y distinguir arranque de cadencia estable sin relajar criterios; medir fuentes ocultas y reemplazos; acotar cancelación/limpieza de imports; evaluar suspensión de decoders sin perder timestamps; después considerar audio de medios mediante H10 y un host browser aislado. Captura de audio del sistema sigue siendo otro incremento independiente.
