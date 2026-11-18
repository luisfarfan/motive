# H14 — aplicación autocontenida: contrato y verificación

Estado actual: **PARTIAL**. B3 se ejecutó firmado fuera del checkout y cargó
37 rutas de dependencias nativas observadas sin depender de `.deps`; firma
estricta, closure ARM64 y herramientas incluidas pasan. MATCHDAY y las salidas
reales tienen su [evidencia B3](h14-show-control-b3-verification.md). La prueba
en otra Mac, notarización y reconstrucción de los binarios upstream siguen
pendientes. El staging unsigned descrito abajo se conserva como evidencia
inicial distinta. No se publicó un instalador ni se solicitó notarización.

## Layout y ownership

`scripts/bundle_portable.py` crea un destino nuevo, sin reemplazar bundles
existentes. Copia únicamente los nueve módulos abiertos por Motive:
obs-x264, obs-ffmpeg, obs-outputs, mac-capture, mac-avcapture, obs-transitions,
image-source, text-freetype2 y mac-videotoolbox. Las copias de obs-outputs y
mac-capture proceden de los artefactos locales de los parches H8/H14; no se
modifican las fuentes ni el bundle original de `.deps`.

El cierre de dependencias Mach-O añade libobs, Metal y las dylibs requeridas,
sin Qt, CEF, frontend OBS, navegador, updater ni recursos de la interfaz OBS.
Las slices se reducen a ARM64. Cada Mach-O obtiene un rpath relativo a su
`@loader_path`; el verificador rechaza dependencias no sistémicas fuera del
bundle, rpaths absolutos y enlaces simbólicos externos/rotos.

`Contents/MacOS` contiene Motive, el helper Keychain, obs-ffmpeg-mux y los CLI
ffmpeg/ffprobe. La importación no requiere una instalación Homebrew durante
el uso ordinario. Los dos CLI se compilan desde el commit FFmpeg
`38b88335f99e76ed89ff3c93f877fdefce736c13`, fijado por obs-deps 2026-10-23,
y enlazan contra las mismas dylibs oficiales ya incluidas. No se reconstruye
otro juego de codecs ni se ejecuta DSP adicional en el motor.

## Rutas persistentes

`src/paths.rs` detecta `Resources/MotivePortable.json`, versión 1 y layout
`macos-portable-v1`, desde el ejecutable. Un marcador existente pero inválido
falla explícitamente; nunca recupera silenciosamente las dependencias del repo.
El resolver no crea directorios ni migra o elimina contenido.

| Contenido | App portable | Desarrollo |
|---|---|---|
| Proyecto, mixer, perfiles, preferencias, assets, inbox y control socket | `~/Library/Application Support/local.motive.studio` | `<checkout>/var` |
| Grabaciones | `~/Movies/Motive` | `<checkout>/var/recordings` |
| Diagnósticos | `~/Library/Logs/Motive` | `<checkout>/var/evidence` |
| Módulos y recursos OBS | `Motive.app/Contents` | `<checkout>/.deps/OBS.app/Contents` |
| Herramientas de importación | `Contents/MacOS/ffmpeg` y `ffprobe` | Herramientas de desarrollo en PATH |

El almacenamiento de Show Control comparte el root de soporte de la app;
no se copian automáticamente configuraciones del simulador. La
[biblioteca de grabaciones](h14-recordings.md) presenta los archivos administrados
y su ubicación, con revisión nativa final separada del empaquetado.
Las pruebas de formatos v1–v5 pertenecen a sus contratos, no al empaquetador.

Los helpers portables deben existir, ser ejecutables y resolver dentro del
bundle. Un helper ausente no cae al PATH. Las rutas de desarrollo permanecen
aisladas; no hay migración automática de las grabaciones ni de los stores H13.

## Construir y verificar

Con Motive detenido y bajo el lock físico cuando se vaya a firmar/ejecutar:

```sh
python3 scripts/bundle_portable.py --profile release --output target/portable/Motive.app
python3 scripts/verify_portable.py target/portable/Motive.app \
  --report var/evidence/h14-portable-static.json --smoke-tools
```

El build necesita Cargo, Clang/Xcode y Python. La aplicación resultante no los
necesita para sus operaciones ordinarias. `--skip-build` exige los artefactos
preparados; `--unsigned` solo prepara una copia inspeccionable y no acredita
una app distribuible. Los scripts no alteran el trust store ni los permisos.

Para firma explícita se proporciona `--sign-identity` con una identidad
existente y autorizada. `--hardened-runtime` es un paso separado que también
requiere su prueba. Se firman primero los Mach-O internos, luego frameworks y
plugins, y finalmente la app. La comprobación usa
`codesign --verify --deep --strict`. No se usa `--deep` para firmar.

`verify_portable.py --smoke-tools` elimina variables DYLD del entorno, limita
PATH a `/usr/bin:/bin` y ejecuta solamente los dos CLI con `-version`, desde
`/`. Esto comprueba carga de herramientas; no abre Motive ni acredita audio,
video, acceso a cámara, imports reales ni recuperación.

