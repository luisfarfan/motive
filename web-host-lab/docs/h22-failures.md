# H22 — fallos y reclasificaciones conservados

Ninguna fila borra el informe original. Un defecto del instrumento se distingue
de un fallo nativo y de una condición no ejecutada; cada nueva conclusión tiene
su archivo propio y hashes de entrada.

| Evidencia original | Resultado / diagnóstico | Continuación |
|---|---|---|
| H19 soak | Peer D 458,98 ms durante hot resize; FAIL real | Cold replacement; causa interna exacta no demostrada |
| H22-baseline/h19-integrity.json | Diferencias heredadas H20 en 18 archivos protegidos fuera de H19 | Verificación acotada v2 de 2136 blobs H19; FAIL original retenido |
| H22-baseline/h19-scoped-integrity.json | Comprobación inicial mezcló cinco cambios de trabajo H22 con baseline | v2 usa blobs del HEAD base para baseline, enumera las diferencias |
| H22-baseline/capacity-audit.json | Binario histórico faltante en el worktree H22 | v2 usa el artefacto histórico retenido, solo lectura |
| H22-native-cold1-build.log | Slot físico ocupado; build NO_EJECUTADO | Log r2 y candidato cold1 separados; no confundir retorno 75 con error de compilación |
| H22-cold1-cycles600-r1 | Timeout de `ps` a ~173 s; evidencia parcial y cleanup | Mismo binario cold1, nuevo observador libproc; r2 de 600 s |
| H22-pilot-r1-lower3h | Divergencia de relojes; duración nativa y supervisor incompatibles | Detector mach_continuous/absolute, assertion de idle sleep propia durante el lock; r2 |
| H22-pilot-r2-goallife3/workload-analysis.json | Clasificador exigía frame transparente tras cierre de evento activo | Reclasificación exige transparencia al completar/idle; cierre interrumpido conserva bytes y revoca autoridad |
| H22-xpc-r1/report.json | Clasificador confundió NSNumber entero 0 con booleano False | Auditor independiente acepta sólo False o entero exacto cero; frontera acotada observada |
| H22-cef-appsandbox-r1 | SIGTRAP en CefInitialize; Mach bootstrap 1100 | BLOCKED, sin entitlement de excepción ni sandbox deshabilitado |
| H22-native-boundary-r1 | Utility sin Seatbelt conserva filesystem/red; browser/red son autoridades compartidas | Observación PASS, terceros BLOCKED |
| H22-transport-first-test.log | Dos pruebas fallaron con SO_RCVTIMEO sobre socket Darwin desconectado | Poll no bloqueante y deadline total; diez pruebas kernel PASS |
| H22-contracts-r1 | Formato Goal y directorio faltante del runner replay | Formato corregido; r2 conserva replay real de 140 frames |
| H22-background-component-audit.json | Componentes Chromium instalados en perfiles frescos previos | Confusor de memoria/capacidad; lanzamientos de perfil antiguo bloqueados |
| H22-campaign-r1 | Matrices detenidas por el hold del perfil anterior | Casos no iniciados NOT_EVALUATED; no inventar fallo de rendimiento |
| H22-network-pilot-r1 | Cuatro intentos UDP IPv6; receta ~NOTFOUND no rechaza resolver en Chromium 150 | Diagnóstico fijado; perfil ^NOTFOUND sin excepciones |
| H22-network-pilot-r2 | Control nativo y NetLog PASS; cero eventos de socket/manifests | Perfil closed-resolver-v2 para el contraste prolongado y matriz final |

El primer ledger de contratos y los logs de builds detallan comandos y errores.
Los perfiles anteriores siguen siendo observaciones reales, pero no certifican
una carga que excluya actualizaciones de Chromium. El PASS de un control de red
no convierte el proceso en un sandbox OS ni resuelve Keychain.

## Cadencia con tres Goal originales — perfil final

`H22-widgets-r2-goal3h-r1` conserva FAIL de rendimiento: uno de los 27 eventos
completos posteriores al warmup (instancia 2, generation 253300) adquirió
54 frames en 1,900673375 s, **28,41098355 FPS <28,5**. El máximo gap de ese
intervalo fue 77,356541 ms y p95 edad 11,388167 ms. Native, contabilidad,
red cerrada y cierre pasan. No se atribuye la pérdida a una causa interna
ni se corrige el umbral por lo pequeño del margen.

La campaña r2 se detuvo como estaba declarado. La continuación r3 conserva
el caso fallido y ejecuta las repeticiones restantes del plan y las otras
configuraciones. Una opción explícita permite continuar sólo si native,
seguridad y funcionalidad pasan y el FAIL es de rendimiento intermitente;
cuatro pruebas negativas/positivas verifican esa frontera. Un fallo nativo,
de evidencia, red o cierre sigue deteniendo la campaña. No se reemplaza
una repetición fallida con otra hasta obtener PASS.

