# Motive Element Lab

Autoría offline de elementos reutilizables y packs modulares. Rama
`codex/motive-elements-foundation`, basada en `6019ad0`. Todo cambio vive aquí.
No es un instalador de Motive ni un renderer audiovisual. El prototipo web
no está integrado con libobs y no acredita aislamiento de procesos.

## Probar la autoría

Ejecutar desde la raíz del worktree. Requiere Python 3.10+, Cargo/Rust con soporte
edition 2024 y las dependencias de Cargo.lock disponibles localmente. Node se usa
solo para las pruebas del runtime JS. No se instala ningún comando global.

```sh
python3 element-lab/sdk/motive_elements.py serve --port 8776
```

Abrir [Element Lab local](http://127.0.0.1:8776/) usando exclusivamente
proxima-browser para el trabajo automatizado. «Creador nativo» permite elegir
cuatro bases, editar properties, validar con el crate real, ver H/V y descargar
el candidato. «Web Element» muestra una celebración real HTML/CSS/JS con eventos
sintéticos, cancelación, movimiento reducido y descarga de paquete web.
El servidor sirve únicamente archivos propios y termina con Ctrl-C.

## Crear, combinar y entregar

```sh
python3 element-lab/sdk/motive_elements.py capabilities
python3 element-lab/sdk/motive_elements.py new element-lab/.scratch/my-lower --template lower-third --id my-lower
python3 element-lab/sdk/motive_elements.py pack element-lab/.scratch/my-lower --set 'title="Alex Rivera"' -o element-lab/.scratch/my-candidate
python3 element-lab/sdk/motive_elements.py compose element-lab/.scratch/my-candidate element-lab/native-elements/community-alert --single-scene -o element-lab/.scratch/my-composition
python3 element-lab/sdk/motive_elements.py preview element-lab/.scratch/my-composition -o element-lab/.scratch/my-preview
python3 element-lab/sdk/motive_elements.py package element-lab/.scratch/my-composition -o element-lab/.scratch/my-elements.motivepack
python3 element-lab/sdk/motive_elements.py verify-package element-lab/.scratch/my-elements.motivepack
```

Las carpetas de salida deben ser nuevas. `pack` exporta una carpeta candidata;
`package` empaqueta esa carpeta con manifest/rules/LICENSE. Los previews nativos
son aproximaciones SVG. La composición conserva geometría: revisar solapamientos
antes de entregar. [Flujo completo para agentes](docs/agent-authoring.md).

## Entregables

| Área | Resultado |
|---|---|
| [Element Schema](element-spec/README.md) | Contrato de autoría versionado, DAG, properties, layouts, eventos y presupuestos |
| [SDK](sdk/README.md) y [compositor](composer/README.md) | CLI offline, validación Rust real, selección, combinación y ensayo simulado |
| [Lower Third](native-elements/lower-third/README.md) | Nombre/descripción, color, entrada/salida, H/V |
| [Community Alert](native-elements/community-alert/README.md) | Mensaje, acento, duración, trigger, variantes |
| [Goal Celebration](native-elements/goal-celebration/README.md) | Equipo, marcador editable, decoración y binding Show Control |
| [Countdown](native-elements/countdown/README.md) | Tiempo, estados informativos, start/reset nativos declarados |
| [Creator Tech](packs/creator-tech-minimal/README.md) / [Neon Arena](packs/neon-arena-minimal/README.md) | Un Starting Soon por colección: 1 escena / 5 fuentes / 5 capas cada uno |
| [Mezcla seleccionada](packs/mixed-example/README.md) | 1 escena / 3 fuentes / 3 capas; orígenes conservados |
| [Celebración web](web-elements/goal-celebration/README.md) | HTML/CSS/JS funcional, layouts H/V y API visual propuesta |
| [Packager](packager/README.md) / [catálogo](marketplace-contract/README.md) | 8 paquetes reproducibles con hashes, licencias y revisión offline |
| [WebKit/CEF](docs/webkit-vs-cef.md) / [WASM](docs/wasm-decision.md) | Evidencia oficial, matriz, recomendación condicional y gates pendientes |

Los ocho archivos distribuibles están en `marketplace-contract/packages/`.
`.motivepack` contiene solo datos declarativos; `.motiveweb` conserva HTML/JS por
separado. Ambos son contenedores experimentales de revisión, no instaladores.

## Verificación y límites

48 pruebas Python, 6 pruebas Node, 30 comprobaciones del harness y 6 del formulario
en proxima-browser, formato/clippy Rust y ocho paquetes reconstruidos byte a byte.
El ensayo del crate real prepara un trabajo simulado, con cero comandos vivos.
Ver [QA y checkpoints](docs/qa-report.md) para resultados y fallos conservados.

```sh
python3 -m unittest discover -s element-lab/tests -p 'test_*.py' -v
node --test element-lab/tests/runtime.test.mjs
python3 element-lab/packager/build_examples.py
python3 element-lab/sdk/motive_elements.py catalog-validate element-lab/marketplace-contract/catalog.json
python3 element-lab/sdk/motive_elements.py rehearse element-lab/native-elements/goal-celebration --events element-lab/tests/fixtures/goal-events.json --enable-for-simulation
```

No se verificó render nativo ni integración libobs. El host WebKit/CEF y la
instalación oficial están pendientes. El formulario ofrece presets configurables,
no un editor libre de capas. El marcador nativo es texto persistente editable;
la actualización dinámica por evento funciona en el ejemplo web. El SDK verifica
bytes PNG; rechaza JPEG/WebP/video hasta disponer de decoders revisados.
Validación JS, CSP y origen opaco no acreditan un sandbox seguro para terceros.

La [auditoría](docs/audit.md), [arquitectura](docs/architecture.md),
[integración futura](docs/integration-contract.md) y
[extracción del SDK](docs/repository-extraction.md) separan estos límites de las
capacidades implementadas. No se inició Motive, ni se tocó H15, hardware, streaming,
grabación o el instalador. No se hizo push, merge, rebase, release ni otro repositorio.
