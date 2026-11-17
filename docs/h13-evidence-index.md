# H13 — índice de evidencia · PARTIAL

Inventario de lectura del 2026-11-17. **No declara H13 completo.** Las pruebas
pertenecen al ejecutable indicado en cada fila; un PASS de un incremento no
certifica por sí solo el bundle final. Los informes originales fallidos se
conservan. Rutas relativas a este worktree, con métricas y hashes de medios en
los JSON enlazados; no se vuelven a decodificar para elaborar este índice.
La producción GPUI dual de más de 30 minutos ya se ejecutó en G; su aceptación
es **parcial**, con continuidad visual, contabilidad terminal y memoria todavía
pendientes. La alerta corregida y la única repetición controlada de exclusión G
pasan; las pruebas físicas terminaron y el lock se liberó.

## Bundles separados

| Clave | SHA-256 del ejecutable firmado | Incremento observado |
| --- | --- | --- |
| A | `914aa8e98371127ed1fef43b0a0497dd558c8d7326b5dae6fb3c92cee785911e` | Canvas; 62 tests, Clippy/formato PASS |
| B | `be13f8555e1e06087be0d443e4040b23acf497337f43f5f363150119cb3ffd3d` | Audio SCK, mixer, micrófono |
| C | `dc9c38a82d72c86cacd668a88c25ec26f0e12cbbb7b9d0c829d3e820a20ef38f` | Salidas duales, exclusión propia, A/V visible; 67 tests |
| D | `dc1188bcffe943b51813311996f84e06684da024bb65d6916c1aeeccf5bba408` | Diagnóstico opt-in de los bloques cero; 69 tests |
| E | `0444029860e28e53b7e74fc0ab836fa790cc8a691f2f7cfc95702cd9e6ac3952` | Tono con anticipación, matriz dual normal y rendimiento; 69 tests |
| F | `f9e0b2865817a08c3fb62afa43f5b4c7becddb2087b57a1902087ca20745570c` | IDs canónicos de audio; 70 tests |
| G | `d9b8d7026e301330d62f2f541af90c1dd245a86f79ad1fd8a35e81b08e0e2d93` | Bundle actual: guard de cierre/importaciones; 71 tests, Clippy/formato PASS |

## Resultados confirmados

