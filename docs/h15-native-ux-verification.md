# H15 — recorrido nativo B4

**PARTIAL.** Auditoría de GPUI con Product Design audit y CUA, sobre contenido
propio. Binario B4 SHA-256 `add4032b359c92fd36782d2157a1f72aaccf55fb50839e2c018d2bab739ccfb2`.
PID 8439; reapertura núcleo PID 9922. No se abrió navegador ni dispositivo real.
Las capturas son los bytes de CUA guardados e inspeccionados; no son recreaciones.
El informe multimedia completo está en [aceptación H15](h15-beta-verification.md).

| Paso solicitado | Salud del recorrido nativo | Resultado observado |
|---|---|---|
| 1. Abrir Motive | PASS | Ventana, preview, capas y botones accesibles por nombre. Captura 01. |
| 2. Preparar cámara/ventana | BLOCKED | Cámara requiere supervisión; selector nativo de ventana no recorrido antes del bloqueo CUA. Ensayo físico de fixture por control separado, FAIL general de frescura. |
| 3. Agregar audio | BLOCKED | Mixer vacío y luego tono añadido por harness; no se atribuye ese alta a GPUI. Micrófono requiere supervisión. |
| 4. Elegir resolución | PASS | Clic 720p actualiza configuración y feedback. Captura 06. |
| 5. Preflight | PASS | Clic visible y resultado válido, sin afirmar entrega. Captura 07. |
| 6. Instalar MATCHDAY | PASS | Revisión/confirmación reales, 73/73 pasos. Capturas 02–03. |
| 7. Live Deck y guardar | PASS | Scroll y clic visible; recibo durable cotejado; gol real admitido. Capturas 04–05. |
| 8. Grabar | PARTIAL | Estado REC observado; inicio por harness, botón nativo de inicio pendiente. Captura 05. |
| 9. Transmitir | PARTIAL | Estado RTMP local observado; inicio por harness, botón nativo pendiente. Captura 05. |
| 10. Detener | PARTIAL | Harness detiene por barreras normales; UI vuelve a salidas detenidas. Captura 06. Clic de stop nativo pendiente. |
| 11. Revisar grabación | PARTIAL | Medios decodificados y hojas revisadas; Biblioteca nativa no recorrida por bloqueo CUA. |
| 12. Cerrar/reabrir/restaurar | PARTIAL | Núcleo nuevo restaura proyecto y reglas desarmadas; CUA no obtiene ventana para completar el diálogo nativo. |

## Capturas y hallazgos

### 1. Apertura

El estudio abre con preview, escena, capas y estados de salida legibles. Los botones principales tienen nombre AX. La captura no acredita navegación completa con teclado ni VoiceOver.

![1. Apertura](/Users/luisfarfan/Developer/products/motive-h15/var/evidence/h15-native-ui-b4/01-open.png)

### 6. Revisión de MATCHDAY

El diálogo informa recursos, presupuesto y alcance. La última línea del cuerpo queda cortada por el viewport inicial, aunque el footer y la confirmación permanecen visibles. Riesgo de lectura: la obligación de guardar queda al final. La captura conserva la ventana completa, incluido ese defecto del contenido.

![6. Revisión de MATCHDAY](/Users/luisfarfan/Developer/products/motive-h15/var/evidence/h15-native-ui-b4/02-matchday-review.png)

### 6–7. Instalación y guardado de proyecto

Instalación 73/73 con recursos creados y recibo UI de save_project, revisión 92. La tarjeta extensa desplaza Guardar Show Control fuera del área visible. Un clic AX fuera del viewport no produjo recibo; esa imagen no demuestra guardado de reglas.

![6–7. Instalación y guardado de proyecto](/Users/luisfarfan/Developer/products/motive-h15/var/evidence/h15-native-ui-b4/03-save-receipt.png)

### 7. Guardado durable

Después de desplazar el diálogo, Guardar es visible y responde con recibo 1/revisión 92. El verificador compara el SHA-256 de los bytes durables. Mejora comprobada: feedback específico sin depender de una nueva revisión. Riesgo AX: el texto del recibo visible no figura en el árbol inspeccionado; VoiceOver sigue pendiente.

![7. Guardado durable](/Users/luisfarfan/Developer/products/motive-h15/var/evidence/h15-native-ui-b4/04-durable-save.png)

### 7–9. Gol real con dos outputs

Clic GPUI de Celebración de gol: botón en curso, solicitud 1 y overlay GOOOAL visibles con REC y RTMP activos. El harness observa luego las dos acciones completas. Esto prueba la interacción; las hojas decodificadas separadas corroboran presencia/entrada/salida del banner, sin asegurar geometría de todos los frames.

![7–9. Gol real con dos outputs](/Users/luisfarfan/Developer/products/motive-h15/var/evidence/h15-native-ui-b4/05-gpui-goal-dual.png)

### 4 y 10. Resolución con salidas detenidas

El clic 720p cambia la cabecera y configuración a 1280×720 y deja feedback UI con revisión 224. Los controles de video estaban deshabilitados durante los outputs (captura 05). Las etiquetas 60 FPS candidato evitan afirmar un rendimiento no medido.

![4 y 10. Resolución con salidas detenidas](/Users/luisfarfan/Developer/products/motive-h15/var/evidence/h15-native-ui-b4/06-video-720p.png)

### 5. Preflight

El resultado explica configuración válida y que no abre conexión ni verifica el medio. La separación entre preflight y entrega es clara. El panel requiere scroll para llegar a este control; no se comprobó aún acceso equivalente por teclado.

![5. Preflight](/Users/luisfarfan/Developer/products/motive-h15/var/evidence/h15-native-ui-b4/07-preflight.png)

## Límites y prioridades de UI

1. **P1, feedback accesible:** conservar el recibo durable y exponer su texto/errores
   al árbol de accesibilidad; comprobar anuncios con VoiceOver. La ausencia en la
   captura AX es un riesgo observado, no una certificación de incumplimiento total.
2. **P2, scroll:** revisar lectura completa del diálogo de instalación y la
   descubribilidad de Guardar bajo la tarjeta. Confirmación y cierre siguen visibles;
   no se afirma que el scroll esté roto, pues sí funcionó en el panel.
3. **P1, cobertura restante:** completar los pasos BLOCKED/PARTIAL con teclado,
   foco y controles de biblioteca/outputs cuando se recupere CUA. No sustituir
   esas interacciones por comandos atribuidos a UI.

Después de la captura 07, CUA rechazó el índice de Cerrar y luego devolvió
`cgWindowNotFound`. El proceso seguía vivo y atendía CLI. Un rebinding y una
reapertura normal no recuperaron CUA: se detuvo el trabajo nativo, sin otro
mecanismo de inyección de eventos. No se diagnostica un crash de Motive a partir
de ese error del instrumento.

La restauración en proceso nuevo se verificó por CLI: cinco escenas, sesión
nueva, configuración desarmada, cero jobs y activación explícita. El feedback del
diálogo nativo, edición concurrente GPUI stock450, Tab/Shift-Tab/Enter/Escape,
atajos y VoiceOver permanecen pendientes. No se abrió cámara/micrófono real ni
se modificaron permisos. No hubo rediseño ni edición de artboards.

Evidencia estructurada: `var/evidence/h15-native-ui-b4/notes.json`,
`reopen-core-report.json`, `decoded-visual-review.json`, `store-restoration.json`.
Todas las instancias propias se cerraron; los stores originales se restauraron
por hash. Las grabaciones y el journal de prueba se conservan.
