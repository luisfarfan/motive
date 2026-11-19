# H17 — recorrido nativo, feedback y accesibilidad

Estado: **PARTIAL**. Se ejecutaron recorridos nativos B7, B8 y B9, con mejoras
AX verificadas en los sitios indicados abajo. No es una certificación completa
de accesibilidad, teclado o VoiceOver. Los FAIL históricos permanecen; las
mejoras de UI no resuelven los gates de captura ni aceptan la beta.

## Identidad y alcance

| Candidata | Owner observado | Ejecutable SHA-256 |
|---|---:|---|
| B7 | 59478 | `d5b702d8b245a143575a6dd77cc80dc047425139f0ebc16db8c1f8451eb0ad31` |
| B8 | 50376 | `5cc0fe08c54f7f4d5e166bce18dbe515a31c92ab92793f3c406e94a42fdc3059` |
| B9 | 71295 | `7ecf6b28288fed4cc7121d755b435310a59d80ced8268475e8c884e8d0576e24` |

Las identidades y estados iniciales están en
`var/evidence/h17-native-{b7,b8,b9}/ready.json`. Cada directorio conserva
capturas PNG, árboles AX, `changes.jsonl`, operaciones del observador y su
estado final. Los controles de producto se operaron desde la UI nativa; los
observadores consultan el owner real y no prueban por sí solos la presentación.
Algunos archivos AX son diffs del árbol anterior, identificados como tales;
no se interpretan como inventarios completos. No se repiten aquí identidades
de dispositivos ni datos personales presentes en los artefactos locales.

## Recorrido B7

Los números de captura siguientes pertenecen a `h17-native-b7/`. El estado
funcional de cada paso se separa de los defectos AX y de la aceptación de medios.

| Paso | Resultado funcional | Evidencia y límite |
|---|---|---|
| 1. Abrir estudio | PASS | `01-open`: preview y controles, revisión 2, outputs idle. |
| 2. Guardar proyecto | PASS | `02-project-save`, revisión 3; texto visible, AX FAIL descrito abajo. |
| 3. Restaurar proyecto | PASS | `03-restore-confirm`; observador registra `UI · load_project`, revisión 4. Título/cuerpo AX ausentes en B7. |
| 4. Añadir fuente propia | PASS | `04-source-audio` y revisión 5: patrón agregado; no se atribuye esta prueba a captura de ventanas de terceros. |
| 5. Configurar audio | PASS | Tono controlado; mute/unmute en revisiones 9/10 y gain posterior desde UI. No equivale a prueba de micrófono. |
| 6. Cambiar video | PASS | `05-video-preflight`; revisión 11, 1280×720 a 30 FPS. |
| 7. Revisar perfiles/preflight | PASS | `06-output-profiles` y `07-recording-preflight`; perfil actualizado en configuración activa, revisión 12. No se acredita persistencia del perfil; preflight no demuestra entrega. |
| 8. Preparar destino local | PASS | `UI · configure_stream`, revisión 13; receptor loopback controlado. Sin emisión pública. |
| 9. Revisar e instalar MATCHDAY | PASS | `08-matchday-review` y `09-matchday-installed`: 73/73 pasos, 4 escenas, 12 fuentes y 23 capas del pack. Revisión AX FAIL; texto inferior requiere scroll. |
| 10. Guardar proyecto y reglas | PASS | Proyecto revisión 103; `10-durable-show-save`, recibo 1/revisión 103 y 7241 bytes durables. Recibo AX ausente en B7. |
| 11. Grabar/transmitir y cambiar escena | PASS | `11-dual-live-deck`; ambos slots active y selección de escena en revisión 110. Aceptación multimedia PARTIAL abajo. |
| 12. Usar Live Deck y editar gain | PARTIAL | `12-gpui-goal-gain`; un job completado y contador goals=1. Edición dentro de stock450 NOT_OBSERVED. |
| 13. Detener y abrir grabaciones | PASS | `13-stopped`, `14-recordings`; grabación se detiene antes de streaming, ambos acaban idle. Biblioteca presenta el archivo, sin certificar su contenido. |
| 14. Guardar, cerrar y reabrir | PASS | Guardados de proyecto/mixer en revisiones 126/127; owner exit 0. `15-reopened-project` y `reopen/restored.json`: nuevo PID 49482, proyecto a 720p30 restaurado, outputs idle. `reopen/cleanup.json` confirma cierre normal. No se afirma restauración automática del mixer o de reglas. |

