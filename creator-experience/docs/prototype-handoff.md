# Creator Library & Live Deck — handoff GPUI

Prototipo independiente de presentación. No contiene una instancia de Production,
cliente MCP, puente de comandos, captura, instalador, conexión de proveedor ni reloj
multimedia. JavaScript vive únicamente en este prototipo; no se instala en los packs.

## Abrir y reproducir

Desde el checkout, ejecutar `python3 creator-experience/prototype/serve.py` y abrir
`http://127.0.0.1:8768/prototype/`. El servidor solo sirve el árbol Creator Experience
por loopback. No se requieren paquetes npm, tipografías descargadas ni red externa.
La raíz servida debe incluir `packs/`; servir `prototype/` aisladamente no permite
cargar los manifiestos. `file://` no es una ruta de apertura admitida por este estudio.

Todo el contenido se carga desde los manifiestos, metadata, decks, reglas e imágenes
locales. El documento de error muestra una carga incompleta, sin inventar datos.

## Fuente visual y extensión

Referencia: copia de solo lectura `design/claude-design/studio-fase-1/project/Main.dc.html`
y `design/direction.md`. Se mantienen sala clara #F2F3F5, controles blancos, escenario
oscuro #17181C, tipografía del sistema, separadores planos y elevación reservada a los
previews. La marca M se reutiliza de ese artboard. No se ha modificado el lienzo.

Las pantallas de biblioteca, detalle, personalización, plan, Deck y Motion son nuevas
propuestas de Creator Experience. No implican aprobación de las futuras pantallas
GPUI ni sustituyen los lienzos de Claude Design. La paleta de cada pack es contenido;
no cambia las señales de estado de la interfaz.

## Recorridos y componentes

| Ruta | Interacciones implementadas | Equivalente GPUI previsto |
|---|---|---|
| `#library` | Búsqueda por nombre/uso/tags, categorías, filtro offline/sin imágenes, resultado vacío y reset | Input, select, botones, lista de colecciones |
| `#pack/creator-tech` / `#pack/neon-arena` | 6 escenas, 2 layouts, propiedades tipadas, restaurar y descargar manifiesto | Inspector con borrador y revisión del owner |
| Detalle / La colección | Autor, licencia, capacidades, recursos, presupuesto y límites de importación | Lista de metadatos, badges informativos |
| Detalle / Plan | Escenarios vacío/MATCHDAY/duplicado, capacidad ausente, conteos globales, confirmación y descarga de revisión | Plan oficial de H14, diálogo y resultado observado |
| `#deck/{id}` | Grupos, estados, cooldown, confirmación, pendientes, cancelación, historial, regla deshabilitada y capacidad ausente | Deck/DeckRuntime y recibos del adaptador oficial |
| `#motion` | Preview por gesto, objetivos reales del manifiesto, reducción de movimiento, abrir composición | Controles de animación existentes del núcleo |

La búsqueda no tiene backend. El filtro «Sin imágenes» produce legítimamente un
estado vacío con estas dos colecciones. «Uso offline» conserva ambas: significa que
los recursos son locales, no que el importador H14 ya las admita.

## Personalización y exportación

Solo se ofrecen los `properties` declarados. El cambio actualiza una copia en memoria
con la misma estructura del manifiesto y su `PropertyValue`:

- `text_content` → `definition.text`.
- `widget_title` → `definition.widget.title`.
- `widget_subtitle` → `definition.widget.subtitle`.
- `shape_color` → `definition.color` de esa forma.

No se recolorean PNG, texto o widget accent como efecto implícito de `shape_color`.
No se expone una sustitución arbitraria de imágenes. Los campos previenen controles
no admitidos y aplican límites de bytes, caracteres, líneas y render de texto de v1.
El navegador no reemplaza a `CreatorPack::from_json`/`set_property`: toda exportación
personalizada necesita validación Rust antes de instalación. No se reescribe el pack
en disco; solo «Descargar manifiesto» entrega una copia explícita al usuario.

La vista SVG aproxima el contain-fit para imágenes, texto y widgets; las formas
rectangulares estiran su caja como en el contrato. El preview ajusta texto para evitar
desbordes: no prueba el rasterizador FreeType ni su tamaño final. Los widgets se
ilustran en estado activo y los countdowns son valores estáticos. No es una grabación
nativa ni prueba de calidad de 1080p.

## Plan e instalación

Se muestra el impacto añadido sobre los límites globales de 8 escenas, 16 fuentes y
32 capas. El escenario MATCHDAY aporta sus 4/12/23 declarados; el escenario duplicado
representa una colección ya presente, sin intentar sobrescribirla. Falta de imágenes,
exceso de capacidad y símbolos existentes bloquean la confirmación del ensayo.

