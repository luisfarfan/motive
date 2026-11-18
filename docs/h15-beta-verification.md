# H15 — estabilización y aceptación de beta

Inicio: 2026-11-17 (America/Lima). Baseline remoto consultado mediante fetch:
`6019ad0acac4b52dcf1ebc44f2006406fde533f8`, igual a HEAD de main.
Rama local `codex/h15-beta-stabilization`, worktree `motive-h15`.
No se modifica `element-lab/`. Sin push, merge, rebase, publicación ni RTMPS nuevo.

**Primer cierre B4: NOT_ACCEPTED para beta privada.** La
[reanudación H15](h15-resume-verification.md) conserva este cierre y sus hashes,
y registra las correcciones y verificaciones posteriores. B4 incorpora restricciones y
recuperación de feedback comprobadas, pero conserva fallos de frescura/recuperación
de ventana y una caída breve de audio de aplicación. No se declara resuelto
`APPLICATION_UNAVAILABLE`, que no volvió a reproducirse. La matriz final y los
procedimientos pendientes están al final de este informe.

Candidato local: `/Users/luisfarfan/Developer/motive-h15-portable/b4/Motive.app`.
Ejecutable SHA-256:
`add4032b359c92fd36782d2157a1f72aaccf55fb50839e2c018d2bab739ccfb2`.
Código runtime: `a2790bf74d7b76ed0f97bc3eb471af2728ccbf70`; los commits posteriores
solo afectan verificación/documentación. Perfil **dev/debug**, ARM64, bundle 15,
firma Apple Development existente: no es una release optimizada ni notarizada.

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

Los checkpoints siguientes conservan resultados intermedios con su binario.
La matriz final usa PASS, PARTIAL, FAIL, BLOCKED o NOT_EVALUATED;
pruebas de contratos no sustituyen captura o medios decodificados.

- A: baseline remoto verificado y worktree aislado; auditoría inicial registrada.
- B–J: ejecución acotada cerrada; los límites no cerrados permanecen explícitos.

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

### Regresiones multimedia B4 y recuperación observada

H8 (`h8-lifecycle.json`) PASS: 12 cancelaciones repetidas contra peer silencioso,
timeout nativo, handshake retrasado, admisión cerrada durante shutdown, salida
y reapertura real. El harness reabre intencionalmente otra instancia; se reconoce
su PID exacto en el recibo y se cierra normalmente antes del siguiente caso.
La primera continuación que encontró ese socket se detuvo sin tocarlo.

`h13-video-1794979118207778000/report.json` PASS: 720p60 vertical, v5 guardado/
cargado, texto/PNG/círculo, Cut/Fade y tono decodificados; 643 frames renderizados,
0 lagged y 0 video_skipped. CPU mediana 60,0% de un núcleo; RSS pico 212,39 MiB.

`h15-regressions-b4/capture-loss-media/report.json` FAIL de recuperación. La
ventana controlada captura inicialmente; su cierre produce SOURCE_UNAVAILABLE
y termina ambos destinos por sus barreras normales. Seleccionar explícitamente
la ventana nueva falla en creación de SCStream: OBS informa error con
localizedFailureReason null; no hay diagnóstico del stream porque create falló.
La fuente queda CAPTURE_NOT_READY (0×0), sin fingir señal ni reintentar
indefinidamente. No se atribuye esa causa opaca a Stage Manager. Owner cierra
normalmente; los medios previos al cierre y todos los estados se conservan.

### E — tres ciclos acotados de decodificadores B4

`h15-regressions-b4/memory-measurement`: 3 ciclos de cuatro videos propios a
1080p30, visibles/ocultos/pausados (20 s cada fase), retirados (60 s), una sola
instancia silenciosa por video; vuelve a cero fuentes tras retirar y cleanup
sin errores. Malloc in-use mediano: 85,58 MiB baseline → 87,41 / 87,48 / 87,47
MiB tras retirar. Malloc allocated: 162,16 → 694,14 / 786,14 / 806,14 MiB.
Footprint mediano final 720,22 MiB vs 375,08 baseline; RSS final 890,05 MiB.
Son métricas diferentes. La reserva retenida no prueba una fuga y no existe
evidencia de stacks/ownership que la descarte por completo.

Ninguna fase excede 1536 MiB ni p95 de colección nativa 2000 µs; sí exceden el
presupuesto RPC de 20 ms tres fases (p95 54,36 / 28,91 / 38,32 ms). Por eso
memoria/rendimiento permanecen PARTIAL aunque el ensayo idle haya mejorado.
El análisis conserva counters, CPU por fase, memoria comprimida, recursos y
diferencias con el baseline en `memory-analysis.json`.

### E — dual 1080p60 durante 120 segundos (B4)

