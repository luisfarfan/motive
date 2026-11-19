# H19 — un host compartido para contenido propio revisado

La candidata medida es **B**, un proceso host AppKit/CEF con varios CefBrowser,
contextos en memoria distintos, orígenes por instancia/generación e inventarios
cerrados. La política **C** conserva agrupación por confianza: solo contenido
propio revisado comparte host. Terceros siguen bloqueados; un host separado por
tercero tampoco demostraría por sí solo su confinamiento. No se mantiene un
segundo motor y no se activa pooling de browser/context/heap.

## Evidencia que decide la dirección

El control nativo con el binario H18 congelado observó 656.86 MiB RSS para un
host. Los primeros diagnósticos H19, de cinco segundos, observaron 658.92,
925.58 y 1192.41 MiB para 1/3/5 widgets en un host. Son señales de escalado,
no capacidad sostenida. Los resultados repetidos finales se separan en
`h19-results.md`; no se reetiquetan estos diagnósticos.

| Alternativa | Qué comparte | Evidencia / decisión |
|---|---|---|
| A: árbol por widget | Instalación CEF en disco y posibles páginas OS | Baseline H18: tres casi agotan 2 GiB; cinco fallan. Conservar opción de lanzar hosts separados; no repetir cinco árboles. |
| B: varios browsers | Browser, GPU, red, almacenamiento, distribución CEF | Prototipo real elegido para pruebas propias. Cada widget tiene contexto/origen/mailbox/identidad/lifecycle; compartir servicios amplía dominio de fallo. |
| C: grupos de confianza | Infraestructura solo dentro de cada grupo | Política conservada sobre B/A, no otro motor permanente. No hay autorización ni sandbox suficiente para terceros. |
| D: pooling selectivo | Heap/browser/context retenidos entre instancias | Desactivado. Reinicio exige final-close y contexto/origen/generación nuevos. Un servicio Chromium que permanece vivo no implica pooling autorizado por Motive. |

## Ownership y límites reales

`Host` inicializa CEF una vez, mantiene instancias visuales y solicita quit solo
cuando todos los browsers cerraron. Cada `State` contiene instance, generation,
browser ID, PID renderer observado, origin, contexto, inventario, binding de
Goal cuando corresponde, mailbox, consumer, visibilidad, salud y epochs.
Los PIDs declarados desde código nativo del renderer se cotejan con identidades
PID/birth del supervisor; no son autoridad proporcionada por HTML.

`OnBeforeClose` borra el browser, revoca frames, une el consumer y libera mailbox,
binding y RequestContext. El host conserva como máximo **32 registros históricos
de creación** para evidencia; este laboratorio no es un manager ilimitado de
sesiones. La estructura conserva diagnósticos acotados, no heaps/browsers para
reuso. Los procesos Chromium compartidos pueden seguir vivos mientras queda
otra instancia; cierre de widget y cierre de árbol son recibos distintos.

Un fallo de renderer revoca inmediatamente todos los estados con ese PID. Si la
asignación de un estado es desconocida, se lo incluye conservadoramente en el
dominio afectado. El cierre CEF se difiere fuera del callback de terminación.
Los pares con PIDs distintos siguen activos. Pruebas puras verifican la regla;
solo un caso con PID realmente compartido podría demostrar ese escenario nativo.
No se exige ni promete a Chromium un proceso separado por widget.

Resize en caliente usa `WasResized` con un nuevo mailbox/epoch y solo geometrías
no usadas antes en ese browser. La callback UI admite dimensiones exactas y el
browser original. A→B→A se rechaza: exige reemplazar browser con generación
nueva. No se presenta esta restricción como una barrera CEF general. El contrato
H20 conserva reemplazo frío hasta resolver esa ambigüedad de forma general.

## Coste de memoria y pipeline

OnPaint copia BGRA completo dentro de su lifetime. Alpha/stride/dimensiones e
identidad se conservan; nunca se retiene el puntero CEF. El máximo lógico por
mailbox sigue siendo un frame pendiente, un lease y una copia transitoria.
Coalescing reemplaza una imagen completa: no se introducen parches de dirty
rectangles que pierdan actualizaciones cuando se descarten frames intermedios.
No hay IOSurface/Metal zero-copy ni texturas/libobs en este host.

La nueva telemetría distingue aceptado, pendiente, adquirido, reemplazado por
coalescing, obsoleto, invalidado al cerrar, revocado por generación, consumido y
liberado sin consumo. Adquirido es una transición, no un destino final adicional.
Se mide duración/bytes de la copia a un Vec con capacidad reservada; incluye
coste temporal y fallos de página, no un benchmark aislado de libc memcpy.
El consumer registra aparte intentos y escrituras terminadas, rechazos de
completion y truncamiento real de su límite de telemetría. Su disco no es OBS.

El análisis de regiones usa exclusivamente metadatos de `PROC_PIDREGIONINFO`
sobre PIDs atribuidos por el supervisor. Distingue COW/private/shared/alias y
reserva virtual; no lee memoria ni rutas. Renderers alcanzaron el límite de
8192 regiones por extensas reservas vacías: el desglose queda PARTIAL. Sumar
regiones compartidas o restarlas de RSS no produce memoria física única.
Los buffers propios tampoco contabilizan V8, cachés, superficies OSR, GPU,
allocator ni futuras texturas. La recuperabilidad se observa tras lifecycle,
no se deduce de una caída aislada de RSS ni de cien procesos nuevos.

## Separación de producto

El launcher solo acepta escenarios, counts y viewports compilados. No admite
URLs, paquetes arbitrarios, scripts ni flags de Chromium. Inventario inmutable,
cookies deshabilitadas por API CEF, permisos rechazados y CSP son controles
adicionales; no sustituyen confinamiento OS. Backend Keychain mock permanece
explícito en cada build/report de pruebas y no es configuración de distribución.

El supervisor conserva 2 GiB RSS, deadlines, PID+birth y muestreo durante cleanup,
con overshoot explícito. No mata por nombre. Su control de procesos observados
no impide una fuga hostil no observada. Production, audio web y la conexión
libobs permanecen fuera del laboratorio. Ver `h19-security.md`,
`h19-distribution.md` y el contrato compilable `h19-h20-contract.md`.