## Licencias y fuentes

El bundle conserva avisos de OBS, librtmp/libcaption, el SDK de dependencias,
FFmpeg CLI y los crates Rust. `prepare_portable_licenses.py` recupera avisos
omitidos en paquetes crates.io mediante el commit exacto registrado en
`.cargo_vcs_info.json`; almacena URL y SHA-256 en un cache de build separado.
No sustituye una revisión ausente por la rama actual. Los avisos no encontrados
se enumeran expresamente y no cuentan como resueltos.

El checkpoint inicial recuperaba **46 paquetes** y dejaba cuatro casos
explícitos pendientes. El rescan completo del 17 de noviembre recupera
**50 paquetes con avisos omitidos**, conserva **86 archivos** de textos y
procedencia, y termina **PASS** con `missing=[]`; no es el total de dependencias
Rust, pues los avisos ya presentes se copian directamente de cada crate.
`mac 0.1.1` y `pathfinder_geometry 0.5.1` usan la alternativa Apache-2.0 que
declaran sus archivos publicados, preservados junto al texto canónico.
`seahash 4.1.0` y `simd_helpers 0.1.0` usan commits oficiales cuyo único cambio
respecto del padre publicado es añadir `LICENSE`. El resolver verifica el
archivo original contra Cargo.lock, todos sus miembros contra el cache local,
los padres/diffs y los hashes de los textos antes de aceptarlos. No modifica el
registry ni inventa avisos de copyright.

La procedencia completa y los límites están en
[h14-license-notices.md](h14-license-notices.md),
`target/portable-licenses/manifest.json` y la evidencia
`var/evidence/h14-license-inventory-1794952511870168000/`.
`--require-complete-notices` sigue rechazando cualquier aviso sin resolver;
el PASS del inventario no autoriza distribución ni certifica la totalidad de
sus obligaciones.

`Resources/ThirdParty/PROVENANCE.json` registra versiones, hashes, módulos,
estado del árbol y fuentes. Las rutas de build que aparecen como procedencia
no se usan como rutas de carga. El conjunto de fuentes correspondiente a todos
los binarios debe prepararse antes de cualquier distribución: enlaces y avisos
por sí solos no acreditan ese gate. No se ha publicado un source offer ni un
instalador.

`scripts/prepare_portable_sources.py --fetch --output <destino-nuevo>` prepara
un candidato local de fuentes, con archivos originales comprobados por SHA-256,
crates originales comprobados contra Cargo.lock y snapshot del árbol Motive.
El primer candidato, `target/source-candidate-initial/manifest.json`, tiene
**19 archivos de fuentes nativas y 463 crates**, sin descargas pendientes.
Su `material_status` es PASS, pero el conjunto sigue **PARTIAL**: hay que
revisar los submódulos detectados y comprobar correspondencia con el binario
final. El detector también marca el `.gitmodules` vacío de opus; la revisión
debe distinguirlo de framework (mbedtls), test/munit (simde) y los submódulos
de OBS. Ese snapshot, incluido su inventario de avisos PARTIAL, se conserva
como evidencia anterior: debe regenerarse con los avisos resueltos y todas
las fuentes/parches del binario final. El informe de avisos detalla estos
gates sin modificar el resultado histórico.

Referencias oficiales: [estructura y firma de código anidado de Apple](https://developer.apple.com/library/archive/technotes/tn2206/),
[firma desde dentro hacia fuera](https://developer.apple.com/documentation/Xcode/using-the-latest-code-signature-format),
[receta FFmpeg fijada por OBS](https://github.com/obsproject/obs-deps/blob/cbf0a3d8a0a34c07e822bda22a5f8214f91801d7/deps.ffmpeg/99-ffmpeg.zsh).

## Evidencia inicial y gates

El staging `target/portable-stage-audit/Motive.app` se creó unsigned con un
ejecutable de desarrollo anterior, exclusivamente para verificar ensamblado.
`target/portable-stage-audit/Motive-portable-audit.json` informa **30 Mach-O
ARM64**, cero dependencias/rpaths/symlinks externos y 156152668 bytes de payload.
No se lanzó ni se firmó; no es la beta candidate ni un resultado del binario
final. El build de los CLI quedó en `target/portable-tools/manifest.json`.

En aquel staging estaban pendientes ejecución, plugins, datos y reapertura.
Los checkpoints B1/B2/B3 posteriores del [índice H14](h14-beta-verification.md)
registran esas operaciones sobre bundles identificados. B3 usa PATH del sistema
y carece de overrides DYLD; guarda proyecto/Show Control fuera del bundle y
los restaura explícitamente tras reabrir, sin iniciar salidas.

El [candidato de fuentes B3](h14-source-correspondence.md) tiene su propia
procedencia y límites; material disponible no equivale a reconstrucción
reproducible ya ejecutada. Firma de distribución/notarización, otra Mac y los
gates de producción restantes continúan separados. La inspección estática no
los convierte en PASS.
