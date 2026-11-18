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
| Memoria y sesión prolongada | PARTIAL | B3 30/60 FPS y soak dual de 1800.07 s completos; ambos medios pasan decode/cadencia/píxeles/PCM; 39 skips y pausa visual 0.601 s conservados; RPC excedido, A/V no evaluado y ownership sin determinar |
| Bundle autocontenido | PARTIAL | B1/B2/B3 ejecutados fuera del checkout, firma/closure/tools PASS; segunda Mac, notarización y reconstrucción pendientes |
| RTMPS externo seguro | PARTIAL | B2 emitió 104,837 s a YouTube privado; usuario confirmó video/audio; MKV decodificado; copia remota y contabilidad completa siguen pendientes |
| Show Control real | PARTIAL | B3 demuestra entradas completas, cancelación posterior y continuidad sin MCP; concurrencia GPUI custom3000 PASS, stock450 NOT_OBSERVED; cancelación anterior no observada y FAIL geométrico estricto custom conservado |
| Live Deck y MATCHDAY | PARTIAL | B3 instalado por GPUI 73/73, celebración real y restauración exacta del proyecto/reglas desactivadas; recorrido de producción restante pendiente |
| Voz opcional | PARTIAL | Benchmark offline ejecutado, recall 50% falla fiabilidad; voz en vivo NOT IMPLEMENTED |
| UX y biblioteca de grabaciones | PARTIAL | Biblioteca y controles integrados; recorrido nativo final pendiente |
| Suite unificada sobre binario final | PARTIAL | 116+129 tests, Clippy/formato y 23/23 suites H1–H12 PASS sobre B3; H13 adicionales y producción nativa completa pendientes |

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
de [Live Deck](h14-live-deck-ui.md) tienen la evidencia GPUI y multimedia B3
descrita abajo; el recorrido completo sigue pendiente. Ninguna prueba de
fuente sustituye esa aceptación final.

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
accesibilidad y el usuario confirmó pegado/guardado exitosos; el owner verificó
asociación y recibo persistido. Cmd+V físico sigue sin prueba independiente.

Sobre estas fuentes: 111 tests raíz + 111 Show Control, ambos Clippy
`--all-targets -D warnings`, formato, prueba de routing nativo de pegado y
3 tests de harness pasan. Logs `var/evidence/h14-build/*-b2.log` y
`secure-paste-native-test.log`. Estas pruebas no sustituyen aceptación multimedia
sobre B2 ni prueban entrega a YouTube.

La [prueba privada RTMPS B2](h14-rtmps-b2-verification.md) posterior conserva
autorización explícita, confirmación GPUI y observación de YouTube Studio por
el usuario. El MKV se decodifica y sigue 21,698 s tras parar streaming. El
reinicio PID 93493 restauró el destino aprobado y la referencia opaca, sin
seleccionar destino ni iniciar salidas (`initial-state.json` bajo
`var/evidence/h14-memory-b2-owner30-1794954833415580000`).

El lifecycle de memoria B2 1080p30 terminó tres ciclos visibles/ocultos/retirados
y cleanup sin errores, conservado en `var/evidence/h14-memory-b2-30-01`.
Las asignaciones activas vuelven cerca del baseline después de retirar fuentes;
RSS y footprint retienen páginas. Esas observaciones no certifican ausencia de
fuga. La reproducción continúa oculta por configuración explícita de FFmpeg;
la siguiente prueba compara pausa manual sin cambiar comportamiento automático.
En ese checkpoint la sesión prolongada todavía estaba pendiente; B3 conserva
su ejecución posterior por separado.

La revisión de los cuadros B1 detectó un frame a escala completa antes del
ScaleIn de la celebración: Trigger y Animate eran acciones separadas. B3
incorpora una acción nativa compuesta y recibos exactos; los resultados de B3
siguientes verifican la corrección sin convertir la toma B1 en PASS.

## Checkpoint B3 — 17 de noviembre

Ejecutable SHA-256
`797b9722b0fe4725b13d5ccd1d2868c21d8f2cfa7ca3db784fee6297504549dc`,
compilado desde `d0deeb5` y empaquetado desde `ceb40ce`, en
`/Users/luisfarfan/Developer/motive-h14-portable/b3/Motive.app`.
116 tests raíz y 129 Show Control, ambos Clippy y formato pasan; logs
`var/evidence/h14-build/*-b3-*.log`. La firma estricta, closure ARM64 y herramientas
del bundle pasan. El PID 11038 cargó 37 rutas nativas observadas sin dependencia
del checkout; su contexto y lista están en
`var/evidence/h14-portable-b3-1794955908679384000`.

El [lifecycle B3 1080p30](h14-memory-b3-verification.md) conserva 89 muestras y
tres ciclos con una fase adicional de pausa explícita. En cada ciclo la CPU
mediana cae 43.7–50.5% respecto a los mismos videos ocultos reproduciéndose;
la pausa mantiene hijos y asignaciones vivas. Retirar las fuentes reduce
aproximadamente 499–502 MiB de malloc in-use. No es un dictamen de fuga ni una
comparación causal B2/B3. Colección nativa p95 0.897 ms cumple el presupuesto;
RPC p95 48.05 ms lo excede. GPU y A/V no están medidos en este lifecycle.

La [verificación Show Control B3](h14-show-control-b3-verification.md) conserva
75 s de MKV y RTMP local. La instalación GPUI completó 73/73 pasos. La pulsación
real de celebración produjo `ui-11038-1`; los cuadros decodificados de las tres
celebraciones completas (UI, MCP y desconexión del cliente) crecen sin el salto
de escala B1 en ambos medios. Hay 2273 frames MKV y 2266 RTMP, hueco máximo
34 ms, PCM continuo sin clipping. El contador progresa solo `0→1→2→3`.
La cancelación posterior, la protección ante edición concurrente MCP/CLI y la
continuidad después de desconectar MCP pasan. Dos intentos no observaron
cancelación anterior al primer tick; se conserva `NOT_OBSERVED`. Esa corrida no
evalúa la edición concurrente desde GPUI. Un trabajo concurrente permanece
`needs_reconciliation`, sin reejecución ni incremento de contador.

