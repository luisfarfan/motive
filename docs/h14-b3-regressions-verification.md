# H14 — B3: consolidación de 23 regresiones H1–H12

Estado: **23/23 suites seleccionadas con reporte primario PASS**, salida de
proceso cero y cleanup registrado satisfactorio sobre el mismo portable B3.
Esto acepta el alcance de esas suites; **no declara H14 ni toda la matriz H13
completos**. El intento inicial fallido de escenas y la primera toma H1 se
conservan aparte, sin reemplazar sus resultados por los de las repeticiones.

El [índice auditado](../var/evidence/h14-b3-regressions-consolidated-01/index.json)
contiene las 23 entradas seleccionadas, el historial excluido, hashes completos
por reporte retenido y los recibos de restauración. SHA-256 del índice:
`1998230ed1b26ec99c794a777b5b498357c263eb2d692a327b6cc3475acfac89`.
La consolidación es offline: no volvió a abrir apps/dispositivos, decodificar
medios ni ejecutar las suites.

## Procedencia y criterio de aceptación

Ejecutable y cliente CLI/MCP son el mismo archivo firmado:
`/Users/luisfarfan/Developer/motive-h14-portable/b3/Motive.app/Contents/MacOS/motive`,
SHA-256 `797b9722b0fe4725b13d5ccd1d2868c21d8f2cfa7ca3db784fee6297504549dc`.
Fuente compilada `d0deeb57e3526eb4f7d6fe00718a56f2b5516e1d`, fuente de
empaquetado `ceb40ce`; UUID ARM64 `13360D38-1520-3D01-9139-BF3FF61745CA`.
No se reconstruyó ni sustituyó B3 para corregir los harnesses.

Se comprobaron por lectura:

- Los cuatro manifests hijos coinciden con el hash retenido en sus wrappers;
  los logs de comandos coinciden también. Los tres wrappers elegidos son
  `PROCESS_COMPLETED`; el primero fallido conserva `PROCESS_FAILED`.
- Hash inicial/final de app y cliente, `codesign --verify` registrado con
  salida cero, contexto de build y `source_binding` inicial/final coinciden.
  La consolidación rehashó además el ejecutable actual y verificó un diff
  vacío de los insumos de producto frente al commit compilado.
- Las **37 copias JSON retenidas** de las cuatro corridas conservan sus hashes:
  34 pertenecen a las tres corridas seleccionadas y tres al intento inicial.
  Las copias auxiliares pueden incluir archivos cambiados sin atribución;
  solo el nombre primario específico de cada suite decide su aceptación.
- Cada primario seleccionado tiene `ok=true`, sin campos superiores de error
  o cleanup pendientes, y su identidad de build coincide cuando la declara.
  Se recalculó el gate de `regression_reports.py`; coincide con las 23
  evaluaciones registradas. No se interpretan como fallo de suite las
  respuestas negativas deliberadamente probadas dentro de un primario.
- Todas las suites seleccionadas terminaron con `native_busy=false` en ambos
  slots. Cada wrapper observa `QUIESCENT_OBSERVED`, sin procesos restantes
  de su grupo, sin errores de diagnóstico y con lease liberado. Esto cubre el
  grupo inventariado; no sustituye la limpieza propia de hijos desacoplados.
- Los scripts permanecieron iguales durante cada invocación. Sus hashes
  históricos están en el índice; los cambios entre intentos se distinguen de
  la identidad del producto.

La validación usa exclusivamente copias `child/reports/SUITE/...`, no los
aliases compartidos actuales de `var/evidence`. El gate y las funciones de
los runners no se modificaron durante esta auditoría. Los flags normales de
macOS y los dispositivos explícitos estaban registrados por el coordinador.
Cada suite arranca un owner nuevo con proyecto **v3 real, 960×540@30 y mixer
vacío**; H11 ejercita posteriormente v4. Esa compatibilidad no se sustituye
por configurar artificialmente un proyecto v5.

## Corridas elegidas e historial

