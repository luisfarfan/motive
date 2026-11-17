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
| Frescura y detección de captura | FAIL | GPUI propio avanza en MKV/RTMP; fixture suspendida y recuperación fallida conservadas; repetir final |
| Integridad/finalización de salidas | PARTIAL | Matriz A/B ejecutada; reordering falla al cerrar, mitigación por defecto sin reordering; repetir final |
| Memoria y sesión prolongada | PARTIAL | Instrumento y self-test PASS; runner y fixture listos, owner/soak pendientes |
| Bundle autocontenido | PARTIAL | B1/B2 ejecutados fuera del checkout, firma/closure/tools PASS; segunda Mac, notarización y reconstrucción pendientes |
| RTMPS externo seguro | PARTIAL | Persistencia revisada; destino privado YouTube aprobado localmente; pegado corregido en B2, entrada segura y emisión pendientes |
| Show Control real | PARTIAL | B1 aceptó evento real de GPUI y completó animación; harness falló durante espera, repetición B2 pendiente |
| Live Deck y MATCHDAY | PARTIAL | Instalación GPUI 73/73 y celebración visibles en B1; comprobación completa de medios y repetición B2 pendientes |
| Voz opcional | PARTIAL | Benchmark offline ejecutado, recall 50% falla fiabilidad; voz en vivo NOT IMPLEMENTED |
| UX y biblioteca de grabaciones | PARTIAL | Biblioteca y controles integrados; recorrido nativo final pendiente |
| Suite unificada sobre binario final | NOT IMPLEMENTED | Identidad final, medios y manifiesto |

Primer checkpoint de instrumentación: **75 tests Rust**, Clippy all-targets
con warnings como errores y formato pasan. Logs en
`var/evidence/h14-build/diagnostic-{tests,clippy}-reviewed.log`.
Son checks del incremento, no PASS sobre un binario final de beta.

Primer arranque nativo conservado en `h14-capture-1794949837386172000`:
falló antes de crear medios porque `@(!bool)` producía un entero JSON, mientras
el contrato Rust exige booleano. Se corrigió a `@NO`/`@YES`, sin relajar el
schema; el arranque siguiente y la consulta MCP del owner pasan. La primera
captura observa un callback SCK `suspended`, cero superficies y
`CAPTURE_NOT_READY`, aunque la fixture registra dibujos. No se inició ninguna
salida con esa fuente. Es evidencia de suspensión, no una atribución causal a
Stage Manager ni prueba de contenido fresco.

El primer ensayo dual del harness conservó su fallo de orden de configuración:
intentaba crear el segundo perfil después de iniciar la primera salida, y el
núcleo lo rechazó con `OUTPUT_BUSY`. Ahora prepara ambos perfiles antes de
iniciar. La repetición `h14-output-integrity-1794950260066766000` decodifica MKV
y RTMP sin huecos ni clipping; los paquetes AAC ausentes de cola caen después
de la orden de parada. La matriz completa posterior conserva los fallos de
reordenamiento y la interpretación causal en [contabilidad](h14-output-accounting.md);
no se restan contadores para declarar equivalencia.

El [informe de captura](h14-capture-investigation.md) conserva la comparación de
productores y recuperación fallida. El benchmark opcional de
[voz offline](h14-voice-offline.md) no habilita voz en vivo. Los controles nuevos
de [Live Deck](h14-live-deck-ui.md) aún necesitan recorrido nativo y medios sobre
el bundle integrado. Ninguna prueba de fuente sustituye esa aceptación final.

Pruebas físicas exclusivamente bajo `motive/var/run/physical-test.lock`, owner
H14 root. Cada fallo y cada repetición conservarán su directorio de evidencia.

## Checkpoint portable B1/B2 — 17 de noviembre

B1 se ejecutó desde `/Users/luisfarfan/Developer/motive-h14-portable/b1/Motive.app`
con PATH del sistema y sin overrides DYLD. Cargó 36 rutas nativas sin dependencia
del checkout; no se modificó HOME. Desde GPUI se revisó e instaló MATCHDAY
(73/73 operaciones, 5 escenas/14 fuentes/25 capas totales, incluidas las previas).
La pulsación de celebración creó el evento `ui-54774-1` y una animación nativa,
observada también en la interfaz. El harness conservó un FAIL propio por un
argumento Python duplicado durante la espera y detuvo ambas salidas. El owner
sí completó posteriormente el trabajo. El fallo original y los medios quedan en
`var/evidence/h14-show-control-b1-01`; no se convierten en PASS por corregir el
verificador. La repetición es obligatoria.

Antes de salir se guardaron explícitamente proyecto v5, mixer vacío y Show
Control; Cmd+Q cerró normalmente. Su `last-shutdown.json` fue copiado a
`var/evidence/h14-portable-b1-1794952716958645000/normal-shutdown.json`.
No hubo transmisión externa. El intento de entrada de credencial se canceló
sin guardar; el reporte del usuario de pegado fallido motivó una corrección
local de AppKit, documentada en [pegado seguro](h14-secure-paste.md).

B2 incorpora esa corrección, compilada desde `d188bb0` y empaquetada desde
`587402c` (el segundo commit cambia solo preparación/documentación de fuentes).
Ejecutable firmado SHA-256:
`16294752571dc8599df8fdadfa4710963c4d51bd957d5cf569be2ff53a539ceb`.
Ruta: `/Users/luisfarfan/Developer/motive-h14-portable/b2/Motive.app`.
La firma estricta, closure ARM64/rpaths y smoke de ffmpeg/ffprobe dan PASS en
`var/evidence/h14-build/portable-b2-verification.json`. El proceso 75663 cargó
41 rutas nativas sin dependencia del checkout; contexto y rutas en
`var/evidence/h14-portable-b2-1794953837847861000`. El nuevo arranque no restauró
ni inició automáticamente proyectos o salidas. El destino aprobado permaneció
sin selección ni clave. El botón Pegar del campo seguro se observó por
accesibilidad; el pegado real por el usuario todavía está pendiente.

Sobre estas fuentes: 111 tests raíz + 111 Show Control, ambos Clippy
`--all-targets -D warnings`, formato, prueba de routing nativo de pegado y
3 tests de harness pasan. Logs `var/evidence/h14-build/*-b2.log` y
`secure-paste-native-test.log`. Estas pruebas no sustituyen aceptación multimedia
sobre B2 ni prueban entrega a YouTube.
