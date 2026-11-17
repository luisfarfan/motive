# Show Control — verificación independiente

Fecha: 2026-11-17. Base H12: `b52d135`. Worktree independiente
`motive-show-control`, rama `feature/motive-show-control`. El alcance es el crate
Rust, sus fixtures y un prototipo de presentación. **No es una prueba de producción
en vivo ni una aceptación multimedia de H13.**

## Resultado reproducible

`python3 show-control/verify.py` terminó con **93 tests Rust aprobados y 27 comandos
de verificación correctos**, incluyendo Clippy `--all-targets -- -D warnings` y
`cargo fmt -- --check`. Cargo.lock está fijado y todas las invocaciones usan
`--locked`. El script no inicia Motive ni solicita permisos.

El [manifest de evidencia](../evidence/verification.json) registra comandos,
códigos de salida, duración de las herramientas y SHA-256 de fuentes, tests,
manifiesto, lockfile y fixtures. Las duraciones no son un benchmark de producción.
No se midió CPU/RSS del motor, no se grabó video y no se atribuyen mejoras de
rendimiento a esta tarea. Los logs completos están en `evidence/`.

| Suite Rust | Tests | Cobertura |
|---|---:|---|
| contracts | 17 | 13 eventos, schemas cerrados, UTF-8, límites, parámetros nativos, secuencias, errores, PID/revisión, fuentes y escena vacía |
| runtime | 14 | Condiciones encadenadas, confianza, debounce/cooldown/rate, orden temporal, dedup, escenarios, fallo parcial, overflow, ciclos, checkpoint/migración y bindings del pack |
| runtime_adversarial | 30 | Prioridad/FIFO, cola atómica, incertidumbre, cancelación/reconciliación, tokens de otro proceso, stale, historial, journal lleno, replay y referencias |
| providers | 8 | Ingreso exclusivamente sintético, dinero sin floats/redondeo, 10.000 muestras, unidades de plataforma, backoff y cursores opacos |
| packs | 12 | Tres manifests, referencias, propiedades transaccionales, capacidades, recursos prohibidos, límites de texto/geometría/animación y nombres |
| deck | 7 | Botones/atajos/grupos, confirmación, cooldown, historial, reloj, pendientes y cancelación |
| cli | 5 | Cuatro escenarios, cargar archivos, propuestas del pack, ocho botones y schemas de todos los ejemplos |

Las pruebas de propiedades son barridos deterministas de límites y muestras
propias; no se declara fuzzing continuo ni un corpus externo.

## Recorridos ejecutados

| Recorrido | Resultado observado | Evidencia |
|---|---|---|
| Gol | Regla `goal-celebration`; plan `overlay_event:trigger`; sonido `CAPABILITY_UNAVAILABLE`; contador=1; duplicado rechazado; segundo evento bloqueado por cooldown | [goal.json](../evidence/goal.json) |
| Donación | `5.00 USD` sintéticos normalizados a 500 unidades menores; alerta planificada; texto preparado, sin síntesis ni audio | [donation.json](../evidence/donation.json), tests providers |
| Chat | Usuario sin autorización no genera job; creador autorizado solicita Fade a BRB; segundo pedido bloqueado por cooldown | [chat.json](../evidence/chat.json) |
| Ráfaga | Capacidad 4; cuatro rechazos por cola llena y un duplicado; cancelación antes de ejecutar; planes de alertas en orden urgente/FIFO y después normal | [burst.json](../evidence/burst.json) |
| Definición cargada | Configuración, eventos JSONL y MATCHDAY cargados; referencias verificadas; misma regla y planes del núcleo independiente | [loaded-pack-definition.json](../evidence/loaded-pack-definition.json) |
| Deck | Ocho botones producen jobs simulados; BRB sin confirmación retorna error; reglas manuales no pueden suplantar voz/chat | `deck-*.json`, [rechazo](../evidence/deck-confirmation-required.log) |
| Packs | Tres manifests válidos; planes no ejecutables; ambos layouts y recursos declarativos dentro de límites | `pack-*.json` |
| Reinicio | IDs consumidos y counters restaurados; cooldown relativo al nuevo reloj; pendientes cancelados; aceptados inciertos; ninguna repetición automática | tests runtime/runtime_adversarial |

Todos los informes de ejecución declaran `simulation_only` y
`live_commands_sent:0`. Los snapshots del simulador derivan de fixtures, no de una
segunda instancia de Production. No prueban que se haya mostrado un frame nativo.

## Fallos conservados y correcciones

