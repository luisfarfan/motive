# H17 — GPUI y GPUI Fast

Fecha: 2026-11-18. Estado de evaluación: **PARTIAL**. Backend de producto:
GPUI Kit 0.10.0 / gpui-pre 0.3.12; GPUI Fast sigue desactivado por defecto.
Los gates de comportamiento visual, foco y accesibilidad tienen que pasar
antes de adoptar un backend. Compilar no los acredita.

## Compatibilidad y build

Kit 0.10.0 expone `gpui-fast` y conmuta sus tipos públicos, Base, Component,
assets y plataforma juntos. Motive usa esas reexportaciones, sin dependencias
directas de tipos GPUI. Se añaden únicamente dos features opt-in:

- `gpui-fast = ["gpui-kit/gpui-fast"]`.
- `ui-profiler = ["gpui-kit/profiler"]`.

La primera resolución falló: Fast requiere wgpu `=30.0.1`, mientras el lock
anterior fijaba 30.0.2. `cargo update -p wgpu --precise 30.0.1` resolvió el grafo
sin parchear librerías. El lock fija la familia gpui-fast en **0.1.17**, y
hdrhistogram 7.6.0 para el profiler. Incluye algunas nuevas selecciones de
aristas windows-sys durante la resolución; no se actualiza GPUI Kit ni el
snapshot upstream. wgpu no compila en estos builds macOS/Metal.

Los primeros builds release A y B completaron en 55,85 s y 74 s. Sus logs
están en `var/evidence/h17-gpui/build-a.log` y `build-b.log`; las compilaciones
posteriores con manifiesto son la identidad utilizada por cada benchmark.
`features-a.txt` y `features-b.txt` conservan los árboles de features ARM64.
El grafo B sigue compilando upstream debido a features aditivas; ello no
significa que la ventana esté usando ambos renderers.