El recibo B7 de reglas y los dos recibos B8 contienen el mismo documento de
7241 bytes, SHA-256
`c217f2f609fc8436bbb092ab6e49da5bc3896ac972af4bac12120a16bc67661a`.
El observador conserva `durable: true`; este informe no modifica stores ni
journals. Los reports de wrappers B7/B8/B9 registran `owner_exit: 0`,
`suite_exit: 0` y `cleanup_errors: []`. El observador B8 terminó antes de la
salida (`observed_owner_exit: false`); allí la prueba del cierre es el wrapper,
no ese campo del observador. B7 y B9 sí observaron la salida del owner.

Después de cerrar los owners, la [verificación de preservación](../var/evidence/h17-store-preservation/restored-after-native-ui.json)
confirmó **PASS**: cinco stores recuperaron sus bytes/ausencia originales y
los 22 archivos de journal permanecieron intactos. `output-profiles.json`
estaba ausente en el estado original y volvió a quedar ausente; el paso 7
anterior sólo demuestra configuración activa.

## Defectos AX conservados de B7

| Hallazgo | Resultado B7 | Evidencia |
|---|---|---|
| Guardar proyecto muestra feedback sin texto AX | FAIL | `02-project-save.png` muestra «UI · save_project · revisión 3» en pie y popover. `02-project-save.ax.txt` expone botones/campos, pero no ese texto. |
| Confirmar restauración omite título y alcance en AX | FAIL | `03-restore-confirm.png` muestra «Confirmar operación» y el alcance de restaurar. Su AX contiene diálogo y Cancelar/Confirmar/Close, sin título/cuerpo. |
| Revisar instalación y recibo de reglas omiten texto AX | FAIL | `08-matchday-review` muestra título/alcance pero AX solo botones; `10-durable-show-save` muestra recibo 1 sin ese texto en AX. Guardar queda bajo la tarjeta y requiere scroll. |

SHA-256 de los archivos iniciales de `var/evidence/h17-native-b7/`, conservados:

| Archivo | SHA-256 |
|---|---|
| `02-project-save.png` | `58d4e6bc673b8b22fe9d4167b6938a0586a34d1c8bd5ca9bd3c0c5435c361d6e` |
| `02-project-save.ax.txt` | `b79e52743270dd2e21f678c0e4fc30393947caa2a702e7ce192b4ced94c14aa1` |
| `03-restore-confirm.png` | `c00c28a9ed3bfee37941ad3522a4bde0695c144b4f220b21791263a67a067e52` |
| `03-restore-confirm.ax.txt` | `6a70a97781c7c7b28e79910619ee5e01b61da86b7221ded28545d45256580746` |

El recibo visible pero ausente de AX ya estaba registrado en
[H15](h15-native-ux-verification.md); B7 conserva una nueva observación del
mismo problema. El recorte inferior de la revisión MATCHDAY y el scroll
necesario para descubrir Guardar no se presentan como resueltos por añadir
texto accesible.

## B8: recibos, teclado y VoiceOver

`02-confirm-accessible.{png,ax.txt}` muestra título y alcance de la restauración
general en imagen y AX: **PASS** del texto. Enter confirmó restaurar el
proyecto; `changes.jsonl` registra revisión 15 y 15 fuentes a 720p30.
`04-receipt-update-accessible` muestra recibo 2/revisión 16 en AX y pantalla,
con feedback tanto en el panel como en el pie. Los snapshots conservan la
secuencia 1→2 sin cambio de revisión y `last_save_error: null`: **PASS** de
actualización de recibo. La repetición del texto en pie y panel corresponde a
dos lugares visibles, no a duplicación accidental de un mismo nodo.

`03-show-restore-review` conserva otro **FAIL** B8: título y cuerpo de
«Restaurar Show Control» visibles, pero solo botones en AX. El armado real
posterior (`armed: true`, `bindings_current: true`, jobs vacíos) mostraba
correctamente el estado del deck; el feedback general volvía a la acción
anterior `load_project`. Ambos sitios se corrigieron y se verificaron en B9.

