# H13 — contrato de salidas independientes

Estado al 2026-11-17: **núcleo, CLI/MCP y presentación GPUI implementados;
aceptación H13 pendiente**, sobre OBS 33.0.1. El registro y los comandos siguientes
ya existen en el worktree H13. Las primeras pruebas reales acreditan control de
dos salidas, supervivencia y recuperación por destino; una discontinuidad de
audio conserva el resultado global de la matriz en FAIL. La nueva presentación
GPUI aún requiere build integrado y operación nativa. Ver los límites y la
evidencia concreta en las secciones 9 y 10; implementar no equivale a completar
la aceptación.

Decisión: [arquitectura H13](h13-production-architecture.md). Referencias de
compatibilidad: [H8](h8-streaming-verification.md),
[H9](h9-scene-transitions-verification.md),
[H10](h10-audio-verification.md) y [H12](h12-creative-studio-contract.md).

## 1. Alcance y propiedad

Una `Production` y su owner GPUI serializan UI, CLI y MCP. Hay dos destinos
estables: `recording` y `streaming`. Cada uno admite un intento a la vez y posee
su output OBS, par H.264/AAC, servicio cuando aplica, señales, métricas y fallo.
No se crea otra instancia OBS, Scene Graph, captura, mezcla ni reloj multimedia.

Ambos encoders de video consumen `obs_get_video()`; ambos AAC consumen
`obs_get_audio()`, mezcla 0. Canvas/FPS son de la producción, no de cada perfil.
El audio global H10 no depende de Cut/Fade. Monitoreo continúa desactivado.
Los perfiles v1 pueden diferir en encoder, bitrate, GOP y reordering, dentro de
sus límites actuales. Cada arranque guarda una copia de su perfil efectivo.

La implementación inicial usa encoders independientes. OBS permite compartirlos
y conserva referencias al asociarlos con outputs, pero `obs-encoder.c::full_stop`
detiene todos los outputs de un encoder fallido. Compartir solo sería una
optimización futura, con compatibilidad completa de configuración y pruebas de
suscripción, finalización y fallos; no es una capacidad de este incremento.

El registro nativo tiene direcciones estables durante toda la vida del engine.
Los callbacks reciben su slot y publican observaciones acotadas; no liberan
recursos, ejecutan comandos ni acceden a Rust. El owner consulta y reconcilia.
La actividad `NSProcessInfo` debe cubrir todos los slots ocupados: liberar uno
no puede retirar la actividad del otro. El graph se libera después del último.

## 2. Modelo de consulta

`OutputTarget` conserva los valores `recording | streaming`; `OutputPhase`
expone `idle | starting | connecting | active | stopping | error`.
La fase describe el ciclo nativo; la necesidad de recuperación es un campo
independiente. En particular, un error recibido mientras quedan workers se
presenta como `stopping`, con el fallo y `recovery_required: true` visibles.

El estado compartido incorpora `output_contract_version: 1` y `outputs`, un
objeto con exactamente las claves `recording` y `streaming`. La consulta nueva
`outputs` devuelve el mismo registro, junto con `pid` y `revision`; no mantiene
una segunda copia calculada por CLI/MCP. Cada entrada contiene:

| Campo | Significado |
|---|---|
| `target` | Identificador estable del destino. |
| `kind` | `recording`, `streaming` o `local_stream` para identificar la ruta UDP heredada; `null` antes del primer intento. |
| `attempt_id` | Contador por destino, monotónico dentro del PID, o `null` antes del primer intento. Identifica muestras de distintos arranques. |
| `phase` | Fase observada según las reglas siguientes. |
| `native_busy` | Quedan recursos activos o workers que impiden liberar/reutilizar el slot. |
| `cancel_requested` | El owner aceptó finalizar este intento. |
| `cancel_deferred` | La petición espera que termine el handshake RTMP. |
| `recovery_required` | Un fallo retenido impide otro arranque hasta recuperación explícita. |
| `failure` | `null` o `{code, native_code, recovery: "explicit"}`; `native_code` puede ser `null` si OBS no dio código. No inventar un código nativo. |
| `profile` | Snapshot del perfil usado por este intento, o `null` antes de iniciar. La selección futura sigue en `output_configuration`. |
| `video` | Snapshot de dimensiones/FPS reales configurados al arrancar. |
| `encoding` | Encoder solicitado y efectivo, hardware y razón de fallback de este destino. |
| `path` | Archivo MKV generado por el núcleo, o `null` para streaming. No es un argumento de arranque. |
| `active_duration_ms` | Duración monotónica desde el inicio observado; se congela al terminar. No se calcula con el reloj de UI ni incluye handshake. |
| `stats` | Bytes, frames de salida, drops y frames codificados del intento, con unidades y ámbito documentados. |

