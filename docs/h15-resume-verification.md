# H15 — reanudación y candidata B6

Continuación solicitada por el propietario después del primer cierre B4.
La evidencia anterior permanece intacta. Directorio de esta sesión:
`var/evidence/h15-resume-01/`. Misma rama y lock físico canónico; sin push,
publicación, RTMPS nuevo, cámara ni micrófono reales.

**Cierre B6: NOT_ACCEPTED para beta privada.** Se corrige la caída de mezcla
reproducida en B4 y se recupera el recorrido nativo, con medios reales y recibos
durables. La suspensión/recuperación de ventanas sigue abierta; tampoco se
declara corregido el fallo histórico de identidad `APPLICATION_UNAVAILABLE`.

Candidata local: `/Users/luisfarfan/Developer/motive-h15-portable/b6/Motive.app`.
Ejecutable SHA-256:
`fe58dc5ca406eb0427d40c5b5a47473aad5d251a75f9d87e170eae9b51cd7d47`.
Código runtime: `08004138d1f3586e133f78175d8a1528c5fb7b06`. Los cambios posteriores
son de instrumentos e informes; no cambian el binario ensayado. Perfil dev/debug,
ARM64, bundle 15, firma Apple Development existente; no es una release notarizada.

## Recuperación del acceso nativo

Reiniciar la sesión de CUA recuperó la observación de Motive. No se cambiaron
permisos, TCC ni ajustes del sistema. Recorrido real sobre B4, PID 33339 y
reapertura PID 35264, ambos cerrados normalmente desde GPUI:

| Acción nativa | Resultado y evidencia |
|---|---|
| Añadir tono | PASS, `02-tone-added.png`; el alta se hizo por clic, no por MCP. |
| Ganancia por teclado | PASS, `03-gain-keyboard.png`; flechas avanzan 1 dB, termina en −12 dB. |
| Seleccionar ventana propia | PASS, `05-owned-window-selected.png`; tras scroll hasta la fila visible. `04` conserva el intento sin efecto. |
| Iniciar grabación y RTMP local | PASS funcional, `06-ui-dual-start.png`; los dos botones se pulsaron realmente. |
| Silenciar | PASS, `07-ui-muted.png` y `muted-state.json`; entrada sigue midiendo, master queda en silencio. |
| Detener independientemente | PASS funcional, confirmaciones reales; `08` es el diálogo, `09` y `stopped-state.json` son el estado terminal. |
| Biblioteca y Finder | PASS, `10-recording-library.png` y AX `11-finder-selected.ax.txt`; selecciona el archivo recién grabado. |
| MATCHDAY, proyecto y reglas | PASS, instalación 73/73 y guardados visibles, `12-save-before-reopen.png`. |
| Salir grabando | PASS funcional, `14-native-quit-confirmation.png`; confirmación, barrera normal, proceso y socket finalizados. |
| Restaurar proyecto | PASS, `16-project-restore-result.png`; `15` es solo la confirmación. La ventana original aún viva vuelve a capturarse. |
| Restaurar reglas desarmadas | PASS, `18-restored-live-deck.png` y `ui-restored-disarmed.json`: sin jobs, bindings actuales, armado false. |
| Armado explícito y Escape | PASS, `19-explicit-ui-arm.png`; después Escape cierra el panel y Cmd-Q termina la aplicación. |

Los dos primeros medios nativos decodifican completos: 1945 frames MKV y
1473 RTMP, sin clipping. Duraciones distintas intencionalmente por inicio y
stop independientes; `ui-media-report.json`. Esto no prueba entrega de toda
la cola de paquetes ni sincronía A/V. VoiceOver y navegación completa con Tab
siguen pendientes.

La carrera stock450 sigue PARTIAL: el cambio real de ganancia llegó 552,8 ms
después de observar la operación, fuera de los 450 ms. No se amplió la
animación. El job quedó `needs_reconciliation`, cursor 0, sin incrementar
goles ni repetir la acción durante otros 8 s (`ui-stock450-race/report.json`).
No se convierte ese resultado en cobertura de la carrera mientras está running.

## Correcciones posteriores

