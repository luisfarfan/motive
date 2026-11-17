# Entrega y compatibilidad con H14

Fecha: 2026-11-17, America/Lima. Rama `codex/creator-experience`, base `57de1c5`.
Esta entrega conserva el aislamiento: solo añade/modifica `creator-experience/`.
El [chequeo final de aislamiento](../evidence/completion-isolation.json) fija los
hashes de UI/pruebas, confirma main limpio y 12 archivos Claude Design intactos.

## Resultados verificables

| Gate | Resultado | Evidencia |
|---|---|---|
| CreatorPack v1, Deck v1 y Config de reglas | PASS ambos packs, crate real | `../evidence/contracts-native.json` |
| Contenido PNG/SVG, metadatos, geometría, referencias, cuotas | PASS ambos packs | `../evidence/contracts-validation.json` |
| Rechazos, properties atómicas, confirmación/pending/cooldown/reloj | 13 controles por pack | `../evidence/contracts-native.json` |
| PNG corrupto, límites, SVG activo/remoto y traversal/symlink | 7 pruebas PASS | `../evidence/contracts-asset-tests.log` |
| Rust formato y Clippy | PASS | `../evidence/contracts-clippy.log` |
| Regeneración en esta Mac | 86 archivos idénticos en dos generaciones | `../packs/tools/reproducibility.json` |
| Parser/acciones/Deck contra H14 | PASS; hashes antes/después estables | `../evidence/contracts-h14-snapshot.json` |
| Navegador independiente final | 213 comprobaciones nuevas + 69 de regresión PASS | `../evidence/completion-browser.json`, `completion-regression.json` |
| Manifest personalizado descargado | PASS contra el harness Rust real | `../evidence/customized-roundtrip.json` |
| Estilo exportado de ambos packs | PASS Rust; cambian solo property y fuente de fondo | `../evidence/completion-style-roundtrip.json` |
| Ejemplo de autoría podcast | 12 archivos idénticos, 12 controles, cinco botones y cuatro eventos simulados | `../agent-authoring/example/evidence/verification.json` |
| Metadatos/checksums propuestos | Dos proyecciones verificadas, 25 archivos cada una; sin ZIP | `motivepack-examples/projection-validation.json` |
| Grabación, streaming, permisos, importación o rendimiento nativo | NO EJECUTADO | Fuera del alcance autorizado |

Se conserva el primer fallo real de reglas/geometría y su corrección: versiones
y variables ausentes en Config, geometría fuera del canvas y empates de orden.
Se conserva también un primer intento de QA con estado previo de navegador:
el botón se bloqueó correctamente por capacidad ausente; el harness se corrigió
para iniciar los escenarios con recarga explícita. No se convierte ese fallo en
una prueba nativa ni se elimina de la evidencia.

## Encaje con H14

Observación final del crate en `8d6ac470da391ecdfdeac4f2b8ab56880a5c5adb`, árbol
H14 con trabajo en curso. La prueba fue de solo lectura y no ejecutó Motive.
`packs.rs` coincide con la base; Deck tiene ampliaciones live que no rompen estos
documentos. El hash del instalador observado se mantuvo
`edd82033af16e47ec9723a056e499d98ae3c3ab1e35c570003cfcee4bf98c40d`.
La primera observación se conserva en `contracts-h14-first-*`; H14 avanzó
durante este trabajo y el gate final se repitió sobre el nuevo snapshot estable.

La instalación sigue siendo una brecha concreta: `include_str!` de MATCHDAY y
`PACK_RESOURCES_UNSUPPORTED` para listas de medios no vacías. Los cuatro PNG
son compatibles con el **tipo de recurso H11**, no prueba de que H14 permita
instalarlos como pack. No se añadió otro instalador para eludir esa limitación.

| Siguiente integración oficial | Condición de aceptación |
|---|---|
| Selección de pack y staging de PNG | Basenames/hashes/tamaños revisados, broker y permisos normales |
| Plan sobre proyecto real | Revisión/idle/capacidades, cuotas con capturas y presupuesto definitivo |
| Bindings | IDs reales devueltos, sin duplicar primera capa creada por overlay |
| Show Control/Live Deck | Reglas con referencias resueltas, owner desarmado al restaurar, confirmación local real |
| Personalización | Cuatro targets tipados v1; cambios de fuente compartida explícitos |
| Fallo parcial/timeout | Recibo y reconciliación; sin retry ciego ni rollback prometido |
| Aceptación visual nativa | Grabar ambas orientaciones, mostrar/ocultar/trigger, animaciones y oclusión real |

## Presupuesto realista

TECH: 6 escenas, 12 fuentes, 27 capas; con sus cuatro slots de captura previstos,
31 capas y 14 fuentes en un proyecto vacío. ARENA: 6/12/27; sus dos slots llevan
el total a 29 capas y 14 fuentes. Reutilizar captura conserva identidad; cada
instancia de escena sigue consumiendo una capa.

Estimación del plan: TECH 42.856.112 bytes, ARENA 43.412.912. Estimación adicional
según puerta nativa H11: 117.475.616 y 126.056.224 respectivamente. Ambas bajo
256 MiB; ninguna cifra es RSS, coste de capturas o benchmark de decoder.
Un aumento de resolución H13 no multiplica coordenadas persistidas ni garantiza
tipografía/imagen equivalente a un recurso con mayor resolución intrínseca.

## Diferencias intencionales del prototipo

Biblioteca/personalizador/Deck se sirven como HTML local para estudiar interacción.
El preview es un render aproximado; usa texto de navegador y widgets ilustrados
activos. Sus timers son únicamente ensayos UI y no marcan el reloj multimedia.
«Plan revisado» nunca se presenta como «pack instalado». Una pestaña separada
permite recorrer siete fixtures visuales: preparado, revisado, instalando,
instalado, error parcial, recurso faltante y revisión obsoleta. Los estados y sus
recuperaciones están rotulados como ejemplos, con avance manual y ningún recibo
nativo. La variante de fondo modifica solo `shape_color`; la receta reducida
afecta al preview sin inventar un campo v1. Las 22 animaciones tienen reproducción
individual, parámetros acotados y ambas orientaciones.

La propuesta `.motivepack`, marketplace y extracción son documentos revisables.
No hay backend, cuenta, pago, infraestructura cloud, plugin ejecutable ni repo
adicional. La app y el uso de packs locales siguen independientes de un catálogo.

La [matriz de aceptación](acceptance-matrix.md) vincula las 17 secciones y los
15 criterios finales con esta evidencia. El cierre inicial omitía tres partes
del prototipo; se añadieron, revisaron y probaron explícitamente. El informe
actual acredita el alcance creativo, los prototipos independientes y las
especificaciones solicitadas. La integración audiovisual sigue siendo otro
trabajo, excluido por instrucción del pedido.
