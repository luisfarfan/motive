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
