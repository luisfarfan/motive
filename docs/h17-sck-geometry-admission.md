# H17 — admisión de geometría de ventana

Estado: **PASS** del contrato offline; captura física con este cambio
**PASS** acotado en el [ensayo independiente B10](h17-capture-verification.md#b10-rechazo-temprano-y-reselección-explícita).
No cierra CAP-01 ni sustituye el FAIL real B9. La tabla inferior conserva
el alcance offline original; el feedback GPUI de este error no se verificó.

## Evidencia y causa

`var/evidence/h17-capture-b9-owner/owner.log` conserva una selección inicial
de 680×452 y una ventana sustituta con ID distinto y el mismo PID propio, con
`SCWindow.frame` de 0×0. La observación del filtro y de la configuración
también era 0×0; `SCStream` terminó con error -3812. El chequeo de ID/PID
permitía admitir la ventana aunque macOS todavía no publicaba dimensiones
utilizables. Véanse el [informe de captura](h17-capture-verification.md) y
la [observación SCK](h17-sck-admission-observation.md), que conservan la
prueba fallida y sus límites.

## Cambio delimitado

El cuarto parche de OBS valida las dos dimensiones del mismo snapshot
`SCWindow.frame`: finitas, al menos 1 y estrictamente menores que el límite
representable de `size_t`. El rechazo ocurre antes de crear el filtro de
ventana, convertir dimensiones a enteros y crear/iniciar `SCStream`.
Las conversiones usan el snapshot validado. La identidad de ventana y
propietario conserva el chequeo existente.

El rechazo marca los settings de esa fuente OBS. `graph.inc` lee la marca
desde el objeto inválido antes de liberarlo, incluso después de liberar los
settings del llamador, y devuelve:

> CAPTURE_NOT_READY: macOS no ha publicado dimensiones válidas para esta ventana. Muéstrala y vuelve a seleccionarla.

La creación siguiente limpia la marca antes de intentar admitir una fuente;
otro fallo de creación conserva `SOURCE_CREATE_FAILED`. No se sustituyen
dimensiones, no se cambia el reloj y no se añade reconexión automática. La
reselección es una acción explícita. El motor conserva su comportamiento
fail-safe existente: la fuente anterior puede haberse separado antes de
rechazar el reemplazo; no se promete conservarla activa.

En la salida temprana se devuelve el semáforo de contenido, se deja el stream
nulo y se inicializa el evento requerido por el destructor existente. Ese
destructor libera configuración, delegado y recursos ya inicializados.
Esta rama no abre ni detiene un `SCStream`; el cierre asíncrono de streams
previamente iniciados no cambia.

`build_obs_capture.py` aplica el parche después de los tres existentes e
incluye tanto el parche como `native/capture-admission.h` en su stamp. El
hash del módulo empaquetado y el snapshot de fuentes identifican el artefacto
posterior; el módulo B9 histórico no contiene esta corrección.

## Verificación offline

Comando: `python3 scripts/verify_h17_sck_admission.py --output var/evidence/h17-sck-geometry-01`.
Evidencia: [report.json](../var/evidence/h17-sck-geometry-01/report.json),
[geometry.log](../var/evidence/h17-sck-geometry-01/geometry.log) y
[cargo-check.json](../var/evidence/h17-sck-geometry-01/cargo-check.json).
El reporte conserva SHA-256 de los inputs y comandos exactos.

| Verificación | Resultado y alcance |
|---|---|
| Admisión previa | PASS del test: upstream reproduce seis fallos esperados; las ocho condiciones parcheadas pasan con libobs real. |
| Geometría y traspaso del error | PASS, 22 casos con libobs real y helpers de producción; caller settings liberados antes de consultar el error en el shell inválido. |
| Valores límite | PASS para cero, negativos, subpíxel, NaN, infinitos y extremos de `size_t`; dimensiones válidas llegan al cast bajo UBSan/float-cast-overflow. |
| Settings reutilizados | PASS: rechazo de 0×0 seguido de admisión de 680×452 limpia la marca; otro fallo de creación conserva error genérico. |
| Liberación del contrato | PASS: cinco instancias válidas y cinco destructores; barrera real `OBS_TASK_DESTROY`; sin errores ASan/UBSan. |
| Orden del guard y cleanup | PASS de inspección automatizada del fuente real parcheado: guard antes de filtro/cast/stream y salida temprana con semáforo/evento. No equivale a ejecutar el destructor SCK. |
| Unidad Objective-C completa | PASS de `clang -fsyntax-only` del fuente con los cuatro parches. |
| Integración del motor | PASS, `cargo check --locked --release`, exit 0, 9,15 s. |
| Captura/reselección real y feedback UI | NOT_EVALUATED en este contrato; requieren el candidato empaquetado y prueba independiente del owner. |

El campo por caso `post_geometry_reached` del reporte expresa si el contador
posterior coincide con lo esperado, no si se ejecutó esa rama: es true tanto
para un rechazo correcto como para una admisión correcta. El total registra
seis entradas (cinco fuentes válidas y un fallo ajeno posterior al guard);
ninguna geometría inválida llega a ella. No se abrió Motive, video, audio,
SCK ni dispositivos durante este contrato. Los valores son sintéticos y la
semántica de creación/settings/destrucción pertenece a libobs real.