| Grupo | Wrapper | Child | Resultado del child | Duración wrapper |
|---|---|---|---|---:|
| Control, 2 suites | [control-01](../var/evidence/h14-beta-b3-control-01/manifest.json) | [1794959476394010000](../var/evidence/h13-regressions-1794959476394010000/manifest.json) | `ok=true` | 6.08 s |
| Escenas, 1 suite | [scenes-02](../var/evidence/h14-beta-b3-scenes-02/manifest.json) | [1794959730526198000](../var/evidence/h13-regressions-1794959730526198000/manifest.json) | `ok=true` | 36.80 s |
| Restantes, 20 suites | [regressions-02](../var/evidence/h14-beta-b3-regressions-02/manifest.json) | [1794959840873390000](../var/evidence/h13-regressions-1794959840873390000/manifest.json) | `ok=true` | 1075.43 s |
| Intento inicial, excluido | [regressions-01](../var/evidence/h14-beta-b3-regressions-01/manifest.json) | [1794959591726088000](../var/evidence/h13-regressions-1794959591726088000/manifest.json) | `ok=false` | 61.63 s |

Las 23 suites seleccionadas suman **1087.02 s** de ejecución; sus tres wrappers
suman **1118.32 s**, incluidos reinicios y restauración. No es una única corrida
continua ni una medición de latencia de usuario.

| Suite | Grupo | Segundos | Primario retenido |
|---|---|---:|---|
| verify_control.py | Control | 1.04 | [PASS](../var/evidence/h13-regressions-1794959476394010000/reports/verify_control.py/control-integration.json) |
| verify_control_delivery.py | Control | 0.92 | [PASS](../var/evidence/h13-regressions-1794959476394010000/reports/verify_control_delivery.py/h9-control-delivery.json) |
| verify_scenes.py | Escenas | 33.99 | [PASS](../var/evidence/h13-regressions-1794959730526198000/reports/verify_scenes.py/scene-acceptance.json) |
| verify_h1.py | Restantes | 22.10 | [PASS](../var/evidence/h13-regressions-1794959840873390000/reports/verify_h1.py/h1-acceptance.json) |
| verify.py | Restantes | 79.39 | [PASS](../var/evidence/h13-regressions-1794959840873390000/reports/verify.py/acceptance.json) |
| verify_encoding.py | Restantes | 251.78 | [PASS](../var/evidence/h13-regressions-1794959840873390000/reports/verify_encoding.py/encoding-comparison.json) |
| verify_encoding_fallback.py | Restantes | 12.23 | [PASS](../var/evidence/h13-regressions-1794959840873390000/reports/verify_encoding_fallback.py/encoding-fallback.json) |
| verify_output_recovery.py | Restantes | 10.15 | [PASS](../var/evidence/h13-regressions-1794959840873390000/reports/verify_output_recovery.py/output-recovery.json) |
| verify_rtmp.py | Restantes | 43.81 | [PASS](../var/evidence/h13-regressions-1794959840873390000/reports/verify_rtmp.py/h7-rtmp.json) |
| verify_rtmps.py | Restantes | 0.75 | [PASS](../var/evidence/h13-regressions-1794959840873390000/reports/verify_rtmps.py/h7-rtmps.json) |
| verify_connect_stop.py | Restantes | 1.10 | [PASS](../var/evidence/h13-regressions-1794959840873390000/reports/verify_connect_stop.py/h7-connect-stop.json) |
| verify_vt_stop.py | Restantes | 63.04 | [PASS](../var/evidence/h13-regressions-1794959840873390000/reports/verify_vt_stop.py/h7-vt-stop.json) |
| verify_profiles_restart.py | Restantes | 1.89 | [PASS](../var/evidence/h13-regressions-1794959840873390000/reports/verify_profiles_restart.py/h7-profiles-restart.json) |
| verify_h8_lifecycle.py | Restantes | 46.44 | [PASS](../var/evidence/h13-regressions-1794959840873390000/reports/verify_h8_lifecycle.py/h8-lifecycle.json) |
| verify_h8_keychain.py | Restantes | 2.10 | [PASS](../var/evidence/h13-regressions-1794959840873390000/reports/verify_h8_keychain.py/h8-keychain.json) |
| verify_h9_transitions.py | Restantes | 47.61 | [PASS](../var/evidence/h13-regressions-1794959840873390000/reports/verify_h9_transitions.py/h9-transitions.json) |
| verify_h9_faults.py | Restantes | 27.96 | [PASS](../var/evidence/h13-regressions-1794959840873390000/reports/verify_h9_faults.py/h9-faults.json) |
| verify_h10_audio.py | Restantes | 33.02 | [PASS](../var/evidence/h13-regressions-1794959840873390000/reports/verify_h10_audio.py/h10-pilot.json) |
| verify_h10_mixer.py | Restantes | 109.11 | [PASS](../var/evidence/h13-regressions-1794959840873390000/reports/verify_h10_mixer.py/h10-mixer.json) |
| verify_h11_runtime.py | Restantes | 99.20 | [PASS](../var/evidence/h13-regressions-1794959840873390000/reports/verify_h11_runtime.py/h11-runtime.json) |
| verify_h11_visuals.py | Restantes | 35.66 | [PASS](../var/evidence/h13-regressions-1794959840873390000/reports/verify_h11_visuals.py/h11-visuals.json) |
| verify_h11_lifecycle.py | Restantes | 10.37 | [PASS](../var/evidence/h13-regressions-1794959840873390000/reports/verify_h11_lifecycle.py/h11-lifecycle-1794960749534728000/report.json) |
| verify_h12_performance.py | Restantes | 153.36 | [PASS](../var/evidence/h13-regressions-1794959840873390000/reports/verify_h12_performance.py/h12-performance-1794960760985746000/report.json) |

