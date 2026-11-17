# H14 — correspondencia B1 y submódulos de fuentes

La revisión de fuentes de B1 comprueba **103 archivos sin diferencias** entre
`611e93006e8e1577e70f9a59d2e76d5ca77fe218`, declarado por el bundle, y el snapshot
`977d2006b35ef70af6ccc5c96dbfb4485e513901`. Incluye Rust, bridge y parches nativos,
Show Control, Cargo.lock/manifiestos, build.rs y las recetas locales de build
y empaquetado. El delta Git posterior al build contiene documentación,
verificadores y recuperación de avisos; no cambia esos insumos compilados.
Esto acredita igualdad de fuentes seleccionadas, no reconstrucción binaria.

El candidato B1 se conserva sin cambios en
`/Users/luisfarfan/Developer/motive-h14-portable/b1/source-candidate`:
347 archivos Motive, 19 archivos nativos y 463 crates. Su manifest tiene
SHA-256 `9614a90b4fdf14272e6fd5459e79f53f8a4404fc670b151a25604580023d4184`,
avisos PASS, material PASS y resultado global PARTIAL. Conserva la lista de
submódulos pendientes que tenía al generarse. Las nuevas fuentes descritas
abajo están en la caché de preparación; no se añadieron retroactivamente a B1.

## Clasificación para el producto y sus recetas

| Fuente | Relación con B1 | Evidencia de configuración |
|---|---|---|
| MbedTLS/framework | Necesario para configurar las bibliotecas TLS presentes en el bundle | MbedTLS 3.6.4 CMakeLists.txt:318–325 exige framework/CMakeLists.txt y añade el subdirectorio incondicionalmente. La receta OBS desactiva programas, pruebas y generación; esas opciones no eliminan el requisito. |
| OBS/plugins/obs-browser | No es uno de los nueve plugins del runtime; necesario para configurar el árbol oficial completo | OBS plugins/CMakeLists.txt comprueba su CMakeLists.txt antes de añadirlo. El submódulo retorna con ENABLE_BROWSER=OFF antes de buscar CEF. Conservar la fuente no añade navegador ni CEF al producto. |
| OBS/plugins/obs-websocket | No está en el runtime; necesario para configurar el árbol oficial completo | OBS comprueba su CMakeLists.txt. ENABLE_WEBSOCKET=OFF retorna antes de buscar sus dependencias. Motive usa su propio control socket. |
| OBS/deps/libdshowcapture/src | Exclusivo de captura Windows, no usado por el build macOS de estos módulos | OBS registra win-dshow solo para WINDOWS. Se conserva su fuente y el hijo capture-device-support para cerrar el inventario declarado. |
| simde/test/munit | Pruebas de SIMDe, no necesarias para la receta utilizada | obs-deps usa -Dtests=false; simde/meson.build:451–453 solo entra en test cuando esa opción está activa. Se conserva el submódulo de pruebas en el conjunto de fuentes. |
| opus | No hay submódulo faltante | .gitmodules está vacío y el árbol oficial recursivo no contiene gitlinks. La alerta inicial era conservadora. |

La clasificación de OBS corresponde a estos nueve módulos de B1: obs-x264,
obs-ffmpeg, obs-outputs, mac-capture, mac-avcapture, obs-transitions,
image-source, text-freetype2 y mac-videotoolbox. Los dos módulos con cambios
locales conservan scripts y parches; los otros módulos y dylibs proceden del
bundle oficial fijado. La revisión no reconstruyó esos binarios ni cambió
opciones de sus compilaciones originales.

## Material añadido a la preparación del siguiente candidato

Se descargaron **seis archivos oficiales, 1.279.497 bytes en total**, sin
ejecutar código ni modificar `.deps`. Diez respuestas oficiales de árboles
recursivos, con hashes y revisiones fijados, comprueban los gitlinks de los
padres y todos los hijos transitivos. No quedan hijos adicionales en esos
árboles. Los archivos originales conservan sus avisos y scripts internos.

