# H17 — reconciliación terminal de Show Control

Estado: **PARTIAL**. La recuperación en el mismo proceso, cancelación posterior
al primer tick y restauración desarmada pasan sobre el owner nativo B7. La carrera
GPUI stock450, cancelación antes del primer tick y presentación multimedia
conservan gates separados.

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
| H17-SC-01 | P1 | Bug de runtime | FAIL | PASS | B7 reproduce terminal con receipt null; reconcile cierra sin rebase/replay y admite load en el mismo proceso. Evidencia nativa abajo. |
| H17-SC-02 | P1 | Barrera de concurrencia | PASS | PASS | Tests conservados de revisión ajena, token/PID incorrectos, dispatch sin recibo y observación sin recibo terminal. No certifica una carrera física. |
| H17-SC-03 | P1 | Cancelación antes del tick | NOT_EVALUATED | PARTIAL | Test cancela job queued sin dispatch/cancel nativo ni contador; deduplicación retenida. Cancelación física antes del primer tick OBS pendiente. |
| H17-SC-04 | P1 | Cancelación después del tick | PARTIAL | PASS | B7: native started/widget_triggered true antes de cancel; terminal cancelled sin pending_ack; contador 0. |
| H17-SC-05 | P1 | Journal y restauración | PASS | PASS | B7: journal retenido, load desarmado, rechazo de press, armado explícito y dos recibos de 1836 bytes cotejados. |
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
  **PASS**, confirmado en `var/evidence/h17-checks/rust-tests.log`, suite
  principal de 120 tests. No abre dispositivos ni ejecuta multimedia.

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
Compilación Python: **PASS**. Al preparar el runner, el ensayo físico era
NOT_EVALUATED; el coordinador lo ejecutó después con el resultado siguiente.

## Resultado nativo B7

Evidencia: `var/evidence/h17-show-b7/report.json`, SHA-256
`9860fbe861b88a9b0f29cc312ccdb98f69a9c4cd02f8626b86c6de8af7b4a6a1`;
respuestas completas en `responses.jsonl`. PID 40290, binario B7 SHA-256
`d5b702d8b245a143575a6dd77cc80dc047425139f0ebc16db8c1f8451eb0ad31`.

La primera carrera pasó. La operación 1, configurada a 450 ms, estaba `running`
con `started=true` y `widget_triggered=true` antes y después de la edición real
de gain por CLI. Ambas observaciones tenían elapsed 0 ms: el primer tick ya había
ocurrido, aunque aún no había transcurrido otro frame. El terminal observado
tenía elapsed 466 ms, `completed` y `pending_ack=false`; no se amplió la duración
configurada para conseguir la carrera.

El job 1 quedó `needs_reconciliation`, cursor 0, expected revisión 11 y recibo
de dispatch 9→11. Load devolvió `SHOW_CONTROL_BUSY`. Reconcile dejó la acción
completed y el job cancelled, conservando revisión 11, cursor 0 y contador 0.
La respuesta nativa contiene el recibo terminal del token
`6562581fdeb006ce3c2f7eda535abd17:animation:1:1`; el journal tiene una intención,
un dispatch y una completion con el mismo recibo y `receipt:null`. Tras el
cooldown, repetir el event ID devolvió `DUPLICATE`.

La cancelación del job 2 también comenzó tras observar `started=true` y
`widget_triggered=true`. El terminal nativo fue cancelled sin pending_ack.
Reconcile retuvo ambos jobs cancelled, cursor 0 y goals 0. El journal conserva
una intención, un dispatch, un cancel_intent y una completion cancelled para
ese token. Sus ocho entradas totales, incluido header, tienen SHA-256
`8f62ef6af524433e6a71ec678c5f992ea83b784a8b65d7b2dc7b9f69984be317`.

Load creó la sesión `340ad969518059f603958e6e3dd2d480`, desarmada, con bindings
actuales y cero jobs. Press fue rechazado mientras estaba desarmada. Armado
explícito dejó cero jobs. Los guardados de revisiones 9 y 25 certificaron 1836
bytes durables y SHA-256
`08e2adfe7b7a66e359523b8b861ff039b6579b383f196382255d73b3d97d3ed8`.
Stores antes/después coinciden por hash; fuente/capa/tono propios se retiraron.
El wrapper `var/evidence/h17-show-b7-owner/report.json` conserva suite exit 0,
shutdown true, owner exit 0 y cero errores de cleanup.

El agregado del runner permanece PARTIAL: no abrió outputs ni decodificó píxeles,
no hizo gestos GPUI y no observó cancelación previa al primer tick. Esos límites
no invalidan el cierre demostrado del bloqueo de reconciliación de B6.
