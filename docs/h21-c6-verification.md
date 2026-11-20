# H21 — C6, respaldo renovable por retorno explícito

Estado: **EN VERIFICACIÓN**. PERSONAL STREAM READY: **BLOCKED**.
Fecha: 2026-11-19. C4/C5 y sus FAIL se conservan.

## Cambio y límites

El ensayo C5 de entrada/salida de fullscreen confirma dos suspensiones SCK
separadas por un retorno explícito a una fuente que volvió a entregar imágenes.
El segundo fallo agotaba el único respaldo de la sesión y detenía ambos outputs.

C6 conserva el intento inicial y permite renovar una oportunidad al aceptar
`select_scene` desde la escena segura hacia otra escena existente. Debe haber
al menos una captura de pantalla visible en la orientación solicitada, y todas
las capturas visibles deben observar fase `running`, sample `complete`, al menos
una superficie y edad entre 0 y 500 ms. Un stop del usuario, un fallo o una fuente
no disponible impiden la renovación. La selección rechazada, el polling de salud,
un patrón sin capturas y una cámara sin captura SCK no renuevan el respaldo.

La observación de una captura fuera de Program se evalúa como destino solicitado
sin modificar su estado nativo. No se reconstruyen fuentes, no se amplía el área
capturada y no se modifica el reloj multimedia, audio, encoders o salidas. El Cut
de respaldo conserva su límite de dos segundos. La reconstrucción SCK durante
outputs sigue BLOCKED por lifetime asíncrono no demostrado.

`capture_recovery.fallback_attempted` mantiene su significado histórico: hubo
un intento durante esta sesión. Se añaden `fallback_armed` y `attempt_count`
para distinguir una oportunidad disponible del número de intentos realizados.
Los contadores se reinician al quedar todas las salidas quiescentes o al cambiar
la configuración del respaldo estando idle.

## Gates propios de C6

- Build release ARM64, firma Apple Development existente, versión local 21.6,
  tests Rust/Show Control/Python, Clippy y formato, hashes de fuentes y bundle.
- Repetición real de fullscreen: al menos dos respaldos confirmados, retorno
  explícito, mismo attempt ID de cada output, mismas fuentes y mixer. Decodificar
  avance en fullscreen y restauración, tono continuo y escena segura final.
- Repetir los contratos afectados y las sesiones físicas sobre el hash C6.
  Ningún PASS C5 se presenta como ejecución C6.

## Construcción observada

`var/evidence/H21-C6-build/report.json`: PASS. 134 tests del núcleo, 136 de
Show Control y 162 Python; Clippy `-D warnings`, formato, release y auditoría
portable estática pasan. Se conservan fuentes archivadas, diff y hashes de cada
input y archivo del bundle; los inputs no cambiaron durante el build.

Ejecutable SHA-256:
`22b5066e3757c25076038d0fa74d235a269e61c48a83c5480caa2f072e1e5db4`.
Bundle: `target/h21/Motive-H21-C6.app`, versión local 21.6, firmado con la
identidad Apple Development ya existente. No se publica ni se afirma notarización.

## Fullscreen real: PASS acotado

`H21-C6-fullscreen/report.json` y `H21-C6-fullscreen-analysis/analysis.json`
pasan. La misma fixture V5 y el mismo recorrido que falló en C5 observan entrada
y salida de fullscreen nativo, dos respaldos confirmados y retorno explícito.
La recuperación de superficies fuera de Program no arma el respaldo por sí sola;
la selección explícita renueva una oportunidad sin aumentar el contador de intentos.

MKV y RTMP conservan sus attempt IDs y siguen activos; no cambia ninguna
identidad de fuente ni instancia del mixer. Ambos archivos se decodifican y
contienen avance de los contadores propios durante fullscreen y restauración,
cadencia continua de paquetes, tono sin corte interior y patrón seguro final.
El stop de streaming deja grabación activa, y owner/fixture/receptor cierran
normalmente, sin errores de cleanup.

Esto corrige el límite de respaldo demostrado en C5. No demuestra recuperación
general de SCK, resolución de CAP-01 ni funcionamiento de Stage Manager o de
un cambio manual entre Spaces. Los otros resultados físicos se incorporarán
después de cada ejecución. Esta candidata aún no es una aceptación personal.

## Base adicional y UI

Los respaldos Window/Application, proyectos v1–v6, política de outputs,
lifecycle Window/Application con análisis y las siete etapas de audio de
aplicación pasan en C6. `H21-C6-baseline-stages` conserva doce exit codes cero,
pero ese dato no es suficiente para aceptar la matriz de salidas:
`H21-C6-output-matrix` contiene **ocho PASS funcionales y un FAIL**.