| Fuente y ubicación relativa al padre | Commit fijado | SHA-256 del archivo |
|---|---|---|
| mbedtls → framework | `2a3e2c5ea053c14b745dbdf41f609b1edc6a72fa` | `f5934ffcad4c32a95f9281f0f95908eb471ee34df721fb9d6ad4adb9567f6b61` |
| obs-studio → plugins/obs-browser | `d4db73e7e5d5b51d853177c8cddc796715a8ac84` | `e68174d5460aaa400208f0e769a786f88e9b66e809ed6b893bda2e9e5b7a3b5f` |
| obs-studio → plugins/obs-websocket | `e28f84975984340e84fc4879cfc05741cc0afde1` | `2e200547fd453b8fecb70f3b1d17f3adf447dd26aa5278dcf2dfb989c51ba6a2` |
| obs-studio → deps/libdshowcapture/src | `8878638324393815512f802640b0d5ce940161f1` | `f473bd8040fd772bb590ad03952031a056dbaab9d9310b10d9ebd8bee3da2407` |
| simde → test/munit | `da8f73412998e4f1adf1100dc187533a51af77fd` | `835a9ee03e3b9560af5a2e4465394e00337398f5baba9d686083b8e1d93f0c30` |
| libdshowcapture → external/capture-device-support | `fe9630974d47f51bf54826e72fb8b654e620aa93` | `bdf253133a61fdf2498628c5a8ec2a52a17e63b0d36abb546009eeaef80bfeb7` |

Cada registro en `scripts/portable-sources.json` incluye URL oficial, SHA-256,
revisión del padre, subruta y función. `source_tree_proofs` fija URL y hash de
cada árbol recursivo. El preparador compara las declaraciones `.gitmodules`,
gitlinks y mappings completos; rechaza diferencias, árboles truncados,
revisiones incorrectas, rutas ascendentes y archivos no comprobados. También
comprueba que el comentario PAX del archivo de cada submódulo y padre con
prueba identifica el commit esperado.

Las nuevas escrituras de caché rechazan destinos que no sean archivos
regulares mediante lstat antes de descargar o copiar. Preparan el contenido
en un archivo temporal exclusivo, comprueban su hash y publican con replace
después de revalidar el destino. No usan un nombre .part predecible ni siguen
enlaces simbólicos colgantes para escribir.

`submodule_material.layout` registra el padre, la subruta inmediata y la
ubicación lógica acumulada de cada archivo. Al ensamblar las fuentes se
elimina únicamente el directorio raíz del archivo y se sitúa su contenido
en esa subruta del padre ya ensamblado. Las ubicaciones lógicas parten del
nombre de la fuente; no sustituyen los directorios concretos de `.deps` que
esperan las recetas de Motive. El preparador almacena archivos y pruebas;
no extrae ni ejecuta automáticamente los proyectos.

La comprobación real de caché devuelve **PASS de material de submódulos**:
25 archivos nativos previstos, seis mappings, diez pruebas, cero archivos
bloqueados y cero diferencias de gitlinks. El resultado global de fuentes
permanece **PARTIAL**. No se generó otro candidato durante esta revisión;
el siguiente snapshot debe crearse tras el commit correspondiente.

## Evidencia y límites

`var/evidence/h14-b1-source-review/report.json` conserva comparaciones SHA-256
de los 103 archivos y las fuentes oficiales consultadas. Los miembros de
recetas/CMake usados para la clasificación están copiados verbatim con sus
hashes. `submodule-material-check.json` conserva el inventario real y confirma
el hash intacto de B1. El resolver tiene **5/5 pruebas** de integridad: mapping
transitivo, omisión/hijo equivocado, rutas/repositorios inválidos y pruebas
de árbol truncadas o modificadas, incluida una revisión PAX incorrecta del
padre. Otras **6/6 pruebas** cubren caché, enlaces colgantes, un enlace
introducido durante staging, un .part previo y fallos de validación; junto
con las tres pruebas de avisos, la suite portable pasa **14/14**. No sustituyen
el chequeo de archivos reales.

La reconstrucción completa desde el material entregable, su relación con
cada Mach-O y la suficiencia de las instrucciones siguen pendientes. Las
fuentes adicionales no acreditan igualdad binaria, cumplimiento legal,
notarización ni distribución. Las verificaciones de la aplicación firmada
pertenecen al informe de ejecución de B1, no a esta revisión estática.
