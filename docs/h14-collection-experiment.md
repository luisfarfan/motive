# H14 — ensayo propuesto de colección de ventanas

**Propuesta ejecutada posteriormente sobre B3; resultado inconcluso.** Durante
la preparación del bundle permanecía NOT_RUN. La [ejecución A→B→A y sus medios](h14-collection-b3-verification.md)
conservan A1/A2 FAIL y B INCONCLUSIVE: contador fresco global, foco sin corroborar.
No cambia Motive, H13, preferencias globales, permisos, Stage Manager ni método
de captura. No atribuye la suspensión observada ni demuestra una corrección.

## Evidencia y límites de las APIs

Apple describe `canJoinAllApplications` como una preferencia que permite unirse
a ventanas de otras aplicaciones y que excluye esa ventana del layout de Stage
Manager. Está disponible desde macOS 13 y es mutuamente excluyente con `primary`
y `auxiliary`; se recomienda normalmente para ventanas flotantes/overlays.
No documenta una garantía de publicación de buffers ni de captura SCK.
[Referencia oficial](https://developer.apple.com/documentation/appkit/nswindow/collectionbehavior-swift.struct/canjoinallapplications).
El SDK local confirma esa semántica en
`AppKit.framework/Headers/NSWindow.h:94–98,147–149`.

`isVisible` puede seguir siendo verdadero aunque otras ventanas tapen la ventana.
`occlusionState` representa visibilidad parcial, incluso admite casos de ventana
transparente o bounding box visible. Ninguna propiedad certifica que un contador
dibujado haya llegado a WindowServer o SCK.
[isVisible](https://developer.apple.com/documentation/appkit/nswindow/isvisible),
[occlusionState](https://developer.apple.com/documentation/appkit/nswindow/occlusionstate-swift.property).
El SDK lo detalla en `NSWindow.h:184–190`; `onActiveSpace` (`:543–544`) informa
sobre el Space activo, no es un identificador de grupo de Stage Manager.

`SCFrameStatus.suspended` informa que no se generó un frame al estar suspendidas
las actualizaciones; no identifica qué componente causó la suspensión.
[Referencia oficial](https://developer.apple.com/documentation/screencapturekit/scframestatus/suspended).
En el SDK, `ScreenCaptureKit.framework/Headers/SCStream.h:41–57` define los
estados. `SCStreamFrameInfoDisplayTime` (`:417–421`) corresponde al momento de
presentación por WindowServer: es una observación posterior a `drawRect`, pero
el avance de píxeles de la toma final sigue requiriendo decodificación.

## Diseño A/B

La nueva `scripts/fixtures/h14_collection_app.m` contiene una ventana **NSWindow**
normal, buffered, con título/cerrar/minimizar, mismo tamaño 680×240 y mismos
`setNeedsDisplay`/`displayIfNeeded` que la ruta AppKit H13. Es un estímulo de video
sin audio: evita usar altavoces, dispositivos o AVAudioEngine para esta pregunta.
El original `scripts/fixtures/h13_audio_app.m` permanece intacto. Esta nueva
fixture no equivale a reproducir el fallo histórico H13 ni a certificar A/V.

Ambos brazos usan el mismo binario, clase, nivel de ventana, dibujo, temporizador,
contenidos, tamaño y telemetría. No se cambia a `NSPanel`, no se eleva a floating,
no se agrega `canJoinAllSpaces`, `stationary` ni `moveToActiveSpace`, y no hay
reactivación periódica ni snapshots offscreen. Cambiar clase/nivel/layer-backing
en el mismo ensayo introduciría otras variables; solo se registran sus valores.

| Brazo | Propiedad antes de mostrar la ventana |
|---|---|
| A: `default` | No se modifica `collectionBehavior`; se registra el valor inicial |
| B: `join-all` | Conserva otros bits y sustituye únicamente el grupo mutuamente excluyente por `CanJoinAllApplications` |

La ventana muestra un contador a 10 Hz y 16 bloques binarios, bit menos
significativo a la izquierda, con geometría registrada en el evento `ready`.
El temporizador pide dibujo a 30 Hz. Cada segundo y al cambiar activación/
oclusiones se registran: uptime monotónico, ID/PID propios, clase/nivel/style,
collectionBehavior inicial/final, visible/occlusion/onActiveSpace, estado de app,
escala, layer-backing, ticks pedidos/dibujados y draw count. La consulta CG se
limita al ID propio y vuelve a filtrar PID+ID; solo conserva bounds/layer/alpha/
on-screen, nunca imágenes ni títulos de otras ventanas. **Es metadata, no prueba
de publicación de píxeles.**

## Procedimiento reservado al owner del lock físico

Construir solo después del build de Motive y fuera de cualquier medición:

```sh
python3 scripts/fixtures/build_h14_collection_app.py --lock-held
```

El script exige que el lock canónico pertenezca al worktree, escribe únicamente
`target/H14CollectionFixture.app` (bundle ID `local.motive.collectionfixture`),
firma ese fixture ad hoc por defecto y conserva hashes/comando/SDK en
`target/h14-collection-build.json`. No abre ventanas ni modifica bundles previos.

Ejecutar un solo brazo y proceso a la vez, guardando su stdout por separado:

```sh
target/H14CollectionFixture.app/Contents/MacOS/MotiveCollectionFixture --collection-arm default
target/H14CollectionFixture.app/Contents/MacOS/MotiveCollectionFixture --collection-arm join-all
```

1. Hacer A→B→A con procesos frescos. Resolver cada ventana por bundle ID, PID e
   ID exactos; no reutilizar IDs ni crear una segunda captura del mismo target.
   Conservar el mismo bundle Motive, módulo SCK, canvas, filtro, posición, perfil
   y receptor controlado; registrar hashes y las transiciones de foco.
2. En cada brazo observar primero 15–20 s con el fixture al frente. Activar
   después el estudio propio de Motive durante 20 s y registrar si el entorno
   de Stage Manager ya existente lo coloca en otro grupo. No cambiar preferencias
   ni inferir pertenencia de grupo solo de `onActiveSpace`/`app_active`. Volver al
   fixture 15–20 s; no elevarlo repetidamente durante las fases.
3. Para cada fase guardar el estado nativo SCK: distribución de statuses,
   callback count, superficies válidas, displayTime, consumo OBS de IOSurface,
   dimensiones, avisos y errores. Si no aparece el primer buffer, conservar
   `CAPTURE_NOT_READY`; no saltar el preflight ni iniciar salidas a la fuerza.
4. Si hay buffers y salidas permitidas, guardar grabación controlada y el
   receptor local existente. Decodificar y comparar el contador binario en
   frames interiores separados por segundos; medir pausas y recuperación.
   `draw_count`, hashes del bitmap local o bytes de encoder solos no satisfacen
   este criterio. No agregar `cacheDisplay` para fabricar la prueba.
5. Cerrar normalmente el fixture entre brazos. Revertir al A fresco distingue
   un efecto reproducible de un simple reinicio de fuente/SCK. Si A no reproduce
   suspensión, el ensayo no explica el fallo H13. Si A falla y B avanza repetible,
   concluir solo que la preferencia cambia el resultado **en este entorno y
   productor**; no declarar una causa general ni incorporar el flag a Motive.

Comparar después con H13 original y la ventana GPUI como ensayos distintos. Una
diferencia AppKit/GPUI también cambia renderer/clase/backing y proceso: por sí
sola no aísla Stage Manager. Cualquier ensayo posterior con `NSPanel`, layer-
backing o flushing debe tener su propio control y registrar una sola variable.