| Área | Bundle | Evidencia y alcance confirmado |
| --- | --- | --- |
| Canvas y video real | A | [Matriz 7/7 PASS](../var/evidence/h13-video-1794931993726668000/report.json): 720p30 y 1080p30/60, horizontal/vertical, VT y control x264. 59/59 avances del patrón a 60 FPS; no duplicación de 30. Cut/Fade, persistencia v5 y continuidad AAC. Cero lag/skips/drops; colas finales 66–67 ms conservadas. |
| Canvas repetido en el bundle actual | G | [Matriz 7/7 PASS](../var/evidence/h13-video-1794939774901717000/report.json): 3019 frames en las siete configuraciones; 59/59 avances a 60 FPS y 29/29 a 30. Cero lag/skips/drops, interior ≤34 ms a 30 FPS y ≤17 ms a 60; cola máxima 67 ms, AAC ≤22 ms. Fuentes controladas, Cut/Fade y persistencia v5; no verifica captura física ni gestos GPUI. |
| Dos entradas y control independiente | B | [Piloto PASS](../var/evidence/h13-system-audio-1794932404437443000/report.json): 440 Hz + aplicación propia 997 Hz, 24,64 s PCM, 741 frames, pico −23,72 dBFS. Pasos solicitados −12 dB producen −11,993/−11,992 dB; mute conserva la otra fuente. Error RMS aislado −0,068/−0,006 dB; sin clipping. |
| RTMP, recuperación y silencio | B | [Etapas RTMP/recovery/silence PASS](../var/evidence/h13-system-audio-1794932515805158000/report.json). El informe global permanece FAIL por su etapa siguiente; [reanálisis de transiciones PASS](../var/evidence/h13-system-audio-1794932515805158000/transitions-reanalysis.json). Recuperación explícita tras nuevo PID del mismo bundle. SCK entregó ceros, por lo que no prueba ausencia física de paquetes. |
| Cut/Fade y mixer v2 | B | [Etapas transitions/persistence PASS](../var/evidence/h13-system-audio-1794932730872027000/report.json); ese informe global permanece FAIL por A/V. Conserva identidad/reutilización y stores de proyecto/perfiles. Cola final VT hasta 133 ms registrada. |
| Micrófono físico | B | [PASS](../var/evidence/h13-system-audio-1794932987734593000/report.json): UID integrado explícito, cinco intervalos mezcla/aislamiento/mute/restauración, 18,176 s PCM, 547 frames, pico −18,75 dBFS. Recaptura acústica del fixture controlada; no implica ausencia de feedback propio. |
| Exclusión del sonido de Motive | C | [PASS con control positivo](../var/evidence/h13-self-audio-exclusion-1794934285059972000/report.json): emisor propio 2011 Hz/−30 dBFS y externo 997 Hz, luego 2011 Hz externo al mismo nivel. Captura de escritorio sin monitorización. Supresión estimada −122,74 dB, limitada por el piso del análisis; gate relativo −45 dB. 401 frames, sin clipping/lag/skips/drops. Emisor desactivado al reiniciar. |
| A/V, condicionado a ventana visible | C | [Con snapshots](../var/evidence/h13-system-audio-1794934345250779000/report.json) y [sin snapshots](../var/evidence/h13-system-audio-1794934414391892000/report.json): siete parejas de pulsos cada uno; mediana audio−video −35,83/−67,48 ms y rango 33/0 ms. PASS bajo gates de desfase absoluto <250 ms y rango <100 ms. No explica congelamientos previos ni acredita ventana oculta. |
| Hueco del tono: diagnóstico y corrección | C/D/E | [Fallo original conservado](../var/evidence/h13-outputs-1794933990447407000/report.json): 11/12 medios PASS, MKV con hueco de 1024 muestras. [Traza anterior](../var/evidence/h13-audio-trace-analysis-1794935248189182000/report.json) localiza cero antes de AAC en tres vidas. [A/B posterior](../var/evidence/h13-tone-lead-analysis-1794935516851025000/report.json): 1/1/1 → 0/0/0 ceros en las vidas observadas; 7576 bloques fuente y 3548 mix. Tono anticipa entrega 20 ms; PTS/fase/480 muestras intactos. Tres MKV y seis RTMP PASS. |
| Matriz dual sin diagnóstico | E | [PASS normal](../var/evidence/h13-outputs-1794935484169154000/report.json): cuatro casos y doce medios, sin errores de análisis/limpieza. Ganancia/mute, widgets, Cut/Fade, pérdida de receptor/muxer, supervivencia y recuperación por destino. Archivos intencionalmente parciales identificados. |
| Matriz dual final | G | [4/4 casos y 12/12 medios PASS](../var/evidence/h13-outputs-1794940477678855000/report.json): smoke, producción, pérdida de receptor y pérdida del helper muxer propio. Stop/restart/recovery independientes, Cut/Fade, widgets y ganancia/mute, sin errores de análisis/limpieza. Diez archivos completos y dos parciales intencionales distinguidos; ocho comparaciones entre destinos. CLI/MCP, sin sustituir aceptación GPUI ni soak. |
| PCM y rendimiento ABBA | E | [28/28 medios funcionales](../var/evidence/h13-performance-reanalysis-1794936503607571000/report.json), 10/28 de cadencia estricta. [Control fresco 6/6 funcionales](../var/evidence/h13-performance-1794936684794726000/report.json), 2/6 estrictos, 7281 frames. Error RMS máximo 0,1123/0,1154 dB, peaks lineales máximos 0,034913/0,035251; sin clipping/lag/skips/drops. Véanse límites cuantitativos debajo. |
| Restauración de ID malformado | F | [Núcleo real PASS](../var/evidence/h13-audio-id-validation-1794937378949652000/report.json): dos stores inválidos rechazados antes de mutar; identidad/instancia conservadas y ganancia controlable después. Restauración del archivo y retirada de la entrada de prueba. No renumera IDs v1/v2 válidos. |
| H8/cierre dirigido | G | [Manifest PASS](../var/evidence/h13-regressions-1794937943048758000/manifest.json): 14 ciclos, 47,6 s, rechazo `SHUTDOWN_PENDING` de ambos arranques, preflights e importación; consultas disponibles. Salida del owner tras liberar peer, stores restaurados y cleanup limpio. |
| Importación real durante cierre | G | [PASS](../var/evidence/h13-import-shutdown-1794938158330488000/report.json): clip 1080p/20,27 s; 29 consultas con worker activo, máximo 88,9 ms. Cierre solicita en 30,7 ms; resultado `completed` observado antes de salir en 3,271 s. Stores intactos e inbox propio retirado. |
| Sistema de audio repetido en el bundle actual | G | [Siete etapas PASS](../var/evidence/h13-system-audio-1794940056194848000/report.json): pilot, RTMP, recovery, silence, transitions, persistence y microphone. 4080 frames; ganancia −12 dB medida entre −11,988 y −11,996 dB; error RMS aislado máximo 0,023 dB. Sin clipping/lag/skips/drops, AAC ≤22 ms. Colas de video de hasta 134 ms conservadas. No incluye A/V, exclusión propia ni ausencia real de paquetes SCK. |
| A/V visible final | G | [PASS](../var/evidence/h13-system-audio-1794941016583790000/report.json): siete pulsos, mediana audio−video +24,271 ms y rango 33 ms; fixture visible activada mediante Finder/CUA, sin snapshots diagnósticos. Alineación de extremo a extremo, incluida reproducción/redraw; no latencia cero ni resolución de los congelamientos históricos. |
| Exclusión propia final | G | [Única repetición PASS](../var/evidence/h13-self-audio-exclusion-1794946744795131000/report.json), tras [control de piso PASS](../var/evidence/h13-self-audio-floor-1794946499075579000/report.json): −123,174221 dB frente al gate <−45 dB, estimación próxima al piso numérico y con control positivo externo. Mismo verificador/gates, cero saturación/lag/skips/drops; gap final de video 133 ms conservado. El [informe final](h13-system-audio-exclusion-final.md) mantiene el primer G FAIL de −16,412 dB y la atribución del fondo INCONCLUSIVE; no se convierte ese archivo ni el PASS de C en esta nueva evidencia. |
| Memoria tras liberar videos | G | [Probe completado](../var/evidence/h13-video-memory-1794940705116187000/report.json), documentado en `89eed5e`: baseline → cuatro videos → cuatro reemplazados → cero durante 20 s. RSS mediana 178,41 → 673,55 → 1030,91 → 1141,38 MiB. Resultado explícito `PROBE_COMPLETED_NOT_A_MEMORY_BUDGET_PASS`; sin gate RSS ni afirmación de ausencia de fugas. [Investigación y vmmap](h13-encoder-tail-investigation.md). |
| Producción GPUI prolongada | G | [Observador cerrado PID 92305](../var/evidence/h13-native-1794941679130733000/report.json): 5402 snapshots, mismo hash G, `collector_ok` y `observed_shutdown` verdaderos. Canvas 1080p30, ventana/cámara, micrófono/app, widgets y perfiles VT 6000/4000 kb/s. [Métricas duales](../var/evidence/h13-native-1794941679130733000/metrics-summary.json): 1814,745 s con ambas salidas activas; RTMP1 1815762 ms (30 min 15,762 s), REC1 1884483 ms. Stop/restart, fallo/recovery dirigidos, cancelación de handshake y cierre dual observados. Aceptación parcial. |
| Medios de la producción nativa | G | [Ocho archivos estructurales](../var/evidence/h13-native-analysis-1794944731171479000/report.json): siete funcional/integridad PASS y RTMP3 intencionalmente parcial INCONCLUSIVE; cadencia estricta 8/8 PASS, video ≤34 ms/AAC ≤22 ms, PCM completo sin saturación. Global INCONCLUSIVE por cobertura/fallo intencional, no aceptación GPUI. El intento RTMP5 no produjo archivo. Diferencias terminales output/decodificado se conservan debajo; ese gate no formaba parte del PASS. |
| Audio nativo con anclas observadas | G | [Informe PCM](../var/evidence/h13-native-pcm-1794944899076084000/report.json) y [resumen](../var/evidence/h13-native-pcm-1794944899076084000/summary.json): 18 comparaciones de ganancia PASS, −12,000512…−11,994918 dB; error RMS máximo 0,142828 dB. REC1/RTMP1 referencias PASS y 34 ventanas de eventos calibradas PASS. 79 fragmentos, 48684 ventanas superpuestas de 20 ms, cero saturación. Fallos RTMP3/5 en REC3 son diagnósticos extrapolados desde ancla posterior; global INCONCLUSIVE, sin afirmar continuidad audible completa ni atribuir el 997 Hz del micrófono a la app. |
| Contenido visual de la toma nativa | G | [Revisión visual FAIL](../var/evidence/h13-native-visual-extract-1794944740966518000/visual-review.md): 16 probes Cut/Fade completos PASS, lower y countdown visibles; Fade cancelado conserva su alcance parcial. Alerta REC3/RTMP3 ocluida por orden de capas; contador de ventana repetido en REC3 a 185/245 s y en una muestra RTMP6. Causa del freeze INCONCLUSIVE. En el tramo largo sí avanza entre las 32 muestras REC1 y 31 RTMP1 de 60 s; no garantiza continuidad dentro de esos intervalos. |
| Medios compactos GPUI | G | [Dos medios funcionales y cadencia estricta PASS](../var/evidence/h13-native-analysis-1794946801711114000/report.json), cobertura INCONCLUSIVE por intentos de handshake sin medio. Video ≤34 ms/AAC ≤22 ms, PCM completo finito sin saturación; peaks MKV/RTMP −12,314496/−16,729690 dBFS. MKV output/decoded 13880/13880; **RTMP 5028/5027**, discrepancia terminal de un frame que no forma parte del gate PASS. Encoded 13883/5030 no equivale a entrega. |
| Revalidación visual compacta | G | [Alerta PASS, ventana FAIL](../var/evidence/h13-native-visual-extract-1794946829324892000/visual-review.md): alerta `order=3` legible completa en ambos medios. Once muestras periódicas (ocho MKV, tres RTMP) conservan contador 193356288; causa INCONCLUSIVE, sin fijar inicio/fin ni garantizar lo ocurrido entre muestras. No repite las verificaciones de Cut/Fade/lower/countdown de la toma principal. |
| Cierre compacto y limpieza | G | [Observador PID 36494 cerrado](../var/evidence/h13-native-1794944801555031000/report.json): 2493 snapshots, collector/shutdown verdaderos. Q5 diálogo obsoleto tras timeout; Q4 mantiene shutdown_pending y RTMP cancel_deferred hasta liberar peer, MKV ya idle. [Salida en 0,835 s desde solicitud de liberación](../var/evidence/h13-native-compact-1794944782314737000/shutdown-outcome.json), no desde Cmd+Q. [Limpieza final](../var/evidence/h13-build/final-physical-cleanup.json): PID propios ausentes, sin force-kill de Motive y lock liberado. |