En `voiceover-before.ax.txt`, `voiceover-on.ax.txt` y `voiceover-off.ax.txt`,
el control de Configuración del Sistema pasa **off→on→off**. Se restauró el
estado inicial. Durante la sesión, el usuario confirmó: «Sí, escuché texto de
restauración». Esto es **PASS** para esa lectura confirmada, con aceptación
VoiceOver global **PARTIAL**: no acredita anuncios automáticos de recibos,
lectura de todos los paneles ni navegación completa.

Enter y Escape tienen resultados funcionales observados, pero los snapshots
tras Tab/Shift+Tab no demuestran foco AX en los controles: reportan la ventana
como elemento enfocado. El recorrido integral de teclado queda **PARTIAL**;
no se deduce orden de foco correcto de la presencia de botones en AX.

## B8: hardware autorizado y medios reales

`05-camera-admission` conserva el intento en el picker; no prueba admisión y
no se convierte en PASS por un clic fuera de viewport. `06-camera-integrated`
y `07-camera-preview`, junto con el cambio a 16 fuentes, prueban la admisión
posterior desde UI. `08-hardware-recording`, `09-microphone-muted`,
`10-hardware-recording-stopped`, `hardware-live.json` y `hardware-stopped.json`
vinculan cámara y micrófono seleccionados explícitamente con grabación, mute,
cambio de gain mientras estaba silenciado, unmute y parada. Las identidades
de dispositivos permanecen únicamente en evidencia local.

El [informe de medios B8](../var/evidence/h17-native-b8/media-analysis/review.md)
es **PARTIAL**: decode estructural **PASS**, H.264 1280×720/30 FPS, AAC stereo
48 kHz, 2705 frames decodificados y 4228 paquetes AAC, sin clipping digital.
El interior del intervalo mute está en silencio; la latencia exacta y la
atenuación calibrada no están evaluadas. La botella de primer plano se retiró
entre el preview y la grabación, no durante la grabación. El patrón animado
y la cadencia del encoder no prueban frescura de cámara a 30 FPS. Persiste
un paquete de video nativo sin correspondencia en el contenedor; no se
certifica entrega completa ni se transcribe/escucha audio en este análisis.

## B9: regresión focalizada y cierre

| Observación | Resultado | Evidencia en `h17-native-b9/` |
|---|---|---|
| Confirmación general y Enter | PASS | `01-project-restore`: título/cuerpo AX; restore registrado en revisión 15. |
| Restaurar Show Control: título y alcance | PASS | `02-show-restore-confirm`: texto visible y AX. Escape cerró la primera revisión sin aplicar restore ni cambiar revisión 15; la restauración posterior sí crea sesión desarmada en revisión 16. |
| Restauración desarmada | PASS | `03-show-restored-disarmed`, snapshots `armed: false`, jobs vacíos; botones del deck disabled y Activar disponible. |
| Armado explícito y feedback | PASS | `04-arm-feedback`: revisión 17, `armed: true`, bindings actuales, jobs vacíos; «Producción activada» en estado, panel y pie, con Activar disabled. |
| Confirmación de cierre durante REC | PASS | `07-shutdown-confirm`: título y alcance en AX. «Finalizar y salir» termina owner PID 71295 con exit 0 y cleanup vacío; sin reapertura automática. |

Los otros diálogos corregidos por la causa común —acción sensible de Live
Deck y revisar/eliminar/iniciar destino RTMPS— tienen verificación de código
y compilación; su recorrido AX/VoiceOver específico queda **NOT_EVALUATED**.
La [revisión de medios B9](../var/evidence/h17-native-b9/media-analysis/review.md)
registra decode estructural **PASS** y entrega **PARTIAL**: 5715 frames
decodificados frente a 5716 observados, y 8931 paquetes AAC en ambos lados.
La hoja de contacto muestra aparición y retiro del gol; no prueba el gate
stock450. El [informe de outputs/audio](h17-output-audio-verification.md)
conserva el análisis completo y las limitaciones de atribución al cierre.

## Medios B7 y gate stock450

El [análisis B7](../var/evidence/h17-native-b7/media-analysis/visual-review.md)
conserva **PARTIAL**, con decode completo de REC y RTMP **PASS**: 3689/3873
frames de video, 5765/6053 paquetes AAC, H.264 720p30 sin B frames, PTS/DTS
monótonos y sin clipping digital. Las hojas de contacto muestran cambio a
MATCHDAY y la alerta GOOOAL en ambas salidas. Son muestras visuales, no una
medición de geometría por frame. Quedan diferencias de contadores y no hay
traza completa que las localice; el receptor con exit 0 no acredita entrega
íntegra.

