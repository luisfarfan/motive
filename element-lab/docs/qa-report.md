# QA y cierre de checkpoints

Validado el 18 de noviembre de 2026 en macOS ARM64. Baseline real
`6019ad0acac4b52dcf1ebc44f2006406fde533f8`. Rama local
`codex/motive-elements-foundation`; todos los cambios están en element-lab/.

## Resultados finales

| Gate | Resultado y evidencia |
|---|---|
| Python / CLI / compositor / paquetes / límites | **48/48**; [L-python-tests.log](../evidence/L-python-tests.log) |
| API JS / tipos / lifecycle / cancelación / errores | **6/6**; [L-runtime-tests.log](../evidence/L-runtime-tests.log) |
| Harness y widget reales en proxima-browser | **30/30**; [L-browser.json](../evidence/L-browser.json) |
| Cuatro formularios y respuestas atrasadas | **6/6**; [L-authoring-browser.json](../evidence/L-authoring-browser.json) |
| Rust fmt / clippy offline con warnings como error | PASS; L-rust-fmt.log y L-rust-clippy.log |
| Reproducibilidad ZIP e integridad de catálogo | **8/8**, dos builds byte a byte; J-packages.json y K-catalog.json |
| Evento con Show Control real | 1 job simulado, 0 comandos vivos; L-show-control-rehearsal.json |
| Flujo de brief → elemento → composición → paquete | PASS; L-agent-authoring.json |
| Alcance de archivos y baseline | L-final.json; sin modificaciones fuera de element-lab/ |

Herramientas observadas: Python 3.14.7, Node 24.20.0, Rust/Cargo 1.99.1. Cargo
compiló exclusivamente el adaptador independiente y su dependencia Show Control.
El soporte mínimo indicado en README no constituye una matriz de CI multiversión.

## Checkpoints A–L

| Etapa | Entregado | Commit estable |
|---|---|---|
| A | Auditoría del motor, capacidades frente a propuestas, hashes | 614cd72 |
| B | Element Schema v1 y fixtures negativas | e14997c |
| C | Compositor y adaptador al contrato Rust real | 094315c |
| D | CLI local, presets y exportación | b038d0f |
| E | Cuatro elementos, recursos originales, H/V, variantes y ejemplos | 730459a; identidad corregida en fc7eeb7 |
| F | Selección modular y combinación de ambas colecciones | 5c3cdd8 |
| G | API visual JS, validación y lifecycle | 84be027 |
| H | Celebración web y formulario funcional, pruebas proxima-browser | 0d00188 |
| I | Matriz WebKit/CEF, inspección de SDK y decisión WASM | 8740494 |
| J | Empaquetador offline y restricciones verificadas | c8d5e3d |
| K | Catálogo local y ocho paquetes independientes | 5e39fbb |
| L | Corpus ampliado, ensayo real, ejemplo de agente, documentación y revisión visual | Commit de cierre que contiene este informe |

I termina como **diseño experimental del host nativo**. No se ejecutó WKWebView,
CEF ni libobs: la única ruta de navegador autorizada es proxima-browser. No se
presenta la inspección estática del SDK como una prueba de captura de frames.
La recomendación condicional y sus gates están en webkit-vs-cef.md.

## Cobertura observable

Los tests nativos ejercitan referencias/ciclos/desconexiones, defaults y overrides,
subcontratos desconocidos, recursos/hash/dimensiones/CRC, paths/enlaces, ambas
orientaciones, todas las variantes, límites globales/ocupados y exportación. Las
pruebas modulares verifican recursos compartidos, deduplicación, eliminación
explícita de huérfanos/reglas incompatibles, namespace y rechazo del merge completo
de los dos packs originales. Estos no se modifican.

El navegador ejecuta el HTML/CSS/JS real con WAAPI: evento correcto, desconocido,
malformado, grande, repetido, no autorizado, rate limit, actualización de properties,
score, entrada/permanencia/salida, cancelación, error controlado, cleanup, reload,
H/V, móvil, movimiento reducido y descarga de ambos tipos de paquete. Los fetch
externo/loopback y ruta privada del iframe fueron bloqueados por CSP; el servidor
rechazó la ruta no declarada. Todas las solicitudes observadas fueron locales y
no hubo solicitudes externas exitosas. No se conectó un servicio externo.

Las seis comprobaciones adicionales usan respuestas reales del servidor local;
solo retienen temporalmente una respuesta para probar que una validación o una
plantilla antigua no reemplaza los cambios más recientes. No fabrican manifests,
respuestas del contrato Rust ni frames nativos.

La inspección visual confirmó la composición horizontal/vertical, el formulario,
el estado activo y el preview final. Capturas útiles: L-authoring-preview.png,
H-active.png, H-vertical.png, H-native-creator.png y H-mobile-stage.png. La captura
full-page H-mobile.png presenta repetición visual del header; se conserva como
artefacto defectuoso y **no** se usa para acreditar el layout. La revisión del DOM
encontró un header y scrollWidth=innerWidth=390; se tomaron capturas de viewport
y del stage para inspeccionar el contenido sin ese artefacto.

## Fallos conservados y correcciones

- D-cli-initial-failure.log: un límite escalar general impedía colores válidos.
  Se corrigió el dominio de color, conservando límites nativos estrictos.
- E-identity-correction.json: una variable local de animación sobrescribía la
  identidad del template; se corrigió y se regeneraron los cuatro ejemplos.
- H-browser-initial-failure.json: locator de formulario ambiguo; se usó el selector
  estable observado en la página. H-browser-reporting-failure.json: un campo HTTP
  sobrescribía el estado del test; se separaron ambos, sin rebajar el gate.
- L-show-control-initial-failure.json: fixture con el tag Scalar incorrecto;
  se corrigió a `int` según el enum real y se verificó la admisión/simulación.
- L-agent-workflow-initial-failure.log: el ejemplo enviaba element.json al comando
  package, que recibe una carpeta candidata. Se corrigió el flujo para empaquetar
  candidate/ y pasó la prueba completa.
- L-browser-initial-failure.json: una variable `document` ocultaba el DOM al cargar
  la base del formulario. Se renombró y se repitieron los 30 checks y los seis de
  formularios/respuestas atrasadas. No hubo cambios de umbrales para ocultarlo.

## Qué falta para producción

No se probó render nativo, memoria real del motor, integración libobs, timing de
frames, host CEF/WebKit, sandbox de procesos ni instalación oficial. Los previews
nativos son esquemáticos; el ensayo Show Control es simulado y usa un snapshot
hipotético. El score nativo es texto editable y la decoración permanece visible.
El SDK valida bytes PNG únicamente; los demás formatos fallan explícitamente.

El formulario sin código configura cuatro bases; composición libre y recursos
se editan por CLI/JSON. No hay marketplace backend, identidad de autor verificada,
proveedores conectados, actualización automática ni runtime WASM. Los paquetes
están preparados para revisión, no aceptados por el instalador de H15. El
[contrato de integración](integration-contract.md) describe exactamente los pasos
que requieren un incremento posterior en el producto.

No se inició Motive, adquirió lock multimedia, grabó, transmitió, tocó hardware,
modificó instalador o cambió el entorno global. No hubo push, merge, rebase,
release ni repositorio adicional. El servidor local del laboratorio sirve solo
contenido propio autorizado y puede cerrarse con Ctrl-C.
