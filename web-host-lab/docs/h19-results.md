# H19 — cierre del Browser Host

**H19: PARTIAL.** Se entrega la implementación y evidencia obtenida dentro del
laboratorio. La candidata sostiene cinco fixtures simples en
la matriz repetida, pero el ciclo combinado largo conserva un FAIL de
continuidad durante resize y crecimiento de footprint sin causa atribuida.
Keychain de producción, terceros e integración final siguen bloqueados.

Se construyó un host CEF/AppKit real con varias instancias visuales y un único
árbol de servicios Chromium, reutilizando el motor, wrapper, mailbox Rust,
binding de Creator Runtime y supervisor existentes. Cada instancia mantiene
identidad/generación, browser, PID observado, origen/contexto, inventario,
propiedades/eventos, frames, visibilidad, salud y cierre propios. Production,
GPUI, libobs integrado y Show Control no se modificaron.

La dirección elegida es B, varios CefBrowser para contenido propio de la misma
confianza, con política C para separar futuros grupos. Se conserva la opción de
hosts independientes; no hay pooling de heaps, contextos o browsers. Compartir
servicios reduce memoria y también comparte privilegios/dominio de fallo. Un
RequestContext distinto nunca se presenta como sandbox OS.

## Evidencia inicial de capacidad y fallo conservado

El control nuevo con el binario H18 congelado registró 656.86 MiB RSS. La matriz
inicial H19 usó un solo host, 640×360 a 30 FPS, 10 s de warmup y una ventana de
60 s por ejecución, tres repeticiones independientes por cantidad. Se mantuvo
el límite de emergencia de 2048 MiB RSS. No se repitió el ensayo fallido de cinco
árboles H18.

| Widgets | Mayor pico RSS MiB | Mediana de medianas footprint MiB | Mediana CPU steady, % de un core | Aceptación de cadencia |
|---|---:|---:|---:|---|
| 1 | 671.17 | 359.96 | 7.97 | Tres repeticiones pasan |
| 3 | 936.80 | 468.92 | 16.96 | Una de tres falla: 26.87–26.93 FPS |
| 5 | 1235.72 | 567.14 | 30.35 | Tres repeticiones pasan; no anulan el fallo con tres |

Son sumas de procesos observados, no RAM física única. El footprint no es RSS.
Los máximos históricos H18 para tres y cinco árboles fueron 1993.27 y
2880.17 MiB: la comparación de topología es orientativa porque H18 fue corto y
el caso de cinco acabó cancelado. No existe baseline H18 sostenido comparable
de CPU. GPU utilization y memoria física exclusiva permanecen sin medir.

El protocolo completo conserva estado PARTIAL: esta matriz no cubre todos los
tamaños, rates y versiones de H16/H18. Hay hashes de los píxeles retenidos
first/latest/visual, pero no hash ni lectura de contador visual de cada frame.
La tasa es de adquisiciones consumidas, no de imágenes necesariamente distintas
ni de salida audiovisual.

El runner marcó los nueve casos PASS de salida, límites, identidad y limpieza;
su alcance nunca incluyó aceptar FPS. La auditoría independiente detectó el
FAIL real en `animated-3-r3`: cada instancia aceptó 2155 pinturas durante la
ejecución completa, pero consumió 1957–1960 y coalesció 195–198. En la ventana
steady entregó 1612–1616 muestras. Los tres consumidores tuvieron pausas
coincidentes de unos 530 ms; OnPaint no tuvo rechazos busy/invalid y su máximo
de publicación fue inferior a 0.5 ms. Esto apunta a trabajo de consumo/disco o
planificación compartida, sin identificar por sí solo una syscall responsable.
La edad hasta adquisición excluye la escritura posterior; la auditoría nueva
también calcula edad al terminar y huecos entre adquisiciones.

La candidata acotada evita repetir `ftruncate` de `latest.bgra` cuando su tamaño
inmutable ya está establecido. Conserva cada `pwrite` completo, píxeles,
completion y telemetría; no se mejora la cifra omitiendo frames del sink. El
resultado inicial y su FAIL se conservan. La comparación puntual independiente
quedó así:

