# `.motivepack` · propuesta de distribución 0.1

**Propuesta, no formato aceptado por H14 y no instalador implementado.** El schema
interno sigue siendo `CreatorPack` v1. La versión del contenedor es independiente
de la versión de contenido y de la versión del manifest.

## Contenedor

ZIP con extensión `.motivepack`, sin cifrado, ejecutables, enlaces ni entradas
especiales. Un directorio raíz lógico, sin carpeta adicional contenedora:

```text
package.json
manifest.json
checksums.json
LICENSE
assets/<basename declarado>
previews/<basename>.png
authoring/<fuentes SVG opcionales>
rules.json                     # configuración declarativa, activación opt-in
deck.json                      # bindings simbólicos, no IDs de una Mac
```

`package.json` propuesto: `package_version: 1`, `id`, `version`, `name`, `author`,
`license`, `description`, `category`, `tags`, `manifest: "manifest.json"`,
`manifest_schema_version: 1`, `coordinate_space: "design960"`,
`minimum_capabilities`, `preview_paths`, `property_ids`, `file_count`,
`total_uncompressed_bytes`, `compatibility_notes`. Son metadatos de un futuro
contenedor; **no añadirlos al manifest v1**. `author` no prueba identidad.

`checksums.json` propuesto: objeto estricto `{ "version": 1, "algorithm":
"sha256", "files": [{"path": "manifest.json", "bytes": 123, "sha256":
"64 dígitos hex"}] }`. Lista todos los archivos regulares salvo a sí mismo.
El hash se calcula sobre los bytes exactos, no sobre JSON reserializado. Las
entradas se ordenan lexicográficamente por path. El SHA-256 del archivo completo
puede entregarse por un canal aparte para fijar la descarga. Checksums internos
detectan corrupción, **no autentican al creador**; firma y confianza quedan para
una propuesta futura separada. No se inventa una firma válida con un hash.

## Verificación antes de instalar

1. Aceptar solo un archivo seleccionado localmente. Leer directorio ZIP antes de
   extraer; no hacer fetch de URLs declaradas por el pack.
2. Límites propuestos: 256 entradas, 128 MiB comprimidos, 128 MiB sin comprimir,
   64 MiB por asset, ratio máximo 100:1. Aplicar cuotas mientras se descomprime,
   incluso si el directorio miente. Estos techos del contenedor pueden ajustarse
   antes de ratificarse; no reemplazan las cuotas H11 ni el presupuesto del grafo.
3. Paths ASCII relativos con `/`, componentes alfanuméricos/guion/guion bajo/punto,
   sin `.` o `..`, prefijos punto, vacíos, `\\`, `:`, NUL, absolutos, drive letters
   o nombres duplicados. Rechazar colisiones case-folded para APFS insensible a
   mayúsculas. Rechazar symlinks, hardlinks, dispositivos y permisos ejecutables.
4. No resolver entradas fuera del directorio temporal privado. Abrir archivos
   exclusivos sin seguir enlaces. No confiar en comprobaciones `realpath` previas
   como defensa contra reemplazo concurrente. Limpiar solo objetos propios.
5. Verificar el inventario exacto y cada hash/tamaño. Manifest ≤256 KiB, Deck ≤64
   KiB; aplicar además el parser real de cada contrato. Rechazar JSON con claves
   duplicadas en el contenedor. Archivos extras o sin checksum invalidan el paquete.
6. Validar tipos por contenido y decodificar mediante el broker oficial. Un PNG
   anunciado no prueba dimensiones ni seguridad del decoder. SVG solo en
   `authoring/`, nunca en recursos de runtime. Ningún HTML/JS/shell/dylib/plugin.
7. Resolver cada `resource.file_name` exactamente a `assets/<basename>`; comprobar
   que su tamaño/hash/dimensiones coincide con el manifest antes de staging.
8. Consultar capacidades runtime y calcular plan sobre revisión/identidad actuales.
   Mostrar cuotas, selección de capturas pendiente, faltantes y conflictos. Fallar
   cerrado si no hay importador compatible. No sustituir silenciosamente el arte.
9. Entregar exclusivamente al instalador oficial de Motive. Su revisión local y
   recibos gobiernan la operación; importar no autoriza emisión ni arranca timers.

## Personalización y actualizaciones

Guardar localmente el manifest original, digest de paquete, bindings devueltos y
un conjunto de cambios tipados `{property_id, base_value, local_value}`. No guardar
secretos ni rutas del dispositivo en el archivo compartible. Los assets se
normalizan por el broker; su ID administrado puede diferir del hash de entrada.

Una actualización se descarga o abre como otro archivo completo y se valida
desde cero. Comparación de tres vías: base instalada, nueva versión y cambios
locales. Mantener el valor local si el target/tipo sigue siendo compatible; pedir
revisión si el ID desapareció o cambió su semántica. Reutilizar bytes idénticos por
hash tras verificación. Un downgrade también necesita revisión.

No ejecutar scripts de migración. Un futuro `migration_version: 1` podrá describir
renombres de property/source IDs con mapeos acotados; no está habilitado en v1.
Mantener la versión antigua utilizable hasta que el instalador confirme la nueva.
No prometer transacciones/rollback: ante fallo parcial, mostrar recursos creados,
bindings conocidos y recibo; reconciliar mediante el propietario antes de reintentar.

Recurso ausente: impedir instalación, conservar el informe y permitir seleccionar
de nuevo el paquete idéntico. Recurso instalado dañado: usar reimportación oficial
del original y reconexión explícita. Nunca buscar rutas del autor ni descargar un
reemplazo de una URL contenida en el pack.

## Acuerdo pendiente con H14

Ratificar nombres del envoltorio, revisión local, staging por recurso, registro de
versiones y recibos parciales con el importador H14. Ningún ZIP es emitido por esta
entrega como paquete instalable: las carpetas son los materiales revisables. El
prototipo únicamente ensaya el plan; no instala ni empaqueta.