- Mixer: sus controles leen el estado actual y no usan el borrador `Forms`.
  Una revisión de salud nativa después de añadir tono mostraba un aviso stale
  que pedía reabrir. Se excluye solo el mixer de ese aviso; se conservan los
  guards de revisión de formularios reales.
- Captura: `obs_source_create_private` conserva un objeto cuando falla el
  callback de creación. Se comprueba `obs_obj_invalid`, igual que ya hacía
  el mixer, y se devuelve `SOURCE_CREATE_FAILED` en lugar de admitir una
  fuente que nunca tendrá frames. El parche diagnóstico registra código de
  error, pertenencia a SCStreamErrorDomain, ventana y PID propio; nunca
  localizedDescription, userInfo ni contenido de otras aplicaciones.
- Audio: se contrasta el búfer dinámico anterior con seis bloques de 1024
  muestras, 128 ms a 48 kHz, mediante `obs_reset_audio2`. No se cambia OBS,
  el mixer, los PTS de origen ni la barrera H8. El margen se reserva al
  iniciar el núcleo, sin reconstruir el mixer durante una producción.

## Localización de la caída de audio

El PCM B4 anterior (`motive-1794978609141673.mkv`) se revisó con ajustes
simultáneos de seno/coseno de 997 y 440 Hz en ventanas contiguas de 5 ms.
En 2,735–2,750 s la amplitud 997 cae a 0,00002–0,00008 mientras 440 permanece
aproximadamente 0,0316. No es solo cancelación de fase de una proyección larga.
`pcm-joint-fit-b4.json` conserva los valores; el FAIL original sigue intacto.

La repetición B4 con el diagnóstico existente `MOTIVE_TEST_AUDIO_TRACE=1`
localizó un bloque de mezcla de 1024 muestras con RMS 0,02225 mientras la
entrada de aplicación continuaba con paquetes de 960 muestras, RMS 0,0446
y PTS continuos. Sus callbacks llegaron hasta 48,24 ms después del PTS;
OBS había crecido únicamente a 42 ms. Esto sustenta contrastar un margen
de mezcla, sin atribuir la caída al encoder o a la pérdida de identidad.
`audio-trace-b4/low-mix-review.json` conserva el contexto. Esta repetición
no obtiene veredicto alineado: su consulta de reloj tardó 83 ms, sobre el
límite de 50 ms. No se relajó ese límite.

El instrumento ahora conserva todas sus consultas iniciales de reloj y
solo acepta una dentro de los 50 ms durante su presupuesto ya acotado.
No ajusta el reloj a los bordes del tono, no omite muestras y conserva la
comprobación de todos los frames y del primer paquete AAC.

Primer contraste B6 con trazas: continuidad PASS en tono/reanudación/cola,
mínimos 0,03132 / 0,03126 / 0,03145, referencia 0,03159; mismas ventanas de
100 ms, guardas de 200 ms y umbral 65 %. Consulta de reloj 17,22 ms.
Los 319 bloques interiores de mezcla mantienen RMS ≥0,03118, sin pérdidas
de registros de diagnóstico. `audio-trace-b6/` y
`h13-system-audio-1795015662469007000/report.json`.

Sin trazas, las seis etapas pilot/RTMP/recovery/transitions/persistence/silence
pasan: `audio-production-b6/` y
`h13-system-audio-1795015727218037000/report.json`. La continuidad conserva
mínimos 0,03143 / 0,03145 / 0,03145, referencia 0,03160. Hay pérdida/reinicio
controlado de la aplicación y recuperación explícita, sin sustituir identidad.
El fallo histórico `APPLICATION_UNAVAILABLE` es distinto: no se ha reproducido
ni se declara reparado por este cambio.

La etapa A/V B6 captura la ventana y el audio de la misma fixture, incluyendo
pausa, ceros, reanudación y pulsos. PASS en 1026 frames decodificados y toda la
continuidad 997 Hz. Los siete pulsos medidos arrojan audio−video −36,875 ms,
sin deriva observada; incluye latencia de la fixture/dispositivo, no afirma
latencia cero. `av-b6/` y `h13-system-audio-1795015870184192000/report.json`.

## Regresiones de captura y outputs