La asignación de `attempt_id` ocurre al comenzar la transacción nativa, después
de validación/preflight y reserva del archivo cuando aplica. Un error de
argumentos no crea intento. Conservar el último snapshot terminal hasta el
siguiente arranque; recuperar reconoce el fallo sin borrar la evidencia del
archivo. Un reinicio del proceso reinicia estos IDs, por eso se usa `(pid,
target, attempt_id)` como identidad de observación, nunca el ID aislado.

Render lag, total de frames renderizados, skips del video global, preview,
capturas y medidores de mezcla son métricas de producción. No copiarlas como
si fuesen pérdidas independientes de ambos outputs. Frames codificados provienen
del encoder del slot; no equivalen a bytes entregados al receptor. Un contador
no disponible debe informarse como `null`, no como cero observado.

`output_capabilities` declara `simultaneous_outputs: 2`, los dos destinos,
`encoder_sharing: false`, `composition_shared: true`,
`deferred_cancellation_supported: true` y
`cancel_connecting_supported: false`. Conserva la identificación del parche H8
y la restricción loopback.
Disponibilidad de una opción de video no constituye verificación multimedia.

## 3. Fases y barreras

| Origen / evento | Resultado |
|---|---|
| `idle` + arranque validado | `starting`; reservar recursos solo del destino. |
| RTMP aceptó el inicio, handshake pendiente | `connecting`; todavía no se declara transmisión activa. |
| Señal de inicio y estado nativo concordante | `active`. |
| Petición de stop desde active | `stopping`, hasta la barrera real. |
| Cancel durante connecting | Continúa `connecting`, con ambos indicadores de cancelación; no se bloquea GPUI. |
| Handshake terminó y había cancel pendiente | Solicitar stop seguro; `stopping`, o terminal si el intento ya falló y terminó. |
| Stop normal y barrera cumplida | `idle`, `native_busy: false`, sin fallo nuevo. |
| Fallo con actividad/worker pendiente | `stopping`, fallo retenido, recuperación pendiente. |
| Fallo con barrera cumplida | `error`, `native_busy: false`, recuperación pendiente. |
| Recover explícito del destino quiescente | `idle`; reconoce solo su fallo y permite otro arranque. |

La barrera de cada slot combina señal/estado de captura de libobs y, para RTMP,
`get_thread_state`: ningún worker de conexión/envío puede seguir usando el
objeto. No basta `stop`, ni `obs_output_active() == false` por separado.
Desconectar señales antes de liberar output, servicio y encoders. No reutilizar
el slot mientras un callback del intento anterior pueda alcanzarlo.

El procedimiento H8 se consulta desde el owner, nunca dentro de una señal. No
extender el parche para implementar el registro. Si falta el procedimiento, el
arranque RTMP falla cerrado. La cancelación diferida puede durar el timeout real
de red; no hay un máximo de cierre garantizado por este contrato. La UI conserva
estado y consultas durante la espera. No usar force-stop ni timeout de UI como
prueba de liberación segura.

## 4. Operaciones UI / CLI / MCP

Los objetos de entrada son cerrados (`additionalProperties: false`); las
operaciones dirigidas exigen `target` con enum exacto. Comparten `Command` y
`Production.apply`.
No reciben punteros, comandos shell, bytes multimedia, hosts, URLs ni rutas de
grabación. No incorporan stream keys. Los errores mantienen el sobre existente
`{ok: false, error: {code, message}}`; las mutaciones exitosas incluyen el estado
compartido observado, sin prometer que el proceso asíncrono ya terminó.

| Operación | Argumentos | Comportamiento |
|---|---|---|
| `outputs` | Ninguno | Consulta de los dos slots, incluso durante shutdown pendiente. |
| `start_output` | `target` | Preflight y arranque de ese destino; permite que el otro siga activo. |
| `stop_output_target` | `target` | Stop controlado de ese destino; connecting devuelve `OUTPUT_CONNECTING`. |
| `cancel_output_target` | `target` | Solicita finalización, también diferida durante connecting. Repetir no crea otra operación nativa. |
| `recover_output_target` | `target` | Solo con ese destino quiescente; libera recursos retenidos y reconoce su fallo. No inicia ni reinicia nada. |
| `cancel_all_outputs` | Ninguno | Solicita finalización de todos los slots, también de conexiones pendientes; no sale de Motive. |
| `preflight_output` | `target` | Valida el destino sin iniciar encoders, reservar archivo ni probar red. |
| `request_shutdown` | Ninguno | Cancela transición y solicita finalización de todos; espera la barrera conjunta antes de salir. |

Stop/cancel sobre un slot quiescente son no-op seguros y no reconocen errores.
Recover sobre un slot idle sano es no-op; sobre uno ocupado devuelve
`OUTPUT_BUSY`. Start sobre el mismo destino ocupado devuelve `OUTPUT_BUSY`.
Start con su recuperación pendiente devuelve `RECOVERY_REQUIRED`. El otro
destino no debe perder su duración, encoder, frames ni recursos al rechazarse
la operación. `cancel_all_outputs` opera sobre el conjunto ocupado observado
por el owner; no deja un modo persistente de cancelación que alcance intentos
futuros después de terminar.

