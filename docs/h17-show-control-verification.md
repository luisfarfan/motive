# H17 — reconciliación terminal de Show Control

Estado: **PARTIAL**. La causa del bloqueo de B6 está localizada y la corrección
del contrato está verificada offline. La repetición sobre el owner nativo de la
nueva candidata y la carrera GPUI stock450 conservan gates separados.

## Evidencia original y causa

El informe H15 permanece intacto. Se leyó
`motive-h15/var/evidence/h15-resume-01/native-b6/explicit-reconcile-restore.json`
sin modificarlo. La extracción acotada y el hash del original están en
`var/evidence/h17-show-control/historical-b6-extract.json`.

En esa sesión, `3e0a23c59bb4cf8e2e7f26b06824fd06`, el job 5 retiene
`needs_reconciliation`, cursor 0 y revisión esperada 165. Su acción tiene el
recibo de dispatch 163→165 y el token `:animation:7:4`. El owner ya retiene
`completed` para ese mismo token, pero `receipt:null`: no pudo atribuir todas
las revisiones posteriores exclusivamente a esa acción. Después de reconcile,
esos campos y el contador `goals=3` siguen iguales, y load responde
`SHOW_CONTROL_BUSY`.

La barrera de revisión impide correctamente continuar la secuencia tras una
edición ajena. El defecto es reutilizar esa misma prueba de continuidad para
cerrar una reconciliación explícita: un terminal nativo durable no concede
permiso para apropiarse de las revisiones ajenas, pero sí permite terminar la
acción conocida y cancelar el resto. B6 no podía representar ambas evidencias
por separado y quedaba bloqueado indefinidamente.

## Corrección y límites

`TerminalReceipt` identifica acción, token completo del owner y PID; no contiene
revisiones ni concede un nuevo dispatch. `OwnerBackend` lo crea únicamente tras
observar la barrera nativa existente: animación sin `pending_ack`, o transición
terminal con el mismo ID. Primero se añade y sincroniza el resultado en el
journal; solo después se devuelve y conserva en el mapa de operaciones. Un
error de escritura sigue devolviendo incertidumbre.

Únicamente `Runtime::reconcile` puede usar este recibo para cerrar una acción
completada sin recibo de mutación final. Exige un único recibo de dispatch ya
aceptado, la misma acción/token/PID y la misma revisión esperada. El tick normal
mantiene el rechazo anterior; el recibo terminal no autoriza el contador ni el
siguiente paso. No se utiliza como fallback de un recibo de mutación malformado.

Si quedan pasos, el job termina `cancelled`; si era la última acción, termina
`completed`. Cursor, revisión y recibos de mutación permanecen intactos. El
registro de acción conserva el error original y añade el recibo terminal. No se
borra el job para admitir load, no se rebobina el journal y no hay replay.

La admisión común de configure/load sigue bloqueada ante jobs activos o
inciertos, y ahora comprueba también operaciones nativas sin terminal, un scope
de dispatch activo o fallo de durabilidad. Una carga admitida sigue creando una
sesión nueva desarmada; no reanuda los jobs de la sesión anterior. Los journals
anteriores permanecen en disco. Configuración guardada v1 no cambia; checkpoints
offline con evidencia terminal usan v3, con lectura de v0–v2 conservada.

## Matriz

| ID | Prioridad | Tipo | Estado previo | Estado actual | Evidencia y prueba restante |
|---|---|---|---|---|---|
| H17-SC-01 | P1 | Bug de runtime | FAIL | PARTIAL | B6 conserva terminal y receipt null; tests demuestran cierre sin rebase/replay. Falta repetir load en el mismo proceso nativo. |
| H17-SC-02 | P1 | Barrera de concurrencia | PASS | PASS | Tests conservados de revisión ajena, token/PID incorrectos, dispatch sin recibo y observación sin recibo terminal. No certifica una carrera física. |
| H17-SC-03 | P1 | Cancelación antes del tick | NOT_EVALUATED | PARTIAL | Test cancela job queued sin dispatch/cancel nativo ni contador; deduplicación retenida. Cancelación física antes del primer tick OBS pendiente. |
| H17-SC-04 | P1 | Cancelación después del tick | PARTIAL | PARTIAL | Un cancel, espera pending, reconcile terminal y ningún contador; contrato offline. Evidencia física H15 no certifica el nuevo binario. |
| H17-SC-05 | P1 | Journal y restauración | PASS | PARTIAL | Tests de append-only, token/PID, no replay y checkpoints v3 pasan; guardado durable/restauración desarmada de la candidata pendientes. |
| H17-SC-06 | P1 | Carrera GPUI stock450 | PARTIAL | BLOCKED | Requiere gesto humano/nativo observado antes del terminal, sin ampliar los 450 ms. |

Riesgo de regresión principal: confundir prueba de finalización con propiedad de
revisiones. Lo cubren las pruebas negativas y el uso exclusivo durante
reconciliación. Un resultado desconocido, journal fallido o ausencia del recibo
de dispatch permanece bloqueado; no hay nuevo mecanismo de reparación de
journals incompletos.

## Pruebas ejecutadas