`h15-dual-short-b4-measurement` y `h15-dual-short-b4-analysis`: cuatro videos
propios, dos outputs VideoToolbox sin reordering, tono y preview. CPU mediana
83,22% de un núcleo, footprint máximo 1239,36 MiB; p95 RPC 17,11 ms. Intervalo
medido: 7199 rendered, 0 lagged, 0 skipped, 0 dropped por destino, 28 descartes
de preview. Cleanup sin errores. No sustituye el soak de 30 minutos de H14.

Decodificación completa: 7240 frames MKV y 7218 RTMP; todos sus PTS/DTS y PCM
se revisan. Gates de cadencia, AAC, tono, clipping y cambio de contenido PASS
con los mismos umbrales del analizador H14. La mayor racha sin cambio significativo
es ~0,600 s en un cuadrante; **no se presenta como cero pausas** ni como una
fuga/fallo demostrado. Se conserva cada framemd5 y CSV. La clasificación general
sigue PARTIAL: full delivery y sincronía A/V no se infieren de esos gates.

### B — contraste final B4

`h15-focus-capture-b4-default/analysis/analysis.json`: FAIL de píxeles en ambos
destinos, con foco VERIFIED y 1339/1331 frames decodificados. Se conserva el
congelamiento de ~15,4 s. El aviso CAPTURE_SUSPENDED aparece en 29 observaciones
mientras ambos outputs permanecen activos: funciona la mitigación de estado,
no la entrega de frames. `h15-focus-capture-b4-join-all/analysis/analysis.json`:
PASS de frescura en las tres fases, 1342/1334 frames, foco VERIFIED. Cleanup sin
errores en ambos ensayos. No certifica ventanas ajenas ni cambia el FAIL default.
Los medios retenidos de pérdida de ventana también decodifican completos
(329/325 frames H.264 y 515/509 frames AAC); eso no repara la recreación fallida
de SCStream (`capture-loss-media/retained-media-decode.json`).

### F/G — guardado, MATCHDAY, recorrido real y reapertura B4

Se usó Product Design audit con CUA exclusivamente sobre la app nativa; ningún
navegador. El [recorrido nativo](h15-native-ux-verification.md) contiene las siete
capturas reales, pasos, hallazgos y límites. MATCHDAY se instaló mediante revisión
y confirmación GPUI: 73/73 pasos, cuatro escenas, doce fuentes, veintitrés capas.
El primer clic AX de Guardar fuera del viewport no produjo recibo; se conserva
como intento sin resultado. Tras scroll del diálogo y clic visible, GPUI muestra
«Configuración guardada · recibo 1 · revisión 92». Los 7241 bytes durables tienen
SHA-256 `812e7ffbc3f4255216ce6aa43defe0ecdf29299bad0eb28ff0282280885cd84b`.
No se atribuye el intento inicial a una pérdida de escritura.

`h15-show-save-b4-02/report.json` PASS: hash/recibo GPUI coincidente, mutación CLI
invalida la revisión anterior, rechazo sin cambiar bytes, IDs rotos rechazados
antes de mutar, restauración desarmada en nueva sesión, guard de sesión obsoleta,
activación y nuevo guardado explícitos. El primer verificador queda preservado:
intentó configurar por una herramienta MCP inexistente; el caso corregido usa
CLI, sin ampliar permisos de MCP. Error de escritura durable está cubierto por
test de contrato con preservación de bytes, no por provocar un fallo del disco real.

`h15-show-control-b4/report.json` PARTIAL: clic real GPUI de gol observado durante
MKV + RTMP; job completo de dos acciones, cooldown/deduplicación, cancelación
posterior al tick, cancelación Show Control, concurrencia MCP/CLI y desconexión
MCP pasan. Cancelación anterior al primer tick NOT_OBSERVED; concurrencia GPUI
NOT_EVALUATED. No se amplía la animación stock de 450 ms para certificarla.
Decodificación completa PASS: MKV 1936 frames, RTMP 1929, gap máximo 34 ms,
PCM sin clipping. Las hojas 01–02 de ambos medios muestran entrada, permanencia
y desaparición del banner; no prueban cada frame, geometría estricta, A/V ni
entrega completa de cola. El marcador visible permanece 0:0 en esas hojas;
el recibo de contador interno no se presenta como cambio visual del marcador.

GPUI selecciona 720p y muestra el preflight válido. Después CUA devuelve
`cgWindowNotFound`, aunque PID 8439 sigue vivo. Rebinding y reapertura normal
(PID nuevo 9922) no recuperan el acceso. Se detiene ese recorrido, sin inyectar
eventos por otra tecnología. `reopen-core-report.json` PASS del núcleo: proyecto
de cinco escenas cargado, Show Control desarmado/sin jobs, bindings válidos y
activación explícita. El diálogo nativo de restauración queda BLOCKED.

