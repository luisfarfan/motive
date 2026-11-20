# H21 — C4, baseline integrado

Estado provisional: **PARTIAL**. PERSONAL STREAM READY: **BLOCKED**.
Fecha: 2026-11-19, America/Lima. No es aceptación de beta pública.

## Candidata

Base: `25aca10dfeaa22345a7c4d9d232613ffb496bf1a`, obtenida con fetch y coincidente
con main/origin/main. Bundle release ARM64, GPUI predeterminado, versión local
21.4, firma ad-hoc; no GPUI Fast ni profiler. Runtime sin modificaciones respecto
de la integración H19/H20. No CEF ni Browser Host dentro de Production.

Bundle: `target/h21/Motive-H21-C4.app`.
Ejecutable SHA-256:
`6e9d91341ffd77e29751bd0a1b459e2f1c266d8fb64084ddff9bd00df5ad33ad`.
`var/evidence/H21-C4-build/` conserva comandos, logs, tiempos, snapshot de fuentes,
patch, inventarios SHA-256 de fuentes y bundle completo. Audit portable estático
PASS. Las dependencias y caches APFS son copias independientes. El build y
verificaciones se ejecutaron bajo el lock canónico, owner `h21-root`.

## Evidencia obtenida

| Comprobación | Resultado y alcance |
|---|---|
| Release optimizada | PASS, compilación nueva en 141.01 s |
| Tests Rust del núcleo | PASS, 130 tests |
| Show Control | PASS, 136 tests del crate separado |
| Clippy all-targets, warnings denegados | PASS |
| rustfmt | PASS |
| Python | PASS inicial de 149 tests; 160 tras añadir validación de supervisión/evidencia H21 |
| Application perdida → respaldo | PASS acotado, C4 nueva, MKV/RTMP decodificados |
| Window perdida → respaldo | PASS acotado, C4 nueva, MKV/RTMP decodificados |
| Inicio/stop/shutdown en esos ensayos | PASS, owners exit 0 y cleanup sin errores |
| Proyectos v1–v6 | PASS con documentos de patrón propios, carga/guardado/restauración reales |
| Un owner GPUI para CLI/MCP | PASS de proceso/PID/revisión y mutación compartida; gestos UI no evaluados aquí |
| Display físico | PASS acotado, pantalla integrada, 60.39 s controlados, MKV + RTMP 1080p60 decodificados |
| Application multiventana | PASS acotado, dos ventanas con contadores propios; foco, resize, minimizar/restaurar/cerrar |
| Window lifecycle | PASS acotado, respaldo al suspender; retorno explícito a la fuente existente tras restaurar |
| Matriz de outputs | 9 PASS funcionales y 14 medios decodificados; entrega terminal PARTIAL |
| Reconstrucción SCK en vivo | BLOCKED por lifetime no demostrado; restricción conservada |
| Audio de aplicación | PASS, seis etapas H13 nuevas tras desbloquear la consola |
| A/V controlada de aplicación | PASS acotado, máximo absoluto 78.604 ms; no prueba deriva horaria |
| Gaming real ligero | Piloto 60.445 s, Display Odyssey + audio de juego/otra app/mic, dual 1080p60; análisis PASS |
| Foco independiente CAP-01 | INCONCLUSIVE: píxeles pasan, pero una fase no mantiene el foreground exigido |
| Reapertura normal | FAIL por identidad ad-hoc incompatible con autorización TCC existente; motiva C5 |
| Tres sesiones personales de una hora | Pendientes; el piloto no las sustituye |

Los dos ensayos de pérdida son repeticiones del runner H20 sobre C4, no PASS
heredados. Mantienen intentos de outputs, número de recursos nativos y mixer;
verifican píxeles propios antes de la pérdida, patrón seguro después, tono,
cadencia y stop independiente. Informes:
`var/evidence/H21-C4-{application,window}-recovery/report.json`.

`verify_h21_project_control.py` prueba documentos v1–v6 con el owner real. Los
documentos mínimos v1/v2/v4 se normalizan al guardar a v3 según su contenido;
v5 conserva configuración 1080p60 y v6 conserva video/respaldo. Los IDs y el
grafo permanecen, las salidas siguen detenidas y no se selecciona hardware.
No acredita restauración de identidades físicas ausentes. El archivo original
se conserva y restaura con su modo; no se cargan los datos personales.
Evidencia: `var/evidence/H21-C4-project-control/` y wrapper `...-owner/`.

## Pendientes y coordinación

El usuario autorizó Display local y dio libertad para seleccionar contenido y
dispositivos disponibles. La primera ejecución se detuvo antes de crear una
captura: el Odyssey observado anteriormente ya no estaba conectado. Conserva
su FAIL de admisión en `H21-C4-display`. Se seleccionó explícitamente la pantalla
integrada observada, cubierta por una superficie nativa propia. No hubo fallback
automático de identidad. `H21-C4-display-r2` y su análisis independiente pasan;
la superficie permaneció hasta retirar la captura con ambos outputs quiescentes.

Multiventana, suspensión/restauración y Display se detallan en
[captura H21](h21-capture-verification.md). El protocolo de foco sigue inconcluso; audio de app y el piloto gaming tienen
evidencia nueva descrita abajo. Las regresiones amplias se retoman en C5. Un PASS corto no
acredita una sesión personal de una hora ni sincronización física A/V.

La primera solicitud de build adicional encontró el lock ocupado por H22 y
se rechazó antes de ejecutar el compilador. Se conserva esa exclusión mutua;
no se retira ni modifica el lock ajeno.

Investigación de lifetime: [H21 SCK](h21-sck-lifecycle.md). Los informes H17–H20,
incluidos C1/C2/C3 y sus FAIL originales, permanecen sin cambios.

## Evidencia posterior y sucesora C5

Tras el desbloqueo confirmado por el usuario, `H21-C4-system-audio-r2-owner`
y `H21-C4-av-owner` cierran normalmente sin errores. Los reports primarios
`h13-system-audio-1795099746555527000` y `h13-system-audio-1795099877554008000`
pasan las seis etapas y A/V respectivamente. Siete pulsos A/V tienen mediana
−44.604 ms y máximo absoluto 78.604 ms; no establecen sincronía física de webcam.

`H21-C4-game-pilot` y su análisis documentan Arkanoid real de código abierto,
modificado para entrada automática y una señal propia. Es una carga 2D ligera.
Durante 60.445 s: 1080p60, VideoToolbox hardware, MKV/RTMP, Display Odyssey,
audio del juego, otra aplicación, micrófono, overlay y Cut/Fade. Ambos medios
se decodifican completos; máximos A/V 37 ms y 31 ms. CPU mediana 27.97% (un core
=100%), RSS máximo 272.125 MiB, footprint máximo 393.954 MiB, drops de output 0.
No prueba deriva por hora, juegos pesados ni una sesión de 60 minutos.

`H21-C4-focus` conserva BLOCKED y su análisis INCONCLUSIVE: el contenido avanza,
pero otro PID interrumpe el foreground exigido en la tercera fase. No resuelve
CAP-01. `H21-C4-regressions-1` conserva FAIL al reiniciar por LaunchServices;
los dos primeros contratos de control pasan y los stores quedan restaurados.
La causa de permisos, el paquete firmado y sus pruebas se documentan en
[C5](h21-c5-verification.md).