El [diagnóstico de cadencia](../evidence/H22-widgets-r2-goal3h-r1/cadence-diagnosis.json)
localiza la reducción antes del consumer: 617 paints, adquisiciones y consumos
para la identidad completa; cero coalescing/pérdidas/rechazos, y 54 paints y
54 adquisiciones dentro del evento fallido. Activo→primer paint fue 71,41 ms,
el mayor gap interno entre paints 66,62 ms y el mayor callback propio de
publish de toda la identidad 0,32 ms. El heartbeat UI solapado máximo fue
55,09 ms para un periodo solicitado de 50 ms. Eso no demuestra un bloqueo UI
de 250 ms ni atribuye causalmente el tramo lento a GPU, compositor, JS o kernel.

`H22-widgets-r3-goal5h-r1` conserva otro FAIL de cadencia: tres intervalos
contemporáneos de las instancias 1, 2 y 4 quedaron en 28,15 / 27,61 / 28,14 FPS.
El mayor gap activo del ensayo fue 163,58 ms; RSS pico 1882,30 MiB. Native, red,
contabilidad y cierre pasan. [Diagnóstico por intervalo](../evidence/H22-widgets-r3-goal5h-r1/cadence-diagnosis-v2.json).
La segunda repetición pasó, con 1891,92 MiB de pico. Ese margen hasta el corte
muestreado de 2048 MiB no representa memoria disponible para captura o encoder,
ni compensa la primera repetición fallida.

En cinco Goal sí hubo coalescing (3/5/2 para esas identidades completas). Los
samples individuales conservan paints adquiridos, no timestamps de todos los
coalescidos: no se puede asignar toda la pérdida a CEF ni al mailbox. La revisión
v2 precisa ese nombre en el diagnóstico derivado y conserva el original. La
espera hasta el primer paint adquirido fue 138,90–151,07 ms y el heartbeat UI
máximo solapado 55,88 ms; no demuestran la causa interna de esa espera.

## Espera física agotada; caso no ejecutado

`H22-widgets-r3/mix5h-r3.log` conserva retorno 75 tras esperar 30 minutos
por el lock de H21. No existe report nativo ni frames para ese intento. El
FAIL del controlador no es un fallo de capacidad, crash ni fuga. La campaña
r4 espera la ausencia del lock (máximo 7200 s), conserva los planes originales
y comienza en el índice 17: siete casos de widgets aún no ejecutados, luego
lifecycle y soaks. Cada trial vuelve a tomar el lock atómicamente; no modifica
ni elimina un OWNER ajeno y conserva los deadlines/RSS originales.

## Goal lifecycle final: cierre tardío real

`H22-lifecycle-r2-goallife3` conserva FAIL `CLOSE_DEADLINE`: 5403,68 ms frente
a 5000 ms. La llamada CefShutdown ocupa 5367,76 ms. Native termina con código
cero, todos los procesos observados salen y el cleanup externo tarda 13,40 ms.
No se elimina el FAIL porque la salida haya terminado dentro del deadline
externo de emergencia (65 s para esta prueba de 45 s).

El [diagnóstico](../evidence/H22-lifecycle-r2-goallife3/shutdown-diagnosis.json)
vincula traces, frames, supervisor y workload. La auditoría de workload pasa
por separado: ocho operaciones, peer activo máximo 68,44 ms y cold replacement
a primer paint en 86,04 ms. También comprueba las barreras de cierre posteriores
al check de plazo, que el auditor original dejó sin evaluar al fallar. No hay
atribución de stack interna ni optimización justificada todavía.

La campaña r4 se detuvo ante ese fallo funcional. La
[revisión previa a r5](../evidence/H22-campaign-r5/review.json) permite ejecutar
únicamente cold resize y los tres soaks aún ausentes, con supervisión original.
No es continuación automática de fallos funcionales ni una repetición destinada
a reemplazar Goal lifecycle por un PASS.

El [contraste instrumentado de cierre](../evidence/H22-goal-shutdown-probe-r1/contrast-analysis.json)
repite una vez el mismo binario/scenario durante 45 s. Cierre 94,73 ms, de los
cuales 60,23 ms están en CefShutdown; no alcanzó el trigger de 200 ms y no se
capturó un sample. Native, barreras y cleanup pasan, pero workload conserva
otro FAIL: uno de diez eventos completos quedó en 28,39567 FPS. Los intervalos
interrumpidos también permanecen en los datos, sin reclamar FPS sostenido para
ellos. El cierre tardío original **no se reprodujo y no se declara resuelto**.