B5 (`729ec07b…a2186`) recrea la ventana y obtiene buffers, pero esa prueba
original no vuelve a grabar después de recuperar. No prueba recuperación de
píxeles finales ni explica el fallo intermitente de creación anterior.

El verificador se amplió con `--record-recovery`, conservando el recorrido
original y los dos pares de medios cuando es posible. En B6 la sustituta
también crea un stream y publica frames, pero se suspende entre el snapshot
y el nuevo start. Motive devuelve `CAPTURE_SUSPENDED`; no arranca una salida
insegura ni finge el segundo par. `capture-b6-media/report.json` conserva FAIL
y `review.json` distingue el rechazo correcto del problema de disponibilidad.
El límite de captura sigue abierto.

Matriz B6: nueve casos funcionales PASS y 14 medios decodificados con cadencia,
AAC continuo y sin clipping. Incluye VT/x264 × MKV/RTMP/dual, stop independiente,
cancelación, shutdown y receptor perdido. Todos conservan aceptación PARTIAL
de entrega; la pérdida deliberada tiene clasificación propia. Los 14 paquetes
trazados ausentes de paradas normales son posteriores al bracket de stop;
otros tres corresponden al receptor terminado deliberadamente. No se observó
ausencia anterior a stop en esta matriz; no invalida los FAIL históricos H14.
`output-matrix-b6/report.json` y `media-review.json` conservan cada relación.
No se cambió `stop_ts`, el interleaver, los plugins de outputs ni H8.

## Foco, rendimiento y video B6

`focus-b6-default/report.json` conserva BLOCKED: aunque se obtuvieron los tres
marcadores, durante la fase inicial Motive volvió a estar al frente. El observador
independiente y la fixture coincidieron; no se acepta una fase incompleta. Los
1340/1331 frames decodificados y el contador avanzan, pero el análisis general
sigue INCONCLUSIVE porque no cubre el foco exigido. El contraste join-all
(`focus-b6-join-all/report.json`) termina HUMAN_ACTION_REQUIRED tras dos peticiones
no corroboradas. Se conservaron ambos medios y se cerraron todos los procesos.
Estos resultados no borran el congelamiento default B4 de unos 15,4 s con foco
válido ni convierten el PASS join-all B4 en aceptación general de captura B6.

`dual-short-b6-measurement/` ejecuta 120 s a 1080p60 con cuatro videos propios,
tono, preview y MKV/RTMP. Footprint pico 1117,95 MiB; CPU mediana 83,16 % de un
núcleo, p95 85,81 %. El RPC p95 bajo carga es 17,51 ms; ninguna fase supera
20 ms, 1536 MiB o 2000 µs de colección nativa. Cero video skips, render lagged
y drops de outputs en el intervalo; 11 descartes de preview. Los 5 s de fase
released no prueban ausencia de fuga ni sustituyen los tres ciclos B4.

Los 7265/7230 frames MKV/RTMP pasan decode, cadencia, píxeles y PCM con los
umbrales anteriores. La mayor racha sin cambio significativo es 0,467/0,517 s;
no se afirma ausencia de pausas. `dual-short-b6-analysis/analysis.json` mantiene
PARTIAL por entrega completa y A/V no evaluadas en ese ensayo. No se repitió
un soak B6 de 30 minutos. La prueba A/V separada de arriba conserva su alcance.

`video-b6/` y `../h13-video-1795016547512593000/report.json` pasan 720p60 vertical,
overlays reales, Cut/Fade y persistencia v5; 658 rendered, cero lagged/skipped.
El RPC idle de 100 consultas pasa: mediana 3,310 ms, p95 12,919 ms y máximo
37,552 ms (`control-latency-b6.json`). El instrumento usa destino exclusivo
para conservar intacto el informe histórico B4.

## Show Control e interfaz del binario final

`native-b6/show-control/report.json` conserva PARTIAL, con clic GPUI real durante
MKV/RTMP, cooldown/deduplicación, concurrencia MCP/CLI, cancelación posterior
al tick y desconexión MCP observados. Sus medios decodifican completos: 2103 y
2094 frames, gap máximo 34 ms, PCM sin clipping. Las hojas `recording-review-02`
y `loopback-review-02` muestran entrada, permanencia y salida de GOOOAL; no
prueban geometría de cada frame, A/V o entrega completa. El marcador visible
0:0 no se confunde con el contador interno de reglas.