| Tres widgets, 72 s cada build | Control anterior | Candidata `repro-r1` |
|---|---:|---:|
| Adquisiciones/s por instancia, ventana de 60 s | 29.20–29.22 | 30.00 |
| Máximo trabajo de consumer, ms | 619.45 | 1.79 |
| Pico RSS del árbol, MiB | 931.59 | 926.61 |
| CPU steady, % de un core | 19.89 | 20.40 |

En la candidata, cada instancia conservó 2154 escrituras completas y una sola
llamada a `ftruncate` para latest; cero rechazos de longitud/descriptor. Se
evitaron 6459 llamadas repetidas en ese lote. La prueba confirma la eliminación
de trabajo redundante. Una pareja secuencial bajo carga global no aislada no
establece que esa syscall haya causado todas las pausas anteriores, ni que CPU
haya mejorado. Los máximos de consumo observados mejoraron; la repetibilidad se
evalúa aparte. [Control auditado](../research/h19-consumer-baseline-audit.json),
[candidata auditada](../research/h19-consumer-candidate-audit.json).

## Capacidad repetida de la candidata

La segunda matriz completa de nueve ejecuciones pasó la auditoría independiente,
con los mismos umbrales y sin cambiar los colectores. Artefacto smoke candidato:
`8a76e3ce6409d911cf04bd4815c5c8065d13aa21a8c620cdf839f0d7b44c311b`.

| Widgets animados propios | Mayor pico RSS MiB | RSS steady, mediana de medianas MiB | Footprint steady, mediana de medianas MiB | CPU steady, mediana % de un core | FPS consumidos en las tres repeticiones |
|---|---:|---:|---:|---:|---:|
| 1 | 712.17 | 552.56 | 364.98 | 7.20 | 30.000–30.017 |
| 3 | 958.50 | 938.55 | 469.24 | 15.90 | 30.000–30.017 |
| 5 | 1251.91 | 1226.09 | 594.47 | 25.64 | 29.983–30.000 |

**Límite demostrado: cinco fixtures smoke propios, 640×360, 30 FPS, en esta Mac
y este pin CEF.** Todos los niveles ensayados inferiores pasan; no se salta el
nivel de tres para aceptar cinco. No se certifican seis o más, Goal5, 1080p,
60 FPS, otras Macs, sesiones ilimitadas o contenido arbitrario. El peor pico
dejó 796.09 MiB hasta el límite muestreado de emergencia; no es una reserva
garantizada ni un cap de asignación impuesto por el kernel.

La mayor edad p95 hasta adquisición fue 12.10 ms y hasta terminar el consumo,
12.23 ms. El máximo trabajo de consumer fue 4.29 ms; ninguna muestra superó
100 ms. El primer paint no transparente apareció como máximo a 405.97 ms desde
`initialize_enter`, en el mismo reloj nativo. El mayor intervalo nativo desde
close solicitado hasta retorno de shutdown fue 164.91 ms; el intervalo de
cleanup del supervisor, medido aparte, llegó a 56.82 ms.

Los picos RSS fueron algo mayores que en la primera matriz compartida:
712.17/958.50/1251.91 frente a 671.17/936.80/1235.72 MiB. Las medianas RSS también
variaron y no siguen necesariamente al footprint. No se atribuye una mejora de
memoria a eliminar `ftruncate`, ni una causalidad aislada de CPU a comparar dos
lotes bajo carga global no controlada. La mejora arquitectónica demostrada es
compartir servicios Chromium y reducir su duplicación respecto de los árboles
independientes de H18. El FAIL previo queda conservado, no reemplazado por esta
matriz. [Auditoría completa de la candidata](../research/h19-performance-candidate-capacity-audit.json).

Tres repeticiones estáticas y tres mixtas también pasaron:

