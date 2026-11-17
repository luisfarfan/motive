# Motive: dirección artística (Fase 1)

Estado: propuesta para aprobación, 2026-11-16. Este documento cubre solo la
pantalla principal del estudio. Los tokens definitivos, la galería de
componentes y el resto de las pantallas empiezan cuando se apruebe esta
dirección (Fases 2 a 5).

Lienzo en Claude Design (fuente de verdad visual):
https://claude.ai/artifact/Xz4yhpz6kQhy13EGLVBDav, con copia en
`design/claude-design/studio-fase-1/`. Prototipo de comportamiento:
`design/prototype/studio/index.html`, servido con `python3 -m http.server`
desde esa carpeta. Capturas: `design/screens/phase-1/`.

## 1. Lo que tomé de la referencia

La captura de Codex funciona por cuatro decisiones. Las conservo y les doy
una regla:

| En la referencia | Regla para Motive |
|---|---|
| Exterior claro, entorno de producción oscuro | **La luz es para controlar; la oscuridad es para mirar.** Solo lo que muestra imagen (programa, miniaturas, vista previa de fuentes) vive en superficies oscuras. Los controles siempre están en la sala clara. |
| La previsualización domina | El escenario es el único objeto con elevación: sombra y radio de 12 px. Lo demás es plano y está separado por líneas finas, no por tarjetas. |
| "EN DIRECTO" en rojo, la escena al aire marcada | **Rojo de tally**: el rojo significa "esto sale al público" y no se usa para nada más. Verde = listo o sano. Ámbar = requiere atención. |
| Esquinas rojas alrededor de la webcam | **Marcas de registro**: la selección se dibuja con cuatro esquinas, no con una caja. Los tiradores aparecen solo al pasar el puntero o al arrastrar. |
| "IA · Alinear al margen", discreto en la fila | El agente propone en contexto, en la fila de la capa afectada. Nunca abre un chat ni ocupa un panel por defecto. |

Lo que descarto de la referencia: la línea de tiempo y la corrección de color
(no existen en el motor), el segundo nivel de ventana dentro del escenario
("Editar / Color / Gráficos") y los números "01, 02…" delante de las escenas.
El número solo aparece como atajo (⌘1…⌘4), que sí es información.

## 2. Principios

1. **Sala y escenario.** Dos materiales y ninguno más: la sala (clara,
   `shell-*`) y el escenario (oscuro, `stage-*`). No hay vidrio, desenfoque de
   fondo ni degradados decorativos. Así cada material tiene un equivalente
   directo en GPUI.
2. **Las señales tienen un solo significado.** Rojo = salida en curso. Verde =
   listo. Ámbar = atención. Índigo = agente. El azul del sistema solo marca el
   foco del teclado y los menús. Ningún color de señal decora.
3. **El agente propone con una línea distinta.** La selección del usuario usa
   esquinas blancas continuas. La propuesta del agente usa un contorno índigo
   discontinuo con trama diagonal, un "fantasma" que muestra el resultado antes
   de aplicarlo. La diferencia es de forma, no solo de color.
4. **Precisión sin ruido.** Los números usan cifras tabulares y comas
   decimales en español (`−6,0 dB`). Las coordenadas son las del lienzo real
   (960 × 540 o 540 × 960), no píxeles de pantalla.
5. **Un solo momento con movimiento continuo.** Solo parpadea el punto de
   tally mientras hay salida. Todo lo demás se mueve únicamente como respuesta
   a una acción.
6. **Honestidad del estado.** Cuando una fuente falla, la interfaz dice qué
   pasó, qué hizo el motor (detener la salida de forma controlada) y qué puedes
   hacer (reconectar). Nada se reinicia por su cuenta.

## 3. Lenguaje visual

### Color

