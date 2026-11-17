# H12 — contrato de integración Creative Studio

Extiende [H11](h11-overlay-ui-contract.md) y conserva el [mixer H10](h10-audio-ui-contract.md).
`Studio` sigue siendo dueño de una única `Production`. La UI envía comandos por
`Studio.command(..., "UI", ...)`; CLI y MCP llegan al mismo owner. Ninguno de los
adaptadores ejecuta el reloj de video, widgets, animaciones o audio.

## Módulos y estado

| Módulo | Responsabilidad |
| --- | --- |
| `ui/studio/creative/mod.rs` | Estado local de biblioteca, borrador, pestañas y observación del worker |
| `creative/importing.rs` | Selector nativo, copia acotada en background, entrega a ImportAsset |
| `creative/library.rs` | Inventario, referencias, presets originales y reutilización de fuentes |
| `creative/draft.rs` | Campos GPUI Kit persistentes, parseo estricto y Definition tipada |
| `creative/inspector.rs` | Creación/edición y protección por revisión |
| `creative/runtime.rs` | Eventos y recibos nativos de animación, sin temporizadores de producto |
| `overlays/assets/staging.rs` | Capacidad Rust local para copiar una selección explícita |

`Creative` contiene estado de presentación. Nunca mantiene una segunda escena,
un mixer paralelo ni una copia autoritativa del runtime. La fuente y su definición
se comparten entre escenas; una capa conserva transformación y visibilidad propias.
Reutilizar una fuente ejecuta `AddLayer` con su ID estable y no crea otra captura.

## Recorrido nativo

Biblioteca → Crear ofrece texto, rectángulo, círculo, countdown y alerta. Recursos
ofrece imagen/video a partir de un asset importado. Presets consulta
`OverlayPresets` y envía sus parámetros originales a `InstantiateOverlayPreset`.
Professional Lower Third, Starting Soon y Be Right Back se editan después con
el inspector tipado. El acento de BRB se selecciona como capa y se anima con Scale;
no hay bucle de animación inventado por GPUI.

El inspector distingue **Contenido**, **En vivo** y **Animación**. Contenido usa
`CreateOverlay` o `UpdateOverlay`, nunca `SetOverlayColor`. Los overlays anteriores
sin `definition` se identifican como «Overlay clásico» y conservan su inspector.
Los atributos inmutables (tipo/asset/subtipo de widget) requieren otra fuente.

Cada borrador captura `Production.revision`. Si cambió el núcleo, Aplicar se
bloquea y Recargar inspector descarta explícitamente el borrador para leer el
estado actual. Esto incluye cambios CLI/MCP y operaciones de salida. La pestaña
En vivo y los recibos de animación consultan el estado nativo aunque el borrador
esté obsoleto. Una respuesta aceptada no se presenta como finalización nativa.

## Importación y consulta nueva

La única API nueva serializable es la consulta sin argumentos `asset_inventory`:

```json
{"op":"asset_inventory"}
```

CLI: `motive ctl '{"op":"asset_inventory"}'`. En MCP, `tools/call` con
`name: "asset_inventory"`, `arguments: {}`. La respuesta conserva el envoltorio
común y añade `result.assets: [{asset: Asset, error: string | null}]`.
Campos desconocidos se rechazan. MCP la anuncia de solo lectura. Un objeto
perdido o corrupto permanece visible con su error; un índice inválido falla la
consulta completa. `list_assets`, `resolve` y el render conservan validación
estricta. Durante importación activa el núcleo puede rechazar la consulta busy.

`AssetCatalog::stage_selected_file(&Path)` es una capacidad interna Rust que la
UI invoca solo con la selección de `prompt_for_paths`. **No tiene comando CLI/MCP
ni admite una ruta serializada.** Abre el componente final sin seguir symlinks,
rechaza archivos no regulares, vacíos o mayores que 64 MiB y copia de forma
acotada a una entrada exclusiva 0600 del inbox privado. Revalida tamaño y tiempos
al terminar. El guard mantiene descriptores y elimina únicamente el inode que
creó; no borra el original ni una entrada reemplazada.

