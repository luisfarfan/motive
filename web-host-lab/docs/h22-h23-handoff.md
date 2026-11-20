# H22 → H23 — transporte y adaptador OBS aislados

Este handoff prepara código y contratos. **No autoriza ni acredita integración
con Production.** CEF con credenciales reales y contenido de terceros continúa
BLOCKED. H23 necesita un acuerdo explícito con el owner de Production y resolver
ese gate antes de una aceptación de producto. No se modifica captura, Show
Control, el reloj multimedia ni el motor existente.

```text
OnPaint CEF → copia completa → mailbox del host → worker Sender
  → socketpair privado, HMAC, deadline → worker Receiver → mailbox del owner
  → admisión existente + barrera del graphics owner → Source::Upload/Draw
  → textura del contexto OBS existente → referencias en escenas existentes
```

Las primeras piezas se verifican separadamente. El replay usa bytes reales
retenidos de CEF, sin CEF vivo conectado al socket. El adaptador llama a APIs
reales libobs y compila/enlaza contra 33.0.1, pero aquí no crea un graphics
context ni prueba texturas GPU o salida codificada.

## Transporte binario implementado

[`poc/frame-transport`](../poc/frame-transport/) es un crate independiente,
sin CEF, OBS ni red pública. Reutiliza `Identity`, `Viewport`, `Mailbox` y
`Lease` de H19. Un socketpair por grant inmutable; no rutas de socket elegidas
por paquete. El owner crea 48 bytes aleatorios: 32 para HMAC-SHA256 y 16 de
nonce. Bootstrap por descriptor privado heredado, longitud exacta y EOF,
deadline 1 s; nunca argv, variables de entorno, archivos, logs o MCP.

El launcher H23 debe verificar ejecutable/inventario y PID/nacimiento, heredar
únicamente los descriptores necesarios y cerrar copias. El endpoint marca
CLOEXEC antes de crear helpers. Una firma HMAC demuestra posesión de la clave;
no confina un host comprometido ni valida semánticamente sus píxeles.

| Offset | Bytes | Campo little-endian |
|---:|---:|---|
| 0 | 8 | Magic MTVBGRA1 |
| 8 / 10 / 12 | 2 / 2 / 4 | Versión 1, flags 1, longitud 88 |
| 16 | 16 | Nonce de lanzamiento |
| 32 / 40 / 48 / 56 | 8 cada uno | Instance, generation, epoch, secuencia estricta |
| 64 / 68 / 72 / 76 | 4 cada uno | Width, height, stride, longitud del payload |
| 80 / 84 | 4 cada uno | Formato 1: BGRA8 premultiplicado sRGB; reservado cero |

Después del header: tag de 32 bytes con dominio `MOTIVE-H22-HEADER\0`, payload
completo, tag de 32 bytes con dominio `MOTIVE-H22-BODY\0` que vincula header y
payload. Se autentica el header antes de interpretar longitudes o reservar
memoria. Se compara con el grant local, incluidos todos los campos/reservados;
el payload se publica sólo tras autenticarlo. El canal acepta **stride packed
width×4**; stride padded se rechaza explícitamente, no se reinterpreta.

Dimensiones positivas ≤1920 y bytes ≤1920×1080×4; epoch/generation/instance no
cero; secuencia creciente. El canal no transporta PTS: la observación de edad
pertenece al owner receptor y nunca gobierna el reloj audiovisual. Cada frame
tiene un deadline absoluto, máximo configurable 2 s, no renovado por paquetes
parciales. El poll no modifica SO_RCVTIMEO de un socket Darwin desconectado.
Se solicitan buffers socket de 64 KiB; el kernel determina su reserva efectiva.

Un error de autenticación/layout/replay/EOF/deadline revoca permanentemente el
receiver y su generación. Los bytes de un lease viejo siguen vivos hasta su
release, pero pierden autoridad para subir/dibujar. Recovery crea socket,
nonce/clave, generación y mailbox nuevos; no reetiqueta frames ni replaya eventos.

Sender usa un lease existente en un worker y no mantiene cola. Receiver publica
en el mailbox de último frame completo, con coalescing y un solo consumidor;
`FRAME_BUSY` es un descarte explícito y la secuencia avanza. La cota de memoria
transitoria es hasta cuatro frames en el receiver, más el productor, buffers
del kernel y textura. El owner debe admitir el número agregado de canales y
su presupuesto antes de crearlos; la cota por frame no equivale a cuota global.

## OBS: contrato compilable y ownership

[`adapter.hpp`](../poc/obs-adapter/adapter.hpp) y
[`adapter.cpp`](../poc/obs-adapter/adapter.cpp) reciben el **contexto existente**.
Create, Upload, Draw, revocación, visibilidad y Destroy deben ejecutarse
serializados por ese graphics owner. Un contexto distinto rechaza la operación;
Destroy conserva el puntero para que el owner pueda reintentarlo en su contexto.
No hay `obs_startup`, segundo compositor, threads audiovisuales ni plugins
registrados automáticamente.

`Frame` es una vista C++ confiable dentro del proceso, no el decoder IPC.
El caller fija los bytes inmutables durante Upload y conserva el lease.
La subida valida grant, secuencia, edad, tamaño y stride antes de crear/mapear
GS_BGRA dinámico. Copia cada fila respetando el pitch real de destino; no guarda
el puntero. Falla cerrado si map/pitch falla. `Uploaded` significa envío al API,
no un fence GPU ni un frame codificado. Completar/liberar el lease después de
esa llamada sigue siendo responsabilidad del owner.

