# WASM · extensión opcional, diferida

No se implementó runtime WASM. HTML/CSS/JS siguen siendo la vía web de autoría.
WASM podría servir para cómputo pesado determinista (por ejemplo un algoritmo
original de partículas o una transformación matemática) cuando un perfil real
muestre que JavaScript no basta. No es una API de layout ni sustituye DOM/CSS.

El [modelo de seguridad oficial de WebAssembly](https://webassembly.org/docs/security/)
separa memoria del módulo y exige imports explícitos, pero la política efectiva
depende del embedding; no elimina agotamiento de recursos, canales laterales o
riesgos de las APIs que el host exponga. No conceder WASI, archivos, sockets,
Production ni credenciales por incorporar WASM.

Para aceptarlo en una versión futura: caso medido, módulo declarado/hash/licencia,
imports permitidos, memoria máxima, deadline/cancelación fuera del módulo,
concurrencia limitada y prueba adversarial. Ningún permiso o extensión `.wasm`
está admitido por el empaquetador web actual. TypeScript sí puede compilarse a JS
antes de empaquetar: declarar el JS resultante y todas sus librerías locales; no
se introduce un compilador TS ni dependencias CDN en este SDK.
