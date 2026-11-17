# Matriz de alcance y aceptación · Creator Experience

Revisión independiente del pedido completo, 2026-11-17. Primer corte de esta
matriz: commit `fdf7dc6`, contrastado con los archivos y resultados ejecutados.
La revisión final incorpora los incrementos posteriores y sus informes
`completion-*`: 213 comprobaciones nuevas y 69 regresiones sobre la interfaz
final. Las brechas iniciales se conservan abajo con su evidencia de cierre;
no se usa una etiqueta global «todo terminado».

## Cómo leer el estado

- **Implementado / validado offline:** existen archivos utilizables y el gate
  indicado se ejecutó. No equivale a instalación ni rendering en Motive.
- **Prototipo / verificado:** interacción real del HTML independiente, comprobada
  con Proxima Browser. Sus fixtures no son estados ni recibos de Production.
- **Especificación entregada:** contrato o decisión revisable; no implementación
  de un servicio que el pedido excluye.
- **Brecha histórica:** parte verificable que faltaba en el primer cierre; se
  conserva el hallazgo y la evidencia concreta de su resolución posterior.
- **Integración futura excluida:** depende de trabajo que este pedido prohíbe
  ejecutar/modificar. No se cuenta como fallo del trabajo creativo, ni justifica
  dejar incompletos el diseño, los recursos o los prototipos independientes.

La calidad «premium» es un juicio de diseño sustentado por composición, arte
original, separación de identidades y revisión visual. Un parser PASS demuestra
compatibilidad estructural; no convierte ese juicio en una garantía automática.

## Secciones numeradas del pedido

