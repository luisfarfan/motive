# Creator Experience · arquitectura de entrega

Estado: estudio y artefactos locales, 2026-11-17. Base de desarrollo: `57de1c5`.
Rama `codex/creator-experience`, worktree independiente. Esta carpeta es el
límite de escritura; H14 y los lienzos originales se consultan en solo lectura.

## Una colección, tres responsabilidades

1. **Contenido portable:** `packs/<id>/manifest.json` usa exactamente
   `CreatorPack` v1. Assets, fuentes editables, layouts, animaciones, propiedades,
   reglas y Deck viven con cada colección. `metadata.json` añade información de
   catálogo sin introducir campos desconocidos en el manifest.
2. **Herramientas de autoría:** generadores de arte/previews y validadores se
   ejecutan localmente. Los previews son ilustraciones de diseño; no son frames
   producidos por libobs. Python/Swift y el validador Rust no se distribuyen como
   código ejecutable dentro de un pack instalable.
3. **Producto:** el importador, permisos, recursos administrados, bindings de IDs,
   operaciones y reloj multimedia pertenecen exclusivamente a Motive. El HTML de
   `prototype/` no tiene conexión a Production ni se carga como Browser Source.

## Flujo de integración previsto

Archivo local seleccionado → verificar contenido e integridad → parsear CreatorPack
v1 → consultar capacidades reales → plan sobre el grafo existente → revisión local
→ instalador oficial → recibos y bindings → habilitar acciones verificadas.

No se infiere disponibilidad real de `Capability::h12_contracts()`: es un baseline
estático. El plan de Show Control continúa siendo `executable: false`. No se
reproduce un plan por CLI desde estas herramientas.

Las fuentes se comparten entre escenas; cada capa tiene dos transforms. Cambiar
un texto compartido afecta todas sus instancias. Las capturas son selecciones del
usuario, no dispositivos incrustados en el pack. Las recetas indican dónde y con
qué orden añadirlas; el instalador debe sumar también esas capas y fuentes.

## Límites que cambian el diseño

- 8 escenas, 16 fuentes y 32 capas en el **proyecto completo**. Dos colecciones
  completas de seis escenas no caben juntas. Ofrecer un proyecto separado o una
  selección/recompilación explícita de escenas con dependencias, nunca truncar.
- `design960`: 960×540 y 540×960. La salida H13 escala las coordenadas a 720p o
  1080p. No se multiplican transforms ni tipografías al exportar el manifest.
- Texto nativo: Helvetica, Arial o Menlo. La fuente de sistema de la interfaz no
  amplía ese enum. Los saltos de línea son explícitos; no hay auto-layout de texto.
- Rectángulos usan stretch; texto, imágenes, widgets y círculos usan contain.
  El área de encaje no es necesariamente el área ocupada por el contenido.
- Color personalizable v1: `shape_color`. `text_content`, `widget_title` y
  `widget_subtitle` son los otros tres targets. No prometer un recolor global de
  PNG, fuente externa, widget accent editable por property ni reemplazo de media.
- No hay cámara ni pantalla declarables dentro de `VisualDefinition` de packs.
  Un marco es un recurso, no una fuente de captura.

## H14

La observación de H14 se registra con hashes en la auditoría. Su instalador
observado está especializado en MATCHDAY y rechaza recursos con
`PACK_RESOURCES_UNSUPPORTED`. La entrega prepara contenido para una integración
posterior; no modifica ese instalador ni afirma instalación nativa de estas dos
colecciones. La compatibilidad del schema es distinta de la instalación y de la
aceptación audiovisual.

## Dependencias de desarrollo

El contenido y el prototipo no dependen de rutas absolutas. El adaptador de
validación usa temporalmente un path relativo al crate autoritativo de Show
Control, para evitar duplicar un schema. El plan de extracción describe cómo
sustituir ese vínculo cuando exista un contrato versionado independiente.
