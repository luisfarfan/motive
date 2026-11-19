# H17 — candidatas portables B7, B8, B9 y B10

Estado del empaquetado: **PASS** para la auditoría local descrita. Aceptación
general de beta: **FAIL** por los gates de captura; no es una distribución
notarizada ni una release publicada.

## Identidades inmutables

Las cuatro apps están en
`/Users/luisfarfan/Developer/motive-h17-portable/{b7,b8,b9,b10}/Motive.app`.
Son ARM64, release optimizadas, backend predeterminado GPUI-pre 0.3.12 y sin
features opt-in. La firma es ad hoc local, sin acceso a Keychain ni Developer
ID y sin notarización. Cada candidata conserva sus archivos; crear B10 no
reemplazó B7, B8 ni B9.

| Candidata | CFBundleVersion | Commit de runtime/preparación | Ejecutable SHA-256 |
|---|---|---|---|
| B7 | `17` | `96b545a1e00b7e0eb7dd0f48be7fd8f5d809dfe7` | `d5b702d8b245a143575a6dd77cc80dc047425139f0ebc16db8c1f8451eb0ad31` |
| B8 | `18` | `1a9dd23` | `5cc0fe08c54f7f4d5e166bce18dbe515a31c92ab92793f3c406e94a42fdc3059` |
| B9 | `19` | `667b027910b12fb029a08534c683a671f1e4b5bb` | `7ecf6b28288fed4cc7121d755b435310a59d80ced8268475e8c884e8d0576e24` |
| B10 | `20` | `8806f283f14df077f5d73de4d03d93da5a990d29` | `1390fa6834c22c7df002b72d3f3e3c9c7d2bb993149663ac07334b4282f279c9` |

| Candidata | mac-capture empaquetado SHA-256 |
|---|---|
| B7 | `cae7b5b1eb8f07d89c93627c1e9eb1de23b68b41f829585d34e813d159ee5792` |
| B8 y B9 | `c316e83d91f2ab1a54dff983232cdcfc1b8fa1e2311b29b4f35bba4f680447b2` |
| B10 | `fae4bb68823d1963b7644da74ae77dcf2b56dd8d29b56948c37803b23047a197` |

`var/evidence/h17-checks/b7-identity.json`, `b8-identity.json`,
`b9-identity.json` y `b10-identity.json` conservan las identidades. B8 incorpora
el diagnóstico SCK previo a start y los primeros textos AX focalizados; B9 completa los textos de
confirmación local y corrige el feedback de armado de Show Control. El plugin
empaquetado B9 coincide byte por byte con B8. Eso no acredita recuperación de
captura, ni permite transferir resultados funcionales entre ejecutables.

B10 incorpora el guard de geometría de ventana y conserva identidad propia
del módulo de captura. La auditoría estática no prueba la recuperación física
de captura; ese resultado pertenece al ensayo de B10.

## Evidencia

Los informes `b7-portable.json`, `b8-portable.json`, `b9-portable.json` y
`b10-portable.json` de `var/evidence/h17-checks/` tienen auditoría estática
**PASS**, cero issues,
firma estricta y smoke de ffmpeg/ffprobe con exit 0. Incluyen dependencias,
plugins, herramientas de medios y rpaths auditados. El campo runtime de cada
informe estático queda `NOT_EVALUATED`: las ejecuciones reales se registran
separadamente y no se altera ese recibo.

`b7-release-build.log` conserva `cargo build --locked --release`. Los logs
`b7-bundle.log`, `b8-bundle.log` y `b9-bundle.log` conservan el empaquetado con
avisos completos y versiones explícitas. B9 se construyó en 12,73 s mediante
`cargo build --locked --release --target-dir target/h17-gpui-a`; el ejecutable
se copió con `cp -c` a `target/release/motive` antes de llamar a
`bundle_portable.py --bundle-version 19 --skip-build --require-complete-notices`
con la ruta B9 indicada arriba. El SHA del ejecutable de build, anterior a
los ajustes de rpath y firma del bundle, queda separado del SHA del bundle
en `b9-bundle-result.json`.

`b9-build-inputs.json` conserva hashes de 195 archivos de runtime/build y el
estado Git inicial. El único archivo modificado era el observador
`scripts/observe_h17_native_ux.py`; los inputs de producto permanecieron
idénticos durante el build. La procedencia del bundle registra por ello
`motive_dirty: true`, sin ocultarlo. La preparación y auditoría de B9 no
abrieron Motive ni modificaron stores o el lock del owner.

B10 se construyó en 17,43 s con el mismo comando release y sin features. Se
clonó el ejecutable con `cp -c` a `target/release/motive` y se empaquetó en
6,63 s con `--bundle-version 20 --skip-build --require-complete-notices`.
`b10-build-inputs.json` registra el commit limpio `8806f283` y 197 inputs de
runtime/build; sus hashes permanecieron iguales después del build, empaquetado
y preparación de fuentes. `b10-build-result.json`, `b10-bundle-result.json` y
sus logs conservan comandos, duración y resultado. La procedencia del bundle
es limpia (`motive_dirty: false`). El SHA del ejecutable anterior al ajuste de
rpath y firma es
`fb64f12bdd80921da8ab834bc66bc8e03b7e3938dd349a2100f4c41aa20c57bb`;
el de la app firmada está en la tabla de identidades.

