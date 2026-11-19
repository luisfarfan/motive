# H20 — fiabilidad de captura para producción personal

Estado: **EN CURSO; PERSONAL STREAM READY no aceptado**.
Fecha de revisión: 2026-11-18, America/Lima. Este hito no acepta una beta pública.

## Base y ownership

- Rama `codex/h20-capture-reliability`, worktree `motive-h20`, creada desde
  `main`/`origin/main` `549d63f1a01625947ef1dfcea1609ab5c0a5295a`.
  `git ls-remote origin refs/heads/main` confirmó ese mismo SHA antes de crearla.
- H17 B10 y sus fallos son la referencia; los resultados históricos se conservan.
- H20 posee sus cambios en captura, núcleo, adaptadores UI/CLI/MCP y sus pruebas.
  La solicitud del propietario autoriza esta evolución de Production. No autoriza
  integrar Browser Host ni cambiar el worktree, rama o ejecución de H19.
- H19 permanece en `motive-h19`, `codex/h19-browser-hardening`. Su contrato
  `web-host-lab/docs/h19-h20-contract.md` se leyó allí en modo de solo lectura.
  El nombre H20 de ese documento describe una futura integración de browser;
  **no es el alcance del presente H20 de captura personal**.
- No editar `web-host-lab/`, `creator-runtime-lab/`, `element-lab/`, `show-control/`
  ni la copia de Claude Design. No merge, rebase, push, publicación ni cambios
  globales. Un futuro handoff de Browser Host debe reconciliar explícitamente
  `src/core.rs`, `src/scene.rs`, `src/engine.rs`, `src/control.rs`, `native/engine.m`,
  `native/graph.inc`, `build.rs` y los contratos de mensajes.
- Recursos físicos y compilación: lock único derivado de `git --git-common-dir`,
  `motive/var/run/physical-test.lock/OWNER`; nunca un lock por worktree. Detectar
  primero ensayos/builds existentes, adquirir con mkdir exclusivo, conservar
  token/PID/inicio/worktree, y liberar únicamente el owner propio tras cleanup.
  Se observaron procesos CEF de H19 durante la revisión; no se inició compilación
  ni captura concurrente. Lock ausente por sí solo no acredita Mac disponible.

## Orden de ejecución y gates

1. **CAP-01 / contraste:** fijar OBS 33.0.1, HEAD upstream y parches H17;
   comparar fuente original, instrumentación observacional y candidata Motive
   con la misma fixture externa, configuración y foco A→B→A corroborado.
   Medir productor, callback/superficie SCK, consumo/render OBS y píxeles
   decodificados por separado. Conservar ensayos fallidos.
2. **Capture Engine:** Display (UUID explícito), Application (bundle único más
   display explícito), Window (bundle/título persistentes más ID/PID runtime).
   Reutilizar `screen_capture` oficial y las escenas existentes. Proyecto v6
   solo cuando requiere tipos nuevos; v1–v5 siguen siendo válidos.
3. **Continuidad:** estado de captura separado de disponibilidad y de píxeles;
   stop intencional nunca se reintenta. Ausencia de buffers sola es incertidumbre.
   Recuperación acotada por fuente/generación, escena segura explícita y ningún
   fallback implícito a escritorio. Verificar lifetime SCK antes de permitir
   sustituciones en vivo; una política de estados no prueba teardown nativo.
4. **Audio/outputs:** reproducir AUDIO-01 y entrega terminal H17 con el mismo
   binario. Mantener buffering fijo de 128 ms, reloj, interleaver y barreras H8
   hasta tener trazas que demuestren causalidad y regresiones verificadas.
5. **Uso personal:** gaming 1080p60, podcast/charlas 1080p30, cada sesión 60 min
   supervisada; pruebas de ventanas, permisos, desconexión, escenas, audio,
   MKV/RTMP local, stop/cierre/reapertura. A/V medido al inicio/medio/final;
   usar gate propuesto |audio−video| ≤80 ms y deriva ≤40 ms/h, sin redefinir
   retroactivamente los gates históricos. Informar CPU, GPU cuando observable,
   footprint/RSS, frames y ownership de recursos sin inferir ausencia de fuga.

Las pruebas automáticas solo capturan fixtures propias. Display requiere una
superficie íntegramente controlada y supervisión; no capturar escritorio personal
para completar una casilla. Juegos, cámara, micrófono y cambios físicos requieren
los recursos y permisos normales correspondientes. RTMPS externo usa exclusivamente
el flujo seguro existente y autorización específica.

## Matriz de aceptación inicial

| Gate | Estado | Evidencia / siguiente paso |
|---|---|---|
| Base independiente y ownership | PASS documental | SHA anterior; H19 leído, sin modificar |
| CAP-01 | FAIL histórico B7 | 15,4/15,6 s sin progreso decodificado; causa interna no establecida |
| Comparación OBS/Motive física | PASS acotado C1r4 | Ambos módulos avanzaron píxeles con foco corroborado; CAP-01 no se reprodujo, sigue abierto |
| Display/Application/Window | PARTIAL | Tres modos implementados en Production/UI/CLI/MCP, v6 compatible; Display físico y app multiventana pendientes |
| Recuperación y continuidad | PASS acotado C3 / PARTIAL global | Cerrar Window/Application propias → respaldo con ambos outputs/audio continuos; reinicio SCK live pendiente |
| Audio y entrega final | PARTIAL | H17 conserva identidad histórica y colas pendientes |
| 3 × 60 min personales | BLOCKED | Depende de gates anteriores y recursos supervisados |
| PERSONAL STREAM READY | BLOCKED | Ningún PASS documental/unitario sustituye los gates físicos |

Investigación fijada y límites: [OBS vs Motive](h20-obs-capture-investigation.md).
Identidades, política y guía de uso: [Capture Engine](h20-capture-engine.md).
Resultados por candidata: [verificación física](h20-capture-verification.md).

## Contrato futuro con H19

Mantener un único owner Production y reloj libobs. Los mensajes de control
transportan identidad/estado, nunca video. Browser Host sigue aislado: futuro
adaptador de frames binarios acotados, identidad/generación/epoch, worker fuera
de render, upload/destrucción en contexto gráfico OBS, audio web desactivado.
Una avería de browser y una avería SCK se gestionarán por fuente sin compartir
credenciales ni reiniciar outputs por defecto. No importar tipos o código H19
hasta su handoff y aceptación de aislamiento/teardown/capacidad.
