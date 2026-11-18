# Empaquetador offline experimental

`../sdk/packaging.py`, Python stdlib. Separa `.motivepack` declarativo (CreatorPack
v1 sin JavaScript) de `.motiveweb` ejecutable en un futuro host. Son contenedores
**de revisión de Element Lab**, no formatos ratificados por el importador H15.
No instala, modifica el proyecto ni ejecuta el contenido.

```sh
python3 element-lab/packager/build_examples.py
python3 element-lab/sdk/motive_elements.py package element-lab/packs/mixed-example -o element-lab/dist/mixed.motivepack
python3 element-lab/sdk/motive_elements.py verify-package element-lab/dist/mixed.motivepack
```

ZIP con entradas ordenadas, fecha fija 1980-01-01, archivos regulares 0644 y
ZIP_STORED: bytes idénticos independientemente de mtime, ruta y reloj de build.
Cada archivo salvo checksums.json tiene SHA-256 y tamaño en el inventario exacto.
package.json incluye identidad, licencia, capacidades, compatibilidad, previews y
marcador de revisión. `payload_files/bytes` excluyen los dos documentos del
contenedor; no hay cálculo autorreferencial ni firma ficticia.

Límites: 256 archivos, 128 MiB de archivo/expansión, 64 MiB por entrada, ratio
100:1. Verificación acepta stored/deflate, rechaza cifrado, otros métodos,
entradas especiales, symlinks, bits ejecutables, colisiones de mayúsculas,
claves JSON duplicadas, paths absolutos/traversal, inventarios incompletos,
archivos extra, hashes/tamaños alterados y tipos activos dentro de previews SVG.
Las lecturas del origen usan descriptores, O_NOFOLLOW y comprobación de cambios.
No se promete protección contra otros procesos privilegiados o del mismo usuario.

El paquete nativo contiene manifest, rules, LICENSE, PNG usados y previews SVG
pasivos generados por el SDK. El web contiene exclusivamente sus assets declarados,
manifest, LICENSE y metadata. Verificar web usa un directorio temporal privado
tras las puertas ZIP, sin abrir HTML ni ejecutar JS. Luego se limpia ese staging.
La revisión estática de código web detecta referencias literales; no demuestra
seguridad de JS ofuscado. Solo contenido propio/autorizado en este prototipo.

Cada paquete se reconstruye dos veces y compara byte a byte. Los ocho ejemplos
están bajo `../marketplace-contract/packages/` y se validan también mediante el
catálogo. El hash externo fija los bytes; **no prueba identidad del autor**.
La instalación futura debe hacer una nueva revisión de confianza y capacidades,
decodificar con el broker nativo y guardar recibos del propietario.
