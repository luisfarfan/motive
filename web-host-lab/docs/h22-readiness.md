# H22 — Browser Host production readiness

Estado: **aceptación parcial; matriz completada y bloqueos críticos abiertos**. No se acepta
H22 completo ni se autoriza Production o contenido de terceros.
Base: `25aca10dfeaa22345a7c4d9d232613ffb496bf1a`, `origin/main` tras fetch.
Rama: `codex/h22-browser-production-readiness`, worktree independiente
`/Users/luisfarfan/Developer/products/motive-h22`. H23 integrará, mediante
handoff explícito, el Browser Host en el owner existente. H21 conserva captura
y Production. No se modifica su worktree, `src/`, `native/`, `build.rs`,
`show-control/` ni los componentes de captura.

## Gates y protocolo antes de medir

- A — funcionalidad/lifecycle: generaciones nuevas, cierre final CEF antes de
  recrear, identidad y frames reales, conservación de paints, leases liberados,
  reap externo de PID/birth. Hide/cancel/resume y fallo sin replay.
- B — rendimiento/continuidad: peers activos con huecos <250 ms durante cambios;
  resize/reemplazo hasta primer paint <1000 ms; no se cambia el gate H19.
  Warmup 10 s + ventana 60 s, >=28.5 adquisiciones/s a 30 FPS, p95 edad <=100 ms.
  Los estáticos no tienen FPS inventado. Soaks de 600 s con ventanas por proceso,
  memoria propia y perfiles separados de las pruebas de cadencia.
- C — seguridad: Keychain y terceros BLOCKED hasta evidencia de configuración
  soportada y confinamiento OS. Mock solo identifica ensayos, nunca producto.
- D — preparación H23: transporte binario autenticado/acotado, identidad,
  revocación y ownership; contrato de texturas OBS compilable por separado.
  Ningún test de contrato acredita texturas reales ni fluidez de streaming.

Lock físico canónico mediante `tools/h22_with_lock.py`, con `mkdir` exclusivo,
token, PID/inicio, cleanup y cesión entre comandos. Cada ensayo CEF conserva
supervisor externo <=720 s y RSS de emergencia muestreado <=2048 MiB. No se
eleva ese límite para pasar. No se autorizan sondas de credenciales reales ni
navegadores personales; el backend mock no acredita observación OS completa de Keychain.
El hallazgo de componentes de Chromium impide afirmar ausencia de tráfico externo
en perfiles anteriores; se conserva y bloquea esa ruta de ejecución. No merge/rebase/push/publicación/distribución.

## Baseline conservado

H19 documenta 1251.91 MiB de pico para cinco fixtures simples 640×360/30,
77.12 MiB de crecimiento de footprint en 600 s y FAIL de continuidad de D de
458.98 ms entre paints adquiridos de D durante hot resize de C (464,16 ms
entre adquisiciones). No acredita Goal5 ni cargas arbitrarias.
El checker de integridad completo conserva un FAIL esperado porque su manifiesto
protegía también Production antes de H20: `H22-baseline/h19-integrity.json`.
Se deben verificar separadamente los 2136 archivos H19 y atribuir las diferencias
heredadas a los commits H20; no reescribir el manifiesto histórico.

Los 2136 archivos H19 pasan la
[auditoría de la base](../evidence/H22-baseline/h19-scoped-integrity-v2.json).
Sus fallos y las diferencias heredadas de H20 permanecen identificados.

## Estado por gate y navegación

| Gate | Estado actual | Evidencia y límite |
|---|---|---|
| A — funcionalidad/lifecycle | PARTIAL | Funcionalidad 38/39 PASS. Mezcla lifecycle, cold resize y los soaks pasan sus barreras funcionales; Goal lifecycle conserva FAIL de cierre: 5403,68 ms frente a 5000 ms, con cleanup completo. |
| B — rendimiento/continuidad | PARTIAL | Simples 1/3/5, Goal1 horizontal, Goal3 vertical, Lower3, Alert3 y mezclas de cinco pasan sus tres repeticiones cortas. Goal3/5 horizontales fallan cadencia. Cold cycles 600 s pasa; mezcla 600 s falla con gaps activos de hasta 465,57 ms. No hay meseta general de memoria demostrada. |
| C — seguridad de terceros | BLOCKED | Mock Keychain sólo LAB; XPC mínimo no acredita CEF confinado. La candidata CEF + App Sandbox falla en Mach bootstrap. |
| D — preparación H23 | PARTIAL | Transporte y contrato OBS aislados pasan; el handoff al graphics owner y las texturas GPU reales siguen pendientes de H23. |