Draw usa el efecto default prestado por OBS, muestreo sRGB, blend
ONE/INVSRCALPHA y restaura blend/framebuffer-sRGB. No usa el efecto que divide
por alpha. La elección corresponde al camino público CPU de
[obs-browser fijado](https://github.com/obsproject/obs-browser/blob/08a0ada1d77b7003735823ff07cf1be1fb427ac1/obs-browser-source.cpp#L598),
con [hash conservado](../research/h22-obs-source.json).
No se afirma que la corrección cromática esté probada en una salida GPU aquí.

Visibilidad es el **total de referencias visibles** de todas las escenas.
Ocultar una referencia no debe suprimir otras. Cero referencias invalida la
imagen admitida; mostrar requiere frame nuevo, sin replay. Un estático sano
puede repetir su textura explícitamente; un animado expira por edad del owner.
Revocar es terminal, y la nueva geometría exige Source/grant nuevos.

## Barreras que H23 debe conectar

1. Registrar el inventario propio mediante el manager existente; conceder una
   identidad y capacidad admitida. H22 no crea otra API de eventos ni de permisos.
   El driver LAB de Goal incluye una celebración inicial por identidad para
   verificar render. No es política de producto: H23 debe arrancar idle y usar
   eventos explícitos del owner, sin copiar el autotrigger ni los enums de fixture.
   El ensayo de recovery no acredita por sí solo ese arranque genérico quieto.
2. Lanzar el host con supervisor y bootstrap privado. El worker de transporte
   adquiere/envía/libera; jamás hacer I/O de socket o esperar CEF desde OnPaint
   o desde el render OBS. MCP sólo controla, nunca lleva video.
3. Conectar la admisión `Upload/Repeat/Blank` de H19 al graphics owner existente.
   El mailbox H19 usa mutex para completion/revocation/drop: **no es una API de
   render hard-real-time certificada**. H23 debe establecer un handoff acotado
   que mantenga bytes vivos y difiera el accounting al worker, o demostrar el
   presupuesto del mecanismo elegido. Este acoplamiento no está implementado
   por convertir `Frame` en una vista C++.
4. Serializar revocación con subida/draw. Antes del reemplazo: blank inmediato
   de la autoridad vieja, cierre CEF asíncrono, OnBeforeClose, join del consumer,
   cero leases/contexto liberado y creación de generación nueva en otro turno
   UI. No ejecutar Create dentro de OnBeforeClose ni habilitar WasResized hot.
5. Ante crash del renderer compartido, revocar su dominio afectado; si el owner
   no conoce la asignación, adoptar el dominio conservador del host. Ante
   crash/EOF del host, revocar todos sus canales y observar reap PID/birth antes
   de recuperar. Ningún ACK JS sustituye esa observación.
6. Destruir texturas/Source en el contexto correcto antes de destruir ese
   contexto. Esperar barriers de workers fuera del render, liberar leases y
   verificar el cierre propio. No destruir procesos ajenos por nombre.

## Evidencia y aceptación

Diez tests de transporte pasan sobre sockets kernel: tampering, campos no
concedidos antes de allocation, replay con lease vivo, fragmentación/EOF,
slow writer con deadline total, backpressure, 100 frames coalescidos, bootstrap
y límites. El [replay entre procesos](../evidence/H22-contracts-r2/replay-provenance.json)
transportó 140 frames BGRA reales de Goal, 921.600 bytes/frame, hash idéntico,
crash 86 y recuperación con tres claves/canales nuevos. Tres hijos reaped y
cero bytes retenidos al cerrar. No es un benchmark de CEF→OBS ni de streaming.

La [verificación inicial](../evidence/H22-contracts-r1/) conserva tests Rust,
Clippy, Python y C ABI heredados; el primer formato de Goal y el directorio
faltante del runner conservan sus fallos. La
[verificación focalizada](../evidence/H22-contracts-r2/summary.json) confirma
formato y replay corregidos sin repetir pruebas ya válidas. El adaptador
compila/enlaza con libobs real; su test es validación de campos y rechazo de
contexto nulo, **sin mocks de GPU ni PASS de texturas**.

La [regresión final r3](../evidence/H22-contracts-r3/summary.json) pasa los
contratos heredados, diez pruebas de transporte, Clippy, formato, compilación/
enlace OBS y otro replay de 140 frames entre tres procesos cerrados. La suite
heredada incluye 32 tests Rust del host, siete del bridge, 132 Python, 13 de
seguridad y los contratos C ABI/Node; 34 tests H22 pasan también por separado.

El host de ensayos conserva como máximo 32 registros de creación por ejecución;
los soaks acotados no prueban churn ilimitado. H23 debe admitir las operaciones
antes de revocar una fuente y definir el agotamiento/reinicio de historiales
dentro del manager; no trasladar literalmente el driver de escenarios al producto.

D queda **PARTIAL para integración**: transporte y adaptador aislados listos
para revisión, acoplamiento no bloqueante al graphics owner pendiente de H23,
y seguridad de despliegue bloqueada. También quedan por resolver el cierre
Goal de 5403,68 ms y los stalls tardíos de la mezcla de 600 s: las barreras
cold y el contrato de transporte no los corrigen por sí solos. H23 necesita escenas reales compartidas,
alpha/color decodificado, movimiento/cadencia, cancelación/recovery/cold resize,
soaks con capture+encoder y cierre completo del único motor. La matriz CEF no
certifica fluidez del juego o transmisión ni suma capacidad automáticamente.
