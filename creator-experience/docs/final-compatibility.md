# Entrega y compatibilidad con H14

Fecha: 2026-11-17, America/Lima. Rama `codex/creator-experience`, base `57de1c5`.
Esta entrega conserva el aislamiento: solo añade/modifica `creator-experience/`.

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
| Navegador independiente | 69 comprobaciones + 8 controles adicionales PASS | `../evidence/browser-validation.json`, `browser-edge-validation.json` |
| Manifest personalizado descargado | PASS contra el harness Rust real | `../evidence/customized-roundtrip.json` |
| Grabación, streaming, permisos, importación o rendimiento nativo | NO EJECUTADO | Fuera del alcance autorizado |

Se conserva el primer fallo real de reglas/geometría y su corrección: versiones
y variables ausentes en Config, geometría fuera del canvas y empates de orden.
Se conserva también un primer intento de QA con estado previo de navegador:
el botón se bloqueó correctamente por capacidad ausente; el harness se corrigió
para iniciar los escenarios con recarga explícita. No se convierte ese fallo en
una prueba nativa ni se elimina de la evidencia.

## Encaje con H14

Observación final del crate en `977d2006b35ef70af6ccc5c96dbfb4485e513901`, árbol
H14 con trabajo en curso. La prueba fue de solo lectura y no ejecutó Motive.
`packs.rs` coincide con la base; Deck tiene ampliaciones live que no rompen estos
documentos. El hash del instalador observado se mantuvo
`6926e94d24b9a300e83dd8b41768e3e2ae26e0857ece3a7e6775abe8bca9fefa`.

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
«Plan revisado» nunca se presenta como «pack instalado». El estado instalado real
se especifica para el handoff GPUI, pero no se finge una instalación en este estudio.

La propuesta `.motivepack`, marketplace y extracción son documentos revisables.
No hay backend, cuenta, pago, infraestructura cloud, plugin ejecutable ni repo
adicional. La app y el uso de packs locales siguen independientes de un catálogo.