### H — bundle y fuentes correspondientes

`h15-build/b4-portable-audit.json` static PASS y tool smoke PASS con entorno limpio:
ARM64, dependencias/plugins incorporados, rpaths relativos, helpers, herramientas,
licencias y firma. Las ejecuciones físicas salen del checkout y usan las rutas
portables reales; no se usa un HOME ficticio ni se importan credenciales nuevas.
Proyecto v1–v5 cubierto por contratos; v5 también por guardado/carga real B4.
Los stores y referencias opacas no se incluyen en overlays ni payloads de video.

`/Users/luisfarfan/Developer/motive-h15-portable/source-candidate-b4/manifest.json`:
material PASS y notices PASS, 25 archivos nativos y 463 paquetes Rust,
sin fuentes bloqueadas ni gitlinks pendientes de materializar. Gate general
PARTIAL: queda reconstrucción fuente→binario y revisión de distribución. No se
emite ZIP/DMG, no se firma con una identidad nueva y no se intenta notarizar.

## Matriz final de aceptación — B4

Rutas cortas relativas a `var/evidence/` de este worktree. El índice local
`h15-final/evidence-index.json` fija hashes de informes, logs, capturas y binario;
los informes de cada sesión fijan además los hashes de sus medios completos.
`h15-final/acceptance.json` conserva la misma decisión en formato estructurado.

| Gate | Estado | Evidencia y límite |
|---|---|---|
| Tests Rust raíz / Show Control | PASS | 119 / 129, `h15-build/*tests.log`; mismo código runtime B4. |
| Clippy / rustfmt | PASS | Raíz all-targets y crate Show Control; logs de build. |
| Instrumentos Python | PASS | 123 tests; chequeos de foco, AVCC exacto y alineación de audio. |
| Compatibilidad proyectos | PASS | Contratos v1–v5; v5 con carga/guardado real, `h13-video-1794979118207778000`. |
| CLI/MCP, owner único y transporte | PASS | `h15-regressions-b4/control-integration.json`, `h9-control-delivery.json`. |
| Video configurable | PASS | 720p60 vertical, texto/PNG/shape/Cut/Fade, video H13 B4; 720p GPUI. |
| Perfiles sin reordering | PASS | Rechazo conservador de true, sin cambiar silenciosamente perfiles guardados; `h15-output-policy.json`. |
| MKV, RTMP local, dual VT/x264 | PARTIAL | Medios utilizables y funcionales; colas no entregadas siguen explícitas en matriz. |
| Stop independiente / cancel / cierre | PARTIAL | Funcional PASS; finalización no prueba full delivery. H8 lifecycle PASS. |
| Receptor perdido intencionalmente | PARTIAL | Clasificación propia, archivo parcial; no confundir con fallo espontáneo. |
| Captura default con foco corroborado | FAIL | Contador congelado ~15,4 s en MKV y RTMP. |
| Captura fixture join-all | PASS | Solo esa condición controlada; no cierre general de captura. |
| Pérdida/reconexión de ventana | FAIL | Termina salidas de forma segura; creación del SCStream sustituto falla. |
| Audio de aplicación y continuidad | FAIL | Caída interior de 997 Hz; fallo histórico de identidad no reproducido ni reparado. |
| Mezcla, mute/gain, pausa/silencio | PASS | Etapas dedicadas B4 y PCM; no subsana el gate estricto de continuidad. |
| Pérdida/recuperación explícita audio | PASS | Etapa recovery con identidad propia; no demuestra recuperación de todo fallo SCK. |
| Micrófono real y convivencia mic/app | BLOCKED | Supervisión requerida; el PASS H14 no certifica B4. |
| Cámara / USB / permisos / sleep-wake | BLOCKED | Requiere persona y hardware autorizado; sin capturas reales desatendidas. |
| Guardado Show Control durable y stale | PASS | Recibo GPUI + bytes, guards e IDs, `h15-show-save-b4-02`. |
| Restaurar desarmado y activar | PASS | Núcleo en proceso nuevo; diálogo GPUI de reapertura bloqueado por CUA. |
| MATCHDAY y Show Control real | PARTIAL | Instalación/clic/medios reales; carrera antes del tick y concurrencia GPUI sin cerrar. |
| UX funcional / accesibilidad | PARTIAL | Siete capturas; feedback mejora. Scroll/AX, teclado/VoiceOver y parte del recorrido pendientes. |
| RPC idle | PASS | p95 12,047 ms vs 45,518 ms B1; no garantía bajo carga. |
| Memoria y RPC bajo carga | PARTIAL | Reservas retenidas, tres fases >20 ms; no fuga demostrada ni descartada. |
| Dual 1080p60, 120 s | PARTIAL | Decode/PCM/cadencia PASS, cero skips en intervalo; pausa ~0,600 s y A/V/entrega no cerrados. |
| Nuevo soak B4 de 30 min | NOT_EVALUATED | Sin repetir indefinidamente el soak H14. |
| Bundle portable local | PASS | Auditoría estática, firma local, tool smoke y ejecución fuera del checkout. |
| Fuentes y distribución | PARTIAL | Material/notices disponibles; reconstrucción, Developer ID/notaría/otra Mac pendientes. |
| Segunda Mac ARM64 | BLOCKED | Procedimiento abajo, no acceso físico autorizado en esta sesión. |
| Nueva prueba RTMPS | NOT_EVALUATED | Requiere autorización específica; no hereda aceptación B2. |
| Voz opcional en vivo | NOT_EVALUATED | P0 abiertos; sin modelos descargados, micrófono paralelo ni promesa de voz live. |
| Limpieza y restauración | PASS | Owners cerrados normalmente, stores originales restaurados por hash, lock liberado. |