Consultas: `readOnlyHint: true`, `destructiveHint: false`,
`idempotentHint: true`. Mutaciones: `readOnlyHint: false`, sin reintento de
transporte automático. Stop/cancel/shutdown conservan `destructiveHint: true`.
Por prudencia las anotaciones de mutaciones pueden mantener
`idempotentHint: false` aunque repetir cancel sea seguro dentro del mismo
intento: una repetición tardía podría alcanzar otro intento. Todas conservan
`openWorldHint: false`. `request_shutdown` sigue en categoría development.
No añadir herramientas de inyección de fallos para ejecutar las pruebas.

Ejemplos del contrato nuevo, utilizables solamente cuando `tools/list` los
anuncie; no prueban por sí mismos la entrega de medios:

```sh
target/Motive.app/Contents/MacOS/motive ctl '{"op":"outputs"}'
target/Motive.app/Contents/MacOS/motive ctl '{"op":"preflight_output","target":"recording"}'
target/Motive.app/Contents/MacOS/motive ctl '{"op":"start_output","target":"recording"}'
target/Motive.app/Contents/MacOS/motive ctl '{"op":"start_output","target":"streaming"}'
target/Motive.app/Contents/MacOS/motive ctl '{"op":"cancel_output_target","target":"streaming"}'
```

Después de `initialize`, el mismo arranque en MCP es:

```json
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"start_output","arguments":{"target":"recording"}}}
```

La UI debe usar las operaciones con destino, mostrar los dos estados y
confirmar la parada donde corresponda. Puede mostrar “Finalizar todos” con
`cancel_all_outputs`. La confirmación visual no sustituye las barreras del
núcleo. Una respuesta `ok` a cancel significa petición aceptada; “Finalizado”
requiere el estado terminal con `native_busy: false`.

## 5. Compatibilidad y persistencia

Los comandos `start_recording`, `start_stream` y `start_local_stream` mantienen
su requisito anterior de que ninguna salida esté ocupada. La posibilidad de
arrancar el segundo destino se obtiene mediante `start_output`; no se cambia
silenciosamente la semántica de los comandos antiguos. La ruta UDP heredada
`local_stream` continúa exclusiva; puede reutilizar el slot `streaming` con
`kind: "local_stream"`, preservando su implementación raw `ffmpeg_output` y
su UDP fijo. No tiene un par de encoders explícitos como la ruta RTMP, por lo
que sus campos no disponibles se informan como `null`. No ocupa un tercer
output concurrente y participa en los mismos guards globales y cierre seguro.
El registro no puede declarar ambos slots libres mientras esa ruta esté viva.

`stop_output` y `cancel_output` antiguos resuelven un único slot ocupado. Si
hay dos ocupados devuelven `OUTPUT_TARGET_REQUIRED` sin modificar ninguno. Si
no hay ninguno, conservan el no-op anterior. `recover_output` antiguo mantiene
su guard global idle; con más de un fallo pendiente devuelve
`OUTPUT_TARGET_REQUIRED`. La recuperación dirigida permite recuperar RTMP
mientras continúa una grabación. Nunca recuperar implícitamente ambos.

Con un único destino relevante, mantener el significado de `status.output`,
`output_path`, `output_code`, `output_failure`, `encoding` y stats heredados.
Con más de un destino ocupado o fallido, la proyección antigua debe indicar
ambigüedad (`output: "multiple"`) y no presentar el código/perfil/métricas de uno
como si describieran toda la producción. Los campos específicos del output no
representable serán `null`; las métricas compartidas siguen disponibles.
Cuando ambos terminan sanos, la proyección puede conservar el último destino
iniciado como hace hoy con el último archivo; `outputs` conserva ambos.
Documentar esta extensión en el informe de implementación y probarla con los
clientes: ninguna suite de una sola salida debe depender de la proyección dual.

La evolución de `preflight_output {target}` se hace explícita: valida el
destino y permite el otro ocupado. Los wrappers de arranque heredados mantienen
su guard adicional global. Su respuesta conserva `ready`, `target`, `profile`,
`configuration`, `network_tested: false` y `encoder_initialized: false`.

No persistir handles, fases, workers, cancelaciones ni errores de una sesión.
Reabrir Motive nunca inicia salidas automáticamente. Mantener perfiles v1 y
selección runtime separada según el contrato existente. Proyecto v5 y mixer
versionado son stores distintos; guardar uno no escribe los otros ni endpoints
o secretos. Cargar proyecto/canvas/mixer/perfiles conserva sus guards y no
reconfigura recursos compartidos mientras un output los usa.

## 6. Preflight y transacción de arranque

El owner valida, en este orden lógico, sin prometer que desaparezcan las carreras
externas entre preflight y start:

