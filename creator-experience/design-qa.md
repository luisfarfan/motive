# QA visual · Creator Experience

Fecha: 2026-11-17. **final result: passed** para el prototipo y los materiales
de diseño revisados; aceptación audiovisual nativa **no evaluada**.

El cierre revisado incluye las 22 animaciones, siete fixtures de instalación y
estilos/variantes. La primera entrega omitía parte de esas interacciones;
la evidencia siguiente registra la ampliación y vuelve a verificar la regresión.

## Cierre del alcance completo

`evidence/completion-browser.json` registra **213 comprobaciones PASS** sobre
el código final: 133 de movimiento, 41 de instalación, 24 de estilos y 15 de
casos de borde. `evidence/completion-regression.json` vuelve a verificar las
69 comprobaciones del flujo anterior; sus selectores se actualizaron al
workbench completo. No se suman repeticiones de una misma suite como cobertura
adicional. El código reproducible está en `validation/browser-completion-checks.js`.

- Las 22 entradas se reproducen en ambos layouts. Se comprueban capa, duración,
  dirección y punto medio de las curvas cuadráticas; reducción estática por
  cada ID, límites válidos/inválidos y Fade restringido a Linear. La transición
  BRB conserva Fade350 y Cut reducido.
- Los siete estados son ejemplos visuales separados del plan. Se recorren
  revisión, avance manual, instalado, cancelación, error parcial, inspección,
  reconciliación, recurso faltante y revisión obsoleta en ambas colecciones.
- El preset de fondo modifica únicamente la property `shape_color` y su fuente;
  los dos manifests descargados pasan el harness Rust real en
  `evidence/completion-style-roundtrip.json`. La receta reducida no se serializa
  como un campo v1 inventado. El color manual y el selector de estilo permanecen
  sincronizados; Restablecer recupera la colección original.
- Se verifican conservación de foco en selects, corrección independiente de
  campos inválidos, preferencia del sistema cambiada sin recargar, rechazo de
  callbacks antiguos y conservación de revisión/entidades al reconciliar.
- Escritorio 1440, tablet 1024 y móvil 390 px: sin overflow horizontal ni imágenes
  rotas. Cero errores/warnings de consola, HTTP fallidos o requests externos.

Revisión visual directa: `completion-motion-desktop.png`,
`completion-motion-midpoint.png`, `completion-motion-390.png`,
`completion-installed-example.png`, `completion-lifecycle-390.png` y
`completion-style-vertical.png`. Se confirma jerarquía, contraste, controles
legibles, adaptación y separación entre shell claro y composición oscura.
Las capturas completas se toman desde scroll cero: evita que Chrome incluya
un elemento fijo situado fuera del viewport como si flotara a mitad de página.
No se oculta ni retoca contenido del producto para capturar.

El ejemplo didáctico de podcast también se abrió en Proxima Browser a 960×540 y
540×960: `completion-podcast-horizontal.png` y `completion-podcast-vertical.png`.
Las dos guías de cámara están rotuladas como selección pendiente y no son fuentes
de video. Texto, márgenes y lower thirds se revisaron sin oclusión ni recorte.

La revisión de código detectó y corrigió antes del gate final: preferencia
reducida capturada al abrir, finalizaciones antiguas que podían cambiar el
estatus nuevo, paso parcialmente creado marcado como completo, número de
revisión obsoleto y foco perdido al reconstruir controles. Los casos de borde
anteriores acreditan esas correcciones. No quedan fallos P0/P1/P2 identificados
en el alcance revisado. Las siguientes secciones conservan la revisión inicial.

## Fuente y comparación

Fuente visual: `../design/claude-design/studio-fase-1/project/Main.dc.html`,
`../design/direction.md` y captura original
`../design/screens/phase-1/01-studio-live.png`. Copia de evidencia:
`evidence/reference-studio.png` (1440×900). Implementación:
`evidence/library-desktop.png` (1440×1000). Comparación conjunta abierta e
inspeccionada: `evidence/source-comparison.png` (1480×580).

Son **flujos distintos**, estudio de producción y nueva biblioteca, respectivamente.
La comparación evalúa sala/escenario, tipografía, logo, superficies y señales;
no promete una réplica píxel a píxel de un lienzo de biblioteca que no existe.
La referencia mantiene su licencia original del repo y no se modificó.

Screenshots a escala CSS 1 px; sin marco de dispositivo. Fuente y aplicación
se redujeron uniformemente a 700 px de ancho únicamente en el panel comparativo.
Para inspección de detalles se abrieron las capturas originales completas de
1440 px y los previews a design960. `detail-final.png`, `deck-desktop.png`,
`motion-final.png` y `vertical-final.png` muestran las regiones de contenido,
control y adaptación. No se infiere fidelidad de texto pequeño a partir del
contact sheet reducido.

## Hallazgos corregidos e historial