Un job de esa sesión quedó `needs_reconciliation`. Restaurar respondió
SHOW_CONTROL_BUSY; reconciliar observó el resultado nativo sin replay ni cambio
de contador, pero no habilitó la carga en esa sesión. Se conservaron los intentos
en `native-b6/mcp-save-restore-02.json` y `explicit-reconcile-restore.json`.
Tras dos intentos se cerró normalmente y se abrió otro proceso. No se borraron
jobs ni se rebobinó el journal para simular recuperación.

En el proceso nuevo, PID 48768, restaurar proyecto y reglas mediante sus
confirmaciones nativas dejó reglas desarmadas, bindings actuales y ningún job
(`ui-restored-disarmed.json`). Guardar desde GPUI generó recibo 1; activar fue
otra acción explícita. `show-save/report.json` verifica hash/bytes, guard stale,
IDs rotos, sesión nueva desarmada y guard de sesión. El guardado final nativo,
con REC activo, produjo **recibo 2, revisión 42**, 7241 bytes durables, SHA-256
`812e7ffbc3f4255216ce6aa43defe0ecdf29299bad0eb28ff0282280885cd84b`, cotejado antes
de restaurar los stores originales (`ui-save-final-receipt.json`).

Al principio CUA solo entregó miniaturas 179×155 que no permitían leer el panel;
se conservaron sin atribuirles un PASS visual. Posteriormente se obtuvieron
capturas reales 1440×980. `07-mixer-external-revision-no-stale.png` verifica la
corrección: mixer abierto, cambio CLI de ganancia de 0 a −1 dB, revisión 42 y
sin aviso stale. `08-durable-save-receipt.png` muestra el recibo final. No se
cambiaron permisos ni se usó inyección de eventos por otra tecnología.

La segunda carrera real stock450 también queda NOT_OBSERVED: la ganancia GPUI
cambió cuando la operación ya había terminado. El job completó sus dos pasos;
no acredita una edición durante running. Se conservan ambos intentos acotados
B4/B6 sin alargar la animación ni repetir indefinidamente. La cancelación antes
del primer tick y la navegación completa con VoiceOver siguen pendientes.

Cmd-Q abrió la confirmación con REC activo; **Finalizar y salir** terminó el
owner 48768 normalmente. El último MKV conserva 9762 frames, 325,367 s hasta
el último PTS, gap máximo 34 ms y cero muestras con clipping. Decode completo
PASS en `native-b6/final-recording-review/report.json`; no es una prueba de toda
la cola de paquetes. El socket real `run/motive.sock` y los procesos estaban
ausentes antes de restaurar los stores. La primera observación auxiliar de
cierre consultó por error `control.sock`; no se usa como prueba del socket real.

## Bundle, fuentes y checks

`portable-b6.json` pasa auditoría estática y smoke de ffmpeg/ffprobe embebidos:
arquitectura, rpaths, frameworks/plugins, helpers, licencias y firma. Ese informe
estático mantiene runtime NOT_EVALUATED; los ensayos anteriores son la evidencia
de ejecución efectiva fuera del checkout, con las rutas reales de macOS.

`/Users/luisfarfan/Developer/motive-h15-portable/source-candidate-b6/manifest.json`
conserva material y notices PASS: 25 archivos nativos y 463 paquetes Rust, sin
fuentes bloqueadas ni submódulos pendientes. Identifica el commit runtime y los
hashes de cada archivo capturado; no incluye las últimas ampliaciones de este
informe. Su gate global es PARTIAL: reconstrucción verificable, revisión de
distribución y segunda Mac pendientes. No se publicó ZIP, DMG ni release.

Los logs de esta reanudación verifican 119 tests raíz, 129 Show Control y 123
Python, Clippy all-targets con warnings como errores y rustfmt de ambos crates.
No se heredan como PASS B6 todos los runners H1–H12 ejecutados con B4; abajo se
delimita la cobertura fresca del binario final.

## Matriz unificada B6