| § | Resultado solicitado | Artefactos concretos | Evidencia ejecutada / estado delimitado |
|---|---|---|---|
| 1 | Dos colecciones, recursos, motion, biblioteca/personalización, Deck, autoría, marketplace y extracción | [Índice](../README.md), las dos carpetas de packs y las secciones siguientes | Entrega mixta de contenido implementado, prototipos verificados y especificaciones. Los cierres de §8 y §11 tienen evidencia específica más abajo; no se infiere una experiencia nativa completa. |
| 2 | Worktree/rama propios, escritura solo dentro de `creator-experience/`, sin interferir H14 | Rama `codex/creator-experience`, [registro de aislamiento](../evidence/isolation-and-build.json), [arquitectura](architecture.md) | Inspección Git registrada: rutas externas vacías, sin ejecución nativa/lock/push/merge/rebase/release. H14 se leyó y el crate independiente se compiló en target propio; no se modificó su checkout. |
| 3 | Auditar documentación, diseños, código y los tres packs previos; capacidades y límites reales | [Auditoría](audit.md), tablas de inventario, geometría, presupuestos, properties y hashes; [migración TECH](../packs/creator-tech/migration-from-0.1.json), [migración ARENA](../packs/neon-arena/migration-from-0.1.json) | Lectura documentada de H11/H12/H13, Show Control y dirección visual. Conserva identidad/contenido reutilizable de los conceptos; diferencia shapes/widgets admitidos, previews conceptuales y capturas pendientes. `packs.rs` original permanece intacto. |
| 4 | Preparar separación futura sin crear repositorios ni herramientas prematuras | [Arquitectura](architecture.md), [plan de extracción](repository-extraction-plan.md) | Especificación entregada. Paths de contenido relativos; única dependencia temporal del validador es el crate autoritativo. No hay `motive-creator`, backend de Hub ni repo adicional implementados. |
| 5 | CREATOR TECH: seis composiciones, identidad editorial, overlays y ambas orientaciones | [Manifest](../packs/creator-tech/manifest.json), [README](../packs/creator-tech/README.md), [contact sheet](../packs/creator-tech/previews/contact-sheet.png), assets, recipes, rules y deck en esa carpeta | Implementado / validado offline: 6 escenas, 12 fuentes, 27 capas, 10 animaciones, 12 properties, 2 PNG alpha+SVG. Starting/Live Coding/Camera/Presentation/BRB/Ending, lower third, chapter, countdown, alert, identity y panel informativo presentes. Capturas son recetas explícitas, no contenido ficticio al aire. |
| 6 | NEON ARENA: seis composiciones, identidad propia, alertas/recompensas/celebración y ejemplos de eventos | [Manifest](../packs/neon-arena/manifest.json), [README](../packs/neon-arena/README.md), [contact sheet](../packs/neon-arena/previews/contact-sheet.png), [reglas](../packs/neon-arena/rules.json), [eventos](../packs/neon-arena/events.jsonl) | Implementado / validado offline: 6/12/27, 12 animaciones, 12 properties, 2 PNG alpha+SVG. Starting/Gameplay/Camera/Community/BRB/Ending; countdown, alert y reward usan widgets existentes. Reglas manuales ensayadas; follow/reward de proveedor quedan deshabilitados. Ninguna conexión live declarada. |
| 7 | Fuentes editables y exportaciones compatibles, arte original, texto editable y licencias | [Generador](../packs/tools/generate.py), [rasterizador](../packs/tools/rasterize.swift), `assets/source/`, PNG y provenance de cada pack; [licencia](../LICENSE) | [Bytes/formatos/hashes/dimensiones](../evidence/contracts-validation.json), [alpha](../packs/tools/asset-alpha-check.json), [reproducción](../packs/tools/reproducibility.json). Cuatro PNG reales con fuentes SVG; texto editable sigue en definitions/properties. No hay video obligatorio: no usarlo evita depender de alpha/audio no verificados. |
| 8 | Nueve patrones de motion, cada uno con propósito, duración/easing, editables, compatibilidad, preview y ejemplo | [Motion System](../motion/README.md), [22 aplicaciones indexadas](../motion/catalogue.json), [generador de catálogo](../motion/build_catalogue.py), vista `#motion` del [prototipo](../prototype/index.html) | Sistema y prototipo verificados: 22 entradas reproducibles en ambas orientaciones, parámetros acotados, salidas/indicadores, curvas cuadráticas muestreadas y reducción. [133 checks motion y 15 de bordes](../evidence/completion-browser.json) cierran M1. El navegador ilustra contratos existentes; no añade motor nativo. |
| 9 | Manifest v1 estricto, metadatos, assets, layouts, reglas, presupuesto y resultado por pack | Ambos `manifest.json`, `metadata.json`, `deck.json`, `rules.json`, `events.jsonl`, README/LICENSE/provenance; [harness](../validation/src/main.rs) | [Parser/planes/reglas/Deck PASS](../evidence/contracts-native.json), [contenido PASS](../evidence/contracts-validation.json), [H14 PASS](../evidence/contracts-h14-compatibility.json). Metadatos de catálogo son sidecar; no se añaden campos al schema original. Las cuotas suman el proyecto completo y las capturas; dos packs completos no caben juntos. |
| 10 | Propuesta `.motivepack`: contenedor, metadatos, integridad, actualización, migración y recursos faltantes | [Propuesta de distribución 0.1](motivepack-proposal.md), [envoltorios/checksums concretos](motivepack-examples/README.md), migraciones declarativas de cada colección | **Especificación entregada:** ZIP propuesto con límites, paths, checksums, licencias, compatibilidad, personalización y actualización revisable. No hay otro instalador, ZIP certificado ni promesa de rollback. Ejemplos concretos de ambas colecciones contrastados con bytes reales: 25 archivos lógicos por pack, inventario/hash/tamaño coherentes; [reporte](motivepack-examples/projection-validation.json). No cambia el estado a formato ratificado. |
| 11 | Galería/ficha/personalizador y flujo visual de instalación, incluidos estilos/variantes y estado instalado | [HTML/CSS/JS](../prototype/), [handoff GPUI](prototype-handoff.md), [captura de biblioteca](../evidence/library-desktop.png), [detalle](../evidence/detail-final.png) | Prototipo verificado: biblioteca/ficha/personalización, presets de fondo por shape_color, variante reducida, export y plan; siete fixtures de lifecycle, incluido instalado-demo, error parcial, recurso faltante y revisión obsoleta. [41 checks lifecycle + 24 estilos](../evidence/completion-browser.json) y [exports Rust](../evidence/completion-style-roundtrip.json) cierran P1/P2. Sigue sin GPUI ni instalador. |
| 12 | Deck con grupos/acciones, cooldown, confirmación, pendientes, historial, reglas desactivadas y capacidades faltantes | Ambos `deck.json`, `rules.json`; [prototipo Deck](../prototype/index.html#deck/creator-tech); [captura](../evidence/deck-desktop.png); [handoff](prototype-handoff.md) | Prototipo / verificado: [69 comprobaciones](../evidence/browser-validation.json), [8 controles de borde](../evidence/browser-edge-validation.json), parser y ensayos de cada botón habilitado en [contratos](../evidence/contracts-native.json). Los resultados dicen ensayo; no se presentan como operaciones multimedia. |
| 13 | Workflow proveedor-independiente para agentes/personas, ejemplos, límites, validadores y checklist | [Guía de autoría](../agent-authoring/README.md), [podcast/dos cámaras generado](../agent-authoring/example/README.md), ambos packs, [herramientas](../packs/tools/README.md), [validadores](../validation/README.md) | Workflow y herramientas entregados. Ejemplo podcast ejecutado: [12 archivos regenerados idénticos y reservas](../agent-authoring/example/evidence/verification.json), [parser, 12 controles y cinco botones PASS](../agent-authoring/example/evidence/contracts.json), cuatro eventos simulados, cero comandos live. Dos cámaras son slots, no dispositivos. Sin framework ni MCP adicional. |
| 14 | Concepto de Hub: catálogo/perfiles/versiones/descargas/previews/búsqueda/licencias/reportes/integridad; offline y opcional | [Mapa de experiencia](../marketplace-concept/README.md), [roadmap](marketplace-roadmap.md), [extracción](repository-extraction-plan.md) | **Especificación entregada** para todos esos objetos y recorridos; catálogo opcional, cuentas no obligatorias, retirada sin borrar locales, integridad separada de autenticidad. Backend/pagos/auth/cloud están excluidos por el pedido; no son entregables faltantes. |
| 15 | QA de contratos/assets/metadata/geométría/motion y revisión visual/responsive/accesibilidad básica con evidencia real | [Validación](../validation/README.md), [QA visual](../design-qa.md), [tokens/contraste](../design-system/tokens.json), [evidencia](../evidence/) | Gates ejecutados: parser+13 negativos por pack, 7 tests de bytes, 86 archivos reproducibles; primera QA 69+8 conservada. Reanudación: [213 checks nuevos](../evidence/completion-browser.json), [69 regresiones finales](../evidence/completion-regression.json), [ambos exports de estilo pasan Rust](../evidence/completion-style-roundtrip.json); screenshots desktop/1024/390 inspeccionados. Q1 cerrado para el código final probado; sin aceptación nativa. |
| 16 | Estructura íntegra bajo una carpeta portable | [Índice](../README.md), packs/design-system/motion/prototype/agent-authoring/marketplace-concept/validation/evidence/docs | Directorios solicitados presentes. Assets y prototipo no necesitan paths absolutos. Targets/caches de desarrollo permanecen ignorados bajo la carpeta. Extracción aún no ejecutada. |
| 17 | Incrementos autónomos, corrección/evidencia/commits locales, sin acciones prohibidas | [Checkpoints A–K](../evidence/checkpoints.md), historial local `ae51f5a` → `fdf7dc6` | Siete commits locales iniciales agrupan incrementos revisables. La reanudación corrigió los tres gaps de interacción y ejecutó QA adicional; los checkpoints registran esos incrementos. Los commits de cierre son del coordinador; no hubo autorización redundante ni acciones públicas. |

## Matriz de los quince criterios finales

| Criterio | Evidencia concreta que lo respalda | Estado que se puede afirmar |
|---|---|---|
| 1. CREATOR TECH completo y premium | Seis escenas×dos layouts en [contact sheet](../packs/creator-tech/previews/contact-sheet.png), [manifest](../packs/creator-tech/manifest.json), QA de composición y [resultados](../evidence/contracts-validation.json) | Colección implementada y revisada como diseño editorial; uso nativo del conjunto requiere integración oficial futura. No depende de esa integración para entregar el arte y las composiciones. |
| 2. NEON ARENA completo y premium | Seis escenas×dos layouts en [contact sheet](../packs/neon-arena/previews/contact-sheet.png), [manifest](../packs/neon-arena/manifest.json), alert/reward y QA | Colección implementada con identidad diferenciada y estados de comunidad; el juicio visual no se sustituye por conteo de archivos. |
| 3. Recursos originales utilizables | Cuatro PNG alpha, cuatro SVG editables, generador, [provenance/formatos](../evidence/contracts-validation.json), [alpha](../packs/tools/asset-alpha-check.json) | Recursos reales compatibles con el tipo imagen H11; no solo screenshots. Licencia/procedencia originales registradas. |
| 4. Manifests validados | [Base](../evidence/contracts-native.json), [H14](../evidence/contracts-h14-compatibility.json), [hashes H14](../evidence/contracts-h14-snapshot.json) | Ambos manifests pasan el parser real; resultados fijados al snapshot observado, no a cualquier H14 futuro. |
| 5. Horizontal y vertical | 24 previews de composición, transforms 960×540/540×960 en manifests, [geometría](../evidence/contracts-validation.json) | Layouts implementados, en canvas y renderizados de forma independiente; respetan contain/stretch y design960. |
| 6. Animaciones compatibles | 10 TECH+12 ARENA en manifests, [validación](../evidence/contracts-native.json) y [contrato motion](../motion/README.md) | Tipos, easing, duración, distancia, escala y referencias validados; sin afirmación de ejecución nativa. |
| 7. Motion Design System | Nueve patrones y 22 aplicaciones en [catálogo](../motion/catalogue.json) | Sistema y 22 previews interactivos con parámetros, ambos layouts y reducción; [133 comprobaciones motion](../evidence/completion-browser.json) y [captura](../evidence/completion-motion-desktop.png) cierran M1. |
| 8. Biblioteca y personalización | [Prototipo](../prototype/index.html), [QA browser](../evidence/browser-validation.json), [export personalizado validado](../evidence/customized-roundtrip.json) | Biblioteca/personalizador y estilos/variantes funcionales; siete estados de instalación son fixtures separados, claramente rotulados. [QA de cierre](../evidence/completion-browser.json) y [exports de estilo validados](../evidence/completion-style-roundtrip.json) cierran P1/P2. |
| 9. Live Deck | [Deck TECH](../packs/creator-tech/deck.json), [Deck ARENA](../packs/neon-arena/deck.json), [captura](../evidence/deck-desktop.png) y pruebas browser/Rust | Prototipo funcional y contratos validados; no reemplaza el runtime de H14. |
| 10. Documentación de generación por agentes | [Guía](../agent-authoring/README.md), [ejemplo de podcast](../agent-authoring/example/README.md), [verificación](../agent-authoring/example/evidence/verification.json), [cobertura de elementos](../agent-authoring/pack-elements-checklist.md) | Workflow y ejemplo reproducible con herramientas normales: 2 escenas, 6 fuentes/7 capas, reserva de dos cámaras; parser/Deck/regeneración PASS. Sin instalación ni capturas reales. |
| 11. Propuesta `.motivepack` | [Especificación 0.1](motivepack-proposal.md), [ejemplos package/checksums](motivepack-examples/README.md) y [proyección verificada](motivepack-examples/projection-validation.json) | Contrato futuro y ejemplos concretos entregados para contraste con H14; hashes/inventario/totales recalculados de forma independiente. No se exige ni se afirma segundo instalador. |
| 12. Arquitectura de marketplace | [Concepto](../marketplace-concept/README.md), [roadmap](marketplace-roadmap.md) | Diseño conceptual entregado; ausencia deliberada de backend/pagos/cuentas. |
| 13. Extracción a `motive-packs` | [Plan de extracción](repository-extraction-plan.md), paths relativos y contenidos portables | Responsabilidades/destinos/gates definidos; no se crea ni mueve un repositorio todavía. |
| 14. Pruebas y evidencia visual | [QA](../design-qa.md), reports JSON/logs/screenshots, [regeneración](../packs/tools/reproducibility.json) | Evidencia real de validadores/browser, fallos iniciales conservados; [213 checks adicionales](../evidence/completion-browser.json), [69 regresiones finales](../evidence/completion-regression.json) y nuevas capturas cierran Q1. No son frames nativos. |
| 15. Compatibilidad final con H14 | [Informe](final-compatibility.md), [snapshot y hashes](../evidence/contracts-h14-snapshot.json) | Compatibilidad de schema/acciones comprobada de nuevo contra H14 `8d6ac470`, hashes estables durante el chequeo. Instalador observado sigue MATCHDAY-only y rechaza recursos; no se modifica. La conclusión separa esta integración futura de M1/P1/P2/Q1 ya verificados. |

## Gaps encontrados y cierre dentro del alcance autorizado

| ID | Falta observada en el primer cierre | Cierre ejecutado y evidencia |
|---|---|---|
| M1 | Galería motion reducía 22 entradas a seis previews reproducibles; selector restante solo navegaba | **Prototipo verificado.** 22 IDs × horizontal/vertical, controles de duración/easing/distancia/escala, reducción y extremos: fase motion 133 PASS en [completion-browser](../evidence/completion-browser.json). [Desktop](../evidence/completion-motion-desktop.png), [midpoint](../evidence/completion-motion-midpoint.png), [390 px](../evidence/completion-motion-390.png). |
| P1 | El plan terminaba en «revisado» y no diseñaba visualmente el estado instalado ni fallos del ciclo | **Prototipo verificado.** Siete fixtures separados, progreso manual, instalado-demo, parcial, faltante y obsoleto; inspección/reconciliación y revisión 7→8. Fase lifecycle 41 PASS en [report](../evidence/completion-browser.json). [Instalado-demo](../evidence/completion-installed-example.png), [parcial](../evidence/completion-partial-error.png), [390 px](../evidence/completion-lifecycle-390.png). Ninguna instalación real. |
| P2 | Estilos/variantes solo existían en metadata y el control global de motion | **Prototipo verificado.** Fondo original/tinta mediante property shape_color, sincronización con color manual, receta original/reducida y recursos no intercambiables explicados. Fase styles 24 PASS; ambos manifests descargados pasan [Rust y diff limitado al fondo](../evidence/completion-style-roundtrip.json). [Vertical](../evidence/completion-style-vertical.png), [390 px](../evidence/completion-style-390.png). |
| Q1 | QA de 69+8 aserciones correspondía a la primera versión | **Evidencia ejecutada.** 213 checks nuevos (133 motion, 41 lifecycle, 24 estilos, 15 bordes), [69 regresiones sobre la UI final](../evidence/completion-regression.json), screenshots de 1440/1024/390. Sin errores/warnings/red externa/HTTP fallidos. Bordes incluyen foco, campos inválidos independientes, cambio dinámico de movimiento reducido y callback viejo incapaz de finalizar otro ensayo. |

El ejemplo didáctico de podcast de la sección 13 ya tiene generación y
verificación ejecutadas: 12 archivos idénticos, 12 controles adversariales,
cinco botones y cuatro eventos simulados; las cámaras son reservas explícitas.
Los previews del ejemplo también se abrieron en Proxima Browser: [horizontal](../evidence/completion-podcast-horizontal.png) y [vertical](../evidence/completion-podcast-vertical.png).
Los fixtures de contenedor de la sección 10 ya están presentes y se
comprobaron además de forma independiente, en solo lectura: inventario exacto,
SHA-256 y tamaños coincidentes, 25 archivos lógicos por pack; 1.201.951 bytes
TECH y 1.221.597 ARENA incluyendo los dos documentos envoltorio. No se creó
ningún ZIP, ni se leyó un paquete externo, ni se ejecutó instalación.

## Lo que permanece futuro por instrucción, no por abandono

- Instalar estas colecciones en Motive, seleccionar capturas, activar Show Control,
  grabar/emitir y verificar píxeles nativos: trabajo del instalador/owner H14 y una
  sesión audiovisual autorizada aparte. Este pedido prohíbe ejecutarlo.
- Escribir las pantallas en GPUI o modificar `src/`, `native/`, Show Control o los
  lienzos fuente: prohibido aquí; el entregable actual es un handoff/prototipo.
- Backend de Hub, cuentas, pagos, cloud, nuevo repo `motive-packs`, herramienta
  `motive-creator`, instalador/exportador paralelo: expresamente fuera del pedido.
- Video alpha/audio, Browser Source, keyframes, nuevas fuentes tipográficas,
  recolor de PNG y properties no incluidas en v1: capacidades futuras descritas,
  sin introducirlas silenciosamente en manifests.

M1/P1/P2/Q1 se cerraron sin esperar ni implementar ninguna de esas capacidades.
Esta revisión no identifica otros entregables pendientes dentro del alcance
creativo autorizado; conserva explícitamente las integraciones y capacidades
futuras que siguen fuera de él.