`h17-native-b7/stock450-race/report.json` y
`h17-native-b9/stock450/report.json` conservan **PARTIAL**, gate
`NOT_OBSERVED`. En ambas tomas hay operación 1 realmente running, duración
450 ms y widget ya activado antes del intento; `pending_after_ui` es null.
La edición de gain observada llegó después del terminal. El job termina una
vez, cursor 2 y goals=1, sin probar el solapamiento solicitado.

En B9, el primer atajo Alt+G con foco reportado en la ventana no creó evento;
no se atribuye a un fallo del atajo dentro de Live Deck, cuyo foco no quedó
demostrado. El botón posterior sí creó el job. `05-stock450-gain.png` no
muestra el gol; `06-stock450-buttons.png` muestra GOOOAL y gain 0 dB. Ver ambos
no prueba que la edición sucediera durante los 450 ms. Tras dos tomas sin
solapamiento, no se amplió la duración ni se repitió hasta obtener un PASS.

## Causa y cambio focalizado

`src/ui/components.rs:label` añadía un `SharedString` como hijo de un `Div`.
En GPUI-pre 0.3.12 ese elemento no tiene ID ni rol accesible: se pinta sin
aportar nodo AX. Los títulos y cuerpos de confirmación eran cadenas directas.

`feedback_label` conserva tamaño, color y contenedor, y usa `Text::new` con
ID explícito estable. Se aplica al pie, su copia del panel y cuatro estados
Show Control: armado, recibo, error de guardado y fallo de runtime. La misma
API cubre título/cuerpo en los ocho sitios de confirmación inventariados:
general, MATCHDAY, restaurar reglas, acción sensible, tres de destinos y
cierre. Cada sitio mantiene un ID distinto cuando cambia el contenido.
Se conservan guards de revisión, botones, callback y scroll. El handler de
armado solo reemplaza el mensaje general cuando `ArmShowControl` responde
`ok: true`; no modifica ledger, revisión ni origen.

GPUI-pre 0.3.12 y GPUI-fast 0.1.17 publican `Role::Label` y contenido como
`value`; AccessKit macOS 0.26.3 lo convierte en `AXStaticText`/`AXValue`.
Referencias instaladas: `elements/text.rs`, `_accessibility.rs` y el test
Kit 0.10.0 `labels_expose_their_text_to_assistive_technology` en
`tests/integration/painted_text.rs`. La identidad no deriva del contenido ni
de una única invocación de `text!` compartida por todo el helper.

No se cambia el helper `label` general ni se añaden foco, acciones,
temporizadores o anuncios automáticos. Presencia AX no equivale a anuncio
VoiceOver de cada actualización.

## Checks y límites restantes

- Check predeterminado **PASS**: `cargo check --locked --release`, 30,41 s.
  Fast **PASS**: `cargo check --locked --release --features gpui-fast
  --target-dir target/h17-gpui-b`, 27,37 s. Comandos, exit codes y logs en
  `var/evidence/h17-ax-build-01/`; estos checks no abrieron la app.
- MATCHDAY, inventario de confirmaciones y feedback de armado: checks
  predeterminados incrementales, formato y diff **PASS**, logs en
  `h17-ax-build-02/`, `-03/`, `-04/`. Inventario de ocho diálogos en
  `h17-ax-build-03/inventory.json`.
- Presentación AX de errores reales de guardado/runtime: **NOT_EVALUATED**;
  no se provocaron fallos de almacenamiento para probar su lectura.
- Teclado y VoiceOver completos: **PARTIAL**, con los límites anteriores.
- Stock450 GPUI: **PARTIAL / NOT_OBSERVED**. Cancelación física pre-tick sigue
  **NOT_EVALUATED** en este recorrido; el test CLI nativo pos-tick está
  separado en [Show Control](h17-show-control-verification.md).

Un check de Cargo no convierte un FAIL histórico en PASS ni certifica la
presentación del siguiente candidato. Los medios y snapshots originales se
conservan; este informe no extiende sus resultados a builds posteriores.