Las trazas iniciales permiten correlacionar las colas de ambos medios: los
100 paquetes de video retenidos aparecen en cada contenedor; falta un AAC
posterior a la orden de parada por salida. Dos frames entre encoder y observer
siguen sin atribución. Esto no se presenta como equivalencia entre contadores
ni entrega total garantizada.

La [prueba posterior de concurrencia GPUI](h14-ui-concurrency-b3-verification.md)
separa dos sesiones: **stock450 NOT_OBSERVED**, porque el segundo clic llegó
después de la animación, y **custom3000 PASS**, con duración temporal de 3000 ms
sin guardar. En custom hay 33 muestras de la misma operación aún running con
ganancia 0 dB y acción `UI · set_audio_gain`; el job queda en
`needs_reconciliation`, cursor 0, `MISSING_MUTATION_RECEIPT`, y el contador
permanece 0. La animación termina sin replay observado en el journal y la
ventana posterior de 0.94 s. Los cuatro medios decodifican completos, con
escalón RMS de 12.009–12.014 dB, sin clipping ni silencio interior de 100 ms.
Los stores conservan sus hashes. El gate geométrico estricto conserva **FAIL**:
cuatro descensos de altura de un píxel en la máscara de custom. El derivado
documenta sensibilidad al umbral, sin cambiarlo ni certificar la geometría.
El PASS concurrente de 3000 ms no sustituye la observación pendiente de 450 ms.

La persistencia B3 está en `var/evidence/h14-persistence-b3-01`: copias anteriores,
guardadas, estado de reinicio y restauración, y recibos de cierre. Proyecto y
Show Control se guardaron/restauraron por GPUI. El proyecto restaurado es
exactamente igual al JSON guardado; reglas y deck coinciden. El nuevo owner
inició con producción predeterminada; al restaurar Show Control quedó
desactivado, sin trabajos ni salida automática. Los stores de mixer y destinos
mantuvieron sus hashes. Las capturas de UI posteriores al reinicio muestran
una miniatura de Stage Manager; AX y JSON del núcleo prueban estas operaciones,
pero no sustituyen una revisión visual completa de ese tramo.

El PID 32487 completó tres ciclos de [lifecycle 1080p60 y soak dual de 1800.07 s](h14-memory-b3-soak-verification.md).
Ambos medios pasan decodificación completa, cadencia, píxeles y PCM; hay 108057 frames
MKV y 108028 recibidos por RTMP. CPU mediana 52.72% de un núcleo, footprint
máximo muestreado 1277.03 MiB, sin clipping ni ventanas silenciosas de 100 ms.
Se conservan 39 skips, un render lagged y una pausa visual de hasta 0.601 s.
RPC de memoria p95 50.88 ms durante el soak excede 20 ms; la colección nativa
p95 0.865 ms del conjunto cumple 2 ms. El análisis original conserva entrega
INCONCLUSIVE y A/V NOT_EVALUATED; no se infiere ausencia de fuga ni ownership
de las asignaciones. Ambos outputs llegaron a
quiescence en 189 ms y el owner cerró normalmente, sin errores de cleanup.

La repetición estática `h14-beta-b3-static-01` verifica 116 tests raíz, 129 Show
Control, ambos Clippy all-targets y formato. Los inputs del producto coinciden
exactamente con `d0deeb5`; scripts/documentación avanzan por separado. Las dos
suites de control en `h14-beta-b3-control-01` pasan con informe primario fresco
y cleanup confirmado. `h14-beta-b3-regressions-01` conserva un fallo del harness
de escenas al buscar `preview.png` bajo el checkout en vez del diagnóstico
portable. Su primer H1 devolvió `ok=true`, pero no acreditó la reproducción
del estímulo esperado por otra ruta de desarrollo; no se selecciona para la
matriz final. Se corrigieron los lectores y se repitieron escenas y H1 sin
alterar B3 ni relajar los checks; los originales permanecen intactos.

La [consolidación de 23 regresiones B3](h14-b3-regressions-verification.md)
selecciona las repeticiones completas de escenas y H1, más las demás suites.
Las **23/23 suites H1–H12** tienen primario fresco PASS, exit cero y cleanup
confirmado. Las tres corridas seleccionadas suman 1087.02 s de suites;
se verificaron hashes, fuente compilada, cliente y restauración de stores,
incluida la corrida fallida. No es una única ejecución continua. El PASS H12
no contiene un límite RSS: su settling final conserva mediana 858.45 MiB.
El resultado no cubre automáticamente las pruebas adicionales H13, los
gestos GPUI, hot-unplug físico ni denegación real de permisos.
El [derivado posterior del soak](h14-memory-b3-soak-verification.md#derivado-posterior-framing-y-paquetes-finales)
prueba la correspondencia inicial de framing Annex B/AVCC y clasifica la cola
como `STOP_BOUNDARY_PACKETS_NOT_DELIVERED`: aparecen 143/144 paquetes de video
finales retenidos y 112/112 AAC por destino. El video ausente tiene DTS
1.267 ms y 5.433 ms después del retorno de stop, respectivamente; no hay
ausencias trazadas anteriores o dentro de su bracket. La diferencia previa
al observer sigue sin localizarse. Se conservan los conteos originales,
el análisis inconcluso y la entrega global parcial; no se afirma identidad
criptográfica de payload ni entrega completa. **La beta sigue no aceptada.**