La cobertura reúne control CLI/MCP, fuentes físicas/ventana, composición y
variantes, encoders y fallback, recuperación de salidas, RTMP local,
validación TLS negativa, stop/reinicio/perfiles, Keychain, Cut/Fade y sus
fallos, mixer, overlays/widgets, persistencia/lifecycle y medición H12.
`verify_h11_runtime.py` ejecutó ambos transportes y `verify_h11_visuals.py`
incluyó video; el x264 explícito de esa prueba conserva su política histórica.

## El fallo inicial y la repetición H1

La primera corrida se detuvo en `verify_scenes.py`, salida **1**, primario
`ok=false`, error `FileNotFoundError`. El [log conservado](../var/evidence/h13-regressions-1794959591726088000/verify_scenes.py.log)
identifica la lectura de `var/evidence/preview.png`: el harness buscaba la
captura nativa en la ruta de desarrollo. La corrección `2130f40` usa la ruta
diagnóstica portable; el nuevo intento de escenas pasa. El primario fallido
sigue con SHA-256
`55b8165d7f6b9bfcb83b5ce983009443a424e806a73b880eb411c91657441c43`.
No se elimina el error porque algunas verificaciones anteriores del mismo
intento ya hubieran sido satisfactorias.

El primer H1 de esa corrida devolvió `ok=true`, pero invocaba `afplay` sobre
`ROOT/var/tone.wav` y no verificaba su salida. Su RMS grabado no prueba que
sonara el estímulo controlado esperado. Esa toma se conserva con SHA-256
`3e92f2b91b59b6512d3f3ab025032432220c83646e923fe92ccec1200994457b`,
pero **no es la seleccionada para la matriz de 23**.

Tras `d988551` y `5537493`, H1 se repitió con
`Library/Application Support/local.motive.studio/tone.wav`, **192044 bytes**,
SHA-256 `92b74b61559478db14a4254488910b2aff1228bbf7c91646c57bab6117505b6c`.
Ambos reproductores devolvieron **0**. La toma seleccionada contiene **256
frames**, duración **8.554 s**, RMS de audio **0.00591515** y **369543 píxeles
no negros** en la comprobación de fuente. El primario nuevo tiene SHA-256
`2704c7bca8f4d19c1ce73cebe54278e5a1708f1b64ed61907b6850ed780f9f74`.
Los checks de contenido y sus umbrales no se relajaron; se fortaleció la
prueba de reproducción y su cleanup. No se probó desconexión física de
hardware removible: tanto H1 como H10 lo declaran explícitamente.