La [cobertura final](../evidence/H22-coverage-final-v2.json) pasa 39/39 casos
ejecutados exactamente una vez; [matriz](../evidence/H22-capacity-final-v2.json):
35 PASS y cuatro FAIL en los gates propios de cada caso. Cadencia tiene 35 PASS,
tres FAIL y un NOT_EVALUATED (cold resize corto, que sí pasa continuidad de
operaciones). Ese PASS de cobertura no acepta H22 ni borra los cuatro fallos.

- [Continuidad y cold replacement](h22-continuity.md): barreras implementadas,
  límites originales y alcance del diagnóstico hot resize.
- [Memoria](h22-memory.md): perfiles por identidad, confusor histórico de
  componentes y contraste final de 600 s (+59,21 MiB, sin meseta demostrada).
- [Seguridad](h22-security.md): CEF fijado, alternativa upstream de namespace,
  XPC, App Sandbox, capacidades por proceso y control de red de laboratorio.
- [Capacidad](h22-capacity.md): resolución/FPS/carga, tres repeticiones,
  resultados PASS y FAIL, hardware observado y admisión de Production en cero.
- [Handoff H23](h22-h23-handoff.md): formato binario, leases, visibilidad,
  revocación, contexto gráfico y trabajo de integración aún necesario.
- [Reproducción](h22-reproduction.md) y [fallos conservados](h22-failures.md):
  comandos, hashes, cambios de instrumento y esperas físicas sin ejecución.


## Instrumentos y contratos verificados

[Contratos r3](../evidence/H22-contracts-r3/summary.json): PASS de Rust, Clippy,
formato, Python, Node, C ABI, diez pruebas de transporte sobre sockets reales y
enlace/validación del adaptador contra libobs 33.0.1. Replay de 140 frames BGRA
Goal entre tres procesos propios, crash 86 y recovery, hashes idénticos y cero
bytes retenidos al cerrar. No conecta CEF vivo a OBS ni crea un segundo motor.

[Snapshots de candidatos](../evidence/H22-build-sources/inventory-v2.json)
conservan fuente propia y hashes sin distribuir CEF. Los binarios finales son
cold4, widgets3 y goal-load3, con política de laboratorio closed-resolver-v2.
[Reproducción](h22-reproduction.md) y [fallos conservados](h22-failures.md)
distinguen errores, slot ocupado, auditorías corregidas y pruebas no ejecutadas.

La [validación consolidada v3](../evidence/H22-validation-index-v3.json) vincula
la regresión completa con las comprobaciones focales posteriores: siete tests
de eventos, seis de integridad/alcance de matriz, cuatro del gate de continuación y
siete de conciliación sin reemplazar FAIL. Identifica los cuatro archivos del
inventario inicial que cambiaron y sus hashes; el índice anterior se conserva.
Los 34 tests H22 iniciales también quedan vinculados. Los helpers de entrega
y los observadores de cierre/heartbeat tienen evidencia de ejecución separada; no se
presentan como parte de una regresión anterior. La fuente de los tres candidatos
nativos sigue coincidiendo con sus
[snapshots inmutables](../evidence/H22-final-native-source-match.json).

## Cierre de la entrega local

Los contrastes separados no borran los FAIL de la matriz: Goal lifecycle cerró
en 94,73 ms, pero volvió a fallar cadencia en un evento; la mezcla repetida
pasó 194 eventos con gap máximo 56,44 ms. Ninguno activó un sample de stack.
El cierre tardío y las pausas de la ejecución original no se reprodujeron en
esos contrastes y **no se declaran resueltos**. [Diagnósticos y errores de auditoría conservados](h22-failures.md).

La [comprobación final de limpieza](../evidence/H22-final-cleanup.json) no
encuentra viva ninguna de las **958 identidades PID/nacimiento** previamente
observadas en 68 informes H22. Los 41 recibos de matriz y diagnósticos confirman
liberación del lock y de la inhibición temporal de idle sleep. Al comprobarlo,
el lock estaba ausente. Ese alcance no excluye procesos nunca observados ni
certifica confinamiento de terceros.

El [inventario final de entrega](../evidence/H22-delivery-inventory.json)
vincula fuentes, documentos, investigación y evidencia local por SHA-256;
verifica el alcance autorizado y la conservación de documentos/evidencia
históricos contra la base. No incluye caches, SDKs o binarios ignorados y no
equivale a publicación, distribución o aceptación de Production.
