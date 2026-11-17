# H13 — índice de evidencia · EN CURSO

Inventario de lectura del 2026-11-17. **No declara H13 completo.** Las pruebas
pertenecen al ejecutable indicado en cada fila; un PASS de un incremento no
certifica por sí solo el bundle final. Los informes originales fallidos se
conservan. Rutas relativas a este worktree, con métricas y hashes de medios en
los JSON enlazados; no se vuelven a decodificar para elaborar este índice.

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
| Dos entradas y control independiente | B | [Piloto PASS](../var/evidence/h13-system-audio-1794932404437443000/report.json): 440 Hz + aplicación propia 997 Hz, 24,64 s PCM, 741 frames, pico −23,72 dBFS. Pasos solicitados −12 dB producen −11,993/−11,992 dB; mute conserva la otra fuente. Error RMS aislado −0,068/−0,006 dB; sin clipping. |
| RTMP, recuperación y silencio | B | [Etapas RTMP/recovery/silence PASS](../var/evidence/h13-system-audio-1794932515805158000/report.json). El informe global permanece FAIL por su etapa siguiente; [reanálisis de transiciones PASS](../var/evidence/h13-system-audio-1794932515805158000/transitions-reanalysis.json). Recuperación explícita tras nuevo PID del mismo bundle. SCK entregó ceros, por lo que no prueba ausencia física de paquetes. |
| Cut/Fade y mixer v2 | B | [Etapas transitions/persistence PASS](../var/evidence/h13-system-audio-1794932730872027000/report.json); ese informe global permanece FAIL por A/V. Conserva identidad/reutilización y stores de proyecto/perfiles. Cola final VT hasta 133 ms registrada. |
| Micrófono físico | B | [PASS](../var/evidence/h13-system-audio-1794932987734593000/report.json): UID integrado explícito, cinco intervalos mezcla/aislamiento/mute/restauración, 18,176 s PCM, 547 frames, pico −18,75 dBFS. Recaptura acústica del fixture controlada; no implica ausencia de feedback propio. |
| Exclusión del sonido de Motive | C | [PASS con control positivo](../var/evidence/h13-self-audio-exclusion-1794934285059972000/report.json): emisor propio 2011 Hz/−30 dBFS y externo 997 Hz, luego 2011 Hz externo al mismo nivel. Captura de escritorio sin monitorización. Supresión estimada −122,74 dB, limitada por el piso del análisis; gate relativo −45 dB. 401 frames, sin clipping/lag/skips/drops. Emisor desactivado al reiniciar. |
| A/V, condicionado a ventana visible | C | [Con snapshots](../var/evidence/h13-system-audio-1794934345250779000/report.json) y [sin snapshots](../var/evidence/h13-system-audio-1794934414391892000/report.json): siete parejas de pulsos cada uno; mediana audio−video −35,83/−67,48 ms y rango 33/0 ms. PASS bajo gates de desfase absoluto <250 ms y rango <100 ms. No explica congelamientos previos ni acredita ventana oculta. |
| Hueco del tono: diagnóstico y corrección | C/D/E | [Fallo original conservado](../var/evidence/h13-outputs-1794933990447407000/report.json): 11/12 medios PASS, MKV con hueco de 1024 muestras. [Traza anterior](../var/evidence/h13-audio-trace-analysis-1794935248189182000/report.json) localiza cero antes de AAC en tres vidas. [A/B posterior](../var/evidence/h13-tone-lead-analysis-1794935516851025000/report.json): 1/1/1 → 0/0/0 ceros en las vidas observadas; 7576 bloques fuente y 3548 mix. Tono anticipa entrega 20 ms; PTS/fase/480 muestras intactos. Tres MKV y seis RTMP PASS. |
| Matriz dual sin diagnóstico | E | [PASS normal](../var/evidence/h13-outputs-1794935484169154000/report.json): cuatro casos y doce medios, sin errores de análisis/limpieza. Ganancia/mute, widgets, Cut/Fade, pérdida de receptor/muxer, supervivencia y recuperación por destino. Archivos intencionalmente parciales identificados. |
| PCM y rendimiento ABBA | E | [28/28 medios funcionales](../var/evidence/h13-performance-reanalysis-1794936503607571000/report.json), 10/28 de cadencia estricta. [Control fresco 6/6 funcionales](../var/evidence/h13-performance-1794936684794726000/report.json), 2/6 estrictos, 7281 frames. Error RMS máximo 0,1123/0,1154 dB, peaks lineales máximos 0,034913/0,035251; sin clipping/lag/skips/drops. Véanse límites cuantitativos debajo. |
| Restauración de ID malformado | F | [Núcleo real PASS](../var/evidence/h13-audio-id-validation-1794937378949652000/report.json): dos stores inválidos rechazados antes de mutar; identidad/instancia conservadas y ganancia controlable después. Restauración del archivo y retirada de la entrada de prueba. No renumera IDs v1/v2 válidos. |
| H8/cierre dirigido | G | [Manifest PASS](../var/evidence/h13-regressions-1794937943048758000/manifest.json): 14 ciclos, 47,6 s, rechazo `SHUTDOWN_PENDING` de ambos arranques, preflights e importación; consultas disponibles. Salida del owner tras liberar peer, stores restaurados y cleanup limpio. |
| Importación real durante cierre | G | [PASS](../var/evidence/h13-import-shutdown-1794938158330488000/report.json): clip 1080p/20,27 s; 29 consultas con worker activo, máximo 88,9 ms. Cierre solicita en 30,7 ms; resultado `completed` observado antes de salir en 3,271 s. Stores intactos e inbox propio retirado. |

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