## Pendientes concretos

1. **Captura P0:** reproducir la suspensión default con los mismos marcadores,
   conservar el contraste join-all y estudiar publicación/visibilidad de ventanas
   con APIs soportadas. No imponer flags a aplicaciones ajenas. Investigar por
   separado el fallo de creación de SCStream tras selección explícita; capturar
   dominio/código completos si OBS los expone. No ocultarlo con reconexión infinita.
2. **Audio P0:** conservar el tramo 2,70–2,80 s y su reloj acotado. La siguiente
   instrumentación debe relacionar paquetes SCK, timestamps y discontinuidades
   antes del mixer. No basta repetir tone_resumed, que pasó B4; no cambiar umbrales.
3. **Outputs:** conservar perfil false y las colas pre-stop históricas. La
   restricción del modo inseguro no demuestra una corrección del cutoff oficial.
   Cualquier cambio de OBS/H8 requiere una prueba nueva de identidad/delivery.
4. **Persona, cámara/mic/USB:** adquirir lock, abrir B4 con preview controlado,
   elegir dispositivo autorizado, comprobar video y tono por altavoz controlado
   al micrófono, mezclar con aplicación de fixture, mute/gain, MKV+RTMP local.
   Desconectar/reconectar el dispositivo, observar causa y recuperación explícita,
   decodificar ambos medios; no capturar conversaciones privadas.
5. **Persona, permisos y sleep/wake:** en una cuenta/Mac de prueba, probar negar
   y conceder permisos mediante UI normal de macOS; nunca resetear TCC global.
   Comprobar ausencia de falsa señal lista y recuperación explícita. Probar reposo
   con outputs detenidos y en una sesión local autorizada, separar ambos resultados.
6. **Persona, UX:** recuperar acceso nativo tras el fallo CUA; recorrer Añadir
   fuente/Audio, grabar/transmitir/detener, Biblioteca y restaurar desde GPUI.
   Tab/Shift-Tab/Enter/Escape y atajos dentro de Live Deck, VoiceOver para labels,
   foco, disabled y recibos. Capturar una edición GPUI concurrente con animación
   stock450 sin falsear origen ni sustituirla por una animación más larga.
7. **Segunda Mac ARM64 macOS 15+:** transferir localmente app+fuentes bajo revisión,
   verificar hashes/firma/arquitectura; lanzar fuera del checkout sin `.deps` ni
   DYLD de desarrollo, importar un medio propio con tools embebidas, guardar/cargar
   proyecto y Show Control, grabar+RTMP local, cerrar/reabrir y revisar rutas.
   Permisos mediante UI normal. Registrar OS/hardware/logs y archivos decodificados.
8. **Distribución:** revisión de licencias/fuentes y reconstrucción verificable;
   Developer ID, notarización y distribución requieren credenciales/autorización
   específicas. Ningún artefacto se ha publicado.

## Cierre de la sesión local

`h15-native-ui-b4/store-restoration.json` verifica por hash project.json,
audio-mixer.json y show-control/configuration.json originales; output-profiles.json
vuelve a su ausencia original. Las versiones de prueba se retienen como evidencia
privada. El journal no se rebobina ni borra. No se tocan Keychain, TCC, preferencias
globales ni `element-lab/`. El lock canónico se libera con owner exacto y sin
procesos propios activos (`h15-build/physical-lock-release.json`).

La candidata mejora guardado/feedback, admisión de perfiles y respuesta del control;
**no cumple aún la aceptación privada solicitada**. Los FAIL restantes tienen
medios y evidencia conservados, sin reinterpretar los resultados H14 como PASS B4.
