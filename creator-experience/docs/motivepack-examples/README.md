# Ejemplos concretos del contenedor propuesto

Estos JSON ilustran la propuesta `.motivepack` 0.1 con los **bytes reales** de
CREATOR TECH y NEON ARENA. No son un nuevo schema de `CreatorPack`, archivos
instalables ni una implementación del importador. No se ha generado ningún ZIP.

| Archivo | Función |
|---|---|
| `<pack>.package.json` | Contenido hipotético del `package.json` del archivo distribuible |
| `<pack>.checksums.json` | Inventario exacto de paths lógicos, bytes y SHA-256 |
| `projection-validation.json` | Relación entre paths lógicos y archivos actuales bajo `creator-experience/` |

Reproducir con `python3 creator-experience/docs/motivepack-examples/build_examples.py`.
Solo se leen materiales propios y se escriben los ejemplos de documentación.
El script no lee paquetes ajenos, extrae archivos, ejecuta contenido ni conecta
a Motive. No reemplaza el broker ni el instalador H14.

El `file_count` incluye `package.json` y `checksums.json`. El tamaño total también
incluye ambos documentos. Checksums cubre todos los archivos excepto a sí mismo;
el paquete entero podrá tener un digest externo una vez exista el exportador
oficial. No se finge un hash de ZIP que no se generó. La autoría ejecutable,
scripts, prototipo HTML y evidencia de desarrollo quedan fuera del payload.

`authoring/*.svg` es fuente editable opcional. `previews/*.png` son estudios de
diseño, no imágenes utilizadas por el motor. Solo los dos `assets/*.png` que
declara cada manifest son recursos de runtime previstos.

Revisión futura con H14: confirmar nombres/versiones del envoltorio, política
de paths y cuotas, verificación del broker y selección local. Estos ejemplos
sirven para discutir el contrato sin introducir otra ruta de instalación.