Rutas relativas a `var/evidence/h15-resume-01/`, salvo prefijo `../`.
`final/acceptance.json` conserva esta decisión; `final/evidence-index.json` fija
hashes de evidencia, instrumentos, informes y binario. Los informes originales
B4/H14 y sus índices permanecen intactos.

| Gate | Estado | Evidencia y límite |
|---|---|---|
| Tests Rust raíz / Show Control | PASS | 119 / 129; `rust-tests.log`, `show-tests.log`. |
| Clippy / rustfmt | PASS | Ambos crates; `clippy.log`, `show-clippy.log`, `final/offline-checks.json`. |
| Instrumentos Python | PASS | 123; `all-python-tests.log`; captura adicional ejercitada sin ocultar su FAIL. |
| Proyectos v1–v5 | PASS | Contratos y v5 real en `../h13-video-1795016547512593000/`. |
| Regresiones existentes completas | PARTIAL | B6 repite video, audio, outputs y Show Control; H1–H12 completos conservan identidad B4. |
| CLI/MCP y owner único | PASS | Estado compartido, edición concurrente y desconexión en `native-b6/show-control/`. |
| Video configurable | PASS | 720p60 vertical, overlays, Cut/Fade y persistencia. |
| Reordering conservador | PASS | `native-b6/h15-output-policy.json`: rechazo sin nuevo attempt ni normalización silenciosa. |
| MKV, RTMP local, dual VT/x264 | PARTIAL | Nueve casos funcionales y 14 medios PASS; entrega completa no aceptada. |
| Stop independiente / cancel / shutdown | PARTIAL | Funcional PASS, medios usables; colas retenidas explícitas. |
| Pérdida deliberada del receptor | PARTIAL | Clasificación separada y medios parciales, `output-matrix-b6/`. |
| Captura default con foco válido | BLOCKED | Fase inicial B6 incompleta; FAIL histórico B4 sigue sin cierre. |
| Captura join-all B6 | BLOCKED | HUMAN_ACTION_REQUIRED tras dos peticiones no corroboradas. |
| Pérdida / recuperación de ventana | FAIL | Buffer inicial recuperado, luego CAPTURE_SUSPENDED al iniciar; `capture-b6-media/`. |
| Audio aplicación: continuidad estricta | PASS | Tono/pausa/ceros/reanudación y A/V; `audio-production-b6/`, `av-b6/`. |
| Identidad APPLICATION_UNAVAILABLE histórica | PARTIAL | No reproducida ni declarada reparada; es distinta de la caída de mezcla corregida. |
| Mezcla / mute / gain | PASS | Seis etapas audio y controles nativos con PCM. |
| Pérdida y recuperación explícita audio | PASS | Reinicio de fixture, identidad autorizada y persistencia, `audio-production-b6/`. |
| Sincronía A/V controlada | PASS | Siete pulsos, −36,875 ms sin deriva observada; no certifica todas las fuentes. |
| Micrófono y convivencia mic/app | BLOCKED | Requiere supervisión; no se hereda el resultado de H14. |
| Cámara / USB / permisos / sleep-wake | BLOCKED | Hardware y acciones normales de macOS con persona. |
| Guardado durable / stale / IDs | PASS | GPUI, recibo, bytes y guards; `native-b6/show-save/`, `ui-save-final-receipt.json`. |
| Reapertura / restaurar desarmado / activar | PASS | Recorrido GPUI real en PID nuevo, sin jobs ni replay. |
| MATCHDAY y Show Control real | PARTIAL | Clic y animación visibles; carreras de 450 ms y pre-tick sin observar. |
| Reconciliar y cargar en la misma sesión | PARTIAL | Resultado observado sin replay, carga siguió BUSY; reapertura explícita pasa. |
| UX / accesibilidad | PARTIAL | Mixer y recibos visibles, cierre/restauración reales; VoiceOver y recorrido íntegro de teclado pendientes. |
| RPC idle | PASS | 100 consultas, p95 12,919 ms. |
| Presupuestos medidos bajo carga | PASS | 120 s; p95 RPC 17,51 ms, footprint 1117,95 MiB, colección <2000 µs. |
| Memoria prolongada / ausencia de fuga | PARTIAL | Sin stacks/ownership concluyentes; no inferir fuga o ausencia de reserva retenida. |
| Dual 1080p60 de 120 s | PARTIAL | Decode/cadencia/PCM PASS; racha visual hasta 0,517 s, full delivery y A/V separados. |
| Nuevo soak B6 de 30 min | NOT_EVALUATED | No se repite el ensayo largo sin nueva hipótesis. |
| Portable local firmado | PASS | Auditoría/tool smoke y ejecución real fuera del checkout. |
| Fuentes y distribución | PARTIAL | Material/notices PASS; reconstrucción y distribución pendientes. |
| Segunda Mac ARM64 | BLOCKED | Procedimiento supervisado abajo. |
| Nuevo RTMPS | NOT_EVALUATED | Sin nueva autorización específica; no se hereda la aceptación B2. |
| Voz opcional en vivo | NOT_EVALUATED | P0 abiertos; sin modelos ni captura paralela. |
| Limpieza / stores / lock | PASS | Hashes originales, journals intactos, cierre normal y lock liberado. |