## H12: PASS funcional y memoria pendiente de interpretación

El primario H12 pasa sus asserts de actividad de render, hijos nativos,
reconciliación, animación, liberación de fuentes y limpieza. **No tiene un
límite de aceptación de RSS**. Usa `proc_pidinfo PROC_PIDTASKINFO` a 20 Hz,
CPU 100% equivalente a un núcleo, con GPUI/preview e instrumentación incluidos;
conserva **2838 muestras**. Los picos menores de 50 ms pueden quedar fuera.

| Fase H12 | CPU mediana % | RSS mediana MiB | RSS máximo MiB |
|---|---:|---:|---:|
| Cero videos | 20.93 | 179.58 | 185.70 |
| Cuatro visibles | 69.44 | 698.89 | 784.61 |
| Cuatro ocultos | 62.20 | 797.59 | 805.69 |
| Cuatro reconciliados | 72.74 | 1027.70 | 1036.69 |
| Animación completa de diez segundos | 74.61 | 1114.27 | 1116.42 |
| Después de retirar | 25.72 | 1047.27 | 1082.06 |
| Settling final, 20.37 s | 26.27 | 858.45 | 1014.64 |

Las 17 fases registran delta `render_lag=0`; no hubo output activo en esta
medición. El RSS sigue elevado al final: no se oculta por el `ok=true`, ni se
interpreta como fuga o ausencia de fuga. Los recuentos de hijos son estados
de fuentes, no trazas de asignador. Esta suite no mide footprint, compresión,
malloc, ownership ni utilización GPU. La [medición H14 de memoria y soak](h14-memory-b3-soak-verification.md)
aporta esas otras observaciones por separado; son corridas distintas y no
se combinan como si fueran una comparación causal controlada.

## Restauración y límites de aceptación

Las cuatro corridas, incluida la fallida, conservan `cleanup_errors=[]` y
`stores_restored=true`. Se rehasharon los backups originales de proyecto y
mixer; `output-profiles.json` estaba ausente en las cuatro y debía volver a
estar ausente. Los recibos del runner comprueban bytes y modos originales
(0644 en esos dos archivos), después de las barreras nativas. Esta auditoría
no leyó los stores vivos, que otras pruebas pueden estar usando ahora.

Los snapshots inicial/restaurado coinciden en proyecto, mixer, selección de
output y configuración de transición. El owner final es nuevo en cada caso,
sin issues ni attempts automáticamente iniciados. Los PID finales registrados
son **68222, 71306, 84030 y 69890** para control, escenas, restantes e intento
inicial respectivamente. Son evidencia histórica; no se afirma que sigan
vivos. La restauración de estos tres stores no equivale a una auditoría de
cada archivo del Application Support ni del Keychain global.

Límites que permanecen explícitos:

- H7 RTMPS verifica **rechazo de raíz no confiable**, no entrega confiable a
  una plataforma ni rechazo aislado de hostname. No modifica el trust store.
- Las suites con ventana/cámara/micrófono usan contenido controlado y permisos
  existentes. No simulan una denegación TCC ni prueban hot-unplug físico.
- La matriz comienza en 540p30/v3; no acredita por sí sola perfiles nativos
  H13 1080p30/60, dual-output, audio de sistema ni exclusión del audio propio.
  Esos ensayos adicionales deben enlazarse como evidencia separada.
- Los gestos GPUI y la caminata nativa H12, así como recepción externa RTMPS,
  segunda Mac y demás gates H14, siguen fuera de estas 23 suites.
- Esta consolidación verifica integridad y semántica de los reportes
  retenidos; no repite sus decodificaciones ni afirma identidad completa
  encoder→archivo a partir de contadores nativos.

El índice conserva `beta_acceptance=NOT_EVALUATED`: los fallos históricos y
los límites de cada primario permanecen visibles junto a los 23 PASS elegidos.
