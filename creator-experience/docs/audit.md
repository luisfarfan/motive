# Auditoría de contratos y contenido existente

Lectura: 2026-11-17, America/Lima. Checkout de Creator Experience basado en
`57de1c5`, aislado de H14. Se leyeron README, producto, plan, decisiones, H11,
H12, H13, dirección visual, design-qa y Show Control. No se abrió Motive ni se
adquirió el lock de pruebas físicas. Esta auditoría describe código observado;
no certifica captura, instalación ni reproducción nativa.

## Inventario heredado

| Colección en `show-control/examples/packs` | Escenas | Fuentes | Capas | Animaciones | Properties | Assets |
|---|---:|---:|---:|---:|---:|---:|
| MATCHDAY | 4 | 12 | 23 | 6 | 4 | 0 |
| CREATOR TECH | 2 | 7 | 9 | 2 | 2 | 0 |
| NEON ARENA | 2 | 7 | 9 | 2 | 1 | 0 |

Los tres son manifests declarativos v1 con texto, formas y widgets. MATCHDAY
ya aporta una colección mayor, reglas y Deck; sus ejemplos de sonido/voz no
demuestran disponibilidad de esas capacidades. Los otros dos son conceptos
pequeños con marcos de cámara dibujados, no capturas. Los SVG y páginas de
`show-control/design` son previews aproximados, no assets admitidos por H11.

Las nuevas colecciones amplían los IDs, contenido y dirección de los conceptos
existentes; no cambian los originales. Añaden composiciones de seis momentos,
arte fuente original y PNG, eventos/Deck propios, metadata de descubrimiento,
recetas de capturas y evidencia. La ausencia previa de alertas completas,
pausas/cierre, recursos exportados, reservas de capacidad y personalización
revisable motivó esos entregables.

La referencia de interfaz es `design/claude-design/studio-fase-1/`, sin edición,
junto a `design/direction.md`: sala clara, escenario oscuro, planos sin tarjetas
elevadas de control, foco azul y estados con significado. Su tabla histórica
de capacidades es anterior a H11–H13; para disponibilidad manda el contrato y
el código actual, no la tabla visual histórica.

## Contrato normativo

`show-control/src/packs.rs` es la autoridad: deserialización estricta,
`deny_unknown_fields`, versión 1. No se añadió un schema alternativo. El
validador de esta carpeta enlaza ese crate por path relativo, sin enlazar el
motor ni libobs. Descripción, categoría, tags, previews, recetas y notas se
guardan fuera del manifest, en sidecars de autoría.

| Aspecto | Límite observado |
|---|---|
| Manifest | UTF-8, máximo 256 KiB; campos desconocidos/versiones distintas rechazados |
| Identidad | ASCII alfanumérico, guion y guion bajo; 1–64 bytes |
| Versión | Tres componentes numéricos acotados; no SemVer prerelease/build |
| Licencia | GPL-3.0-or-later, CC0-1.0, MIT o CC-BY-4.0 |
| Grafo | 1–8 escenas, 1–16 fuentes, máximo 32 capas sumadas |
| Referencias | Escenas/fuentes/capas únicas; toda fuente debe utilizarse |
| Recursos | Hasta 16 descriptors; hasta 64 MiB por recurso; total declarado ≤512 MiB |
| Animaciones/properties | Hasta 64 cada una; 8 operaciones simultáneas como máximo |
| Eventos/reglas | 32 clases de evento y 64 referencias de regla como máximo |
| Transform | x/y finitos ±4096; width/height 1–4096; order 0–31 |
| Dimensión intrínseca texto/forma/widget | Hasta 1920×1080; widget al menos 240×100 |
| Texto | Hasta 4096 bytes, 16 líneas; size 8–192; caracteres × size ≤24576 |
| Fuentes tipográficas | Helvetica, Arial, Menlo; no fuente descargable |
| Widget | lower_third, countdown, alert; título ≤160 caracteres/3 líneas; subtítulo ≤256/4 |
| Duración widget | Lower third 0; countdown 1 s–1 h; alert 100 ms–60 s |
| Imágenes | PNG/JPEG/WebP ≤2048×2048; hash SHA-256, bytes y dimensiones declarados |
| Video | MP4/MOV/WebM ≤1920×1080, ≤60 s; broker H11 verifica H.264/VP8/VP9, ≤60 fps |
| Nombres de recursos | Basename seguro sin rutas, URL, prefijo punto ni `..` |
| Video simultáneo | Máximo 4 fuentes en H11; este tope no se deduce del máximo de descriptors |