1. Comando cerrado y destino válido; no shutdown pendiente.
2. Slot destino quiescente y sin recuperación pendiente; no ruta UDP exclusiva.
3. Sin importación/transición/animación pendiente que el guard existente impida
   al arrancar; no detener ni reconstruir una producción que ya está en curso.
4. Fuentes de la producción preparadas según la política H9/H10 y sin fallos
   compartidos pendientes. El fallo de otro output no bloquea este destino.
5. Perfil seleccionado válido y disponibilidad anunciada de encoder. Detectar
   VideoToolbox no prueba que una segunda sesión hardware pueda inicializarse.
6. Canvas actual compatible; dimensión/FPS compartidos no cambian al arrancar.
7. Streaming: endpoint explícito `127.0.0.1`, puerto 1024–65535, servicio/módulo
   disponible, referencias Keychain válidas y vinculadas cuando apliquen.

Preflight no negocia RTMP, accede al contenido de archivos privados ni abre un
archivo de grabación de prueba. Un fallo de almacenamiento puede producirse en
start o después. No afirmar “disco disponible” a partir de que el directorio
existe; si se informa espacio libre, etiquetarlo como observación instantánea.

Start de grabación crea exclusivamente un archivo nuevo en `var/recordings`
mediante la política actual del núcleo. Si la transacción falla, solo puede
retirar el archivo vacío que acaba de reservar; preservar cualquier contenido
y registrar su ruta. Start de streaming no prueba ni cambia el otro output.
El rollback libera solo el slot en preparación.

Auto puede pasar de VideoToolbox a x264 únicamente durante preparación de video
y antes de iniciar el output. Conservar la causa. No reintentar por AAC, muxer,
fallo de red ni fallo de un encoder ya activo. Si el segundo arranque falla,
el primero mantiene sus encoders, capturas, reloj y contadores. No hay reconexión
automática ni cambio de calidad para intentar ocultar un fallo de capacidad.

## 7. Política de fallos y recuperación

| Fallo | Alcance y recuperación |
|---|---|
| RTMP rechazado, receptor perdido, error TLS | Solo streaming; esperar workers, recuperar y arrancar explícitamente. MKV continúa. |
| Creación/escritura/muxer MKV | Solo recording; preservar archivo parcial. RTMP continúa si los recursos compartidos siguen sanos. |
| Encoder H.264/AAC de un slot | Solo ese destino con los pares independientes; el error puede implicar finalización asíncrona. |
| Fuente visual actualmente en programa perdida | Política H9: detener todos los outputs ocupados, conservar IDs afectados y recuperar fuentes mientras idle. |
| Fuente exclusiva de escena destino no preparada | Rollback H9; la escena anterior y ambos outputs continúan. |
| Entrada individual del mixer perdida | Aislar entrada según H10; demás entradas y outputs continúan. Mostrar issue y permitir recuperación por entrada. |
| Video/contexto o mezcla compartida no utilizables | Finalización de todos, fallo compartido explícito; no atribuirlo a un solo destino. |

Mantener separados los fallos compartidos y los fallos por output. Resolver
`streaming` no reconoce una cámara, micrófono ni fallo MKV. Un fallo local de
otro destino no debe entrar en el guard genérico `recovery.required()` que
bloquee iniciar/recuperar el sano. La pérdida aislada de una entrada conserva
la política actual de readiness para nuevos arranques; no implica que las
salidas existentes estén corruptas.

Códigos OBS ya mapeados que se conservan: `OUTPUT_BAD_PATH`,
`OUTPUT_CONNECT_FAILED`, `OUTPUT_INVALID_STREAM`, `OUTPUT_DISCONNECTED`,
`OUTPUT_UNSUPPORTED`, `OUTPUT_NO_SPACE`, `OUTPUT_ENCODE_ERROR` y
`OUTPUT_HDR_DISABLED`. Un fallo desconocido sigue como `OUTPUT_FAILED`.
Errores de comando incluyen `OUTPUT_BUSY`, `OUTPUT_CONNECTING`,
`OUTPUT_TARGET_REQUIRED`, `RECOVERY_REQUIRED`, `SHUTDOWN_PENDING`,
`ENDPOINT_REQUIRED`, `ENCODER_UNAVAILABLE` y los de fuentes/perfil existentes.
No incluir claves, URLs con credenciales ni mensajes arbitrarios secretos en
`failure` o respuestas MCP. La protección H8 de logs continúa vigente.

## 8. Shutdown y configuración compartida

`request_shutdown` marca una intención global, cancela la transición mediante
H9 y solicita finalizar cada slot. Cualquier conexión pendiente mantiene el
owner y su memoria vivos. El polling del owner ejecuta el stop diferido cuando
sea seguro. `shutdown_requested` solo se publica cuando todos los outputs y
workers son quiescentes. Cmd+Q, menú Quit y cierre de ventana usan este camino.

