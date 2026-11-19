# H19 — auditoría inicial y criterios congelados

Fecha de trabajo del propietario: 2026-11-18 (America/Lima). Rama local
`codex/h19-browser-hardening`, worktree `motive-h19`, desde main
`549d63f1a01625947ef1dfcea1609ab5c0a5295a`. El baseline H18 indicado,
`dc8d36c2acc9bbecc24200f09128c3babca40b4b`, ya es ancestro de esta base.
Production pertenece a H17. Solo se modifica `web-host-lab/`, más la corrección
de acoplamiento de herramientas de `AGENTS.md` expresamente autorizada.
Antes de esa corrección se observó el worktree H17 limpio, con el mismo HEAD y
sin cambios en AGENTS; no se modificó su checkout. No push/merge/release.

## Matriz inicial

| Pri. | Evidencia / causa | Hipótesis y corrección propuesta | Regresión y aceptación |
|---|---|---|---|
| P0 memoria | H18: 658.70/1993.27/2880.17 MiB RSS para 1/3/5 árboles; cinco FAIL. Cada instancia duplica servicios CEF. | Medir un host congelado; candidato B: varios CefBrowser con contexto/origen/mailbox propios dentro de un host, solo contenido propio de igual confianza. | 1/3/5 reales, 10 s warmup + 60 s ventana, 3 repeticiones, RSS <2048 MiB y cleanup. No equivalencia RSS=RAM única. |
| P0 identidad | H18: identidad única i1 y cierre global. | Mapear browser→instancia, capacidades estables por generación, inventario/origen privado, estados por instancia. | Ningún frame/evento cruzado; close/hide/restart/crash conserva estados de pares según renderer real. |
| P0 Keychain | H18: SecItemCopyMatching bloquea CefShutdown; mock evita tarea real. | Localizar servicio/prefs de OSCrypt en código exacto; configuración oficial sin credenciales o gate BLOCKED. | No consultar Keychain real; mock permanece exclusivo de laboratorio, nunca PASS de distribución. |
| P0 sandbox | Callback/CSP/RequestContext no prueban frontera OS; browser privilegiado. | Matriz por proceso/superficie, probes propios y mecanismo público de broker/confinamiento. | Denegaciones observables identifican capa; terceros BLOCKED hasta demostrar todas las fronteras. |
| P1 frames | H18: 31 paints aceptados sin destino final registrado. | Contabilidad conservativa completa, bytes/copias y leases adquiridos/consumidos/invalidados. | Ecuación de conservación, cierre y revocación bajo backpressure; evidencia H18 intacta. |
| P1 sesión prolongada | 100 procesos nuevos no prueban host largo. | Crear/cerrar/recrear browsers dentro del mismo CefInitialize. | A/B/C→cerrar B→D, ocultar A, resize C, restart D, crash, recuperación y cierre con reap. |
| P1 resize | H18 usa reemplazo frío. | WasResized soportado solo con barrera/epoch seguros; conservar reemplazo si ambigüedad A→B→A. | Nuevas dimensiones y epoch sin reutilizar callback antiguo; latencia <1000 ms cuando demostrable. |
| P1 Goal | H18 cuatro cierres nativos reales. | Reutilizar binding/activos originales con identidad multi. | Bootstrap/properties/event/repeat/cancel/resume/dispose, H/V/hidden/crash/restart; ACK separado de píxeles y reap. |
| P1 métricas | Ensayos H18 cortos, GPU no disponible. | CPU por deltas Mach, RSS y footprint por identidad, fases separadas; telemetría de frames sostenida. | No mezclar relojes/CPU startup/steady, no declarar FPS audiovisual; null para medición ausente. |
| P1 libobs | Adaptador de política existente, sin transporte Production. | Contrato compilable de manager/failure domain/adapter dentro del lab. | Tests reales del contrato; draw/texture/clock OBS requieren handoff H17 y H20. |
| P2 distribución | CEF ARM64 y firma ad-hoc; sin distribución. | Inventario binario/licencias/roles/entitlements por versión. | Sin eliminar recursos necesarios; Developer ID/notarización y segunda Mac no autorizados aquí. |

## Comparación de arquitecturas antes de decidir

A conserva árboles independientes como control y posible frontera futura; no
repetir cinco en la configuración fallida. B elimina duplicación del browser y
servicios para contenido propio, pero comparte dominio de fallo y privilegios.
C es una política de agrupación por confianza sobre B y hosts separados; no
habilita terceros por sí sola. D pooling queda desactivado: primero demostrar
revocación, final-close y ausencia de contaminación; no reutilizar JS heaps.
La selección final depende de los resultados nuevos, no de estos supuestos.

Se conserva el protocolo H16/H18 sin modificar sus umbrales: RSS 2048 MiB,
deadline máximo 720 s, warmup 10 s, ventana 60 s, tres repeticiones; FPS de
adquisición >=95% solicitados para animación, edad p95 <=100 ms, primer frame
<=3000 ms, resize <=1000 ms y cierre del árbol <=5000 ms. Cada resultado indicará
si ejecutó el protocolo completo o un diagnóstico corto. Un soak acotado no
demuestra ausencia de fugas. No se vacía caché del OS ni se cambia energía global.

## Alcance de memoria

Registrar RSS y `proc_pid_rusage` physical footprint por proceso/árbol. Ambos
totales son sumas secuenciales; no equivalen a páginas físicas exclusivas.
Framework mapeado, recursos CEF y páginas compartidas pueden contarse varias
veces en RSS. Reserva virtual, residencia, dirty/private y recuperabilidad no
son intercambiables; solo se asignarán cifras cuando una API observada las dé.
Buffers Rust se contabilizan por ownership; sus bytes no estiman el heap de V8,
superficies OSR/GPU, cachés, texturas futuras ni allocator. Recuperación observada
después de cerrar una instancia no demuestra liberación de toda reserva nativa.