Los límites de escena/fuente/capa pertenecen al proyecto completo. Un pack que
pasa aislado puede no caber junto al proyecto del usuario. Dos colecciones
completas de seis escenas exceden ocho escenas incluso con todas las demás
cuotas libres. La propuesta deja reservas para capturas, sin prometer que cada
proyecto existente tenga espacio.

## Geometría y render

H13 conserva `design960`: 960×540 y 540×960. Escala de composición 1 para
legacy540, 4/3 para hd720 y 2 para full_hd1080; 30/60 FPS no cambian el manifest.
No hay dos canvases activos simultáneos. Las definiciones conservan su
resolución intrínseca al aumentar la salida, por lo que texto e imágenes no
se vuelven automáticamente assets de doble resolución.

`native/graph.inc` configura `OBS_BOUNDS_STRETCH` solo para forma rectangular.
Texto, imágenes, widgets y círculos usan `OBS_BOUNDS_SCALE_INNER`, centrados
dentro del rectángulo. Por eso la caja de un layout no equivale al contenido
ocupado; no estirar un PNG de paisaje para fingir adaptación vertical. Los
previews deben conservar esa regla y declarar su aproximación tipográfica.

Color RGB24, opacidad 0–1. Rectángulo/círculo son las únicas geometrías nativas.
El borde es ≤32 y ≤mitad de la dimensión menor. El PNG alfa está admitido;
SVG solo es fuente editable. No se verifica alpha de video, GIF animado,
Browser Source, HTML/JS arbitrario, filtros GPU, fuentes externas ni audio de
video. Las capturas se añaden mediante selección normal del usuario; no hay
una variante cámara/pantalla en `VisualDefinition` del manifest.

## Dos presupuestos diferentes

El plan de packs usa `w*h*4` para formas, `w*h*12` texto, `w*h*16` widgets,
16 MiB por imagen y `1920*1080*16` por video. Este cálculo es deliberadamente
distinto de la puerta nativa H11: `8*w*h` por fuente, más 8 MiB por texto y
16 MiB por widget. Para imágenes/video, H11 usa dimensiones del asset resuelto.
El validador adicional calcula ambas estimaciones; no presenta una como RSS
ni como verificación del decoder. El techo común es 256 MiB. Los presupuestos
no cubren fuentes de captura, encoders, picos de reemplazo ni memoria total.

Medición sobre los manifests entregados (solo aritmética): CREATOR TECH
42.856.112 bytes en el plan, 117.475.616 bytes en la estimación H11; NEON ARENA
43.412.912 y 126.056.224 bytes respectivamente. Cada colección tiene 6 escenas,
12 fuentes y 27 capas. CREATOR TECH tiene cuatro slots de captura y NEON ARENA
dos; reutilizan dos fuentes seleccionadas, para 31/14 y 29/14 capas/fuentes
respectivamente en proyecto vacío. Un proyecto preexistente requiere su propio
preflight.

## Personalización y movimiento

`set_property` solo admite `text_content`, `widget_title`, `widget_subtitle` y
`shape_color`. Actualiza una copia y valida antes de confirmar. No admite
reemplazar assets, cambiar tipografía, recolorear PNG ni cambiar widget accent
mediante un property. Una edición de fuente compartida afecta todas sus capas.
El inspector nativo puede editar más atributos de una definición; eso no
amplía el contrato de personalización v1.

FadeIn/FadeOut son lineales. SlideIn/SlideOut y ScaleIn/ScaleOut admiten
linear/ease_in/ease_out/ease_in_out, duración 100–10000 ms, distancia ±1920,
scale_from 0,1–2. Una operación por capa, hasta ocho, sin cola implícita.
Cut/Fade de escenas es un contrato separado: Cut 0 ms y Fade 100–5000 ms.
Las transiciones de escena y las animaciones de capa tienen barreras mutuas.
La UI espera recibos nativos, no extrapola reloj ni transforma aceptación en
finalización. Movimiento reducido se resuelve con las capacidades disponibles
y una propuesta explícita; no añade un tipo nuevo al manifest.

