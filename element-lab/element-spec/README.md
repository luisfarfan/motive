# Contratos de autoría v1

Un **Element** es una unidad reutilizable de identidad, anatomía, recursos,
propiedades y comportamiento visual declarado. No es otro owner audiovisual.
Una primitive es una capacidad cerrada del motor; un composed element es un
grafo de primitives; un Creator Pack reúne composiciones exportadas.

`element.schema.json` describe autoría nativa. `web-element.schema.json` describe
contenido HTML/CSS/JS que solo ejecuta el harness experimental. Son contratos
distintos y sus paquetes tienen políticas diferentes.

## Semántica nativa

| Campo | Regla v1 |
|---|---|
| schema_version / kind | Exactamente 1 / native_element; versiones desconocidas fallan |
| id / version | ID local de hasta 48 caracteres; versión numérica major.minor.patch |
| root / nodes | DAG local, máximo 64 nodos y profundidad 32; sin referencias ausentes, ciclos o nodos desconectados |
| primitive.native | `VisualDefinition` del crate real; el JSON Schema no duplica sus campos |
| composed.children | Referencias a nodos existentes; grupos de autoría sin transform heredado ni renderer propio |
| layers | Solo primitives; toda primitive debe tener capa; layouts horizontal y vertical obligatorios |
| layouts | Coordenadas design960: 960×540 / 540×960; order 0..31; límites finales del crate |
| resources | Bytes locales verificados, hash SHA-256, dimensiones, licencia; rechaza recursos sin uso |
| properties | Tipo, default, bounds y bindings explícitos; sin coerción ni dos escritores sobre un destino |
| variants | Patches tipados de properties; default → variante → overrides explícitos |
| states | Documentación: native_widget, authoring_only o future; no crea una máquina ejecutable |
| animations | Fade/slide X/scale del contrato; `animation_ref` materializa valores después de aplicar properties |
| events | Reglas visuales de Show Control deshabilitadas; `$scene` resuelve la única escena exportada |
| dependencies | Solo nodos embebidos a la versión del elemento; no resolver registries ni descargar código |
| capabilities | required se valida; future se informa en unsupported, sin simular implementación |
| budget | Cuotas locales más límites globales; estimaciones de textura, no un límite de RSS |
| metadata / license | Descripción, categoría, tags, límites y licencia declarados |

Las referencias se namespacean por el ID del elemento. IDs largos exportados se
acortan con un sufijo SHA-256 determinista. Un elemento exporta una escena; se
pueden combinar varias con `compose`, conservándolas o usando `--single-scene`.
No hay herencia CSS, expresiones, scripts, fuentes tipográficas empaquetadas,
keyframes ni transiciones nuevas. La selección de escena puede pedir una
transición ya admitida mediante una acción real.

`creatorpack_property` solo admite un binding hacia text_content, widget_title,
widget_subtitle o shape_color. Las demás propiedades son `compile_time`:
modifican una definición antes de exportarla. Un recurso se cambia editando su
descriptor y bytes y volviendo a validar; no existe un selector dinámico de
paths. El SDK verifica PNG de 8 bits sin entrelazado. JPEG/WebP/video pueden
existir en el contrato nativo, pero sus bytes se rechazan con
`ASSET_DECODER_UNAVAILABLE` hasta implementar un verificador adecuado.
Licencias distintas entre un elemento y sus recursos se rechazan para no perder
atribución al exportar al contrato v1.

## Validación normativa

Los archivos publicados usan vocabulario JSON Schema 2020-12 para herramientas
de edición. **Pasar solo JSON Schema no acredita compatibilidad Motive**.
`validate` ejecuta el dialecto estricto documentado en `sdk/common.py`, resolución
semántica, assets, presupuestos y el crate Rust. Los campos native y actions
permanecen deliberadamente abiertos en el schema exterior y cerrados por Rust.
La implementación local añade límites de profundidad/tamaño, rechazo de NaN,
claves duplicadas, paths, enlaces y archivos especiales. No es un validador
genérico de todos los keywords de JSON Schema.

La API v1 del laboratorio es experimental y fijada al baseline indicado por
`capabilities`. Cambios incompatibles requieren nueva schema_version y migración
explícita; no convertir un documento de una versión futura silenciosamente.

## Semántica web

El entry point y todo import estático/asset deben estar declarados y tener hash.
TypeScript se compila antes de empaquetar; no hay compilador TS ni CDN implícito.
Las dependencias locales declaran versión, licencia y asset; no hay descarga.
Solo HTML, CSS, JS/MJS, SVG y PNG en este prototipo. Los límites de mensaje y
frecuencia se aplican en JS; FPS y memoria son solicitudes para un futuro host,
no garantías. Todos los permisos del prototipo son falsos. Ver el
[contrato del runtime](../web-elements/runtime-prototype/README.md) y la
[integración futura](../docs/integration-contract.md).