## Estado del bundle G y pendientes de cierre

- La [corrida inicial de 22 suites](../var/evidence/h13-regressions-1794938214930619000/manifest.json)
  conserva PASS de control/control_delivery y FAIL de H1 por `SOURCE_AMBIGUOUS`
  antes de las salidas. Una fixture propia de un ensayo interrumpido permanecía
  bajo LaunchServices y duplicaba bundle/título. Se retiró únicamente su PID
  verificado; [evidencia de limpieza](../var/evidence/h13-regressions-1794938214930619000/owned-fixture-cleanup.json).
  El rechazo del núcleo fue correcto; no se cambiaron código ni gates. Stores
  restaurados y sin errores de cleanup. Las [20 suites desde H1](../var/evidence/h13-regressions-1794938328448756000/manifest.json)
  se reanudan: H1 PASS en 22,2 s y scenes PASS en 33,5 s tras retirar la fixture
  duplicada. La matriz sigue **EN CURSO**, sin inferir PASS final por esos casos.
- Recorrido GPUI final dual con cámara, ventana propia, micrófono/aplicación,
  gain/mute, widgets/Cut/Fade, fallos por destino y cierre con salidas:
  **PENDIENTE**, según [checklist nativo](h13-native-acceptance.md).
  [Observador previo](../var/evidence/h13-native-1794936995861463000/report.json)
  corresponde a preparación sin salidas, no a aceptación de medios. Tamaño
  1024×780, temas y cierre idle observados no sustituyen ese recorrido.
- Sesión prolongada/soak y verificación final de restauración: **PENDIENTES**.
  Las tomas de 11–25 s y ABBA de 20 s no se presentan como una sesión larga.
- Las ventanas de cierre por sockets dejaron un ensayo **INCONCLUSIVE** porque
  el proceso terminó antes de la admisión; EOF no demuestra el guard. El H8
  determinista y la importación real constituyen evidencias separadas.

## Límites conservados

Congelamientos reales de ventana en los ensayos A/V previos siguen sin causa
demostrada; el segundo avanzó hasta 21,233 s y luego mantuvo el contenido
12,934 s. [Evidencia original](../var/evidence/h13-system-audio-1794933205287443000/report.json).
Snapshots pueden redibujar la vista y visibilidad no prueba causalidad.

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