Fuentes oficiales consultadas: [Kit v0.10.0](https://github.com/longbridge/gpui-kit/blob/v0.10.0/website/docs/getting-started.md),
[GPUI Fast](https://github.com/longbridge/gpui-fast), y código publicado de
`gpui-kit-0.10.0`, `gpui-pre-0.3.12` y `gpui-fast-0.1.17` en el registro Cargo,
identificado por los checksums de Cargo.lock.

## Notificaciones, dependencias y límites

`Studio::new` conserva el heartbeat de 33 ms. Cada vuelta ejecuta Show Control,
lifecycle y lectura del nuevo preview; una vez por segundo consulta salud,
importaciones e inventario de dispositivos. La notificación final es
incondicional, aun si la secuencia de preview no avanzó. El mismo Studio es
una sola entidad grande: su `Render` construye los paneles y consulta estado
compartido. La mayoría del layout visible no son vistas independientes
retenibles. Que Fast retenga otras entidades no elimina esa reconstrucción.

Hay datos externos al seguimiento de entidades GPUI: snapshots de libobs,
medidores, progreso de operaciones y duración de outputs. Eliminar `notify()`
solo porque no llegó preview dejaría esos datos obsoletos. No se cambia ni el
heartbeat ni Production, ni se adopta un refactor especulativo.

El backend Fast retiene vistas/layout/texto y conserva contenido de scroll;
en su código macOS está habilitado con Metal. Cambios externos a entidades
necesitan notificación explícita. El diagnóstico oficial
`GPUI_VIEW_RETENTION=0` permite aislar retención; `GPUI_SCROLL_LAYERS=0` aísla
las capas de scroll. Estas variables se eliminan del entorno de la prueba
para comparar los defaults. [Retención](https://github.com/longbridge/gpui-fast/blob/main/docs/retained-mode.md),
[scroll](https://github.com/longbridge/gpui-fast/blob/main/docs/scroll-layers.md).

La implementación 0.1.17 conserva nodos AX al reutilizar subárboles y aplica
invalidación AX; sus listas virtuales desactivan la capa cuando accesibilidad
está activa. Esto es evidencia de diseño del backend, no una prueba de
VoiceOver en Motive. Window Composition es opt-in para contenido nativo:
Motive no la activa ni la requiere para el preview. Browser Engine conserva
su decisión independiente.

## Instrumentación reproducible

`ui-profiler` compila un adaptador pequeño a los histogramas oficiales
`Window::frame_duration_snapshot` / `input_latency_snapshot`. Únicamente con
`MOTIVE_UI_PROFILE=1` escribe una línea JSON por segundo a stderr. No genera
otro timer, reloj audiovisual, RPC ni motor de telemetría. Un build por defecto
excluye este módulo completamente.

Distingue duración CPU de `Window::draw`, invalidación→presentación, intervalos
animados, input→frame y tiempo del cuerpo del heartbeat. Estas métricas no
miden fin de trabajo GPU ni latencia captura→pantalla. Los histogramas se
restan para cada intervalo; falta de inputs es `NOT_EVALUATED`, nunca latencia
cero. Registra notificaciones con/sin preview nuevo sin asumir que una
notificación sin preview sea innecesaria. Retiene hasta 128 muestras de
heartbeat entre lecturas y declara cualquier descarte. El muestreo ocurre
antes del render actual: la última fracción antes del cierre no entra en la
última línea, y una ventana sin renders no produce filas.

El collector reutiliza `memory_diagnostics`, `cpu_interval` y `summarize` de
H14 para CPU, RSS, footprint, memoria comprimida, malloc in-use/allocated,
RPC, preview drops y contadores libobs. CPU 100% equivale a un núcleo.
El collector del patrón consulta memoria/estado cada 0,5 s; esas consultas
también pasan por `Studio::command`, que notifica incluso al leer. Ambos
builds reciben la misma carga, pero este resultado no es CPU idle sin RPC.
El lifecycle usa su intervalo existente de 1 s.
No se equipara RSS o memoria reservada con fuga.

Preparación aislada (no abre la aplicación):

```sh
python3 scripts/h17_gpui_benchmark.py prepare --variant a --output var/evidence/h17-gpui/build-a-final
python3 scripts/h17_gpui_benchmark.py prepare --variant b --output var/evidence/h17-gpui/build-b-final
```

Cada preparación conserva hashes de entradas antes/después del build, hash
binario, módulos nativos, versión de Rust/macOS y comandos. Si cambian las
fuentes durante el build, devuelve `BLOCKED` y no prepara un bundle. Los apps
son bundles de desarrollo con firma ad hoc: no son la beta portable ni usan
Keychain/certificados.

Bajo el lock canónico, sin otro owner/build/codificador de fixture en marcha:

```sh
python3 scripts/h17_gpui_benchmark.py run --app RUTA_APP_A --output var/evidence/h17-gpui/pattern-a1
python3 scripts/h17_gpui_benchmark.py run --app RUTA_APP_B --output var/evidence/h17-gpui/pattern-b1
python3 scripts/h17_gpui_benchmark.py run --app RUTA_APP_B --output var/evidence/h17-gpui/pattern-b2
python3 scripts/h17_gpui_benchmark.py run --app RUTA_APP_A --output var/evidence/h17-gpui/pattern-a2
```

Son owners frescos, 1024×780, calentamiento de 5 s y 30 s de muestra, patrón
y overlay propios, mixer vacío y outputs detenidos. No es idle sin preview:
la composición y preview avanzan. El runner confirma PID real del binario y
peer del socket, no carga stores, y solicita cierre normal verificando exit 0.

Para cuatro decoders propios: generar antes de medir con
`verify_h14_memory.py --prepare-fixture RUTA_NUEVA.mp4`, verificar su SHA-256,
y añadir `--workload four-videos --fixture RUTA --fixture-sha256 HASH` a run.
Reutiliza el lifecycle H14 a 1080p60, tres ciclos visibles/ocultos/retirados,
10 s por fase, sin outputs. Conserva el resultado original del harness,
cleanup y todas las muestras. Correlaciona intervalos completos del profiler
con fases por reloj de pared con control de deriva; no mezcla el import con
la fase estable. El p95 por segundo se conserva como tal: la mediana de esos
p95 no se anuncia como p95 de todos los frames.

## Gates de adopción

| Gate | Estado | Evidencia o siguiente paso |
|---|---|---|
| Compilación release A/B ARM64 | PASS | Logs y lock anterior; repetir bindings tras estabilizar fuentes H17 |
| Métricas patrón/preview ABBA | NOT_EVALUATED | Collector listo; requiere lease audiovisual serializado |
| Cuatro videos 1080p60/tres ciclos | NOT_EVALUATED | Lifecycle H14 reutilizado con profiler |
| Scrolling/listas/Live Deck/editor | NOT_EVALUATED | Mismo recorrido nativo en A/B, con filas de perfil y observación |
| Diálogos/popovers/foco/eventos | NOT_EVALUATED | Confirmar clic/Tab/Enter/Escape y estado compartido real |
| Ausencia de pantallas stale | NOT_EVALUATED | Contrastar preview y estados nativos durante interacciones |
| VoiceOver/accesibilidad | BLOCKED | Requiere usuario presente, sin cambiar preferencias personales automáticamente |
| Adopción como default | BLOCKED | No hay todavía evidencia suficiente de mejora y regresiones |

La beta conserva GPUI actual mientras estos gates no estén resueltos.