Durante shutdown se permiten consultas y peticiones repetidas de cancelación/
shutdown; los nuevos arranques o cambios de configuración devuelven
`SHUTDOWN_PENDING`. La UI muestra el motivo de espera por destino. Un timeout
de observación no fuerza destrucción. `shutdown` inmediato heredado sigue
rechazando outputs ocupados. Ante un drop anormal del owner, conservar la
protección nativa que evita liberar memoria usada por workers.

Cambiar canvas/FPS/variante requiere todos los outputs quiescentes y ninguna
transición/animación pendiente. Antes de `obs_reset_video`, liberar encoders
inactivos que conservan referencias al contexto viejo. Mantener guards globales
para editar/cargar perfiles o endpoint en este incremento; preparar ambos
perfiles/endpoint antes de emitir. Recovery por destino y start no requieren
cambiar esos ajustes y funcionan con el otro output activo.

## 9. Implementación y verificación incremental

### Evidencia real disponible y límites actuales

La implementación vive en `native/output-slots.inc`, `native/encoding.inc`,
`native/engine.m`, `src/output.rs`, `src/output_runtime.rs`, `src/engine.rs`,
`src/core.rs` y `src/control.rs`. `scripts/verify_h13_outputs.py` realiza ensayos
con patrón, overlays, tono y un receptor FFmpeg local propio; conserva cada
archivo/segmento, operaciones, observaciones, hashes y errores. Los resultados
siguientes corresponden al ejecutable SHA-256
`dc9c38a82d72c86cacd668a88c25ec26f0e12cbbb7b9d0c829d3e820a20ef38f`, no al futuro
bundle que incorpore la nueva presentación GPUI.

| Ensayo conservado | Resultado y alcance |
|---|---|
| [Primer smoke](../var/evidence/h13-outputs-1794933571099068000/report.json) | Lifecycle/control PASS. El reporte inicial conserva un fallo del analizador PCM; no se sobrescribió. |
| [Reanálisis del mismo smoke](../var/evidence/h13-outputs-1794933571099068000/reanalysis-1794933732548210000/report.json) | PASS con la corrección del analizador registrada en `analysis_correction`, sobre los mismos medios. |
| [Matriz de cuatro casos](../var/evidence/h13-outputs-1794933990447407000/report.json) | Control/lifecycle PASS en `smoke`, `production`, `receiver-loss` y `muxer-loss`; 11 de 12 medios pasan su análisis. Resultado global **FAIL**, con un defecto de continuidad de audio pendiente. |

La matriz demuestra dos salidas con perfiles separados, parada/reentrada de RTMP
mientras MKV continúa, parada de MKV mientras RTMP continúa, pérdida real del
receptor y terminación del muxer propio con recuperación explícita del destino.
El caso `production` incluye Cut/Fade, edición de lower third, countdown/alerta y
gain/mute. Los transcripts incluyen operaciones CLI y MCP. Esto no acredita
interacción GPUI ni una sesión prolongada de producción.

El fallo retenido es `smoke-recording`: una ventana PCM de 100 ms centrada en
0,35 s mide −34,0759 dBFS frente a −33,0103 dBFS esperados. El diagnóstico
identificó un hueco real de aproximadamente 1024 muestras cerca de 0,32 s.
La corrección posterior del tono se documenta en
[investigación de arranque](h13-audio-startup-investigation.md). No se ensancha la tolerancia ni se
convierte el resultado global en PASS por haber pasado el control de estados.
Los archivos parciales de los casos con fallo intencional se identifican como
tales; que decodifiquen no acredita cierre limpio de esos destinos fallidos.

La repetición completa sin diagnóstico **PASS** corresponde al bundle
`0444029860e28e53b7e74fc0ab836fa790cc8a691f2f7cfc95702cd9e6ac3952` y al
[nuevo informe](../var/evidence/h13-outputs-1794935484169154000/report.json):
cuatro casos y doce medios, con los umbrales originales. No reemplaza los
informes fallidos anteriores. Quedan gates de GPUI, handshake/cierre dual,
sesión prolongada, comparación de carga y regresiones completas. Cada gate
se cerrará con evidencia del binario integrado final.

### Secuencia de integración

1. Tipos, registro nativo, consultas por destino, guards conjuntos y wrappers.
   Pruebas de validación/compatibilidad; una sola salida conserva H7/H8.
2. Primer MKV + RTMP concurrente con patrón móvil y tono, antes de incorporar
   dispositivos. Decodificar ambos y verificar parada en ambos órdenes.
3. Fallos parciales reales, recovery por destino, handshake pendiente y cierre.
4. Escenas, Cut/Fade, overlays, mixer y captura del sistema en la misma sesión;
   completar contratos y controles GPUI, sin lógica duplicada.
5. Duración, calidad/perfiles distintos, GPUI como operador y regresiones.

Ningún paso se acredita solamente con `ok`, `started`, un mock o un snapshot.
La aprobación de este documento no reemplaza los gates físicos.

### Preparación reproducible

