# H22 — cold replacement y continuidad

Cold replacement conserva el gate original **<250 ms** para peers activos.
Hot resize permanece deshabilitado en el contrato de Production. No se afirma
una causa interna demostrada de GPU/Chromium para el FAIL de H19.

## Qué permite concluir H19

El soak H19 conserva **458,98 ms** entre observaciones del peer D durante el
resize de C. La preparación propia del resize tomó aproximadamente 5,46 ms;
el target volvió a paint en 447,49 ms. La
[precisión de la observación](../evidence/H22-baseline/resize-observation-precision.json)
distingue 458,97725 ms entre timestamps de paint de los frames adquiridos 119 y
121, y **464,156541 ms entre sus adquisiciones**. El frame 120 fue coalescido
y no conserva timestamp individual; no se puede afirmar que todos los callbacks
CEF se detuvieran por 458,98 ms. El FAIL del consumer permanece real.

En esa identidad, el mayor trabajo registrado del consumer fue 0,255 ms y el
mayor callback propio de publish 0,254 ms. No muestran una llamada propia de
400 ms, pero no localizan el tiempo sin scheduling entre iteraciones/callbacks
ni el trabajo interno del compositor. El accounting completo no convierte ese
hueco real en continuidad.

Esto sitúa el tramo lento después de la preparación propia, compatible con
CEF resize/compositor/GPU y scheduling compartido. No se obtuvo una traza
interna que discrimine esas causas, ni una reproducción instrumentada que
permita atribuir la pausa a un mutex específico. Host, GPU y servicios
compartidos conservan un dominio común de fallo. Reemplazar cold evita esa
ruta de WasResized; su éxito no prueba la causa exacta del fallo hot.

## Ruta oficial del CEF fijado