- `cargo test --locked --manifest-path show-control/Cargo.toml`: **PASS**, 136
  pruebas; siete nuevas y todas las anteriores conservadas.
- `cargo clippy --locked --manifest-path show-control/Cargo.toml --all-targets -- -D warnings`:
  **PASS**.
- Formato del crate y `git diff --check`: **PASS**.
- Test nuevo del owner `reconfiguration_keeps_native_operations_and_storage_failures_blocked`:
  **NOT_EVALUATED** en este checkpoint; requiere compilar el binario de tests
  principal. No abre dispositivos ni ejecuta multimedia.

Los backends de tests representan el contrato del owner; sus recibos no son
recibos físicos de libobs ni evidencia de presentación. Una primera ejecución
del test nuevo de cancelación falló por buscar `event-1` cuando su fixture usa
`button-1`; se corrigió la aserción para verificar el conjunto `seen` completo.
Clippy detectó un patrón de versiones que se sustituyó por `1..=3`.

## Protocolo mínimo de aceptación nativa

1. Tomar el lock físico canónico. Registrar hash de candidata, PID, sesión,
   fingerprint y stores previos. Usar MATCHDAY y tono propios, sin cámara ni
   micrófono. Guardar proyecto y reglas, cotejando recibo/hash/bytes durables.
2. Disparar una celebración stock de 450 ms. Observar su token y fase nativa;
   aplicar una edición de gain mientras está running. Una edición posterior
   al terminal no cubre la carrera. Conservar comandos/respuestas y tiempos.
3. Comprobar que el job entra en `needs_reconciliation`, sin segundo dispatch
   ni incremento de contador. Load debe responder BUSY mientras esté incierto
   o haya una operación sin terminal.
4. Observar terminal nativo con `pending_ack=false`. Reconcile debe conservar
   token, revisión, cursor y contador, dejar la acción completed y cancelar los
   pasos restantes. Cotejar un solo dispatch y completion en journal, con recibo
   terminal exacto; no aceptar una observación de CLI como sustituto del owner.
5. Load debe admitir una sesión nueva desarmada, con cero jobs nuevos; verificar
   que el journal anterior persiste. Armar requiere una acción explícita con
   PID/revisión actuales. Guardar y comprobar otro recibo durable.
6. Repetir cancelación de job queued y running, distinguiéndolas de la fase del
   primer tick OBS. Para GPUI, conservar observación nativa del gesto de edición
   y su efecto; el ensayo CLI no satisface esa fila.
7. Dos intentos sin entrar en la ventana de carrera dejan esa fila BLOCKED.
   Restaurar stores y cerrar mediante las barreras normales; confirmar proceso,
   socket, workers y lock liberados. Si se grabó/transmitió por loopback,
   decodificar ambos medios y conservar el análisis independiente de entrega.

## Runner nativo H17

`scripts/verify_h17_show_recovery.py --output var/evidence/h17-show-recovery-NN`
implementa un ensayo independiente sobre un owner portable ya abierto y fresco.
Recibe los tres `MOTIVE_TEST_*` de `h15_run_owned.py`. `--owner-pid` permite fijar
el PID esperado; si se omite, obtiene el peer de ese socket una sola vez y
verifica ejecutable y nacimiento antes de cualquier mutación. Cada conexión
valida de nuevo `LOCAL_PEERPID`; cada comando coteja el lock canónico.

La fixture es una alerta propia creada mediante `create_overlay`, una regla
explícita `configure_show_control` y un tono sin monitoreo. No instala MATCHDAY
ni atribuye acciones a GPUI. Usa el protocolo socket de CLI y conserva respuestas
completas con brackets monotónicos. El trigger dura siempre 450 ms: para cubrir
la carrera, el estado nativo anterior y el incluido en la respuesta de gain
deben confirmar `running`, primer tick ejecutado y elapsed <450 ms. Dos intentos
fallidos conservan BLOCKED.

Reconcile debe conservar cursor, revisión, recibo de dispatch, contador y job;
el recibo terminal se coteja con el journal nativo. Después comprueba deduplicación,
cancelación posterior al primer tick, load desarmado, rechazo estando desarmado,
armado explícito sin jobs y save durable. Cancelar antes del primer tick sigue
NOT_EVALUATED: el control público no ofrece batching atómico ni se cambia su reloj.

El único store escrito es `show-control/configuration.json`, mediante el API.
El runner guarda bytes previos, valida recibos/hash/longitud y restaura solo si
los bytes actuales coinciden exactamente con su última escritura reconocida.
Los otros stores se cotejan por hash, los journals históricos permanecen
intactos y los propios solo pueden crecer por prefijo. La fixture se retira por
API. Contadores de IDs/migración del proyecto en memoria no se rebobinan; el
caller conserva la responsabilidad del cierre normal del owner.

`python3 -m unittest discover -s scripts -p test_h17_show_recovery.py -v`:
**PASS**, cinco pruebas offline del verificador (recibos inválidos, duración,
primer tick, restauración exacta y rechazo de enlaces/cambios ajenos).
Compilación Python: **PASS**. Ensayo físico del runner: **NOT_EVALUATED** al
prepararlo; no se ejecutó ni se tomó el owner sin cesión explícita del coordinador.