- Adquirir el lock físico **compartido y canónico entre worktrees**, registrar
  owner/PID/worktree y coordinar el bundle firmado. H10 documentó
  `var/run/physical-test.lock`; no crear locks distintos con el mismo nombre
  dentro de cada worktree y asumir exclusión. Resolver la ubicación compartida
  antes de ejecutar; un lock antiguo no es permiso para interrumpir otro ensayo.
- Fijar commit, estado del árbol, hash del ejecutable, firma, versiones OBS y
  FFmpeg, hash de scripts, canvas, perfiles, dispositivos explícitos y PID.
  No reconstruir ni cambiar el bundle durante una ejecución.
- Guardar evidencia bajo un directorio nuevo `var/evidence/h13-outputs-<id>`;
  incluir solicitudes/respuestas, tiempos monotónicos, medios, logs controlados
  y hashes. Restaurar solo la configuración de prueba que el ensayo cambió.
- Preparar endpoint con puerto libre y receptor FFmpeg propio en `127.0.0.1`.
  Esperar listener por PID/puerto, sin abrir una conexión de prueba que consuma
  la única aceptación del receptor. Conservar cada tramo de streaming aparte.

### Matriz mínima de ensayos

| Caso | Secuencia y gate |
|---|---|
| D1: coexistencia | MKV, esperar active, iniciar RTMP, mantener ambos ≥15 s. Un PID/graph; instancias visuales/audio constantes; ambos H.264/AAC decodificables. |
| D2: orden inverso | RTMP primero, MKV después; detener MKV, RTMP continúa ≥5 s; después detener RTMP. No reinicio de encoder/captura del superviviente. |
| D3: reentrada RTMP | MKV continua; detener RTMP, esperar barrera, nuevo receptor, recuperar si hubo fallo y arrancar otra vez. MKV contiene ambos tramos sin hueco interior. |
| D4: red fallida | Terminar solo el receptor propio; streaming falla y drena, MKV sigue ≥5 s; recovery/start explícitos. No reconexión automática. |
| D5: muxer fallido | Terminar solo el helper MKV identificado; RTMP sigue ≥5 s, recording falla y permite recovery/start dirigido. Conservar MKV parcial. |
| D6: arranque rechazado | Con un destino activo, provocar fallo validado del otro; cero cambios de recursos/perfil/contadores del sano, salvo avance natural. |
| D7: handshake | Receptor silencioso/demorado propio; seis cancels rápidos, salida restante continua; ni recovery ni reset prematuros. Esperar barrera H8 real. |
| D8: shutdown | Ambos activos, y caso MKV activo + RTMP conectando. Cmd+Q/cierre y API; no “finalizado” mientras haya workers, PID termina después de barreras. |
| D9: producción | Dos escenas, Cut/Fade, lower third editado, countdown/alerta, gain/mute. Ambos medios muestran los mismos eventos durante el solapamiento. |
| D10: contratos | Repetir controles por CLI y MCP; enums/argumentos extra inválidos; wrappers antiguos exclusivos; stop ambiguo no altera ningún slot. |
| D11: restauración | Guardar/cargar stores y reiniciar mientras idle; IDs y perfiles preservados, cero salidas autoarrancadas, proyectos antiguos legibles. |
| D12: duración | ≥30 min representativos a 1080p30 con ambos outputs y eventos periódicos; CPU/RSS, contadores y media completa conservados. 1080p60 requiere ensayo propio. |

D6 no se limita a afirmar aislamiento a partir de una validación JSON: incluir
al menos un fallo real de recursos/preparación si puede inducirse con seguridad.
Si no es reproducible, dejar ese subcaso pendiente; D5 cubre fallo real durante
grabación, no prueba agotamiento de disco ni imposibilidad de crear el archivo.

### Fallo MKV controlado sin abrir capacidades externas

Reutilizar el método de `scripts/verify_output_recovery.py`: con recording y
streaming activos, buscar el único hijo directo `obs-ffmpeg-mux` del PID del
estudio que está bajo prueba. Revalidar PID padre, ejecutable del bundle propio
y correspondencia con el MKV observado inmediatamente antes de enviar SIGTERM.
Si hay cero o varios candidatos, fallar el ensayo; nunca señalizar por nombre
global ni matar el proceso Motive. Registrar PID/helper, momento del fallo y
estado de ambos destinos. El receptor RTMP es otro proceso propiedad del ensayo.

Ese mecanismo provoca una pérdida real del muxer; no debe presentarse como
prueba de disco lleno, retirada de volumen o permisos. No llenar el disco de la
máquina ni tocar permisos globales. No añadir a MCP rutas arbitrarias, señales
de procesos, `fail_output` ni variables persistentes de fault injection.