| Escenario, 72 s por repetición | Pico RSS máximo MiB | Footprint steady, mediana MiB | CPU steady, mediana % de un core | Adquisiciones steady |
|---|---:|---:|---:|---|
| Un widget estático | 711.06 | 183.74 | 0.63 | Cero, según contenido sin cambios |
| Cinco widgets: uno animado y cuatro estáticos | 1194.88 | 511.35 | 8.14 | Destino 1: 29.983–30 FPS; pares: cero |

Para los estáticos se verifican paint inicial, píxeles retenidos, identidad,
conservación y cierre. Su edad p95 sin muestras permanece null; no se inventa
una cadencia continua. El lote fue pausado entre casos para la ventana H20,
registrada por separado. [Auditoría estática/mixta](../research/h19-performance-static-mixed-audit.json).

## Sesión de diez minutos: resultados distintos por gate

El host mantuvo un único `CefInitialize` durante 600 s y ejecutó la secuencia de
eliminación, recreación, ocultación, resize y crash/recovery. El runner terminó
PASS de sus gates de ejecución, memoria, identidad y limpieza. La auditoría de
ventanas estables también pasó. **La aceptación funcional combinada quedó FAIL**
por continuidad de un par durante resize; no se reemplaza ese resultado por los
otros PASS. [Runner](../evidence/H19-candidate-soak/lifecycle-3-600s/report.json),
[ventanas y recursos](../research/h19-performance-soak-audit.json),
[FAIL funcional conservado](../evidence/H19-candidate-soak/lifecycle-3-600s/analysis.json).

| Medida del árbol | Ventana inicial 30–90 s | Ventana final 540–590 s |
|---|---:|---:|
| RSS mediano, MiB | 824.10 | 403.50 |
| Footprint agregado mediano, MiB | 468.55 | 545.67 |
| CPU, % de un core | 19.27 | 18.74 |
| Procesos, mediana | 8 | 8 |
| Adquisiciones/s de instancias finales, reloj nativo | 29.967–30.000 | 29.980–30.000 |

Las ventanas de recursos y frames se calculan en sus propios relojes; no se
restan timestamps entre ellos. El pico RSS fue 925.16 MiB. El footprint creció
77.12 MiB pese a caer el RSS: browser +45.55 MiB, renderers agregados +28.78 MiB
y GPU aproximadamente +3.41 MiB. Esto no prueba liberación de RAM, memoria plana
ni ausencia de fugas. No se atribuye ese aumento a una caché, heap o allocator
concreto. Hace falta perfilarlo y demostrar un límite/meseta antes de aceptar
sesiones de producto prolongadas.

Los ocho epochs conservaron exactamente sus pinturas:
53,597 aceptadas = 53,586 consumidas + 10 coalescidas + 1 invalidada por cierre.
Todos terminaron con cero bytes/leases propios retenidos. Cinco epochs ya
retirados se observaron así mientras el mismo host seguía vivo, con hashes
conservados en [el recibo durante la sesión](../evidence/H19-candidate-soak/live-retired-epochs.json).
La [comparación posterior](../research/h19-soak-retirement-match.json) confirma
los cinco hashes y la identidad del host en las muestras conservadas.
Eso demuestra liberación lógica de buffers propios, no de todas las páginas
Chromium. Los 49,657,651,200 bytes copiados son tráfico acumulado; no RAM viva.

La mayor edad p95 al terminar consumo fue 12.31 ms en las ventanas estables.
El cierre nativo hasta retorno de shutdown tardó 157.15 ms, de los cuales
61.05 ms correspondieron a `CefShutdown`; el intervalo independiente del
supervisor fue 42.47 ms. No quedaron procesos observados propios tras cleanup.

