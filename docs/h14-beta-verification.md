# H14 — Beta Candidate: ejecución y gates

Estado: **EN EJECUCIÓN; beta no aceptada**. Rama `codex/h14-beta`, worktree
independiente `motive-h14`, desde `main`/`origin/main`
`57de1c55150aceb42c574b0308e1a9a2752eb70a`. No se autoriza push, merge,
release, publicación ni emisión pública de H14.

## Baseline

H13 y Show Control no tuvieron archivos solapados en su merge. Show Control
sigue siendo un crate independiente; el simulador no conecta al motor.
Se conservaron las pruebas de H13 en `motive-h13/var/evidence`, con hashes y
límites en el [índice histórico](h13-evidence-index.md). No certifican H14.
La [aceptación H13](h13-native-acceptance.md) permanece parcial por captura
congelada, diferencias de contabilidad terminal y memoria residente.

Leídos los contratos, la verificación H12/H13, las decisiones y el código del
owner, captura, outputs, empaquetado y Show Control. `docs/product.md` conserva
exclusiones históricas previas a H13; H14 sigue el alcance solicitado, sin
añadir Windows/Linux, nube, CEF ni otro reloj/compositor/mixer.

## Incremento inicial: observar antes de corregir

El filtro asíncrono existente observa cámara, pero la captura SCK de OBS usa
IOSurface y render síncrono. Sus dimensiones no demuestran nuevos buffers.
Se compila una copia local del módulo oficial OBS 33.0.1, verificada contra
el archivo fuente fijado. El parche añade observaciones atómicas, no cambia
buffers, timestamps, filtrado, captura, render ni recuperación. `.deps` queda
intacto. El código fuente y avisos de ese módulo deben acompañar la distribución.

`capture_diagnostics` distingue callbacks, estados SCK, muestras con superficie,
PTS/repeticiones/regresiones, consumo de superficie por OBS, intentos de bind,
renders con textura y errores. Son contadores distintos; no prueban contenido
fresco. `NO_RECENT_CAPTURE_BUFFER` es un aviso, no prueba de pérdida: una ventana
estática puede ser válida. Error fatal de sesión/estado stopped sí entra en la
política existente de parada controlada y recuperación explícita.

El registro del proc diagnóstico ocurre después de crear exitosamente la
captura, evitando retener un contexto liberado cuando falla `create`. Las
edades no restan timestamps posteriores al instante observado. La revisión
independiente encontró ambos riesgos antes de la primera ejecución física.

Fuentes primarias: [Apple SCFrameStatus](https://developer.apple.com/documentation/screencapturekit/scframestatus),
[captura de Apple](https://developer.apple.com/documentation/screencapturekit/capturing-screen-content-in-macos),
[callbacks libobs](https://docs.obsproject.com/reference-libobs-callback)
y el árbol local fijado de OBS 33.0.1. `idle` no significa fuente perdida.

Las [trazas de salidas](h14-output-accounting.md) observan metadata antes del
plugin, sin equipararla a escritura o recepción. `output_diagnostics {target}`
es una consulta acotada CLI/MCP. Al salir tras las barreras, el owner guarda
`last-shutdown.json`; ese archivo no certifica medios completos.

Rutas de ejecución ahora separan el bundle marcado portable de desarrollo;
no se migran ni borran stores existentes. El paquete de desarrollo conserva
sus rutas. La verificación del paquete autocontenido se registrará por separado.

## Gates de entrega

| Área | Estado actual | Evidencia pendiente |
|---|---|---|
| Frescura y detección de captura | PARTIAL | Instrumentación compilada; reproducir escenario y analizar contenido real |
| Integridad/finalización de salidas | PARTIAL | Callback oficial y harness; matriz A/B multimedia |
| Memoria y sesión prolongada | NOT IMPLEMENTED | Mediciones H14 de carga equivalente |
| Bundle autocontenido | PARTIAL | Cierre Mach-O estático preparado; ejecución fuera del checkout pendiente |
| RTMPS externo seguro | NOT IMPLEMENTED | Dominio/entrada segura en desarrollo; destino privado autorizado pendiente |
| Show Control real | PARTIAL | Recibos/journal con 108 tests; adapter propietario y medios pendientes |
| Live Deck y MATCHDAY | NOT IMPLEMENTED | Instalación revisable y operación real GPUI |
| Voz opcional | NOT IMPLEMENTED | Comparación y benchmark WAV, sin modelo obligatorio |
| UX y biblioteca de grabaciones | NOT IMPLEMENTED | Listado/estados/Finder y recorrido real |
| Suite unificada sobre binario final | NOT IMPLEMENTED | Identidad final, medios y manifiesto |

Primer checkpoint de instrumentación: **75 tests Rust**, Clippy all-targets
con warnings como errores y formato pasan. Logs en
`var/evidence/h14-build/diagnostic-{tests,clippy}-reviewed.log`.
Son checks del incremento, no PASS sobre un binario final de beta.

Pruebas físicas exclusivamente bajo `motive/var/run/physical-test.lock`, owner
H14 root. Cada fallo y cada repetición conservarán su directorio de evidencia.
