# H15 — estabilización y aceptación de beta

Inicio: 2026-11-17 (America/Lima). Baseline remoto consultado mediante fetch:
`6019ad0acac4b52dcf1ebc44f2006406fde533f8`, igual a HEAD de main.
Rama local `codex/h15-beta-stabilization`, worktree `motive-h15`.
No se modifica `element-lab/`. Sin push, merge, rebase, publicación ni RTMPS nuevo.

## Auditoría inicial de H14

Se revisaron README, plan, decisiones, aceptación/producción H13 y los informes
H14 de beta, captura, colección y seguimiento, pruebas H13 adicionales, outputs,
memoria/soak, recorrido nativo, Show Control/contrato, portable y RTMPS B2.
Los informes históricos y medios permanecen intactos en sus worktrees.
Un PASS histórico no certifica el binario H15.

| Bloqueo | Clasificación inicial | Evidencia / siguiente comprobación |
|---|---|---|
| Contador capturado congelado H13 | Bug reproducido; causa inconclusa | Píxeles repetidos, productor dibuja. Separar publicación, recepción SCK y consumo/composición; no inferir frescura de callbacks. |
| Suspended / sin primer IOSurface H14 | Resultado inconcluso de captura | Preflight bloquea correctamente. Observar foco del sistema y ventana antes de repetir. No imputar Stage Manager. |
| A→B→A sin foco corroborado | Limitación del verificador / posible interacción humana | CUA contradice app_active/key. Observación independiente PID + timestamp; si no cambia, HUMAN_ACTION_REQUIRED. |
| APPLICATION_UNAVAILABLE durante tone_resumed | Bug reproducido; disparador no observado | Buffers recientes (161 ms), fixture viva otros 16,73 s. Revisar cada condición de identidad, sin equiparar silencio a pérdida. |
| Gaps con frame_reordering=true | Bug reproducido / modo no confiable | Matriz 15 casos; siete medios fallan cadencia. Mantener off y revisar admisión de perfiles persistidos. |
| Dos AAC ausentes antes del stop | Pérdida real; compatible con cutoff OBS, no PASS | Primer video cruza stop_ts; siguiente AAC anterior queda fuera. No modificar OBS/H8 sin evidencia. |
| Callback contado pero paquete posterior al stop ausente | Comportamiento documentado OBS, entrega parcial explícita | Observer precede al plugin; no igualar encoder, dispatch, escrito, recibido y decodificado. |
| Encoder→observer sin identidad temporal | Resultado inconcluso | Interleaver puede retener; no atribuir cada delta por resta de contadores. |
| Footprint/reservas tras retirar videos | Resultado inconcluso; no fuga demostrada | In-use vuelve cerca del baseline; RSS/allocated/footprint difieren. Pruebas comparables con ownership. |
| RPC p95 50,88 ms >20 ms | Incumplimiento medido | Colección nativa <1 ms; investigar scheduling/transporte y preview. |
| 39 skips y pausa visual 0,601 s | Degradación observada; causa inconclusa | No aceptar cero pausas por gate <1 s. No repetir soak sin hipótesis. |
| Guardar reglas GPUI sin store nuevo | Resultado inconcluso / limitación de observación | No hay receipt de mutación; otro guardado previo sí pasó. Revisar validación, revisión, error y feedback duradero. |
| Shutdown queue / collector idle TIMEOUT | Limitación de cobertura | PID sale y no inicia output; no se observó rechazo específico. Separar salida normal de recibo de solicitud. |
| Stock450 y cancelación antes del tick | Carrera no observada | Custom3000 y cancelación posterior no sustituyen el escenario. |
| VoiceOver, foco real, hot-unplug, sleep/wake, permisos | Dependencia de interacción humana | No abrir cámara/micrófono sin supervisión; preparar pasos concretos. |
| Segunda Mac, firma de distribución y notarización | Requisito externo de distribución | Bundle local firmado no equivale a distribución aceptada. Sin certificados nuevos ni notarización. |

## Checkpoints y evidencia H15

La aceptación sigue **NOT_ACCEPTED** mientras se ejecutan las correcciones y
verificaciones. Cada gate final usará PASS, PARTIAL, FAIL, BLOCKED o NOT_EVALUATED;
pruebas de contratos no sustituyen captura o medios decodificados.

- A: baseline remoto verificado y worktree aislado; auditoría inicial registrada.
- B–J: en ejecución. Resultados y hashes se añadirán al cerrar cada checkpoint.

### B — foco observable (checkpoint)

`h15-focus-01/report.json`: AppKit consultado desde un proceso independiente
corrobora fixture→Motive→fixture contra active/key de la fixture. No se usa CUA
ni se cambian preferencias. La petición LaunchServices no cuenta como prueba:
solo la coincidencia contemporánea permite un marcador. Metadata no prueba píxeles.