## Trabajo pendiente concreto

1. **Captura P0:** una persona debe mantener el foco fixture→Motive→fixture
   durante cada fase completa del protocolo, mientras el observador independiente
   registra PID/ventana/timestamp. Repetir default y join-all, decodificar ambos
   destinos y conservar cualquier congelamiento. No basta marcar un instante de
   foco. Investigar la suspensión de la ventana recreada antes de admitirla, sin
   imponer flags a otras aplicaciones ni cambiar Stage Manager/TCC.
2. **Audio histórico:** instrumentar el disparador exacto de
   APPLICATION_UNAVAILABLE si reaparece. La reserva de 128 ms cubre el jitter
   observado de mezcla, no una pérdida de identidad o permiso. Mantener los mismos
   umbrales y la recuperación explícita.
3. **Entrega y sesiones largas:** conservar reordering=false, el cutoff y los
   paquetes ausentes antes de stop de H14. Cambiar OBS/H8 solo con una hipótesis
   reproducida. Perfilar ownership/asignaciones antes de atribuir reservas a fugas.
4. **Persona, hardware:** con lock y B6, elegir cámara/mic autorizados, usar tono
   controlado sin conversaciones privadas, mezclar con fixture, mute/gain, MKV y
   RTMP local. Desconectar/reconectar USB, observar causa, recuperar explícitamente
   y decodificar. Permisos y sleep/wake se prueban en una cuenta/Mac de prueba,
   mediante UI normal, sin reset global de TCC.
5. **Persona, UX:** recorrer Tab/Shift-Tab/Enter/Escape y atajos de Live Deck con
   VoiceOver; comprobar labels, foco, disabled, errores y recibos. Observar una
   edición real durante los 450 ms originales y la cancelación anterior al tick;
   no sustituirlas por duraciones ampliadas. Revisar el caso BUSY tras reconciliar
   sin borrar el journal ni reejecutar acciones.
6. **Segunda Mac ARM64 macOS 15+:** verificar hash/firma, ejecutar B6 fuera del
   checkout sin `.deps` ni DYLD de desarrollo, importar medio propio con tools
   embebidas, guardar/restaurar proyecto y reglas desarmadas, MKV+RTMP local y
   cerrar/reabrir. Registrar OS/hardware, permisos normales y medios decodificados.
   Reconstrucción, Developer ID y notarización conservan autorización separada.

## Limpieza y cierre local

`store-restoration.json` verifica byte a byte los originales previos a esta
reanudación: proyecto `38cf4184…49b74f`, mixer `d572433f…3635c` y configuración
Show Control `6f54a1d6…95a4e17`. `output-profiles.json` continúa ausente. Las
versiones de prueba quedan en copias privadas; los 16 journals se conservan
sin rebobinar y las grabaciones permanecen en `Movies/Motive`.

`physical-lock-release.json` verifica ausencia de owners, fixtures y receptores,
socket real eliminado y liberación del lock con su propietario exacto. No se
tocaron `element-lab/`, Keychain, permisos o ajustes globales. Hay commits locales
estables, sin push/merge/rebase/publicación. La candidata es más fiable dentro
de su alcance comprobado; los bloqueos de aceptación siguen explícitos.