El caso VideoToolbox streaming-stop solicitó start cuando el tono aún tenía
cero frames y fase `warming`. Motive denegó `AUDIO_NOT_READY`; no se creó ningún
attempt de output. El verificador histórico no espera muestras antes de start.
Se conserva el FAIL y se investiga/repite por separado. El coordinador H15
devuelve cero tras recorrer los casos aunque uno falle; no se usa ese exit code
para convertir el resultado en PASS. La entrega terminal de los casos restantes
continúa PARTIAL.

`H21-C6-ui-owner-r2` pasa apertura normal, permisos pantalla/cámara/micrófono,
gesto real de UI para renombrar la escena a `H21 C6 UI`, lectura coincidente
por CLI/MCP y shutdown del mismo PID. No se guardó el proyecto del usuario.
El primer runner se detuvo antes de abrir Motive por faltar una variable de
rutas de verificación; su error y fuente se conservan en `H21-C6-ui-owner`.

La repetición sin modificar el caso antiguo de streaming produce PASS funcional
y cola PARTIAL en `h14-output-integrity-1795105826793174000`. No elimina el FAIL
de preparación inicial ni demuestra que aquel verificador espere readiness.
Las sesiones H21 comprueban expresamente muestras/phase `ready` antes de start.
Las regresiones físicas C6 H9 transitions, H10 audio y H10 mixer también pasan;
manifest `h13-regressions-1795105643358445000`. Los dos tests nuevos de equivalencia
de modo elevan la suite Python a 164; verifican propiedades escalares, no captura.

## Stage Manager y resolución autorizados

El usuario autorizó cambios temporales y restauración. Se captura únicamente
la ventana propia V5 durante estas pruebas, no el escritorio reorganizado.

- `H21-C6-stage-manager`: normal UI `stage-manager-on` off → on → off, observado
  además en la preferencia del sistema. Runtime y decodificación PASS; mismas
  fuentes, mixer y attempts de salida; cierre limpio y preferencia `0` tras salir.
- `H21-C6-resolution-r3`: CoreGraphics cambia temporalmente Odyssey de
  3840×1080 a 3200×900 a 240 Hz y restaura el modo. Runtime y decodificación PASS;
  avance de imagen y tono en ambos destinos. `restored-after-exit.json` comprueba
  el modo original exacto 111 después del cierre del proceso de prueba.

El primer intento de resolución falló antes del cambio: la función UUID está
exportada por ColorSync, no por CoreGraphics. r2 cambió y restauró la geometría,
pero su comparación rechazó el alias de modo 110 al solicitar 111. El SDK documenta
que `CGDisplaySetDisplayMode` dura lo que el proceso; al salir se observó otra
vez 111. Se inspeccionaron los exits normales y la restauración exacta antes de
liberar el lock retenido. Ambos FAIL permanecen intactos.

r3 compara todas las propiedades físicas y flags durante la transición, permite
solo la diferencia del identificador de modos duplicados y exige nuevamente el
identificador original después del exit. No cambia preferencias permanentes.
Estos ensayos no certifican Display Capture durante un cambio de resolución ni
el comportamiento de aplicaciones personales bajo Stage Manager.

## Foco CAP-01: no reproducido en esta secuencia

`H21-C6-focus` verifica por PID de foreground y metadata propia las tres fases
de 45 s A → Motive → A. `H21-C6-focus-analysis-r2` pasa píxeles decodificados,
avance del contador y correspondencia temporal por fase en MKV/RTMP. La primera
ejecución del analizador conserva INCONCLUSIVE: faltaba activar la prueba de
conversión Annex B/AVCC fijada para establecer el primer paquete VideoToolbox.
r2 ejecuta esa prueba sobre los mismos medios sin cambiar sus bytes ni criterios.

CAP-01 no se reproduce aquí y sigue siendo un riesgo histórico; no se declara
reparado ni se borran los fallos anteriores. La entrega terminal sigue separada
del avance de píxeles y no se deduce de él.

## Spaces: BLOCKED por condición no observada

Los tres intentos conservan sus informes FAIL. El primero llegó a fullscreen,
pero el atajo no produjo un cambio observable de `on_active_space`. El segundo
terminó al observar respaldo durante la animación: el bit de estilo fullscreen
todavía no demostraba que hubiera finalizado. V7 añade el callback real de fin
de transición y el tercer ensayo espera además la geometría SCK correspondiente.
Esa preparación pasó, pero nuevamente vencieron los 90 s sin observar el cambio
de Space. Los procesos propios cerraron normalmente.

El usuario confirmó después que cambió al escritorio anterior, cuando el ensayo
ya había cerrado. Esa respuesta no sustituye una observación durante la captura.
No se acepta Spaces ni se atribuye el límite a un fallo demostrado de Motive.

## Primera sesión larga Podcast: FAIL conservado

`H21-C6-podcast-60min` terminó aproximadamente a los 101 s por `Audio input issue`;
el último estado sano conservado corresponde a 100,277 s. Owner, fixture y receptor
cerraron normalmente, sin errores de limpieza. No se cumplió el objetivo de una hora.