Durante la fase temprana de resize, C necesitó 447.49 ms hasta su primer paint
nuevo, dentro del límite de 1000 ms. Sin embargo D, que no cambiaba de tamaño ni
de lifecycle, tuvo un hueco de observación de **458.98 ms**, frente al gate
inalterado de **250 ms**. Su trabajo de consumo junto al hueco fue solo
0.06–0.12 ms. La preparación de epoch de C tomó 5.46 ms; el tramo posterior fue
de 442.03 ms. La evidencia sitúa la pausa después de la preparación propia,
alrededor de `WasResized`/composición, pero no identifica una causa interna CEF,
GPU o de planificación. No es evidencia para culpar a `ftruncate` ni cambiar
el umbral. Los ocho diagnósticos cortos posteriores pasaron, conservando el FAIL
del ensayo largo. [Revisión funcional de 30 casos finales y 103 epochs](../evidence/H19-candidate-functional-review.json).

Hot resize sigue disponible como experimento cerrado para reproducir el
problema. No queda aceptado para continuidad de producción. El manager H20
requiere reemplazo frío, cuya ejecución y cadencia de pares también deberán
validarse al integrarlo. No se realizó otra tanda buscando un PASS del mismo
fallo sin una corrección demostrada.

## Funcionalidad nativa y límites

Los diagnósticos finales cubren crear A/B/C, cerrar B, crear D, ocultar A,
redimensionar C, cerrar/recrear D, provocar fallo de renderer C, recuperar C,
suspender A por cierre y recrear A con nueva generación. Frames retenidos/epochs y
marcadores en píxeles comprueban identidad; la evidencia de cierre y reap es
independiente de los ACK de JavaScript. El fallo conocido revoca todos los
miembros del PID afectado; en estas ejecuciones los widgets tenían PIDs
distintos. Un crash real con PID compartido permanece NOT_EVALUATED, aunque su
regla de revocación tiene tests compilados.

Resize usa `WasResized` y un mailbox nuevo por epoch. Solo se permite una
geometría no usada antes en ese browser; A→B→A exige reemplazo frío. La suspensión
del laboratorio destruye el browser y reanuda con otro, no conserva un heap ni
prueba suspensión del sistema operativo. El límite nativo de 32 registros de
creación y las ventanas temporales de pruebas no equivalen a una sesión
ilimitada de producto.

Las seis regresiones Goal con tres instancias pasan: estándar 640×360,
horizontal 960×540, vertical 540×960, controles, hidden y crash/restart. Se
reutilizan sin modificación los activos y API originales. Bootstrap, props,
goal.scored, active, rechazo de repetición, cancel/resume/dispose y transparencia
se comprueban junto con pixels reales. Solo la instancia destino recibe el
evento; los pares conservan transparencia. Hidden observa cancel ACK antes de
ocultar y resume ACK antes de mostrar. El reinicio dispara un nuevo evento
explícito del fixture, no un replay automático de Production.

Goal tiene un perfil de procesos/memoria distinto al fixture smoke. Estas
pruebas son funcionales cortas y no aceptan capacidad Goal de cinco instancias.
La captura hidden ocurre durante la entrada, no después de desplegar todo el
marcador. La revisión visual conserva esa diferencia.
Las vistas derivadas [horizontal](../evidence/H19-candidate-goal-horizontal/instance-1-g195002-e1/visual.png)
y [vertical](../evidence/H19-candidate-goal-vertical/instance-1-g195003-e1/visual.png)
provienen de BGRA reales conservados junto a ellas; el PNG deshace la
premultiplicación para previsualizar, sin modificar esos bytes originales.

En los diagnósticos del primer binario final, el resize independiente tardó
60.08 ms hasta el primer paint de la nueva geometría; dentro del ciclo de vida,
198.25 ms. Ocultar produjo un hueco de 4020.06 ms en el destino mientras cada
par mantuvo 114 observaciones en la ventana comprobada. El script lento produjo
509.02 ms de hueco y los pares siguieron pintando. Los 24 eventos dirigidos se
recibieron exactamente en el destino y cero en cada par. El consumidor lento
coalesció 167 pinturas por instancia sin perder su clasificación terminal.

## Seguridad y configuración de producción