La lectura adicional del commit CEF
`cf60f42d20a8c68c74bc790cf5ade0de8acbbcd3` conserva
[fuentes y hashes](../research/h22-resize-sources-v2.json).
[AlloyBrowserHostImpl::WasResized](https://github.com/chromiumembedded/cef/blob/cf60f42d20a8c68c74bc790cf5ade0de8acbbcd3/libcef/browser/alloy/alloy_browser_host_impl.cc#L348)
reenvía la llamada al hilo UI si es necesario. El delegado OSR la transmite a
la vista. Allí `hold_resize_` deja un único resize en vuelo y marca otro como
pendiente, sin ejecutar un segundo cambio de tamaño inmediatamente.

[La vista OSR](https://github.com/chromiumembedded/cef/blob/cf60f42d20a8c68c74bc790cf5ade0de8acbbcd3/libcef/browser/osr/render_widget_host_view_osr.cc#L1087)
sincroniza propiedades, cambia bounds/escala del compositor, asigna un nuevo
LocalSurfaceId e invoca EmbedSurface antes de notificar al RenderWidgetHost.
El hold se libera cuando OnPaint observa el tamaño esperado; si había un resize
pendiente, publica otra tarea UI. Es estado de esa vista, no evidencia de un
mutex global que haya congelado al peer D. El nombre SynchronizeVisualProperties
tampoco demuestra por sí mismo una espera bloqueante de 458,98 ms.

La inferencia limitada es que hot resize atraviesa renderer/compositor/surface
además del código propio. Falta correlacionar esas etapas internas con el hueco
real de H19 para atribuir causa; los traces nativos H22 y el cambio cold no
reconstruyen retrospectivamente esa información. No se cambia CEF ni se activa
un reloj externo para hacer desaparecer el fallo.

## Barrera nativa implementada

`Host::Replace` revoca inmediatamente la generación y solicita cierre
asíncrono. OnBeforeClose completa el cierre del browser, termina/join del
consumer, escribe la contabilidad terminal y libera el RequestContext.
Una tarea UI posterior comprueba browser cerrado, cero pending/consumer,
frames escritos y contexto/mailbox liberados antes de crear la nueva
generación. La geometría queda fija durante esa generación y epoch reinicia
en 1. No se crea el browser nuevo dentro de OnBeforeClose.

Los traces conservan consumer_join_enter/joined, frame_report_enter/written,
context_released y cold_replacement_barrier_passed. El auditor verifica orden,
browser ID nuevo, instance estable, generation creciente, alpha/stride/hash,
ausencia de paints tardíos y cero bytes propios retenidos. El límite a primer
paint permanece **<1000 ms**; no garantiza que el widget ya esté listo para
recibir un evento ni acredita presentación en OBS.

## Evidencia nativa

La tabla siguiente pertenece a los perfiles anteriores al control de red.
Sus traces y frames acreditan las operaciones observadas, pero el hallazgo
posterior de componentes impide tratarlos como una carga que excluya updates
de Chromium. La matriz final usa otros binarios y su propia evidencia.

| Ensayo | Cobertura | Reemplazo → primer paint | Mayor gap de peer activo |
|---|---|---:|---:|
| cold1 resize, 12 s | Horizontal → vertical → horizontal, 3 simples | 80,61–85,99 ms | 54,35 ms |
| cold1 lifecycle, 30 s | Crear/cerrar/hide/show/resize/crash/recover/suspend | 80,34 ms | 48,70 ms |
| cold1 cycles, 600 s | 27 generaciones, 16 reemplazos, 64 operaciones auditadas | 55,57–139,62 ms | 55,87 ms |
| cold2 resize, 12 s | Binario actualizado, 2 reemplazos y 4 operaciones con create | 56,83–65,54 ms | 48,53 ms |
| Widgets, 45 s | Lower Third + Alert activos, lifecycle del tercero | 63,56 ms | 56,24 ms |
| Goal original, 45 s | Dos Goals activos durante lifecycle del tercero | 64,58 ms | 72,50 ms |

Informes: [resize cold1](../evidence/H22-cold1-resize-r1/analysis.json),
[lifecycle cold1](../evidence/H22-cold1-lifecycle-r1/analysis.json),
[600 s cold1](../evidence/H22-cold1-cycles600-r2/analysis.json),
[resize cold2](../evidence/H22-cold2-resize-r1/analysis.json),
[widgets con peers activos](../evidence/H22-pilot-r2-widgetlife3/workload-peer-analysis.json),
[Goal con peers activos](../evidence/H22-pilot-r2-goallife3/workload-peer-reclassification.json).
Los primeros informes cortos preceden al conteo adicional de create; no se
reescriben. El soak y cold2 incluyen esa observación explícita.

Para motion continuo, el auditor usa muestras anteriores y posteriores al
intervalo: recortar un borde no puede esconder un stall. Mide por separado
el timestamp de paint asociado a cada frame adquirido, su adquisición y su
completion. Los paints coalescidos tienen contadores completos, pero no un
timestamp individual en `frames.json`; por eso un gap de esa columna no
localiza por sí solo el retraso dentro de CEF. Para Goal/Lower Third/Alert, los intervalos
activos vienen de eventos tipados, y se conservan completos, incluidos los
cancelados o interrumpidos. Cada operación exige otro widget realmente activo
en su instante y comprueba todos los intervalos activos solapados. No se exige
30 FPS a una animación que ya completó ni a un widget estático.

Los huecos all-time de widgets intermitentes quedan en `analysis.json`, incluso
los segundos de idle; su gate de continuidad corresponde al auditor de
workload. No se usa ese tratamiento para borrar huecos dentro de actividad.
Cancel debe recibir ACK antes de ocultar; no hay paints tras 250 ms de settle
hidden, y resume no puede replayar el evento. Crash exige salida nativa 86
y generación nueva, sin confundir ACK con reap.

## Candidatos finales con resolución cerrada

Estos ensayos usan los binarios finales y exigen por separado control de red
positivo, cero eventos de socket y ausencia de manifests. No heredan el PASS
de los perfiles anteriores.

| Ensayo final | Operaciones con peers auditadas | Cold → primer paint | Mayor gap de peer activo | Pico RSS |
|---|---:|---:|---:|---:|
| Mezcla lifecycle, 45 s | 8 | 73,85 ms | 46,85 ms | 937,45 MiB |
| Goal lifecycle, 45 s | 8 | 86,04 ms | 68,44 ms | 1350,88 MiB |
| Cold resize simple, 12 s | 4 | 78,10–81,83 ms | 52,76 ms | 929,94 MiB |
| Cold cycles simple, 600 s | 64 | 72,27–91,67 ms | 58,34 ms | 986,13 MiB |
| Mezcla lifecycle, 600 s | 70 | 73,83–93,15 ms | 109,78 ms durante operaciones | 933,70 MiB |

[Mezcla lifecycle final](../evidence/H22-lifecycle-r2-widgetlife3/workload-analysis.json):
PASS funcional y de rendimiento; cierre nativo 55,03 ms y cleanup externo
11,54 ms. Las seis identidades cerradas conservan cero bytes de frames retenidos.
El [Goal lifecycle final](../evidence/H22-lifecycle-r2-goallife3/shutdown-diagnosis.json)
conserva **FAIL de cierre**: 5403,68 ms desde close_requested hasta shutdown_return,
frente al máximo original de 5000 ms. Los primeros 35,93 ms incluyen cierre de
browsers, joins, informes y liberación de contextos; 5367,76 ms ocurren dentro
de CefShutdown. Cleanup externo 13,40 ms, cero identidades propias observadas
vivas y cero bytes de frames retenidos. La auditoría independiente de eventos
y peers pasa; eso no reclasifica el gate final de cierre.

Las muestras finales muestran browser/GPU/network/storage durante parte de
la espera, y luego sólo browser antes de salir. Sin stacks internos no permiten
asignar la causa a uno de esos procesos. El
[código CEF fijado](https://github.com/chromiumembedded/cef/blob/cf60f42d20a8c68c74bc790cf5ade0de8acbbcd3/libcef/browser/main_runner.cc)
despacha tareas pendientes UI/IO y desmonta los runners; describe posibles
etapas, no identifica la que demoró esta ejecución. Sus
[fuentes y hashes](../research/h22-shutdown-sources.json) quedan conservados.
La campaña r4 se detuvo; tras verificar reap, contabilidad, red y las barreras
que el gate de plazo había dejado sin evaluar, r5 continúa sólo casos
independientes no ejecutados. No cambia binarios, timeout ni resultados previos.
El [cold resize final](../evidence/H22-lifecycle-r3-coldresize3/analysis.json)
pasa sus dos reemplazos de geometría, cierre de 101,43 ms y cleanup externo
de 11,76 ms. El [cold cycles final de 600 s](../evidence/H22-soak-r2-coldcycles3/analysis.json)
pasa 64 operaciones, 16 reemplazos y 27 generaciones: cinco ventanas continuas
auditadas a 30,00 adquisiciones/s, peor p95 edad 13,69 ms. Cierre 2317,59 ms,
cleanup 13,47 ms y cero frames/leases retenidos. Ese cierre cumple 5000 ms,
pero su duración no elimina el FAIL de Goal ni demuestra latencia constante.
El [soak de mezcla](../evidence/H22-soak-r2-widgetmix3h/workload-analysis.json)
pasa peers durante operaciones, 14 reemplazos y cierre en 121,86 ms, pero
**falla rendimiento global**: 11/194 eventos completos, hasta 465,57 ms de gap
activo en la cola estable. El máximo de la tabla sólo cubre operaciones y no
debe interpretarse como máximo de todo el ensayo. El
[diagnóstico](../evidence/H22-soak-r2-widgetmix3h/stall-diagnosis.json) correlaciona
los gaps tardíos con heartbeat UI, sin causa interna demostrada.

El [Goal vertical de 600 s](../evidence/H22-soak-r2-goals3v/workload-analysis.json)
pasa 291 eventos completos: mínimo 29,07 adquisiciones/s, p95 edad máximo
15,00 ms y gap activo máximo 81,69 ms. Cierre 65,14 ms, cleanup 9,01 ms y pico
RSS 1425,31 MiB. No ejecuta el escenario de crash/lifecycle que conservó el
cierre tardío y no lo reemplaza. El heartbeat UI máximo fue 85,29 ms.

## Fallos conservados y alcance

El primer soak cold1 falló por timeout del observador ps; la repetición usa
otro observador, el mismo binario CEF y nuevos directorios. El primer piloto
de widgets falló por divergencia de relojes; el siguiente detecta suspensión
explícitamente. Ninguno de esos FAIL se cambia a PASS.

El auditor inicial de Goal lifecycle exigía transparencia final también al
cerrar deliberadamente una animación activa. El native report ya acreditaba
revocación y cierre, y los bytes finales conservaban correctamente el último
frame previo al cierre. El FAIL original queda junto a una reclasificación
nueva: transparencia sigue siendo obligatoria para un Goal completado o idle,
mientras un cierre interrumpido exige las barreras de revocación. No cambia
ningún frame, timing ni umbral de rendimiento.

La continuidad aquí es CEF→consumer del laboratorio, no juego/captura/OBS/
encoder/stream. Los nuevos soaks de la matriz final tienen sus propios
binarios y resultados; no heredan automáticamente el PASS cold1.

El auditor final contabiliza además cada dispatch nativo: inicio visual,
rechazo esperado del fixture estático o interrupción explícita antes de activo.
Un dispatch sin respuesta al siguiente evento/cierre final falla; no se deduce
que un widget sea estático por ausencia de actividad. Goal admite una actividad
inicial de bootstrap por identidad: es una celebración solicitada por el driver
cerrado de la fixture para probar render, incluida una identidad reconstruida.
No demuestra que un arranque genérico de producto permanezca idle tras recovery.
H23 debe arrancar ese widget en idle y enviar sólo eventos explícitos del owner;
no transportar el autotrigger ni los enums de prueba. La ausencia de replay al
mostrar se comprueba dentro de la misma generación; la revocación entre
generaciones impide reutilizar sus frames/eventos con autoridad vieja. Se
registra latencia dispatch→active sin introducir otro umbral de FPS ni afirmar
que el ACK pruebe píxeles semánticos, presentación OBS o latencia de MCP/UI.
Los pilotos originales conservan sus informes y tienen auditorías adicionales
`workload-event-accounting.json`, todas PASS (máximo dispatch→active observado 3,69 ms, en widget lifecycle).
