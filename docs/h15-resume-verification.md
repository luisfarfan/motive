# H15 — reanudación y candidata B6

Continuación solicitada por el propietario después del primer cierre B4.
La evidencia anterior permanece intacta. Directorio de esta sesión:
`var/evidence/h15-resume-01/`. Misma rama y lock físico canónico; sin push,
publicación, RTMPS nuevo, cámara ni micrófono reales.

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

La validación sin trazas y las regresiones del candidato se registran a
continuación al completarse. El fallo histórico `APPLICATION_UNAVAILABLE`
es distinto: no se ha reproducido ni se declara reparado por este cambio.