## Mezcla final de 600 s: pausas tardías

`H22-soak-r2-widgetmix3h` conserva FAIL de rendimiento: **11/194 eventos
completos** incumplen el criterio; mínimo 25,88942 adquisiciones/s y mayor gap
activo 465,57 ms entre timestamps de paints adquiridos (460,46 ms entre
adquisiciones). Todos los eventos fallidos están entre 470 y 583 s, después
del último ciclo de lifecycle. Los 70 checks de operaciones con peers pasan,
con máximo 109,78 ms; esa observación no borra los stalls posteriores.

El [diagnóstico por intervalo](../evidence/H22-soak-r2-widgetmix3h/stall-diagnosis.json)
conserva correlación con heartbeat UI: máximo solapado 488,38 ms. Las dos
identidades afectadas tienen máximos propios de publish 1,10/2,13 ms y trabajo
del consumer 3,31/3,84 ms. Sí hubo coalescing, por lo que no están los timestamps
individuales de todos los paints. El observador no detectó suspensión del SO
(cota inferior 0 ms, incertidumbre máxima 0,020 ms). No distingue bloqueo de
event loop, programación de timers o scheduling del SO.

Native, eventos, contabilidad, red y cierre pasan: 31 generaciones, 14 cold
replacements en 73,83–93,15 ms, cierre 121,86 ms y cleanup 9,95 ms. La suite
continúa a Goal vertical bajo su gate explícito de fallo sólo de rendimiento.
La mezcla no queda admitida a 600 s por sus resultados cortos.

App Nap es una hipótesis pendiente, no una causa demostrada. Apple documenta
[reducción de prioridad y throttling de timers/I/O](https://developer.apple.com/library/archive/documentation/Performance/Conceptual/power_efficiency_guidelines_osx/AppNap.html),
pero no se observó ese estado directamente en esta ejecución. No se desactiva
globalmente ni se añade una activity assertion por conjetura. El diagnóstico
se limita primero a un sample de un host propio si reaparece el hueco.

La inspección posterior del Chromium fijado debilita la explicación simple de
App Nap: [InitializeMac](https://github.com/chromium/chromium/blob/150.0.7871.252/content/app/mac_init.mm)
ya registra `NSAppSleepDisabled` para el browser. Es código upstream del proceso,
no un cambio global realizado por H22. El
[inventario de fuentes](../research/h22-scheduling-sources-v3.json) conserva
esa inicialización de Chromium; no demuestra un estado runtime de todos los helpers ni asigna
causa al fallo. No se añade otra activity assertion a ciegas.

El [único contraste de la mezcla](../evidence/H22-widget-stall-probe-r1/contrast-analysis.json)
usó el mismo binario durante 600 s, con observador externo y límite de un sample.
Pasó 194 eventos completos: mínimo 29,88905 FPS, gap activo máximo 56,44 ms,
heartbeat máximo 101,77 ms, cierre 166,42 ms y cleanup 12,16 ms. El observador
atribuyó el host por árbol, ruta y PID/nacimiento; no activó el sample. No se
capturó stack y **no se reprodujo ni se declara reparada** la pausa original.
No se añaden flags de energía, cambios nativos ni repeticiones hasta obtener
PASS. Haría falta una traza causal del event loop/scheduling durante una
recurrencia antes de justificar una corrección.

El primer auditor de workload de ese contraste arrancó antes de que terminara
su análisis previo y conservó FAIL por `analysis.json` ausente. El informe
`workload-analysis-v2.json` se ejecutó después sobre la misma evidencia nativa
y pasa. El diagnóstico vincula ambos hashes: es un error de orden del auditor,
no una reclasificación de un fallo visual. No forma parte de los 39 casos
originales de capacidad.

## Precisión de los agregados finales

La [conciliación v2](../evidence/H22-summary-scope-precision.json) separa el
resultado de los gates propios del caso de la evaluación de FPS sostenido.
Cold resize de 12 s ya tenía PASS nativo/de continuidad y NOT_EVALUATED de
cadencia continua; el primer agregado trataba ese grupo como FAIL al exigir
una ventana inexistente. V2 añade `case_result`, conserva todos los campos
anteriores y mantiene el NOT_EVALUATED y la no admisión de capacidad de 72 s.
Ningún FAIL nativo cambia: los 39 casos son 35 PASS y cuatro FAIL, y sus
gates de cadencia son 35 PASS, tres FAIL y un NOT_EVALUATED. Seis tests de
matriz y siete de cobertura verifican esa distinción y la integridad de datos.
