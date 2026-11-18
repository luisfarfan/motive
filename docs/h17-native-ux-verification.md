# H17 — feedback y confirmación en accesibilidad nativa

Estado inicial: **PARTIAL**. Este informe recoge dos defectos AX observados en
B7 y una corrección focalizada pendiente de inspección en B8. No certifica el
recorrido completo de UX, teclado o VoiceOver.

## Evidencia B7

Proceso observado: PID `59478`; ejecutable B7 SHA-256
`d5b702d8b245a143575a6dd77cc80dc047425139f0ebc16db8c1f8451eb0ad31`.
La identidad está en `var/evidence/h17-native-b7/ready.json`. Las capturas
corresponden al estudio nativo y contenido controlado. Se conservan sin editar.

| Hallazgo | Resultado B7 | Evidencia |
|---|---|---|
| Guardar proyecto muestra feedback sin texto AX | **FAIL** | `02-project-save.png` muestra «UI · save_project · revisión 3» en el pie y el popover. `02-project-save.ax.txt` expone botones/campos, pero no ese texto. |
| Confirmar restauración omite título y alcance en AX | **FAIL** | `03-restore-confirm.png` muestra «Confirmar operación» y «Restaurar el proyecto guardado y reemplazar la composición actual.». `03-restore-confirm.ax.txt` contiene el diálogo y Cancelar/Confirmar/Close, sin el título ni el cuerpo. |

SHA-256 de los archivos de `var/evidence/h17-native-b7/`:

| Archivo | SHA-256 |
|---|---|
| `02-project-save.png` | `58d4e6bc673b8b22fe9d4167b6938a0586a34d1c8bd5ca9bd3c0c5435c361d6e` |
| `02-project-save.ax.txt` | `b79e52743270dd2e21f678c0e4fc30393947caa2a702e7ce192b4ced94c14aa1` |
| `03-restore-confirm.png` | `c00c28a9ed3bfee37941ad3522a4bde0695c144b4f220b21791263a67a067e52` |
| `03-restore-confirm.ax.txt` | `6a70a97781c7c7b28e79910619ee5e01b61da86b7221ded28545d45256580746` |

El recibo durable de Show Control visible pero ausente del árbol AX ya estaba
registrado en [H15](h15-native-ux-verification.md). Las dos observaciones B7
anteriores prueban feedback de proyecto y confirmación; no se presentan como
una nueva observación del recibo de Show Control.

## Causa y cambio focalizado

`src/ui/components.rs:label` añade un `SharedString` como hijo de un `Div`.
En GPUI-pre 0.3.12 ese elemento no tiene ID ni rol accesible. Por ello se pinta
sin aportar un nodo AX. El título y el cuerpo de `confirm_command` también
eran cadenas directas.

El helper nuevo `feedback_label` conserva tamaño, color y contenedor, y usa
`Text::new` con un ID explícito estable. Se aplica solamente al feedback del
pie, su copia del panel y cuatro estados de Show Control: armado, recibo de
guardado, error de guardado y fallo de runtime. Cada sitio tiene un ID distinto
que permanece cuando cambia el contenido. El diálogo genérico de confirmación
usa el mismo tipo de texto para su título y cuerpo, conservando los guards de
revisión, botones y callback existentes.

La API instalada en GPUI-pre 0.3.12 y GPUI-fast 0.1.17 publica `Role::Label`
y el contenido como `value`. AccessKit macOS 0.26.3 lo convierte en
`AXStaticText` y `AXValue`. Referencias de código instalado: `elements/text.rs`,
`_accessibility.rs`, y el test de Kit 0.10.0
`tests/integration/painted_text.rs:labels_expose_their_text_to_assistive_technology`.
Los IDs no derivan del contenido; tampoco se utiliza una única invocación de
`text!` dentro del helper, que repetiría la identidad entre varios textos.

No cambia el helper `label` general ni se añaden foco, acciones, temporizadores
o anuncios automáticos. La lectura AX de estos textos no equivale a probar
anuncios de VoiceOver.

## Verificación

- Compilación predeterminada: **PASS**, `cargo check --locked --release`,
  30,41 s. Fast: **PASS**, `cargo check --locked --release --features gpui-fast
  --target-dir target/h17-gpui-b`, 27,37 s. Logs y comando/exit code/tiempo
  separados en `var/evidence/h17-ax-build-01/default.{log,json}` y
  `fast.{log,json}`. Estos checks no abrieron la app.
- `cargo fmt --all -- --check` y `git diff --check`: **PASS**, logs y resultados
  en el mismo directorio. Ocho IDs explícitos distintos en los ocho sitios
  modificados, comprobados en el diff.
- Inspección nativa B8 del feedback, recibo, error y confirmación:
  **NOT_EVALUATED**. Comparar imagen y árbol AX; comprobar que recibo 1→2
  actualiza el texto sin duplicar nodos y que Cancelar no aplica el comando.
- Recorrido completo de teclado y VoiceOver: **NOT_EVALUATED**.

Los fallos B7 permanecen como evidencia del candidato B7. Un check de Cargo
no los convierte en PASS ni certifica la presentación del candidato siguiente.