**Keychain de producción BLOCKED.** El código exacto de Chromium inicia
OSCryptAsync globalmente antes del uso de cookies. El proveedor macOS puede
alcanzar SecItemCopyMatching mediante un worker MayBlock; un trabajo ya iniciado
puede bloquear el cierre del pool. Contextos en memoria y cookies deshabilitadas
no eliminan esa inicialización. Se investigaron las APIs y código fijados sin
consultar, enumerar ni modificar el Keychain real. No se demostró una opción
oficial apropiada que cierre ese gate. El backend mock se identifica como prueba
en todos los builds y no sirve para aceptar distribución.

**Terceros BLOCKED.** Tres renderers reales recibieron EPERM al abrir un archivo
señuelo privado que el browser sí podía abrir. Es una denegación OS concreta de
un archivo, no confinamiento general de HOME/Keychain/red. Los probes web propios
de fetch/WebSocket/popup/cookie/worker fallaron y un listener propio aceptó cero
conexiones; los contadores de callbacks permanecieron cero, por lo que no se
atribuye el bloqueo a callbacks ni a una política OS de red. Browser, GPU,
servicios de red, DNS/WebRTC, dispositivos, IPC hostil y escape requieren todavía
pruebas suficientes. Se mantuvo el sandbox CEF; no hubo políticas Seatbelt,
sandbox-exec, flags de bypass ni cambios globales.

El siguiente candidato de confinamiento es un servicio XPC con App Sandbox y un
broker de capacidades usando mecanismos públicos. Es un diseño investigado,
no una frontera implementada o validada en este hito. Separar hosts por nivel de
confianza tampoco desbloquea terceros por sí solo.

## H20 y distribución

H20 puede comenzar trabajo aislado con el `BrowserHostManager` compilable y los
contratos existentes de frame/lifecycle/admission. Necesita handoff de H17 para
modificar Production y deberá demostrar transporte binario autenticado y
acotado, upload/destrucción de texturas dentro del graphics context de OBS,
visibilidad compartida entre capas, revocación, fallos y cierre bajo composición
real. El reloj y salida audiovisual pertenecen a libobs. No hay video por MCP,
web audio, PTS tomado del host ni otro renderer Production.

El límite de capacidad se aplica al contenido, viewport y FPS ensayados. H20
necesita además presupuesto agregado de todos sus grupos/hosts; multiplicar el
límite de un host no demuestra capacidad de toda Production. Los límites
estructurales del manager (hasta 16 registros activos configurables) no son una
autorización de rendimiento para 16 widgets.

La telemetría ahora clasifica exactamente todo paint aceptado y separa leases
retenidos de transiciones adquiridas. El máximo de buffers propios no representa
el heap/cachés/superficies Chromium. Las copias CPU completas se conservan; dirty
rectangles y GPU zero-copy no se introdujeron sin ownership demostrado.

El bundle seleccionado mide 329.381 MiB de archivos y conserva el framework
completo. La mayor parte del crecimiento respecto de H18 proviene de incorporar
los 19,690,678 bytes de créditos Chromium que faltaban. ARM64 y sellos ad-hoc
fueron verificados. Developer ID, Hardened Runtime/JIT, notarización, empaquetado
Motive y compatibilidad en otra Mac siguen pendientes. No se publicó ni firmó
con identidad personal.

## Índice de evidencia

- [Resumen verificable del cierre](../evidence/H19-closeout.json) e
  [índice SHA-256 de fuentes y evidencia H19](../evidence/H19-final-evidence-index.json).
- [Auditoría y criterios iniciales](h19-audit.md), [arquitectura](h19-architecture.md).
- [Memoria y mediciones](h19-memory-analysis.md), [matriz inicial](../evidence/H19-final-capacity/summary.json).
- [Capacidad seleccionada](../research/h19-performance-candidate-capacity-audit.json),
  [estáticos/mixtos](../research/h19-performance-static-mixed-audit.json),
  [soak: recursos](../research/h19-performance-soak-audit.json) y
  [soak: FAIL funcional](../evidence/H19-candidate-soak/lifecycle-3-600s/analysis.json).
- [Diagnósticos nativos iniciales](../evidence/H19-final-diagnostics/summary.json) y
  [diagnósticos seleccionados](../evidence/H19-candidate-diagnostics/summary.json).