## Rendimiento y límites de calidad

En el ABBA fresco 1080p60 con video H11 sin audio, patrón y tono, CPU media
estable single/dual fue 63,87/67,58% y RSS activo 442,20/460,65 MiB: diferencia
descriptiva de +3,71 puntos CPU y +18,46 MiB. CPU 100% representa un núcleo de
Motive; no incluye helpers/receptor. Solo dos observaciones por brazo, con
calentamiento y memoria retenida. No acredita optimización ni ausencia de fugas.

Los interiores del control fresco fueron ≤17 ms; cuatro de seis medios tienen
gaps finales de hasta 67 ms. Las ocho tomas tail con reordenamiento desactivado
cumplen cadencia estricta en 30/60 FPS, VT/x264; no cambió el default ni demuestra
garantía universal. El pico x264 del ensayo inicial fue 1233,63 MiB. Los
reanálisis corrigieron DTS inicial de B-frames y downmix del instrumento,
conservando archivos, hashes y gates de nivel. Detalle:
[rendimiento/colas](h13-encoder-tail-investigation.md).

La [producción nativa dual](../var/evidence/h13-native-1794941679130733000/metrics-summary.json)
mide CPU mediana/p95 **70,7128/81,8563%** y RSS mediana/máximo observado
**243,6563/262,3906 MiB** en 3283 sondeos del tramo dual. Cero render lag,
video skips, drops por output y clipping de mezcla; `preview_busy_drops`
**+221** (148→369), distinto de pérdidas del encoder. CPU representa un núcleo
lógico de Motive, no helpers; los sondeos no garantizan capturar cada pico.
El período completo del PID, incluida preparación y pruebas posteriores,
alcanza RSS 348,625 MiB y preview +371: es otro alcance.

