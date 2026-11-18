# Reproducir H16 sin ejecutar un navegador

El resultado reproducible de esta etapa es el build del crate independiente,
sus pruebas y la comprobación de API nativa con `-fsyntax-only`. No existe un
bundle ejecutable del host enlazado, firmado o probado. No se afirma un build
bit a bit reproducible de Chromium ni de Motive.app.

Entorno observado: macOS 27.2 ARM64, Python 3.14.7, rustc/cargo 1.99.1,
Node 24.20.0 y Apple clang 21.0.0 de Xcode. Python necesita el filtro de
extracción `tarfile` disponible desde 3.12; Rust necesita edition 2024 y las
APIs usadas por este crate. Estas versiones alternativas no se han probado.
No se instalaron herramientas globales. CMake no estaba disponible en PATH;
las comprobaciones de headers usan directamente clang, sin CMake.

## Preparación local

Ejecutar desde el worktree H16:

```sh
cd /Users/luisfarfan/Developer/products/motive-h16
python3 web-host-lab/tools/fetch_sources.py --download --extract
cargo vendor --offline --locked --manifest-path web-host-lab/poc/browser-host/Cargo.toml web-host-lab/.cache/rust-vendor
PYTHONDONTWRITEBYTECODE=1 python3 web-host-lab/tools/test_lab.py
```

El primer comando de Python permite únicamente descargar los seis archivos
fijados en [sources.lock.json](../research/sources.lock.json); no resuelve nuevas
versiones, instala, carga o ejecuta los binarios. Verifica SHA-256 antes de extraer
con filtro de rutas seguras. Si falta red, un hash no coincide o falta un archivo,
falla. Sin `--download` verifica la caché existente. Nunca sustituir el framework
de `.deps` para esta comparación.

`cargo vendor --offline` usa las dependencias que ya estaban disponibles en la
caché de Cargo; conserva los checksums del lock propio del laboratorio. Si faltan,
falla sin descargarlas. Para preparar otra máquina se deben obtener exactamente
esas versiones y comprobar sus checksums/licencias antes de repetir; este script
no instala Rust ni modifica configuración global. No copiar la configuración
impresa por `cargo vendor` al repositorio principal.

`test_lab.py` genera su propia configuración de fuente vendorizada, establece
`CARGO_HOME=web-host-lab/.cache/cargo-home`, usa el target local del crate y ejecuta
Cargo con `--offline --locked`. Lee Element Lab desde este mismo checkout. Todos
los temporales, paquetes y binarios de pruebas quedan dentro del laboratorio.
La caché ignorada no se incluye en los commits ni en una distribución.

## Qué verifica

| Comprobación | Evidencia regenerada | Alcance |
|---|---|---|
| Rust: 18 pruebas | `M-rust-tests.log` | 9 unitarias y 9 de IPC con UnixStream real; no proceso CEF |
| Clippy y formato | `M-clippy.log`, `M-format.log` | Todos los targets, warnings tratados como error |
| Python: 9 pruebas | `M-security.log` | Importación, hashes, bytes inmutables, rutas y política del broker |
| Proyección + Node: 2 pruebas | `K-goal-message.json`, `M-projection.log`, `M-runtime.log` | Evento real de fixture validado por Rust y runtime JS original |
| 4 comprobaciones CEF | `I-native-api.json`, `M-native-api.log` | Fixture y helper frente a A y B, sin enlazar ni ejecutar |
| Fuentes | `M-source-audit.json` | 6 archivos, hashes, fuentes CEF extraídas y diferencias |
| Alcance Git | `M-static-summary.json` | Ningún archivo cambiado fuera de `web-host-lab/` respecto a la base |

El resumen contiene fecha, comandos, HEAD previo al commit de cierre y hashes del
código probado. El manifiesto de hashes permite distinguir cambios locales del
contenido verificado; no pretende incluir su propio hash ni el commit futuro.
Los logs finales reemplazan solo los logs `M-*` de la ejecución anterior; los
fallos iniciales conservados tienen nombres separados. Todos viven en
[evidence/](../evidence/).

Los dos paquetes CEF tienen rutas separadas y coinciden con sus headers. Antes
de cada comprobación nativa se verifican los headers extraídos contra el archivo
fijado, y se registra compilador, fuente y hashes del fixture. No se mezclan A/B.
`-fsyntax-only` valida firmas y código C++; no valida símbolos del wrapper,
dependencias dinámicas, ejecución del sandbox, callbacks o destrucción real.

## Gate nativo pendiente

La instrucción de esta tarea exige autorización específica para una excepción a
la política de navegador. No se ha concedido. Por eso no se proporciona aquí un
comando para iniciar CEF ni se usa un navegador alternativo a proxima-browser.

Además de esa autorización, queda trabajo de implementación: entry point del
host, build/enlace del wrapper y helpers coincidentes, bundle portable, supervisor
externo con límites y reap del árbol, transporte de frames, conexión Rust/C++ y
bootstrap/dispatcher del runtime. El fixture actual tiene `RunOwnedFixture` sin
`main`; el helper tiene código preparado pero tampoco se ha enlazado. La tarea
demorada de cinco segundos es cooperativa, no un watchdog externo.

Una futura prueba autorizada empezaría únicamente con el HTML original incluido,
640×360 a 30 FPS, sin dispositivos ni credenciales, bajo el protocolo fijado en
[benchmarks/](../benchmarks/README.md). El consumidor
`poc/frame-consumer/check_frame.py` está preparado para un buffer real y sus
metadatos; todavía no se ejecutó contra salida CEF. Un JSON de observaciones o
un buffer artificial no cumplen ese gate. Contenido de terceros continúa
bloqueado hasta demostrar también aislamiento del proceso y de recursos del OS.
