# H12 — revisión visual y de uso nativo

Revisión del bundle H12 firmado `dfbfc652…5126f`, 17 de noviembre de 2026.
Referencia aprobada: `design/screens/phase-1/01-studio-live.png`, 1440×900.
Se inspeccionaron los PNG guardados exactos, además de operar GPUI. No se alteraron
los artboards. Contenido propio de prueba; no se comparan las imágenes del programa
como si fueran los recursos de la referencia.

## Evidencia y recorrido

| Paso | Evidencia local en `var/evidence/h12-ui/` | Resultado |
| --- | --- | --- |
| 1. Crear/editar/animar texto | 01–04; grabación incremental de 105,733 s | Flujo operativo; se movió Aplicar y recibo/Cancelar al inicio del inspector |
| 2. Importar video | `05-video-imported.png`, estado worker #1 | Solo se anuncia disponible después de `completed` |
| 3. Producción integrada clara | `06-native-recording-light.png` | Preview, escena al aire, mixer y controles corresponden al núcleo real |
| 4. Producción integrada oscura | `07-native-rtmp-dark.png` | RTMP local, texto editado, contador y video visibles; salida decodificada aparte |
| 5. Error y recuperación | `08-invalid-import.png`, `09-missing-asset.png` | Código visible, catálogo conservado, acción de creación bloqueada para asset inválido |
| 6. Inspector compacto claro | `10-compact-light-inspector.png` | Ventana 1024×780; crear círculo, editar dimensiones/borde y aplicar mediante scroll |
| 7. Biblioteca compacta oscura | `11-compact-dark-library.png` | Pestañas, límites, uso del recurso y acciones accesibles por scroll |

Las capturas grandes corresponden a ventana lógica 1440×980, con backing 2×;
las compactas a 1024×780. La referencia tiene 80 px menos de alto lógico. Por ello
se compara jerarquía, alineación, espacio y estados, sin anunciar igualdad pixel
a pixel ni una puntuación automática de similitud. Se inspeccionaron guardados
06, 07, 10, 11 y la referencia juntos. Los PNG de medios decodificados son otra
evidencia: no sustituyen capturas de interfaz.

## Hallazgos

1. **Conservado — estructura principal.** Encabezado horizontal con identidad,
   producción, estado y acciones; preview dominante a la izquierda; escenas/audio
   a la derecha; capas debajo. El borde rojo durante salida y selección de escena
   mantienen la jerarquía de la referencia. La columna lateral tiene proporción
   similar. El indicador morado de captura lo añade macOS y no es parte del diseño.

2. **Corregido en H12 — acciones de inspector fuera de vista.** Los formularios
   largos colocaban Aplicar tras todas las propiedades. Ahora Aplicar/Crear está
   arriba; el recibo actual y Cancelar aparecen antes de las opciones. A 1024×780
   se alcanzó el borde al final del formulario, se volvió arriba y se aplicó.
   Sigue siendo necesario hacer scroll para propiedades inferiores; no quedan
   todas simultáneamente visibles. No se añadió un segundo sistema de formularios.

3. **Verificado — feedback del trabajo real.** Biblioteca diferencia importación
   pendiente/completada/fallida, referencias a escenas y asset perdido. El error
   de importación aparece en el panel y en el estado inferior; no se confunde con
   un recurso disponible. Animaciones muestran op ID y estado del núcleo. Al
   quedar obsoleto un borrador, la UI requiere recarga: no aplica valores viejos
   silenciosamente. La primera toma que no cambió a Fade demuestra que el operador
   debe comprobar el resultado del comando, no solo pulsar el botón.

4. **Pendiente de pulido — densidad y contenido auxiliar.** La biblioteca se abre
   como panel flotante sobre preview/sidebar, no como lienzo nuevo de Claude.
   Mensajes de importación se repiten en estado superior del contenido, recibo y
   pie; ocupan altura. El mixer ofrece peak/RMS/estado real, con más texto que la
   referencia. Los presets conservan nombres de fuente `Message`/`Background`/
   `Accent`; el usuario puede renombrarlos. Es funcional, con mayor carga visual.

5. **Limitación conservada — miniaturas de escenas.** Solo la escena activa tiene
   preview real; las demás muestran «Sin vista previa». La referencia ilustra
   miniaturas de todas las escenas. No se presentan capturas antiguas como si
   fueran previews en vivo. Esto no bloqueó Cut/Fade ni modificó las fuentes.

6. **Accesibilidad parcial.** Botones, sliders y campos tienen nombres observados
   en AX y se operaron con foco/teclado. Muchos textos estáticos de GPUI no aparecen
   como nodos de texto AX, por lo que se verificaron visualmente. No se completó
   un recorrido con VoiceOver ni medición formal de contraste; no se declara
   conformidad WCAG. El menú Motive observado no ofreció una acción Quit y Cmd-Q
   no cerró esta sesión; el harness cerró el proceso idle por el núcleo. Se conserva
   como limitación del shell nativo, sin atribuirla al adaptador creativo.

## Resultado

Los recorridos crear → editar → animar → grabar/transmitir y
seleccionar archivo → esperar worker → usar/reparar asset funcionan con evidencia
real. No hay controles H11 que pretendan ejecutar un reloj o mezclador en GPUI.
La fuente de verdad funcional es Production y la visual sigue siendo el diseño
aprobado. Quedan los puntos de pulido/accesibilidad anteriores; esta revisión no
equivale a una aprobación de todas las pantallas ni a un rediseño de los artboards.

Medios, métricas y reservas de estabilidad: [informe H12](h12-creative-studio-verification.md).