- [Regresión Goal inicial](../evidence/H19-final-goal-review.json),
  [regresión con el consumer candidato](../evidence/H19-candidate-goal-review.json).
- [Seguridad y fuentes exactas](h19-security.md), [distribución](h19-distribution.md).
- [Contrato H20](h19-h20-contract.md), [reproducción y fuentes de builds](h19-native-host.md).
- [Verificación estática anterior a la candidata](../evidence/H19-final-static/summary.json),
  [verificación de la candidata](../evidence/H19-candidate-static/summary.json).

## Verificación y procedencia

La verificación de la candidata pasó sus 19 comprobaciones: 38 tests Rust,
111 tests Python, siete tests Node y cuatro programas C++ compilados y
ejecutados, además de clippy/fmt. Los programas C++ son pruebas sintéticas del
ABI, writer, routing y política; la evidencia CEF está en los ensayos nativos
separados. El test del writer usa archivos temporales reales, mantiene first y
latest distintos y verifica rechazo sin modificar bytes.

Los builds usados en benchmarks tienen hashes inmutables y snapshots de fuentes
verificados. El builder rechaza reutilizar un nombre H19 ya registrado: una
reproducción debe usar un nombre nuevo. Se conservan logs, PNG/BGRA, metadatos,
trazas, muestras del supervisor comprimidas, fuentes de medición y análisis
independientes. Los archivos de fuentes de las candidatas son completos para
sus manifests; el primer build exploratorio antiguo conserva una laguna de
procedencia de frame-bridge, identificada como PARTIAL en su índice. No se
sustituye ese archivo por una versión posterior ni se afirma build binario
reproducible o source correspondence completo de distribución.

También se conservan errores de herramientas: una clasificación de seguridad
con generación esperada equivocada, un checker de lifecycle con profundidad de
ruta equivocada y la primera invocación del harness de compilación sin un flag
de warnings existente. Sus correcciones tienen resultados nuevos. Esos errores
no son fallos de ejecución CEF; el FAIL de cadencia inicial sí es un resultado
nativo real y permanece en la aceptación de esa matriz.

La [revisión de gobernanza](../evidence/H19-governance-review.json) comprobó
igualdad de bytes y modos de los archivos heredados frente a la base: evidencia
histórica, assets/API Goal y archivos fuera del laboratorio, salvo la corrección
autorizada de `AGENTS.md`. Main y H17 se observaron limpios en las comprobaciones
de solo lectura. No se hizo push, merge, rebase, release, notarización ni cambios
globales de permisos o preferencias.

La [revisión final de integridad](../evidence/H19-final-governance.json) vuelve
a comprobar los 2711 archivos protegidos y las fuentes del candidato. Ejecutar
`python3 web-host-lab/tools/h19_verify_evidence_index.py` verifica los bytes y
modos retenidos, sin compilar ni lanzar CEF. Su PASS es de integridad: conserva
H19 PARTIAL y el FAIL funcional del soak. El índice excluye su propio hash; Git
identifica el commit contenedor, evitando una referencia circular.

Durante los ensayos el propietario autorizó coordinación con el H20 de captura.
Se adoptó el directorio común `motive/var/run/physical-test.lock`, adquirido con
`mkdir` exclusivo y un archivo `OWNER` dentro, y liberado solo por su dueño
después de observar cleanup. El
lote estático/mixto se pausó entre casos para una tanda de compilación H20: el
coordinador Python quedó detenido, el CEF activo terminó normalmente y el lock
se cedió. Después se readquirió antes de reanudar. Su tiempo total de lote
incluye la pausa; las ventanas de cada caso siguen intactas. Esta coordinación
operativa no es handoff para integrar Browser Host en Production ni modifica
el alcance del H20 de ScreenCaptureKit.

## Matriz final de aceptación