El estado final se llama **Plan revisado (simulación)**, nunca «instalado». La revisión
JSON descargable declara `simulated: true`, `executable: false`, `requires_idle: true`
y es un documento de revisión separado, no un esquema alternativo de CreatorPack.

El instalador H14 observado solo acepta MATCHDAY y rechaza recursos externos.
Instalar Creator Tech y Neon Arena sigue pendiente. El futuro flujo real tiene que
verificar bytes/hashes/licencias, tomar una revisión de Production, mantener el owner
idle, vincular IDs retornados, manejar errores parciales y observar el resultado
oficial. La interfaz no debe declarar éxito al pulsar un botón o aceptar una propuesta.

Estado instalado previsto en GPUI: mostrarlo solo después de recibo terminal exitoso,
inventario verificado y bindings completos para la misma identidad/revisión. Presentar
pack ID/versión/digest, escenas añadidas y «Configurar capturas». Ante resultado parcial,
usar «Instalación incompleta» con recursos creados y recuperación explícita; nunca
promover una confirmación a instalado. Es una especificación futura, no un estado
alcanzable desde el prototipo.

## Live Deck: semántica visible

Los botones y grupos provienen de los `deck.json` validados. Se muestran únicamente
`rule`, `overlay`, `animation`, `scene`, `countdown` y `composite`; no se inventan
acciones de audio, shell o navegador. Los atajos son una referencia visual, no globales.

El ensayo refleja ready → awaiting_confirmation → pending → simulated/rejected/
cancelled, junto con disabled y cooling_down. La falta de capacidad se muestra como
un bloqueo de preflight, no como una nueva variante serializada de ButtonState.
Un checkbox de ensayo puede mantener solicitudes pendientes para revisar su estado.
Un segundo checkbox retira capacidades de animación/escena solo en el ejemplo y recorre también las acciones anidadas de las reglas/composites. Un pendiente permite ensayar explícitamente éxito, cancelación o rechazo `SIMULATED_REJECTION`.
Los botones que apuntan a reglas deshabilitadas muestran esa razón explícitamente.

Cada solicitud local tiene un ID y cooldown desde su aceptación. Cambiar de ruta invalida una confirmación abierta; Escape siempre cancela, y las confirmaciones se revalidan contra el pack y estado actuales. Cambiar de colección también invalida la revisión de su plan. Pendientes bloquean
repeticiones hasta completar/cancelar el ensayo. El historial está acotado a 64 entradas
y presenta las 10 últimas del pack seleccionado. Los timers de JavaScript actualizan
solo ese ensayo de interfaz; no controlan progreso nativo, countdowns ni medios.

En GPUI, una confirmación requiere el token/revisión real del adaptador; una marca
booleana del frontend no autoriza operaciones multimedia. Deben conservarse errores
estructurados, estados pending_ack y recibos reales aunque el borrador esté obsoleto.

## Motion y accesibilidad

Los seis previews toman sus scene_id, layer_id, kind, duration_ms, distance y scale_from
de animaciones reales de los packs. El SVG animado pinta el target de esa composición. Si la capa está oculta, solo se activa una copia local para ilustrar ese gesto; no se modifica el manifiesto. Un preview adicional entre Live Coding/Gameplay y BRB toma el Fade de 350 ms del Deck y hace Cut inmediato con movimiento reducido.
CSS/Web Animations solo ilustra el gesto: sus curvas y transform-origin no son evidencia
de equivalencia visual exacta con libobs. Al terminar vuelve al estado inicial del
preview. Los gestos no se reproducen automáticamente ni en bucle.

Se respeta `prefers-reduced-motion` y un control de reducción adicional. El preview se
vuelve estático; no genera una animación nativa de duración cero. Hay labels de campos,
botones nativos, diálogo modal nativo, foco visible, enlace para saltar navegación,
regiones de estado y razones textuales además del color. Layouts responsivos contienen
el escenario sin recortar su relación de aspecto. El QA ejecutado y sus límites se
registran por separado en la evidencia de esta entrega.

## Verificación reproducible

- `node --check creator-experience/prototype/app.js` comprueba sintaxis, no interacción.
- Proxima Browser es el único navegador autorizado para QA.
- Probar búsqueda vacía/reset, cambio de colección/escena/orientación, edición/export,
  conteos y bloqueos de plan, confirmación/cancelación de Deck, pendiente/cooldown,
  movimiento reducido, desktop 1440px y móvil 390px.
- Revisar errores de consola, recursos locales, overflow, lectura de texto y navegación
  por teclado. Capturas y resultados reales deben conservarse en `evidence/`.