La primera toma `h15-focus-capture-b1-01` termina antes de capturar porque la
fixture anunció ready antes de publicar metadata CG. Se corrige la espera del
harness; el fallo permanece. La segunda toma de 45 s produce MKV/RTMP locales y
verifica foco durante las tres fases (23/20/16 observaciones interiores, spans
12,29/10,60/8,40 s). Cleanup sin errores y owner cerrado normalmente.
El análisis original queda INCONCLUSIVE: el rectángulo CG cambia al perder foco.
Se incorpora observación separada de frame/content AppKit para comprobar la
geometría del productor sin confundirla con el rectángulo de una miniatura.
No se declara resuelta la captura antes de medir los píxeles por fase.

### C — diagnóstico de audio y cobertura de continuidad (checkpoint)

B1 añade metadata de identidad de aplicación: PID autorizado/observado, cantidad
de instancias registradas, terminated, consulta independiente del PID y motivo
exacto. Se conserva al fijar el fallo. No modifica la política de salud, no
reconecta automáticamente ni acepta otra identidad. Los 116 tests raíz pasan.

`h13-system-audio-1794977342854410000/report.json` repite en orden pilot, RTMP,
recovery, transitions, persistence y silence sobre B1: seis etapas PASS, sin
fallo inesperado en reanudación/cola. No abrió cámara ni micrófono. La pérdida
controlada registra `no_registered_instance` y PID ausente, seguida de recuperación
explícita. **El fallo intermitente H14 no fue reproducido; no está reparado.**

El verificador ahora comprueba todas las ventanas interiores de 100 ms de tono,
reanudación y cola a 997 Hz, y rechaza estados failed/disconnected no previstos.
Conserva las aserciones anteriores y los límites de silencio/pausa. Su contraste
offline con el medio histórico H14 y el nuevo B1 queda separado en
`h15-audio-continuity-checker/report.json`; no reescribe aquellos informes.
El nuevo checker rechaza la pérdida tardía histórica. También conserva un
fallo de una ventana del tono inicial en B1 (mínimo 0,01691 frente a
referencia 0,03160), aunque reanudación/cola pasan y no hay fallos de identidad.
La alineación se investigó como hipótesis, aún sin demostrar; no se amplía el guard
de 200 ms para producir un PASS. El PASS del runner anterior sigue acotado a
sus aserciones originales.

### D — restringir el modo que pierde cadencia/audio

Se impide iniciar cualquier destino con `frame_reordering=true`, incluido el
UDP heredado, antes de reservar archivo/attempt. Preflight devuelve
`FRAME_REORDERING_UNSUPPORTED`; capabilities solo anuncia false. Los perfiles
v1 siguen cargando y conservan exactamente el valor guardado; la UI permite
desactivarlo explícitamente y explica el bloqueo. No se modifica OBS, stop_ts,
interleaver, muxer, encoders ni barrera H8, y no se añade una espera de drenaje.
La restricción trata los fallos H14 demostrados; no promete entrega completa
del perfil sin reordering. 116 tests raíz y Clippy all-targets PASS.

### E — latencia del control, sin cambiar multimedia

La cola acotada despierta al owner GPUI por eventos; deja de esperar al tick de
preview de 33 ms. El listener usa poll del socket, sin sondeo de 10 ms. Conserva
un único Production, serialización y replies; no añade reconexiones ni reintentos.
100 consultas comparables sin outputs: B1 mediana 17,926 ms / p95 45,518 ms;
B2 mediana 1,326 ms / p95 10,983 ms, máximo 42,765 ms. Evidencia:
`h15-rpc-baseline-b1/report.json`, `h15-rpc-wakeup-b2/report.json`, hashes de
binario/fuentes en cada build-binding. Presupuesto p95 <20 ms PASS en este caso,
no garantiza latencia bajo carga ni cierra el soak H14. Tests raíz y Clippy PASS.
No se ha demostrado una fuga ni se modifica el compositor/allocator.

### F — guardado observable y validación de bindings

La escritura ya era durable. El defecto concreto era el feedback: Guardar no
incrementa la revisión de producción y la UI solo anunciaba cambios de revisión.
Ahora devuelve recibo tras fsync/rename/fsync de directorio (SHA-256 exacto, bytes,
sesión, PID, revisión, secuencia y fingerprint) y muestra resultado/error persistente
en Live Deck. GPUI envía la sesión/revisión mostrada; CLI/MCP pueden exigirla con
`expected`. El comando legacy sin guard conserva la semántica de guardar el estado
actual. Guardar no invalida jobs admitidos ni modifica el ledger de revisiones.
Configurar/guardar/activar rechazan referencias de fuente/escena/capa inexistentes;
restaurar permanece desarmado. 118 tests raíz y Clippy PASS, incluidos rechazo
stale/sesión, IDs rotos, hash de bytes durables y preservación ante error.
Recorrido nativo/reapertura aún pendiente de comprobar sobre el candidato.

### B — causa acotada con foco y píxeles, no resuelta globalmente