El verificador original comprobaba las condiciones antes de guardar la muestra
que fallaba; por eso el código concreto del aviso no quedó registrado. Se corrige
únicamente ese orden de observación en los runners de estudio y gaming. No se
modifican el binario C6 ni los criterios. La repetición r2 conserva el estado
rechazado para distinguir fallo de captura, clipping y aviso de silencio.

La petición de palmadas se emitió a los 51,882 s; su confirmación llegó a los
259,123 s, después del cierre. Aún no demuestra que el archivo contenga una
referencia física utilizable. La sincronía cámara/micrófono sigue sin medir.

La repetición r2 registra el motivo concreto a los **132,781 s**:
`AUDIO_INPUT_CLIPPING`, un bloque saturado en el micrófono integrado `audio-2`.
Los tres canales siguen en fase `ready`; la identidad de aplicación coincide,
ambas salidas están activas, sus drops son cero y no hubo respaldo de captura.
El verificador solicita cierre por el warning; no es una interrupción espontánea
de los outputs ni un crash. Owner/fixture/receptor cierran normalmente.

La confirmación de palmadas r2 llega a los 143,789 s. La coincidencia temporal
orienta la revisión del archivo; no atribuye retrospectivamente el primer FAIL
al mismo motivo. El contador de entrada usa el pico previo al fader: reducir el
gain de Motive no elimina una saturación que ya llega del dispositivo. Se leyó
un nivel CoreAudio de 0,3764705956 (38% en macOS), sin modificarlo. El ajuste
temporal a 20% y restauración exacta fue autorizado por el usuario. Un wrapper
propio verifica el UID, aplica el nivel dentro del lock y lo restaura en `finally`;
retiene el lock si no puede probar la restauración. La primera lectura no cambió
ningún valor. La decodificación completa de los cuatro archivos fallidos pasa,
sin convertir por ello las sesiones incompletas en PASS.

La revisión visual r2 observa movimiento de manos, pero el recuadro del invitado
oculta parte del contacto: sincronía física INCONCLUSIVE. r3 mueve ese mismo
recuadro a la esquina superior izquierda y registra su geometría para el
analizador; no cambia el binario. La entrada autorizada se observa en
0,200000003 antes de iniciar. r3 se interrumpe a los 94,2 s por el mismo warning de clipping de micrófono.
Ambas salidas siguen activas y sin drops en la muestra rechazada. El nivel
físico siguió en 20% hasta el final y volvió exactamente a 0,3764705956;
owner/fixture/receptor cerraron normalmente.

Tras esa repetición se cambia el objetivo del siguiente ensayo a recolección
diagnóstica de continuidad. El flag explícito `--collect-microphone-clipping`
permite continuar únicamente ante `AUDIO_INPUT_CLIPPING`, severity `warning`,
recovery `reduce_device_gain`, del ID exacto del micrófono seleccionado. Conserva
la primera observación completa y marca `audio_quality_status=FAIL`. No reinicia
contadores ni admite otros avisos/fallos: clipping del mixer u otra entrada,
fuentes perdidas y outputs interrumpidos siguen deteniendo la prueba. El modo
estricto predeterminado y los FAIL anteriores permanecen intactos.

El analizador separa duración/decodificación de esa calidad: aunque todos los
gates de medios pasen, una entrada saturada produce PARTIAL global y conserva
FAIL de audio, con exit code no cero. Esto permite obtener evidencia horaria
sin convertir la saturación en un aprobado. No modifica el runtime de C6.

## Podcast r4: FAIL a los 55 min 46 s, audio sin warnings

La recolección r4 conserva **3345,767 s**, once recorridos Cut/Fade y mixer,
con cero avisos de audio y cero drops de salida hasta la observación rechazada.
No se completa la hora. El fallo es `Unplanned capture fallback`: la ventana
`source-5` recibe `SOURCE_UNAVAILABLE` mientras SCK sigue `running`, sample
`complete`, superficie de 9,772 ms, sin suspensión ni errores. La cámara continúa
recibiendo frames y ambos outputs están activos cuando se inicia el Cut seguro.
El verificador cierra después; owner/fixture/receptor salen normalmente y el
micrófono vuelve exactamente a su scalar original. No fue un crash ni clipping.

La confirmación de la palmada inicial llega a 1006,106 s y la final a 3362,748 s,
esta última después del cierre. Sus instantes físicos aún deben localizarse en
los archivos; no se confunden con la hora del mensaje.

El control `visual_health` de C6 reutiliza `find_window`, que usa el inventario
filtrado del selector. Ese inventario excluye ventanas por título vacío, nivel
distinto de cero o metadata de `NSRunningApplication`, además de identidad.
Esos criterios de presentación no prueban la desaparición de una ventana ya
admitida. Se prepara una reproducción real cambiando únicamente el nivel de
una ventana propia después de iniciar la captura. El campo exacto que causó
el rechazo original no quedó registrado: no se atribuye todavía a oclusión,
Spaces, suspensión SCK ni a CAP-01.