`b10-portable.json` confirma auditoría estática **PASS**, cero issues y las dos
herramientas de medios con exit 0. Sólo se ejecutó `-version` para cada
herramienta, con cwd `/` y sin variables DYLD; no se abrió Motive ni se generó
media en esta etapa. Su campo runtime permanece `NOT_EVALUATED`.

Los runners B7 lanzan el ejecutable con cwd `/`, sin variables DYLD, y hablan
con el socket del owner portable verificando PID. La matriz de nueve salidas
de `h17-output-matrix-b7` y la sesión de `h17-show-b7-owner` comprueban este
runtime fuera del checkout; cada caso termina el proceso normalmente. Los
fixtures y receptores son instrumentos externos, no dependencias del producto.
No se ha probado todavía la segunda Mac. El recorrido nativo B7/B8 y las
verificaciones posteriores de B9 pertenecen al
[informe UX](h17-native-ux-verification.md); este informe de empaquetado no
declara aprobados esos recorridos.

Los ensayos posteriores de B10 tienen recibos separados:
[captura y reselección explícita](h17-capture-verification.md),
[cancelación antes del tick](h17-show-before-tick-protocol.md) y
[recursos duales 1080p60/720p60](h17-b10-resources.md). La secuencia controlada
de admisión negativa/reselección pasa con alcance acotado; el gate general de
captura no queda cerrado. Pre-tick sigue **BLOCKED** tras dos intentos reales.
Recursos conserva **PARTIAL**: los cuatro medios pasan los controles de
formato/cadencia/píxeles/PCM, con delivery inconcluso y A/V sin evaluar.
Ninguno de esos resultados transfiere a B10 los PASS funcionales de B7 o B9.

## Fuentes y distribución

`/Users/luisfarfan/Developer/motive-h17-portable/source-candidate-b7/manifest.json`
conserva material **PASS**: 25 fuentes nativas, 463 paquetes Rust, avisos
completos, sin materiales bloqueados ni revisión de submódulos pendiente.
Su snapshot Motive es `4398f04`; el runtime es idéntico al de B7 (el siguiente
commit solo instrumenta un verificador de audio).

Se preparó además
`/Users/luisfarfan/Developer/motive-h17-portable/source-candidate-b9/manifest.json`
mediante `scripts/prepare_portable_sources.py --output` y esa ruta, usando
archivos ya cacheados, sin `--fetch`. Registra commit `667b027`, 25 fuentes
nativas y 463 paquetes Rust; `material_status`, avisos y materiales de
submódulos son **PASS**, con listas de pendientes vacías. SHA-256 del manifest:
`7eb87512795cb273b2b09e6b63f8c15fcd9a9271f5550994cea21758920aab81`.

`var/evidence/h17-checks/b9-source-correspondence.json` coteja los 195 archivos
de inputs B9 con sus copias y hashes del snapshot: **PASS**, cero diferencias.
El snapshot conserva también el observador modificado; el inventario no lo
presenta como contenido del commit limpio. Los logs de preparación están en
`b9-source-candidate.log` y `b9-source-preparation.json`.

El snapshot nuevo
`/Users/luisfarfan/Developer/motive-h17-portable/source-candidate-b10/manifest.json`
se preparó desde el commit limpio `8806f283`, sin `--fetch`, antes de editar
este informe. Conserva 25 fuentes nativas y 463 paquetes Rust; materiales,
avisos y materiales de submódulos tienen **PASS**, con listas de pendientes
vacías. SHA-256 del manifest:
`12d15421b65d9099cea6f104f10ff6c67ffaa59bee8423b480890475b39a09d7`.
`b10-source-correspondence.json` coteja los 197 inputs del build con sus copias
y entradas del inventario: **PASS**, cero diferencias. Los comandos y logs
quedan en `b10-source-preparation.json` y `b10-source-candidate.log`.
La corrección posterior `1e01dcc` sólo cambia el analizador offline y sus tests
para reconocer la resolución explícita del plan. Sus 149 tests Python finales
y el FAIL instrumental previo quedan en el informe de recursos; no cambia el
runtime B10 ni se presenta como parte de su snapshot de fuentes.

El estado agregado del paquete de fuentes sigue **PARTIAL**. Materiales
completos y coincidencia de archivos no acreditan una reconstrucción binaria
reproducible. Antes de distribuir deben verificarse las instrucciones de
rebuild y el flujo de firma/distribución autorizado. No se ha publicado
instalador, binario ni oferta de fuentes.

Los tests de formato de proyectos v1–v5 y reglas guardadas cubren compatibilidad
de lectura; la restauración nativa B7 de Show Control se comprobó desarmada con
armado explícito y recibos durables. Los ensayos conservan journals y restauran
únicamente stores propios mediante comprobación de bytes/hash. El recorrido
GPUI y el recibo final de preservación se documentan en los informes H17.
