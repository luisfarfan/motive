# H14 — avisos Rust y procedencia verificable

El rescan completo del 17 de noviembre de 2026 termina **PASS para el
inventario de avisos**: cero omisiones, 50 paquetes recuperados y 86 archivos
de texto/procedencia con SHA-256 comprobado. Los paquetes que ya contienen
avisos no necesitan esta caché. El resultado no certifica distribución,
corresponding source, firma ni notarización.

Evidencia local:
`var/evidence/h14-license-inventory-1794952511870168000/report.json` conserva
el comando, exit code 0, hashes del resolver y de cada archivo, y la copia del
manifest. SHA-256 del manifest completo:
`3c13d794b0b09416a960c24a7029748f9027ce45835f83e12e6dcae52625e95e`.
El checkpoint previo de 46 paquetes y cuatro omisiones permanece como
evidencia histórica; no se cambian sus resultados.

## Los cuatro avisos recuperados

Las excepciones revisadas están fijadas en
`scripts/portable-rust-notice-supplements.json`. El resolver primero comprueba
el `.crate` original contra Cargo.lock y contra su hash fijado, y compara todos
sus miembros con el registry local. Rechaza enlaces, rutas ascendentes,
contenido modificado y archivos que excedan sus límites. No cambia el registry.

| Paquete | Opción usada | Prueba conservada |
|---|---|---|
| mac 0.1.1 | Apache-2.0 | Cargo.toml y README publicados declaran MIT/Apache-2.0. Todos los archivos del crate coinciden con los blobs de la revisión oficial `66afc663b68a65633ea165c742b5a9c6734581c2`. El crate no aporta revisión VCS. |
| pathfinder_geometry 0.5.1 | Apache-2.0 | Cargo.toml y cabeceras publicadas declaran ambas alternativas. Se conservan las cabeceras con los avisos de 2019 y 2020 de Pathfinder Project Developers. Su revisión declarada `a5e98fac00f433fe2ff4b2135383d82491b8bfc5` no está disponible mediante la API consultada; no se sustituye por otra. |
| seahash 4.1.0 | MIT | El commit oficial `3088c5c912b70b586d27bf553fbe964e025a2c89` tiene como único padre la revisión publicada `94b632aeac099031c373599313d5b5f0acbbaec0` y como único cambio añade LICENSE. La API oficial GitLab entrega el texto aunque las rutas web/raw consultadas devolvían 403. |
| simd_helpers 0.1.0 | MIT | El commit oficial `82040194cd05affb060bf94d6f19f82a771d07fb` tiene como único padre la revisión publicada `ca1a2f84aa386d758e98f8a609d990263932fb85` y como único cambio añade LICENSE. |