Secuencia observable: selección → copia → `ImportAsset {file_name}` → operation ID
`running` → `completed` o `failed`. El botón permanece ocupado durante la copia
local y el worker del núcleo, también cuando lo inició MCP. «Recurso disponible»
solo aparece después de `completed` para el mismo ID. Si otro cliente sustituyó
el último recibo, la UI lo declara y pide revisar el inventario; no inventa éxito.
El guard se libera tras el estado terminal. `Production` se destruye antes del
guard al cerrar Studio, de modo que su worker termina antes de limpiar la copia.

Importar requiere salida idle. Límites originales: imagen PNG/JPEG/WebP hasta
2048×2048; video H.264/VP8/VP9 hasta 1920×1080, 60 fps y 60 segundos. Video sin audio.
Eliminar se desactiva si hay referencias y requiere el diálogo nativo existente;
el núcleo vuelve a validar. Se muestran escenas que utilizan cada recurso.

Recuperación: reimportar el original idéntico → mismo asset ID reparado → detener
salida si procede → En vivo / Reconectar fuente. No se sustituyen rutas arbitrarias,
no se reconectan silenciosamente todas las fuentes. Un crash puede dejar una copia
staged huérfana; la eliminación por RAII no es una política de recuperación tras
crash y no se elimina basándose en un PID potencialmente reutilizado.

## Eventos, animaciones y concurrencia

| Tipo | Operaciones En vivo |
| --- | --- |
| Lower third | Show / Hide |
| Countdown | TimerStart / TimerStop / TimerReset |
| Alerta | Trigger / Hide |
| Video | Play / Pause / Restart / Stop |
| Texto, imagen, forma | Show / Hide |

Los eventos afectan la fuente en todas sus escenas. El ojo de la lista afecta
solo la capa. Ocultar una capa de video **no pausa** el decodificador; se explica
Pause/Stop en el inspector. `remaining_ms` proviene de libobs y se redondea hacia
arriba al mostrar segundos, igual que el countdown nativo.

`AnimateOverlay` recibe scene ID, layer ID y Animation validada: Fade/Slide/Scale
in/out; duración 100–10000 ms; Slide −1920…1920 px; Scale 0.1…2. Fade es lineal;
Slide/Scale permiten Linear/EaseIn/EaseOut/EaseInOut. La UI muestra operation ID,
phase, progress, pending_ack y error reales; `CancelOverlayAnimation` usa ese ID.
No interpola progreso ni cambia visibilidad al enviar el comando.

Una operación por capa, hasta ocho. No se inicia otra mientras la capa está
running/cancel_pending/pending_ack. Cut/Fade y mutaciones estructurales siguen
los rechazos de H11; el núcleo es la validación definitiva. La UI desactiva los
controles que puede anticipar y presenta el error estructurado si otra operación
concurrente invalida la acción. Las animaciones pueden usarse durante grabación
sin reconstruir fuentes o encoder. Crear fuentes y editar video requiere idle.

## Persistencia y verificación

Guardar/restaurar usa los comandos originales de proyecto v4. No guarda entidades
GPUI, operation IDs transitorios ni un reloj alterno. Escenas v3, mixer y perfiles
de salida conservan sus almacenes/versiones anteriores. Restaurar sigue siendo
explícito; no se reanuda un countdown como si el proceso nunca hubiera cerrado.

[Informe de aceptación](h12-creative-studio-verification.md) separa implementación,
evidencia real y límites. `observe_h12_native.py` consulta exclusivamente status
MCP para documentar operaciones realizadas en GPUI. `verify_h12_performance.py`
mide CPU/RSS de proceso y mantiene separados los presupuestos estimados. Todas
las pruebas físicas requieren el lock compartido y un bundle firmado exclusivo.
No hay Browser Source/CEF, filtros de audio ni reloj multimedia por MCP en H12.
