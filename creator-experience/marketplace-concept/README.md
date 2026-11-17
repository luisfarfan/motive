# Catálogo opcional · mapa de experiencia

La biblioteca local del [prototipo](../prototype/index.html) es el punto de
partida visual. No se conecta a un marketplace.

Explorar → ficha → comparar versión/capacidades/licencia → descargar por decisión
explícita → verificación local → personalizar → revisar plan → instalador oficial.
Una carpeta recibida por otro medio entra directamente en verificación local.

| Objeto de catálogo futuro | Campos esenciales |
|---|---|
| Colección | ID estable, nombre, categoría, tags, autor, preview, versiones |
| Versión inmutable | versión, digest del archivo, bytes, licencia, capabilities, changelog, alcance de QA |
| Creador | nombre público, atribución, colecciones, estado de identidad separado |
| Reporte | pack/versión, código tipado, descripción voluntaria, estado de revisión |
| Selección editorial | colección, motivo, fecha, posibles intereses declarados |

No implementar estos objetos como tablas/servicios aún. El catálogo puede caer o
desaparecer sin impedir abrir proyectos ni usar recursos instalados. Un retiro
del catálogo informa al usuario; no borra sus archivos a distancia.

Ver [roadmap](../docs/marketplace-roadmap.md) y
[propuesta de contenedor](../docs/motivepack-proposal.md).
