# H17 — diagnóstico escalar de la configuración SCK

El fallo B7 de sustitución llega a `startCapture` con error -3812. No conserva
las dimensiones de `SCWindow`, del filtro o de configuración de esa instancia;
por ello no permite elegir una corrección de formato, publicación o lifecycle.
La evidencia y sus límites permanecen en [captura B7](h17-capture-verification.md).

El parche separado
`native/patches/obs-33.0.1-sck-admission-observation.patch` añade una observación
en el camino síncrono de creación, inmediatamente antes de `startCapture` y
solo para captura de ventana. No modifica admisión, configuración, tamaños,
shaders, callbacks, esperas o stop.

La línea `motive_capture_admission` incluye únicamente:

- `created_ns` nativo y PID de Motive, para correlacionar una instancia.
- Window ID y PID del propietario efectivamente encontrados en SCK, junto
  con el PID esperado ya autorizado por Motive.
- Ancho/alto de `SCWindow.frame`.
- `contentRect` y `pointPixelScale` del filtro, bajo disponibilidad macOS 14;
  `filter_geometry=0` significa API no disponible, no un rectángulo observado
  de tamaño cero.
- Ancho/alto configurados, FPS OBS y fracción exacta de FPS configurada
  (inversa de `minimumFrameInterval`).

Los datos del filtro se copian a escalares antes de liberar su referencia;
el log posterior no accede a ese objeto liberado. No se enumeran ni imprimen
otras aplicaciones, títulos, nombres, URLs, buffers de imagen o `userInfo`.
Solo hay una línea por intento de start; no se registra por callback de medio.
No se asigna a una misma cifra un reloj distinto del que declara el campo.
El callback de start conserva su error tipado y omite la impresión duplicada
de `localizedFailureReason`; su decisión y cleanup permanecen iguales.

`scripts/build_obs_capture.py` aplica este tercer parche después de diagnóstico
y admisión, y lo incorpora al stamp. B7 empaquetado conserva sus bytes y la
identidad histórica. Un nuevo binario con esta observación requiere otro
nombre de candidata.

El contrato `verify_h17_sck_admission.py` comprueba que este parche no cambie
las expresiones de admisión, ejecuta las ocho condiciones con libobs real y
ASan y valida sintaxis de la unidad Objective-C completa. Esta comprobación
no abre SCK ni valida geometría real.

Prueba del parche de observación: **PASS** en
`var/evidence/h17-sck-admission-observation-01/report.json`, ejecutada después
de liberar el lease GPUI. Las ocho condiciones mantienen sus resultados;
ASan no reporta errores y la unidad Objective-C completa pasa sintaxis sin
diagnósticos. El verificador confirma igualdad de las expresiones de admisión
antes/después de añadir observación. `py_compile` y `git diff --check` pasan.
No se reemplazó `target/mac-capture-h14/mac-capture.so` ni se reconstruyó B7.

SHA-256 del parche:
`2fe751080f1d560ee5c0e5b3e86ed58523a5c27ac219e33b4e8fe03b57732f17`.

Captura física con el nuevo diagnóstico: **NOT_EVALUATED**. El próximo ensayo
debe ser una sola repetición
acotada del caso de sustitución, comparando los escalares del start inicial y
fallido, sin sleeps ni ajustes de preferencias del usuario.