**Contabilidad terminal pendiente:** `output_frames`/decodificados son
8177/8176 en REC3, 1229/1228 en RTMP4 y 1149/1147 en RTMP3 de fallo intencional;
los otros cinco archivos coinciden. `encoded_frames` supera en 2–3 el contador
output y no mide entrega. El contador OBS de despacho no confirma escritura/
recepción final; el log de REC3 imprime 8176 frente al máximo 8177 del snapshot.
La semántica de parada es compatible con diferencias terminales, sin una traza
que identifique cada paquete. Cadencia 8/8 PASS y cero drops no acreditan
preservación de todos los últimos cuadros. [Tabla, código y log](h13-production-verification.md#medios-estructurales-y-contabilidad-terminal).
La toma compacta suma otro caso: RTMP **5028 output/5027 decodificados**,
con 5030 encoded; MKV coincide 13880/13880, con 13883 encoded. Sus dos PASS
de cadencia no resuelven esta contabilidad ni cambian el alcance del gate.

## Estado del bundle G y pendientes de cierre

**Regresiones: 23/23 suites distintas PASS en sus últimas ejecuciones G.**
H10 incorpora la [metrología revisada](h13-h10-metrology.md), con referencias
aisladas y ensayos nuevos. El conteo agrega resultados por suite de los siguientes
manifiestos; no vuelve verdes los manifiestos fallidos ni declara H13 completo:

| Manifiesto | PASS incorporados al conteo | Resultado del manifiesto |
| --- | ---: | --- |
| [H8 dirigido](../var/evidence/h13-regressions-1794937943048758000/manifest.json) | 1 | PASS |
| [Primera tanda](../var/evidence/h13-regressions-1794938214930619000/manifest.json) | 2: control y control_delivery | FAIL al llegar a H1 por fixture ambigua |
| [Reanudación desde H1](../var/evidence/h13-regressions-1794938328448756000/manifest.json) | 14: H1, scenes, captura, encoding/fallback, recovery, RTMP/RTMPS, connect/VT stop, profiles restart, Keychain, H9 transitions/faults | FAIL al llegar a H10 audio |
| [H10 mixer](../var/evidence/h13-regressions-1794939220662892000/manifest.json) | 0 | FAIL en la ganancia del tono con micrófono abierto |
| [H11/H12 restantes](../var/evidence/h13-regressions-1794939397028955000/manifest.json) | 4: H11 runtime, visuals, lifecycle y H12 performance | PASS |
| [H10 con referencias](../var/evidence/h13-regressions-1794940354925977000/manifest.json) | 1: piloto H10, 32,9 s | FAIL global: el mixer posterior falla su comparación de mute mezclado |
| [Mixer H10 final](../var/evidence/h13-regressions-1794940880710737000/manifest.json) | 1: mixer MKV/RTMP, 110,0 s | PASS con referencias aisladas de ganancia/mute, recuperación y persistencia |

Los siete manifiestos terminan con bytes/modos de stores restaurados, sin errores
de cleanup y con el mismo hash G inicial/final. Los PASS de RTMPS conservan su
alcance de rechazo TLS no confiable; no acreditan una entrega RTMPS positiva.
La producción nativa posterior usa el mismo binario y no volvió a ejecutar ni
sumar estas 23 suites. Sus resultados y los FAIL conservados siguen separados.

- La primera tanda
  conserva PASS de control/control_delivery y FAIL de H1 por `SOURCE_AMBIGUOUS`
  antes de las salidas. Una fixture propia de un ensayo interrumpido permanecía
  bajo LaunchServices y duplicaba bundle/título. Se retiró únicamente su PID
  verificado; [evidencia de limpieza](../var/evidence/h13-regressions-1794938214930619000/owned-fixture-cleanup.json).
  El rechazo del núcleo fue correcto; no se cambiaron código ni gates. Stores
  restaurados y sin errores de cleanup. H1 repite PASS en 22,2 s y scenes en
  33,5 s tras retirar la fixture duplicada; el manifiesto original sigue FAIL.
- [H10 audio original](../var/evidence/h13-regressions-1794938328448756000/reports/verify_h10_audio.py/h10-pilot.json)
  permanece FAIL: diferencia muted/lower 0,517758 dB frente al gate <0,5 dB.
  [H10 mixer original](../var/evidence/h13-regressions-1794939220662892000/reports/verify_h10_mixer.py/h10-mixer.json)
  permanece FAIL: −9,621392 dB frente al intervalo (−13, −11) dB. Los
  diagnósticos [pilot](../var/evidence/h13-h10-pilot-audio-diagnosis-1794939269396896000/report.json)
  y [mixer](../var/evidence/h13-h10-mixer-audio-diagnosis-1794939476988910000/report.json)
  muestran contribuciones en torno a 440 Hz con el micrófono abierto; no aíslan
  su causa ni convierten una proyección espectral alternativa en PASS.
  El [primer diagnóstico mixer inválido](../var/evidence/h13-h10-mixer-audio-diagnosis-1794939451029840000/report.json)
  conserva sus valores dB nulos y su etiqueta de error del harness.
  La primera repetición con referencias mantiene un [nuevo mixer FAIL](../var/evidence/h13-regressions-1794940354925977000/reports/verify_h10_mixer.py/h10-mixer.json):
  ratio 440 Hz de mute mezclado 0,033069 frente a <0,03, con micrófono audible.
  La corrida final mide ganancia y supresión del tono contra referencias con
  micrófono muteado; mantiene la etapa de micrófono audible con tono muteado y
  registra su espectro mezclado como diagnóstico. Estímulos, márgenes y límites
  están declarados en [metrología H10](h13-h10-metrology.md), sin cambios al
  producto. La [validación offline del checker](../var/evidence/h13-h10-reference-checker-1794940054296064000/report.json)
  rechaza el hueco histórico de 1024 muestras; las nuevas grabaciones físicas,
  no ese control aislado, aportan los dos PASS H10 al conteo final.
- Recorrido GPUI dual con cámara, ventana propia, micrófono/aplicación,
  gain/mute, widgets/Cut/Fade, fallos por destino y cierre con salidas:
  **EJECUTADO, aceptación parcial**, según el
  [observador cerrado](../var/evidence/h13-native-1794941679130733000/report.json).
  La última acción es `request_shutdown` UI revisión 179; ambos slots llegan
  a `idle/native_busy=false` antes de observar salida del PID. La revalidación
  compacta y sus cierres Q4/Q5 están registrados en la
  [aceptación nativa](h13-native-acceptance.md); el
  [checklist](h13-native-checklist.md) conserva los pasos y alcances no ejecutados.
  Proyecto, mixer y definiciones de perfiles ya se restauraron por GPUI tras
  reabrir en la sesión compacta PID 36494.
  [Observador previo](../var/evidence/h13-native-1794936995861463000/report.json)
  corresponde únicamente a preparación sin salidas y conserva ese alcance.
- La sesión prolongada **sí se ejecutó**, con más de 30 minutos de ambos
  primeros outputs. No recibe un PASS global: quedan el FAIL visual posterior
  de REC3, el nuevo FAIL de continuidad compacta, contabilidad terminal y
  memoria. La alerta ocluida original permanece archivada; corregir su orden
  por UI sí produjo una nueva toma con alerta completa PASS. Nada de esto
  borra los archivos originales ni convierte el muestreo de 60 s en prueba
  de frescura por frame.
  La restauración de los manifiestos de regresiones anteriores sí se comprobó.
- La exclusión propia en G tiene **una repetición controlada PASS** después
  de un único control de piso PASS. El primer FAIL y el origen INCONCLUSIVE
  de su fondo permanecen en el [informe final](h13-system-audio-exclusion-final.md).
  Este gate H13 es independiente del agregado 23/23 y no acredita atenuación
  universal ni una corrección de producto.
- Las pruebas físicas terminaron. La [limpieza final](../var/evidence/h13-build/final-physical-cleanup.json)
  registra PID propios ausentes y lock liberado, sin force-kill de Motive.
  Esto no transforma la aceptación parcial en H13 completo.
- Las ventanas de cierre por sockets dejaron un ensayo **INCONCLUSIVE** porque
  el proceso terminó antes de la admisión; EOF no demuestra el guard. El H8
  determinista y la importación real constituyen evidencias separadas.

## Límites conservados

Congelamientos reales de ventana en los ensayos A/V previos siguen sin causa
demostrada; el segundo avanzó hasta 21,233 s y luego mantuvo el contenido
12,934 s. [Evidencia original](../var/evidence/h13-system-audio-1794933205287443000/report.json).
Snapshots pueden redibujar la vista y visibilidad no prueba causalidad.
El [freeze nativo posterior de REC3](../var/evidence/h13-native-visual-extract-1794944740966518000/visual-review.md)
también sigue sin atribución: el fixture registra dibujo/audio avanzando y una
correlación con oclusión, pero el snapshot de captura no mide frescura. No se
adjudica a Stage Manager ni se demuestra reparación por activar la ventana.
La [toma compacta](../var/evidence/h13-native-visual-extract-1794946829324892000/visual-review.md)
añade once muestras sin avance del contador; la atribución sigue inconclusa.

Sin aceptación física de revocación de permisos, USB hot-unplug, cambio de
display, sleep/wake ni `awaiting_audio` por ausencia real de paquetes. Cámara
mantiene preset 720p/cadencia propia: compositor 60 FPS no prueba captura 60 FPS.
La solución de anticipación es exclusiva del tono determinista; no se declara
corrección de micrófono o SCK. El drenaje final de la traza no garantiza EOF de
la destrucción asíncrona. La firma ordinaria del bundle local pasa; el symlink
externo de frameworks OBS limita `codesign --strict` y portabilidad de release.

Contratos de integración: [video/audio](h13-video-audio-contract.md),
[salidas](h13-output-contract.md), [regresiones](h13-regressions.md).
Informe incremental con contexto: [verificación](h13-production-verification.md).