La revisión adversarial reprodujo dos fallos en una tanda de 24 tests: 22 pasaron
y 2 fallaron. Una acción local actualizaba la revisión esperada antes de una acción
multimedia; un nombre de contador válido para la acción no era restaurable por el
checkpoint. Ambos se corrigieron y sus regresiones pasan.

Otra tanda reprodujo 29 aprobados/1 fallido: dos escenas podían declarar el mismo
símbolo de capa, reduciendo 23 referencias a 22 al construir el snapshot. El formato
ahora exige IDs globalmente únicos. También se cubrió el caso de Deck sin regla
coincidente, que debe mostrar rechazo, nunca éxito simulado.

La revisión encontró además un código de busy que no aplazaba, recorte de historial
durante el procesamiento de eventos hijos y riesgo de observar/cancelar un token
nativo reutilizado por otro proceso. Las regresiones se añadieron después de
corregirlos; no se afirma haber observado crashes nativos. Ver
[auditoría de seguridad](security.md) para los límites de cada prueba.

## Evidencia visual

Se inspeccionó el HTML independiente mediante proxima-browser a 1440 y 390 px:
sin overflow horizontal, siete previews visibles cargados, sin errores de consola
ni requests externos. Se ejercitaron gol, confirmación, cancelación y sonido
deshabilitado. El servidor temporal de loopback y el navegador se cerraron.

- [Captura escritorio](../design/preview-desktop.png)
- [Captura móvil](../design/preview-mobile.png)
- [Prototipo HTML](../design/index.html)

Los nueve SVG se generan de los manifests con un renderer de documentación.
Aproximan tipografía, layout y estado de widgets; no son recordings nativos ni
assets importables por H12. No se copió el diseño de Claude ni recursos comerciales.

## Estado de entrega y límites

| Categoría | Entrega |
|---|---|
| Implementado y verificado | Crate independiente, eventos, reglas, cola, preparación tipada, simulador CLI, checkpoints, Deck, normalización sintética y validación/planificación de packs |
| Prototipo | Presentación HTML, previews SVG, interacciones visuales; Creator Tech y Neon Arena son conceptos menores |
| Contrato preparado | Adaptador futuro del owner, etapas/operaciones, proveedor y reintentos limitados, bindings simbólicos, modelo de Deck |
| Integración pendiente | Production real, GPUI/MCP principal, receipt de revisión propia, journal durable antes de dispatch, importador con IDs reales y evidencia audiovisual |
| Fuera de alcance | STT/VAD real, TTS, soundboard, OAuth/conexión de cuentas, capturas, nube, plugins, multistream y emisiones públicas |

Las fuentes ausentes o recuperándose no se recrean. Una recuperación con revisión
nueva necesita una intención nueva explícita. La revisión de admisión se conserva
incluso después de una mutación propia: para secuencias en vivo hará falta el
contrato de receipt descrito en [integración](integration.md). Un comando aceptado,
un timeout o una petición de cancelación no demuestran terminación nativa.

La política de eventos fuera de orden es conservadora y puede descartar entregas
legítimas tardías; cada conector real deberá acordar una política explícita. Los
journals son acotados y fallan cerrados al llenarse. Checkpoint no equivale a
persistencia transaccional automática ni garantiza exactly-once entre crashes.
Los metadatos de media de un pack se validan como declaraciones, no se abren ni se
decodifican archivos. Capacidades disponibles son el contrato H12, no detección de
un runtime. Los límites de hardware anteriores continúan sin nuevas afirmaciones.

## Aislamiento y siguiente incremento

Todos los cambios están bajo `show-control/`. No se modificaron Cargo.toml raíz,
build.rs, core/engine/output/audio/scene, GPUI, native, proyecto v4 ni originales de
Claude Design. Se conservaron los tests existentes del repositorio; no se ejecutaron
las regresiones físicas H1–H12 porque H13 posee el bundle y esta tarea debía ser
independiente. No hubo push, merge, rebase, release o cambio global del sistema.

Tras estabilizar H13, integrar primero show/hide/trigger de fuentes existentes y
un Cut/Fade mediante un adaptador armado localmente, ejecutado por el mismo owner.
Verificarlo en grabación/RTMP local, con concurrencia UI/MCP, fallos y reinicio.
Solo después abordar el tap del mixer y voz local, conectores autenticados,
soundboard/TTS y un instalador de packs. El [roadmap documental](research.md)
identifica APIs oficiales, privacidad, scopes y mediciones necesarias.
