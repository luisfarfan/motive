# H17 — admisión estricta de captura SCK

Estado: **PARTIAL** de aceptación de captura; **PASS** del contrato de
admisión descrito aquí. No se ejecuta una captura física en esta prueba ni se
declara resuelto el congelamiento o la suspensión histórica.

## Defectos comprobados en OBS 33.0.1

`plugins/mac-capture/mac-sck-video-capture.m:init_screen_stream` devolvía
`true` cuando la enumeración no contenía la ventana solicitada. También
devolvía `!did_add_output` dentro de las dos ramas donde `did_add_output`
era falso. `sck_video_capture_create` interpretaba esos tres resultados como
éxito y devolvía una instancia sin captura válida. Por ello el guard B6
`obs_obj_invalid` no podía detectar esos casos: el callback no había fallado.

Además, la enumeración del plugin comparaba únicamente Window ID. El núcleo
ya verificaba Window ID y owner PID antes de crear, pero esa observación no
protegía la enumeración posterior del plugin contra un cambio de identidad.
No se ha demostrado que esa carrera explique la toma B6; es un defecto de
admisión identificable en el código, separado de la suspensión posterior.

## Cambio limitado

`native/patches/obs-33.0.1-sck-admission.patch` se aplica después del parche
diagnóstico, sobre copias en `target/mac-capture-h14/source`. La verificación
de archivo fijado y el SHA-256 del tarball permanecen. El stamp del build
incluye los dos parches.

- Ventana ausente: retorna fallo y el callback create devuelve NULL.
- Se transmite `motive_window_owner_pid` desde la identidad ya autorizada por
  el núcleo. Si el setting es distinto de cero, el plugin exige coincidencia
  exacta del PID y Window ID. Un propietario ausente no satisface el PID.
- Fallo al registrar output de pantalla o audio: retorna fallo. Se libera y
  pone a NULL el stream cuya captura nunca se inició, sin solicitar stop.
- Los dos `NSError **` de registro no se liberan: el llamador no es su dueño.
  Los logs de esas ramas conservan solo tipo de output, código y pertenencia
  al dominio SCK, sin texto de aplicaciones.

La regla de ownership de `NSError` devuelto por referencia está documentada
por [Apple](https://developer.apple.com/library/archive/documentation/Cocoa/Conceptual/MemoryMgmt/Articles/mmRules.html).
El header SDK de `SCStream` declara `addStreamOutput:...error:(NSError **)`.
No hay alloc/copy/retain de ese error en el llamador. El destructor de eventos
OBS contiene el guard `if (event)`; el caso de create fallido con evento NULL
es admitido por ese destructor.

No se cambia filtrado de ventanas de terceros, `collectionBehavior`, buffers,
timestamps, manejo de superficies, callback de stop ni lifetime de sesiones
arrancadas. El setting de PID queda fijo durante la instancia: cambiar la
identidad requiere la recreación explícita que ya utiliza el núcleo. La
compatibilidad del plugin sin ese setting conserva su selección por Window ID;
Motive siempre lo proporciona para una fuente de ventana.

## Evidencia reproducible

```sh
python3 scripts/verify_h17_sck_admission.py \
  --output var/evidence/h17-sck-admission-new
```

El verificador comprueba el tarball fijado y los archivos de origen, aplica
los mismos dos parches en un directorio exclusivo y extrae las expresiones
reales de retorno/selección de ambas variantes. Las condiciones de entrada
son sintéticas. Esas expresiones se compilan en un contrato C que usa creación,
`obs_obj_invalid` y destrucción reales de libobs con AddressSanitizer; no
invoca SCK, WindowServer ni dispositivos. En otro paso compila con
`-fsyntax-only` la unidad Objective-C completa parcheada, validando el setting,
el miembro del struct y la propiedad pública de identidad.

Resultado final: `var/evidence/h17-sck-admission-03/report.json`, **PASS**.
SHA-256 del parche:
`1c9963f1a6ddddbd36099c78fe7fa1e4739063c2c4fdffd3a99869e7a10ee5cc`.

| Condición del contrato | Upstream | H17 |
|---|---|---|
| Ventana ausente | FAIL | PASS |
| Fallo de registro de output screen | FAIL | PASS |
| Fallo de registro de output audio | FAIL | PASS |
| Mismo Window ID y PID distinto | FAIL | PASS |
| Identidad exacta | PASS | PASS |
| Setting PID ausente, compatibilidad del módulo | PASS | PASS |
| Window ID distinto | FAIL | PASS |
| Owner ausente con PID exigido | FAIL | PASS |
| Destrucción de todas las instancias admitidas | PASS | PASS |
| Sintaxis de la unidad Objective-C completa | NOT_EVALUATED | PASS |
| Captura física / frames decodificados | NOT_EVALUATED | NOT_EVALUATED |

Upstream admite ocho instancias; el contrato cuenta seis admisiones incorrectas.
H17 admite únicamente los dos controles válidos. Las ocho/dos instancias
admitidas se destruyen respectivamente; no aparece un error ASan. Esta prueba
no ejecuta el cleanup real de SCStream ni acredita ausencia de carreras en
sus callbacks.

Se conserva `h17-sck-admission-01/`: el primer harness falló al compilar por
omitir `-I native`, necesario para `obsconfig.h`; no llegó a ejecutar el
contrato. `-02` pasó antes de corregir el ownership del NSError y reducir los
logs; `-03` corresponde al parche final. No se presentan esos fallos del
instrumento como fallos físicos de captura.

## Riesgo y aceptación pendiente

El comportamiento visible cambia de una fuente aparentemente creada que no
captura a `SOURCE_CREATE_FAILED`. Una admisión exitosa continúa sin probar
frescura visual. El contrato no resuelve suspensión después de crear, cambio
de foco, minimización, reapertura ni recuperación con outputs activos.

El nuevo bundle debe verificar la ventana propia identificada, las fases de
foco corroboradas, el estado SCK y píxeles decodificados de MKV/RTMP, además
del cierre. Esos gates permanecen **NOT_EVALUATED** en este informe, y los
FAIL históricos de captura conservan su efecto sobre la aceptación de beta.