| Rol | Claro | Sobre escenario | Uso |
|---|---|---|---|
| Sala | `#F2F3F5` / elevado `#FFFFFF` / hundido `#E9EBEE` | n/a | Fondo, barra de título, controles |
| Tinta | `#16181D` · `#545A65` · `#868C96` · `#B3B7BF` | `#F1F2F4` · `#A2A7B0` · `#6B7079` | Cuatro niveles de texto |
| Escenario | n/a | `#17181C` / elevado `#222429` | Programa, miniaturas, tarjetas sobre el lienzo |
| Directo | `#DC3328` | `#FF5247` | Estado al aire, borde de tally, escena al aire |
| Listo | `#17905D` | `#45D690` | Salud de fuentes, contadores en cero |
| Atención | `#B36A00` | `#FFB547` | Fuente perdida, bloqueos |
| Agente | `#5552D4` | `#A3A1FF` | Propuestas, historial, marca del agente |
| Foco | `#0A7AFF` | `#0A7AFF` | Anillo de teclado, resaltado de menú |

La variante de sala oscura (`data-theme="dark"`) mantiene el escenario un
escalón más oscuro que la sala, para que siga leyéndose como "el pozo" donde
vive la imagen.

El naranja de las cintas y la barra del rótulo es **contenido** (el color de
acento editable del overlay), no un color de la interfaz.

### Tipografía

SF Pro (la fuente del sistema), que es lo que GPUI resuelve de forma nativa en
macOS. La personalidad no viene de una fuente exótica: viene de la escala, del
peso y de las cifras tabulares.

| Estilo | Tamaño / interlineado | Peso | Uso |
|---|---|---|---|
| Título de escena | 22 / 28, −0,02 em | 650 | "Taller" |
| Código de tiempo | 15 / 20, tabular | 600 | Reloj de directo |
| Sección | 13 / 18 | 600 | "Capas", "Escenas", "Audio" |
| Cuerpo | 13 / 18 | 400–500 | Nombres, botones, menús |
| Secundario | 12 / 16 | 400–500 | Datos técnicos, valores, segmentos |
| Nota | 11 / 14 | 400–500 | Detalle de fuente, atajos |

Sin mayúsculas sostenidas en etiquetas ni fuente monoespaciada para datos:
las cifras tabulares bastan.

### Espacio, radios y profundidad

- Rejilla de 4 px. Filas de capa de 46 px; controles de 28 px (24 px
  compactos); barra de título de 52 px.
- Radios por jerarquía, no uno para todo: escenario 12, miniaturas 7–8,
  popovers 10, controles 6, segmentos 5, chips 999.
- Elevación: escenario (sombra de objeto), popovers y avisos (sombra flotante).
  Nada más tiene sombra.

### Movimiento

Duraciones y curvas alineadas con los `MotionTokens` por defecto de GPUI Kit
0.10, para no inventar un segundo sistema:

| Token | Valor | Uso en el prototipo |
|---|---|---|
| `fast` | 120 ms | Hover, presión (escala 0,97), tiradores |
| `normal` | 180 ms | Popovers, aviso, fantasma del agente, corte de escena (200 ms) |
| `slow` | 280 ms | Aplicar o deshacer una transformación, borde de tally |
| `enter` | cubic-bezier(0.16, 1, 0.3, 1) | Todo lo que aparece |
| `exit` | cubic-bezier(0.4, 0, 1, 1) | Todo lo que desaparece |
| `move` | cubic-bezier(0.2, 0, 0, 1) | Cambios de posición o tamaño |

Con `prefers-reduced-motion` (en macOS, "Reducir movimiento"), todas las
transiciones son inmediatas y el punto de tally deja de parpadear.

## 4. Anatomía de la pantalla principal