Los eventos Show/Hide/Trigger/TimerStart/TimerStop/TimerReset afectan una
fuente compartida. Ocultar una capa no pausa countdown ni video. Un contador
de Show Control es una variable local, no un contador gráfico enlazado
automáticamente. Eventos de proveedores requieren ingreso confiable fuera
del pack; ejemplos `simulated:true` no acreditan conexiones reales.

## Deck y H14 observado en solo lectura

Deck v1: 1–8 grupos, 1–64 botones, máximo 64 KiB, IDs/órdenes/atajos únicos.
Targets tipados: rule, overlay, animation, scene, countdown, composite.
`deck_actions` conserva condiciones; un botón manual no puede convertirse en
evento de voz/chat para saltarse autorización. Las reglas se validan con
`Config::from_json`, referencias de pack y preparación de acciones tipadas.

Worktree H14 observado en commit `611e930`, con documentación de trabajo aún
modificada. `src/creator_packs.rs` contiene un instalador revisado especializado
en MATCHDAY (`include_str!`), rechaza cualquier lista de recursos no vacía con
`PACK_RESOURCES_UNSUPPORTED` y detecta solo texto/forma/widget/animación/
transición. Por tanto, compatibilidad del manifest v1 **no significa** que
CREATOR TECH o NEON ARENA puedan instalarse mediante ese panel. Requieren
ampliación del instalador oficial, staging de PNG y binding de sus reglas.

H14 conserva el manifest de packs sin cambios. Amplía Deck con estados live,
owner session y confirmación local no serializable; no debe reutilizarse el
booleano de ensayo del prototipo como autorización real. Restaurar deja la
sesión desarmada. Recibos, cooldowns, revisiones e historial pertenecen al
owner. Ni los generadores, ni el HTML, ni este validador conectan a Production.

| Archivo observado | SHA-256 |
|---|---|
| Base/H14 `show-control/src/packs.rs` | `f9d0ca8fb48aad21b2cb2cecb0627b1e6018dea5063490351afffcdb6996ede0` |
| Base `show-control/src/deck.rs` | `0c554d212b77377456cfcb4352e5a00af25a27172f0a613dc632b09d6b806119` |
| H14 `show-control/src/deck.rs` | `84199e76af64f0b38147cc9c6308a8f5e2faa15382caa9b6cc35c844e3f62279` |
| H14 `src/creator_packs.rs` | `6926e94d24b9a300e83dd8b41768e3e2ae26e0857ece3a7e6775abe8bca9fefa` |
| Base `native/graph.inc` | `1b2e492bb25233076182a59e129cc3a41e066c59b91565024ce67fba5ebb061c` |

Estos hashes fijan lo leído, no prometen que H14 siga inmóvil. Antes de integrar,
contrastar el commit final, capacidades/graph revision y resultado del instalador
oficial. No se modificó ninguno de esos archivos.

El harness independiente también se compiló contra el crate de H14, en lectura,
y ambos packs pasaron los mismos gates. `contracts-h14-snapshot.json` conserva
commit, instante UTC y hashes antes/después; fueron estables durante esa prueba.
Es compatibilidad comprobada de parseo/acciones del crate, no aceptación del
instalador especializado ni del owner.

## Evidencia y próximos gates

`python3 creator-experience/validation/validate.py` ejecuta el parser Rust real,
preparación de reglas/Deck, mutaciones adversariales y comprobación de PNG,
hashes, geometría y presupuestos. Escribe `evidence/contracts-native.json`,
`contracts-validation.json` y `contracts-rust.log`; un resultado ausente o FAIL
no se describe como validación completada. PNG usa CRC y descompresión zlib
acotada de todas las filas; no sustituye el broker y el decoder de Motive.

QA visual debe revisar texto, oclusión, márgenes, adaptación vertical y estados
animados sobre capturas del prototipo. Aún así, solo grabaciones nativas futuras
pueden demostrar el resultado audiovisual. H14 conserva la responsabilidad de
instalación, seguridad del owner y prueba real; no se amplía aquí ese alcance.