Un segundo caso opcional puede verificar creación denegada con un directorio
`var/recordings` **exclusivamente de la fixture de este worktree**, ningún MKV
abierto y permisos originales registrados. Retirar temporalmente permiso de
escritura al directorio propio, intentar recording mientras RTMP continúa y
restaurarlo en `finally`. No hacerlo en un store compartido, con otro ensayo ni
con privilegios elevados; comprobar que macOS realmente denegó la creación.
Si esas precondiciones no se garantizan, omitir y documentar ese caso. No se
requiere cambiar el API de producción ni seleccionar un path externo.

### Análisis de medios y métricas

Decodificar cada MKV/segmento RTMP completo con FFmpeg, contar frames con
ffprobe, y verificar H.264, dimensiones/FPS reales, AAC 48 kHz estéreo. Inspeccionar
DTS por stream, PTS de video decodificado y cadencia AAC. Conservar los huecos
de cola separados de los interiores; no excluirlos del informe. Para FPS altos,
escalar el análisis de cadencia según `fps_num/fps_den`, no reutilizar umbrales
30 FPS que oculten frames perdidos. Mantener intactos los gates de suites viejas.

Los encoders independientes no generan archivos binariamente idénticos y cada
output empieza en un tiempo distinto. Comparar eventos visuales y señal conocida
en el intervalo común, alineados por marcadores decodificados. Registrar el
desfase y cómo se midió. No comparar el segundo cero de ambos archivos como si
fuera el mismo instante. El polling 4 Hz y frames/FPS sirven para asociar etapas,
no para afirmar sincronización A/V exacta a una muestra. Medir A/V con marcadores
de la fixture y declarar su incertidumbre antes de juzgar el resultado.

Medir gain/mute y presencia de frecuencias conocidas en ambas salidas. Comparar
RMS nativo y decodificado con el mismo estadístico e intervalo, siguiendo H12;
conservar el margen H10 en sus regresiones. Exigir cero bloques nativos de
clipping inesperado durante la aceptación y registrar peak decodificado, sin
suponer que AAC reproduce exactamente el peak de entrada. Audio continuo debe
demostrarse también en el output superviviente alrededor de cada start/stop/fallo.

Registrar deltas de render lag, drops y skips desde antes de preparar la segunda
salida; registrar también el periodo estable para distinguir arranque y carga
sostenida. Comparar CPU/RSS con el mismo canvas, fuentes, visibilidad y perfiles:
un output contra dos, en orden alternado. No atribuir mejoras a App Nap/Metal/VT
ni reducir gates a partir de un único ensayo. Conservar resultados fallidos.

### Reutilización de scripts existentes

| Archivo | Reutilizar / adaptación necesaria |
|---|---|
| `h7_support.py` | Cliente MCP, captura de operaciones, `process_sample`. `stop`, `measure` y `media` asumen singleton y 30 FPS: crear variantes H13 o parámetros con defaults antiguos intactos. |
| `verify_rtmp.py` | Receptor propio, espera listener, rechazo/desconexión y perfiles. Sus asserts de una salida y FPS fijos son regresiones históricas, no el nuevo ensayo dual. |
| `verify_output_recovery.py` | Fallo real del hijo muxer. Ampliar en suite nueva con identificación reforzada y prueba del RTMP superviviente. |
| `verify_h8_lifecycle.py` | Pares silenciosos, proxy demorado, repetición de cancel, shutdown; ejecutar serialmente. No importar directamente: actualmente ejecuta trabajo al cargar el módulo. |
| `verify_h9_transitions.py` / `verify_h9_faults.py` | Fixtures de escenas y fallos destino/compartido; adaptar observación de ambos destinos conservando assertions H9. |
| `verify_h10_audio.py` / `verify_h10_mixer.py` | Estímulo, amplitud tonal, RMS por bloques, mute/gain, persistencia y PTS. No mezclar estadísticos para hacer pasar micrófono variable. |
| `observe_h12_native.py` | Observador pasivo, timestamps, origen UI, transcript acotado. Añadir registro por `(pid,target,attempt_id)` y mantener simultáneas las dos muestras. |
| `verify_h12_native_media.py` | Decode, DTS/PTS, audio, ROI, estabilidad de instancias. Hoy fija 960×540/30 y campos singleton: parametrizar geometría/ROI/FPS y alinear cada medio. |
| `verify_h12_performance.py` | Sampler macOS `proc_pidinfo` 20 Hz y comprobación contra `ps`; conserva límites de muestreo y separación de carga estable/picos. |
| `verify_h12_regressions.py` | Manifiesto serial de 22 suites y hash del bundle. No adquiere lock por sí solo: requiere dueño externo. Añadir H13 aparte sin reemplazar gates previos. |

La aceptación final incluye controles GPUI para ambos destinos y evidencia de
`last_action` originada en UI, con CLI/MCP como observadores. La paridad de los
comandos CLI/MCP se verifica en otra etapa explícita. No declarar integración
GPUI completa a partir de una ejecución realizada solamente por terminal.

## 10. Contrato de integración GPUI