```
┌ ● ● ●  motive │ Luz y materia ▾     ( ● En directo 00:18:42 │ Grabando )     ◎ Agente 1 │ Grabando  Emitiendo  ■ Finalizar ┐
│ Taller  [▭ 16:9 | ▯ 9:16]  960 × 540  30 fps                                       │ Escenas 4                        + │
│ ┏━━━━━━━━━━━━━━━━━━━━ borde de tally (rojo) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  │ ┌──────────────┐                   │
│ ┃                                                                                 ┃  │ │  miniatura   │ Inicio         ⌘1 │
│ ┃                 PROGRAMA (lienzo real 960×540, contain-fit)                     ┃  │ ┌──────────────┐                   │
│ ┃                                                    ⌜‾‾‾‾‾‾‾‾⌝                  ┃  │ │  al aire     │ Taller ● Al aire ⌘2│
│ ┃                                                    ⌞________⌟ ← marcas          ┃  │ ┌──────────────┐ …                 │
│ ┠ Ajustar ▾  ⊡                     VideoToolbox H.264  6000 kb/s  30 fps  Perdidos 0 ┨  │ Audio                           ⚙ │
│ Capas en Taller                                                    + Añadir fuente  │ 🎙 Voz   Micrófono…       0,0 dB   │
│ ⠿ T  ▬  Rótulo        👁  380 × 72                                              ⋯   │ ▮▮▮▮▮▮▮▮▮▮▯▯▯▯ |                   │
│ ⠿ ▢  ▬  Webcam        👁  X 618  Y 296 │ An 284  Al 200   ◎ Alinear al margen… Ver ⋯ │ ───────────○──  🔈                 │
│ ⠿ ▭  ▬  Presentación  👁  960 × 540                                             ⋯   │ 🖥 Sistema …                       │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Barra de título unificada.** Proyecto a la izquierda; el estado de
  producción en el centro (la única pieza de la sala que "grita"); salidas a la
  derecha. Finalizar solo existe mientras hay salida.
- **Escenario.** El programa ocupa todo el espacio y se ajusta manteniendo la
  proporción. El pie muestra los contadores reales del motor (codificador,
  bitrate, fps, fotogramas perdidos, CPU).
- **Capas con inspector en línea.** La fila seleccionada se convierte en el
  inspector: X, Y, ancho y alto editables, y la propuesta del agente si existe.
  Las demás filas muestran solo el tamaño.
- **Riel derecho.** Escenas con miniaturas y atajos; debajo, el mezclador.

## 5. Comportamiento ya prototipado

| Interacción | Comportamiento |
|---|---|
| Cambiar escena | Clic, `1`…`4` o `⌘1`…`⌘4`. Corte con fundido de 200 ms (las transiciones reales son futuras). |
| Seleccionar capa | Clic en el lienzo (de arriba hacia abajo) o en la fila. `Esc` deselecciona. Doble clic en el lienzo enfoca el campo X. |
| Mover | Arrastrar. El imán actúa sobre el borde, el centro y el margen seguro (32 px), con guías rojas. `⇧` restringe el eje y `⌘` desactiva el imán. El margen seguro aparece mientras arrastras. |
| Redimensionar | Las esquinas mantienen la proporción (`⇧` la libera); los lados son libres e imantan al margen. Etiqueta de tamaño bajo la selección. |
| Valores exactos | Escribir y pulsar `↩`; `↑` y `↓` suman ±1 (con `⇧`, ±10); arrastrar la etiqueta X/Y/An/Al los ajusta; `Esc` revierte. |
| Empujar | Flechas ±1 px y `⇧` + flecha ±10 px, en coordenadas del lienzo. |
| Orden y visibilidad | Asa de arrastre en la fila, `⌘]` y `⌘[`, menú ⋯ y ojo. |
| Deshacer | `⌘Z` y `⇧⌘Z` para posición, tamaño, orden, visibilidad y cambios del agente. |
| Orientación | 16:9 ↔ 9:16 con transformaciones independientes por variante, como en el núcleo. |
| Propuesta del agente | "Ver" muestra el fantasma, la trayectoria y el diff (X 618 → 644). "Aplicar" (o `↩`) anima el cambio y deja un aviso con "Deshacer ⌘Z". "Descartar" deja un aviso con "Recuperar". |
| Grabar y emitir | Emitir pasa antes por una comprobación previa animada. Detener y Finalizar piden confirmación. Al terminar, "Grabación guardada". |
| Fuente perdida | La salida se detiene de forma controlada y se conserva el motivo. La fuente pasa a "Sin señal" en el lienzo, la fila y el estado. "Reconectar fuentes" no reinicia la salida. |
| Audio | Medidor estéreo segmentado con retención de pico, fader en dB (doble clic = 0 dB, flechas ±1, `⇧` ±6) y silencio. |

Controles del prototipo (abajo a la izquierda, fuera del producto):
**Alcance** Visión/Hoy, **Apariencia**, **Anotado**, **Ventana 1024 × 700**
y **Perder la cámara**.

## 6. Lo implementado frente a lo futuro

El modo **Hoy** aplica los límites reales del motor actual. El modo
**Anotado** marca cada zona en verde (existe), ámbar (parcial) o índigo
(futuro).

| Elemento | Estado en el motor (2026-11-16) |
|---|---|
| Escenas, capas, fuentes reutilizables, transformaciones por variante | Existe (proyecto v3; CLI y MCP) |
| 960 × 540 y 540 × 960 | Existe |
| Grabación y RTMP local, VideoToolbox con respaldo x264 | Existe; **una salida a la vez** (`simultaneous_outputs: 1`) |
| Cambiar escena, visibilidad o recursos durante una salida | Hoy requiere detener la salida (Hoy lo bloquea con un aviso) |
| Selección en el lienzo y campos numéricos en la UI | Siguiente hito del plan; el núcleo ya acepta `set_transform` |
| Agente por MCP | Existe; la **revisión de propuestas** (fantasma, aplicar, descartar) es futura |
| Nivel de micrófono | Existe (`audio_peak`); **fader y silencio** son futuros |
| Audio del sistema | Futuro |
| Rótulo con texto | Futuro; hoy es el overlay animado original con color editable |
| Miniaturas en vivo de escenas no activas | Por medir: requiere renderizado adicional del motor |
| Contadores del pie | Existen en el motor; el panel es nuevo |
| Línea de tiempo y corrección de color de la referencia | Fuera de alcance; no se dibujan |

## 7. Viabilidad en GPUI Kit 0.10 (primera lectura)

Revisé el código fuente de `gpui-component 0.10.0` incluido en Cargo.lock.

| Pieza | Plan |
|---|---|
| Botones, iconos, segmentos, menús, popovers, tooltips, avisos, entradas, deslizadores, paneles redimensionables, barra de título | Reutilizar los componentes de GPUI Kit (`button`, `menu`, `popover`, `tooltip`, `notification`, `input`, `slider`, `resizable`, `title_bar`) con un tema propio |
| Tokens | Extender `ThemeColor`/JSON de tema con los roles `shell-*`, `stage-*` y señales; usar `MotionTokens` tal cual |
| Lienzo del programa, marcas de registro, tiradores, guías, fantasma | Desarrollo específico: elemento `canvas` de GPUI sobre la textura de vista previa de libobs |
| Medidor segmentado | Desarrollo específico: N quads pintados; no depende de máscaras CSS |
| Fader en dB | Personalizar `slider` (marca de 0 dB, doble clic) o crear un componente propio |
| Miniaturas de escena | Requiere decidir en el motor cómo renderizar escenas inactivas (coste a medir) |

Por validar técnicamente: la trama diagonal del fantasma (se puede sustituir
por un tinte plano con contorno discontinuo), el contorno discontinuo, las
cifras tabulares (`tnum` en `FontFeatures`), el arrastre para reordenar
filas y el fundido entre escenas (capturar el fotograma anterior).

## 8. Activos y licencias

Todas las imágenes del prototipo se generan con código en `art.js` (cintas,
bokeh y una persona ilustrada y desenfocada como sustituto de una cámara).
No hay fotografías, recursos de stock ni material de terceros. Los iconos son
un juego propio de 16 px con trazo de 1,5 px. La marca reutiliza la "M" de
`docs/assets/motive-banner.svg`. Todo se publica bajo la licencia del
repositorio (GPL-3.0-or-later).

## 9. Decisiones que necesito que apruebes

1. **Sala clara por defecto** y la sala oscura como alternativa del sistema.
   El escenario siempre es oscuro.
2. **Índigo para el agente.** Lo separa del azul del foco y del verde de
   "listo". La alternativa es dejar al agente sin color propio y distinguirlo
   solo por la forma (contorno discontinuo y marca ◎).
3. **Marcas de registro** como lenguaje de selección, en lugar de una caja con
   ocho tiradores siempre visibles.
4. **Inspector en línea en la fila de capa**, como en la referencia. La
   alternativa es un inspector lateral fijo, que deja más espacio para
   propiedades futuras (recorte, opacidad, anclajes) pero quita ancho al
   programa.
5. **Escenas en columna con miniaturas grandes**, frente a una rejilla de dos
   columnas que muestre más escenas sin desplazamiento.