| Nivel | Estado | Alcance del resultado |
|---|---|---|
| A — Host propio funcional | **PARTIAL** | CEF real, alpha, multi-instancia, eventos, Goal, crash/recovery, ownership y cierre demostrados; el ciclo combinado largo falla continuidad de un par durante resize. |
| B — Host eficiente para Motive | **PARTIAL** | Cinco smoke propios pasan las tres repeticiones y 2 GiB; falta protocolo completo, caracterización del crecimiento de footprint y aceptación de transiciones/sesiones de producto. |
| C — Seguro para terceros | **BLOCKED** | Una denegación de archivo en renderer no cierra browser/GPU/red/HOME/Keychain/permisos/escape; no hay configuración de credenciales de producción aceptada. |

| Pri. | Gate | Estado y evidencia final | Siguiente condición concreta |
|---|---|---|---|
| P0 | Memoria y topología | **PASS limitado:** B/C elegida; 1/3/5 smoke bajo 2048 MiB y cleanup | Mantener límite cinco en el dominio ensayado; caracterizar cada contenido/resolución y grupos agregados antes de admitirlos |
| P0 | Identidad y autoridad | **PASS propio:** frames retenidos, epochs, routing y eventos dirigidos; sin autoridad Production en JS | Crash nativo de PID realmente compartido y auditoría de IPC hostil siguen pendientes |
| P0 | Keychain | **BLOCKED:** causa de arranque/worker investigada, mock solo laboratorio | Opción oficial o confinamiento aceptado que evite credenciales innecesarias, más cierre demostrado sin backend test |
| P0 | Sandbox OS | **BLOCKED:** syscall de archivo denegada en tres renderers y probes propios; matriz amplia incompleta | Broker/confinamiento público y pruebas negativas por proceso/superficie; terceros continúan deshabilitados |
| P1 | Pipeline | **PASS limitado:** conservación exacta, buffers propios liberados, full writes y un truncado inicial por epoch | Transporte real y ownership de textura/OBS; no aceptar FFI confiable como decoder hostil ni timestamps como PTS |
| P1 | Cadencia | **PASS seleccionado / PARTIAL completo:** 9/9 animados, 6/6 estáticos/mixtos | Más tamaños/rates/contenidos, hashes/counters por frame y salida audiovisual real; GPU sigue NOT_EVALUATED |
| P1 | Lifecycle largo | **PARTIAL:** recreación/crash/cleanup pasan; footprint +77.12 MiB; continuidad de D **FAIL 458.98 ms** | Perfilar crecimiento y pausa tras resize; demostrar meseta/latencia de pares sin cambiar umbrales |
| P1 | Resize | **PARTIAL:** epoch y geometría correctos, latencia propia <1000 ms; par excede 250 ms | Hot resize no aceptado para Production; mantener reemplazo frío y probar su ejecución/cadencia antes de integración |
| P1 | Goal | **PASS propio:** seis escenarios de candidata, 19 epochs, cero contaminación observada | Capacidad sostenida con Goal y composición OBS; no extrapolar smoke5 a Goal5 |
| P1 | H20/libobs | **PASS contrato / NOT_EVALUATED integración:** manager compilable y fixtures aisladas | Handoff explícito, transporte autenticado, graphics context, alpha/cadencia/teardown con outputs reales |
| P2 | Distribución | **PARTIAL auditoría / BLOCKED release:** ARM64, notices, hashes y ad-hoc correctos | Keychain/OS gates, Developer ID, Hardened Runtime/JIT, notarización, fuente/licencias completas y otra Mac |

Los commits locales de construcción incluyen `7972d35` (gobernanza), `2bca75e`
(frames/manager), `68065c0` (supervisor/control), `20f1705` (host multi),
`40b8048` (seguridad/distribución), `37e3412` (procedencia), `59e9690`
(diagnósticos) y `8dfe5c7` (writer y comparación). El cierre añade los resultados
finales y sus índices a la misma rama `codex/h19-browser-hardening`, desde
`549d63f1a01625947ef1dfcea1609ab5c0a5295a`. Los reportes históricos H16/H18
permanecen intactos. No se publicó ni integró esta rama en main.