`src/ui/studio/outputs.rs` presenta el registro compartido obtenido mediante
`Production::status()` y envía los mismos `Command` por `Studio::command` con
origen `UI`. No conserva un segundo estado de salida, no consulta dispositivos,
no crea workers ni llama directamente a libobs. `chrome.rs` compone los controles
de cabecera; `panels.rs` enruta el panel Salidas; `forms.rs` usa la confirmación
existente ligada a revisión. `mod.rs` declara el módulo. El aviso sobre el canvas
abre Salidas para resolver el destino correcto; el indicador live de escenas
consulta las fases del registro y admite ambos destinos activos.

| Control / sección | API exacta y presentación |
|---|---|
| **Grabar** | `Command::StartOutput { target: OutputTarget::Recording }`; CLI/MCP `start_output` con `target: "recording"`. |
| **Transmitir** | `Command::StartOutput { target: OutputTarget::Streaming }`; CLI/MCP `start_output` con `target: "streaming"`. Reutiliza el receptor local configurado. |
| Botón de un destino activo / **Detener** | `Command::StopOutputTarget { target }`, `stop_output_target`; confirmación nombra únicamente ese destino. El otro continúa. |
| **Cancelar inicio** | `Command::CancelOutputTarget { target }`, `cancel_output_target`; pide cancelación segura durante `starting`/`connecting`. El estado sigue ocupado hasta la barrera real. |
| **Recuperar REC/RTMP** | `Command::RecoverOutputTarget { target }`, `recover_output_target`; habilitado para fallo terminal sin `native_busy`. No arranca otra salida automáticamente. |
| **Detener todas las salidas** | `Command::CancelAllOutputs`, `cancel_all_outputs`; visible al principio del panel. Confirma ambos destinos y conserva abierto el estudio. |
| **Comprobar** por destino | `Command::PreflightOutput { target }`, `preflight_output`; comprueba configuración y readiness, sin abrir conexión ni prometer entrega de medios. |
| Tarjetas **Grabación MKV / Transmisión RTMP local** | `outputs.recording` / `outputs.streaming`: fase, fallo estructurado y código nativo si existe, intento, duración, perfil usado, encoder/fallback, dimensiones/FPS, bytes, frames y drops. Identifica UDP heredado cuando `kind: "local_stream"`. |
| **Receptor de transmisión** | `ConfigureStream`, `SelectStreamCredential`, `CredentialStatus`; formularios existentes ligados a revisión. Configuración y vinculación solo con ambas salidas detenidas. Nunca muestra una clave. |

Mientras hay cancelación o drenaje, el control muestra **Finalizando** y no
permite iniciar ni recuperar el slot. `cancel_deferred` muestra que la conexión
aún tiene trabajo pendiente. Un error de un destino no deshabilita por sí mismo
el arranque/control del otro; la validación final pertenece siempre al núcleo,
incluidos fallos compartidos, shutdown o un cambio ocurrido entre render y click.

El tiempo se formatea exclusivamente desde `outputs.<target>.active_duration_ms`.
No se usa `frames / 30`, un cronómetro GPUI ni timestamps de recepción MCP. Al
detenerse, la tarjeta conserva la duración y el snapshot del intento hasta el
siguiente arranque. El perfil seleccionado para el próximo intento se muestra
separado del perfil realmente utilizado. La cabecera y el canvas ya no atribuyen
`encoding: null` o métricas legacy agregadas a un destino cuando hay dos salidas.

La implementación de UI pasó revisión estática, `rustfmt` y `git diff --check`.
Esto **no** acredita build ni aceptación visual/nativa. Pendiente sobre el bundle
final: layouts 1024×780 y 1440×980; ambos inicios por click; detener cada destino
manteniendo el otro; error y recovery dirigidos; cancelación pendiente; detener
todo; cambios recibidos desde MCP con el panel abierto; confirmación obsoleta
rechazada; y evidencia `origin: UI` correlacionada con los medios decodificados.
Los handlers heredados ambiguos `StartRecording`, `StartStream`, `StopOutput`,
`CancelOutput` y `RecoverOutput` ya no se utilizan desde esta presentación.

## 11. Fuentes oficiales

- [API Output](https://docs.obsproject.com/reference-outputs): inicio asíncrono,
  encoders asignados y finalización de captura.
- [API Encoder](https://docs.obsproject.com/reference-encoders): propiedad y
  configuración de los encoders.
- [OBS 33.0.1 obs-output.c](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs-output.c):
  referencias, interleaver y retirada de suscripciones por output.
- [OBS 33.0.1 obs-encoder.c](https://github.com/obsproject/obs-studio/blob/33.0.1/libobs/obs-encoder.c):
  múltiples callbacks, reloj absoluto y propagación de `full_stop`.
- [OBS 33.0.1 AdvancedOutput.cpp](https://github.com/obsproject/obs-studio/blob/33.0.1/frontend/utility/AdvancedOutput.cpp):
  precedente oficial de compartir encoder de streaming con grabación.