B3 default (`h15-focus-capture-b3-01/analysis/analysis.json`) **FAIL**: foco
independiente corroborado; MKV/RTMP decodifican 1344 frames, pero repiten el
contador durante ~15,4 s. La fase Motive al frente tiene cero ticks de avance.
La fixture sigue dibujando; SCK emite suspended, deja de entregar superficies y
OBS sigue renderizando su última textura. Al volver el foco, el contador avanza.
El primer paquete VT se correlaciona por conversión exacta AnnexB→AVCC con
SPS/PPS del CodecPrivate y fuente OBS fijada, sin tolerancia ni desplazar origen.

B3 `join-all` (`h15-focus-capture-b3-join-all/analysis/analysis.json`) **PASS de
frescura** en ambos medios y las tres fases. Solo cambia collectionBehavior de
la fixture; no cambia Stage Manager/TCC/Spaces. Apple documenta
[canJoinAllApplications](https://developer.apple.com/documentation/appkit/nswindow/collectionbehavior-swift.struct/canjoinallapplications)
para ventanas que pueden unirse a otras apps. Este contraste acota la condición
de suspensión; no demuestra una reparación general de ventanas ajenas.
[suspended](https://developer.apple.com/documentation/screencapturekit/scframestatus/suspended)
expresa ausencia de nuevas actualizaciones. La UI ahora muestra suspensión en
Capas/diagnóstico y preflight rechaza suspended/stopped; idle o un buffer antiguo
no se convierten en fallo. No destruye/reconecta fuentes ni detiene outputs
activos ante suspensión. El retorno de frames borra el aviso por observación.

### C — corrección del reloj del instrumento

La referencia anterior era la respuesta de start, posterior al inicio multimedia;
además hold puede sobrepasar un cambio de fase. Se conserva ese resultado como
`application_continuity_control_clock`. La comparación nueva ancla el primer AAC
a una consulta nativa con reloj nombrado y bracket <=50 ms; verifica primer tamaño,
prefijo completo, PTS y todos los conteos de muestras decodificadas. Usa cambios
reales de modo de la fixture. No ajusta el reloj al tono ni cambia el umbral/guard
de continuidad. Los archivos históricos sin ese bracket no obtienen un PASS
retroactivo. El fallo intermitente de identidad continúa abierto.

El helper de regresiones adopta reordering=false por defecto como perfil H15
permitido. Los ensayos que soliciten true explícitamente deben comprobar rechazo;
la matriz H14 original y sus resultados permanecen intactos.

### C — resultado B4, límite conservado

`h13-system-audio-1794978516071979000/report.json`: pilot, RTMP, recovery,
transitions y persistence PASS. Silence conserva FAIL del nuevo gate de
continuidad: amplitud 997 Hz 0,016809 frente a referencia 0,031605 en la ventana
interior 2,7–2,8 s; resumed y tail PASS, sin failed/disconnected inesperado.
El nuevo bracket es 38,85 ms y relaciona 1.688.576 muestras de 1649 frames AAC.
La hipótesis inicial de un borde de fase **no explica** esta caída. El análisis
de 20 ms (`h15-audio-b4/low-projection-review.json`) conserva una caída a 0,0190
y 0,0106 alrededor de 2,72–2,76 s mientras 440 Hz continúa. No se conoce todavía
si es discontinuidad/ausencia en captura o tratamiento temporal del audio; los
meters espaciados no observan ese intervalo. No se cambia el umbral ni se declara
reparación. El log registra buffering OBS de 42 ms, sin demostrar causalidad.
El fallo H14 de identidad tampoco se ha reproducido: son dos límites distintos.

### D/E — matriz conservadora y regresión del candidato B4

`h15-output-matrix-b4/report.json`: ocho primeros casos funcionales PASS
(VideoToolbox/x264 × recording/streaming/dual, cancelación y receiver-loss).
Cada medio decodifica, cumple cadencia, AAC continuo y ausencia de clipping;
las colas conservan `STOP_BOUNDARY_PACKETS_NOT_DELIVERED`, y receptor perdido
queda INCONCLUSIVE/medio parcial intencional. No se ocultan diferencias de contadores.
El noveno caso original es FAIL del harness: el padre dejó un zombie mientras
el verificador esperaba que desapareciera en ps. Owner ya había salido normalmente
y escrito el terminal. Se corrige reaping en `h15_run_owned.py`; el nuevo caso
`h15-regressions-b4/shutdown-reaped` obtiene functional PASS / PARTIAL de cola,
owner exit 0, sin force-stop. No reemplaza el informe fallido.

Control MCP/CLI compartido, desconexión de cliente y recepción fragmentada PASS.
El test live de perfiles verifica rechazo de preflight/start sin incrementar
attempt y conserva la selección unsafe hasta desactivación explícita. Latencia
B4: mediana 3,399 ms / p95 12,047 ms / máximo 27,868 ms en 100 consultas idle;
el gate p95<20 ms pasa. No implica latencia garantizada bajo carga.