El texto Apache-2.0 procede de la [fuente canónica de Apache](https://www.apache.org/licenses/LICENSE-2.0.txt).
Los casos MIT conservan los JSON completos de commit y diff como prueba:
[simd_helpers](https://api.github.com/repos/lu-zero/simd_helpers/commits/82040194cd05affb060bf94d6f19f82a771d07fb),
[seahash commit](https://gitlab.redox-os.org/api/v4/projects/redox-os%2Fseahash/repository/commits/3088c5c912b70b586d27bf553fbe964e025a2c89),
[seahash diff](https://gitlab.redox-os.org/api/v4/projects/redox-os%2Fseahash/repository/commits/3088c5c912b70b586d27bf553fbe964e025a2c89/diff).
La equivalencia de mac usa el [árbol de la revisión oficial](https://api.github.com/repos/reem/rust-mac/git/trees/66afc663b68a65633ea165c742b5a9c6734581c2?recursive=1).

| Material | SHA-256 |
|---|---|
| Texto Apache-2.0 canónico, usado por mac y pathfinder_geometry | `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30` |
| LICENSE MIT oficial seahash | `23f18e03dc49df91622fe2a76176497404e46ced8a715d9d2b67a7446571cca3` |
| LICENSE MIT oficial simd_helpers | `d69f24ad84ec2ade64c0b68bdb31b41170e997b158370342056918329cc9af1e` |
| mac-0.1.1.crate | `c41e0c4fef86961ac6d6f8a82609f55f31b05e4fce149ac5710e439df7619ba4` |
| pathfinder_geometry-0.5.1.crate | `0b7b7e7b4ea703700ce73ebf128e1450eb69c3a8329199ffbfb9b2a0418e5ad3` |
| seahash-4.1.0.crate | `1c107b6f4780854c8b126e228ea8869f4d7b71260f962fefb57b996b8959ba6b` |
| simd_helpers-0.1.0.crate | `95890f873bec569a0362c235787f3aca6e1e887302ba4840839bcc6459c42da6` |

`PUBLISHED-*` identifica copias de las declaraciones, autores, README y
avisos presentes en el archivo publicado. `PUBLISHED-SOURCE-HEADERS.txt`
recopila cabeceras verbatim con separadores de procedencia; no es un NOTICE
atribuido al autor. El LICENSE oficial de seahash no contiene una línea de
copyright: se conserva exactamente, junto a sus autores declarados, sin
inventarla. La selección Apache no afirma una licencia nueva para los crates;
usa la alternativa ya declarada por el paquete publicado.

El paquete local show-control incluye ahora una copia exacta del LICENSE raíz
que corresponde a su declaración GPL-3.0-or-later. El inventario completo lo
detecta localmente y no necesita recuperar un aviso remoto.

## Repetición y comprobaciones

```sh
python3 scripts/prepare_portable_licenses.py
python3 scripts/test_portable_rust_notices.py
```

El primer comando usa `cargo metadata --locked --offline` para enumerar las
dependencias ARM64 actuales; no compila. El segundo pasó **3/3 pruebas** de
integridad: procedencia y cabeceras preservadas, rechazo de padre equivocado o
diff con código, y rechazo de cambios al registry o al texto remoto. Estas
pruebas sintéticas validan el resolver; la evidencia de los cuatro paquetes
anteriores procede de archivos y respuestas oficiales reales.

`--retry-missing --registry-dir <cache-exacto>` repara únicamente omisiones de
un inventario previo y etiqueta ese alcance; no sustituye el rescan completo.
El empaquetador vuelve a comprobar los hashes al copiar textos y pruebas.
`--require-complete-notices` mantiene el rechazo si quedan omisiones.

## Fuentes correspondientes: gates separados

`target/source-candidate-initial/manifest.json` conserva 19 archivos de
fuentes nativas y 463 crates, sin descargas bloqueadas. Su `material_status`
PASS solo significa que esos materiales están presentes. El resultado global
es PARTIAL y sigue pendiente por razones concretas:

1. Su snapshot Motive es de `635eecbe57c845bfdcecf307cd3996c75e168b9f`, anterior
   al binario final. Debe regenerarse desde el árbol final, incluidos el crate
   local Show Control, scripts, parches nativos y los avisos ahora resueltos.
2. Debe verificarse el vínculo de cada Mach-O final con fuente, revisión,
   opciones de build y parches aplicados, incluyendo los binarios oficiales de
   OBS/obs-deps, los módulos locales mac-capture/obs-outputs y los CLI FFmpeg.
   Una URL o un archivo fuente descargado no demuestra esa correspondencia.
3. El escáner detecta cualquier `.gitmodules`, pero no descarga ni clasifica
   gitlinks. En opus el archivo es vacío. MbedTLS declara `framework`; simde
   declara `test/munit`; OBS declara `deps/libdshowcapture/src`,
   `plugins/obs-browser` y `plugins/obs-websocket`. Se necesita registrar las
   revisiones exactas y materializar lo necesario, o justificar desde el
   ensamblado y recetas finales por qué un submódulo no forma parte del producto
   ni es necesario para reconstruirlo. El simple listado no cierra ese gate.
4. El candidato anterior conserva el inventario de avisos PARTIAL que tenía
   al crearse. No se reescribe: el candidato final debe incorporar el nuevo
   manifest PASS y sus textos/pruebas íntegros.
5. Falta validar que el conjunto y las instrucciones entregables permitan
   reconstruir el binario correspondiente. El script no certifica
   reproducibilidad ni obligaciones de distribución por completar descargas.

Firma de distribución, notarización, prueba fuera del checkout y prueba en
otra Mac son comprobaciones independientes del inventario de avisos y del
candidato de fuentes. Este informe no las marca PASS ni publica ningún
artefacto o source offer.