| Severidad | Hallazgo inicial | Corrección y evidencia final |
|---|---|---|
| P2 | Badges de biblioteca tapaban el identificador del arte | Eliminados sobre la imagen; `library-desktop-initial.png` → `library-desktop.png` |
| P2 | Miniaturas tenían 540 px de alto al reducir ancho | `height:auto`; `detail-desktop-initial.png` → `detail-final.png` |
| P2 | Logo tipográfico no correspondía al artboard | Reutilizado el SVG M original; comparación conjunta |
| P2 | Slide del ensayo desplazaba hacia el lado opuesto | X = −distance; valores reales de `PackAnimation`, browser-validation |
| P2 | Escape podía conservar valor de confirmación anterior | Reset por apertura; `browser-edge-validation.json` |
| P2 | Skip link alteraba la ruta y callbacks podían afectar otro ensayo | Foco sin cambio de ruta; identidad de solicitud y pack revalidados |
| P2 | Neon perdía profundidad y una geometría salía del canvas | Orden del arte y frame corregidos; contact sheets y contracts-validation |

La primera pasada visual estaba bloqueada por esos defectos. Se conservan las
capturas iniciales. Se corrigieron y recapturaron a la misma anchura de 1440 px.
Los screenshots finales móviles se tomaron a 390×844, sin el foco transitorio
del skip link sobre el escenario. Los avisos de ensayo que aparecen en algunas
capturas son UI real y no se borraron del archivo. No quedan P0/P1/P2 abiertos
en los flujos revisados.

## Cinco superficies de fidelidad

- **Tipografía:** sistema macOS en controles, pesos y jerarquía legibles; fuente
  nativa de contenido restringida a Helvetica/Arial/Menlo. UI de authoring y
  AppKit/FreeType no son equivalentes exactos. Se conservan saltos explícitos;
  el navegador ajusta texto de preview y no certifica su rasterización nativa.
- **Espacio/alineación:** sala clara, separadores planos, escenarios dominantes,
  radios moderados y sombra del preview. Los contact sheets muestran márgenes
  y separación de áreas de captura/lower thirds. Se corrigieron miniaturas y
  geometría que violaban la composición. Inspector largo requiere scroll;
  agrupación contextual de propiedades es un refinamiento futuro P3.
- **Color/tokens:** shell #F2F3F5, ink #16181D y stage #17181C heredados. Ningún
  estado declara una salida real. TECH y ARENA se distinguen por paleta y forma.
  `design-system/tokens.json` registra siete pares de contraste de contenido
  entre 12,35 y 16,68; eso no es una auditoría automática de cada píxel de UI.
- **Imágenes:** cuatro PNG alpha originales, bordes y motivos sin texto baked;
  SVG fuente editable. Se inspeccionaron ambos contact sheets y previews
  completos. Marcos vacíos son áreas reservadas para capturas, no dispositivos
  ni personas ficticias que aparenten señal. PNG/SVG y hashes validados.
- **Copy:** controles en español, nombres/contenido editorial originales del
  pack en inglés y editables. Prototipo local visible; plan confirma revisión,
  no instalación. Recurso/acción faltante y regla deshabilitada tienen texto,
  además de color. La incompatibilidad de importador se explica en la ficha.

## Interacción, movimiento y accesibilidad

Proxima Browser fue el único navegador. `evidence/browser-validation.json`
registra 69 aserciones: búsqueda/filtro/estado vacío, seis escenas y dos
orientaciones, edición y rechazo de texto inválido, descarga personalizada,
capacidad/presupuesto del plan, confirmación/cancelación/pending/cooldown,
reglas deshabilitadas, recursos ausentes, teclado y movimiento reducido.

Se revisaron layouts 1440×1000, 1024×768 y 390×844. Sin overflow horizontal ni
imágenes rotas en las vistas evaluadas. Cero errores/warnings de consola, cero
HTTP fallidos y cero solicitudes externas durante la suite. El manifest
descargado pasó después el validador Rust (`customized-roundtrip.json`).

Ocho controles adicionales verifican Escape tras confirmación previa, ruta del
skip link, cancelación/repetición frente a callbacks anteriores, rechazo simulado,
selector de escena Motion, Fade350, Cut reducido y lower third representativo
con 320 ms y distancia −32 px. La captura
`motion-midpoint.png` pausa **la animación del navegador** en mitad del tiempo
declarado para inspeccionar posición; no es una muestra del reloj OBS. La galería inicial
ilustraba seis gestos reales y un ejemplo separado de transición de escena.

Foco visible, skip link, inputs con label, botones nativos, diálogo modal y
estatus legibles por texto comprobados. Preferencia de movimiento reducido
del sistema y selector local ejercitados. No se ejecutó auditoría completa con
lector de pantalla, zoom del sistema ni equivalencia GPUI; quedan fuera de este
PASS de prototipo.

## Checklist final

- [x] Fuentes visuales abiertas y comparación conjunta inspeccionada.
- [x] P2 encontrados corregidos con evidencia posterior.
- [x] Recursos reales y ambas orientaciones revisados.
- [x] Interacciones y estados bloqueados ejercitados.
- [x] Red, consola, teclado y movimiento reducido comprobados.
- [x] Integración nativa pendiente diferenciada de diseño validado.
