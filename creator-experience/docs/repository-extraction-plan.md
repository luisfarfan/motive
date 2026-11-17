# Preparar ahora, extraer después

No se creó ningún repositorio adicional, remote, backend ni publicación.

| Futuro destino | Contenido | Condición de extracción |
|---|---|---|
| `motive-packs` | `packs/`, fuentes gráficas, previews, licencias, motion declarativo, authoring, validación de contenido | Contrato de packs versionado y CI offline reproducible |
| `motive` | Production, broker, importer, UI GPUI, Show Control/Deck runtime, permisos, bindings/recibos | Permanecen en la app; no copiar a herramientas de packs |
| `motive-creator` posible | Editor/exportador dedicado | Solo si autoría con herramientas normales resulta insuficiente; sin implementación actual |
| `motive-hub` posible | Índice de catálogo, versiones, perfiles, reportes y distribución opcional | Resolver integridad/licencias/compatibilidad antes de alojar contenido |

La carpeta `prototype/` y las especificaciones GPUI son estudios de producto. Su
implementación no se traslada como renderer de runtime. El HTML no forma parte
del paquete instalable. `evidence/` sigue asociado a la versión exacta de cada
entrega; los binarios de compilación, caches y servidores no se trasladan.

## Orden recomendado

1. Fijar una versión de contrato y su suite de conformidad desde Motive. Decidir si
   se publica un crate pequeño solo de modelo o una CLI de validación. No copiar
   manualmente `packs.rs` ni mantener schemas divergentes.
2. Mover contenido manteniendo `packs/<id>/` y paths relativos. Sustituir únicamente
   el path de desarrollo del harness por la dependencia versionada o CLI fijada.
3. Conservar GPL-3.0-or-later, fuentes editables y atribuciones. Los fonts de sistema
   son referencias, no archivos redistribuidos. No exportar .deps ni SDKs.
4. Ejecutar los mismos validadores y regeneración; comparar hashes de manifests y
   recursos. Revisar previews por versión de macOS/fonts, no exigir hash idéntico
   de raster tipográfico entre distintos sistemas operativos.
5. Publicación futura requiere autorización separada. Generadores pueden vivir en
   el repositorio de autoría, pero jamás incluirse como scripts ejecutables de un
   `.motivepack` que Motive vaya a cargar.

Un pack debe abrirse sin red ni checkout de Motive para inspeccionar JSON/PNG/SVG.
La validación autoritativa sí necesita el contrato fijado hasta que exista un
validador distribuible. Esa dependencia temporal se declara, no se oculta.
