# H21 — C5, identidad estable para apertura normal

Estado: **FAIL de continuidad en fullscreen; sucesora C6 en preparación**.
PERSONAL STREAM READY: **BLOCKED**.
Fecha: 2026-11-19, America/Lima. C4 y sus informes permanecen intactos.

## Motivo y construcción

C4 podía capturar al arrancar desde el supervisor, pero su reapertura normal
mediante LaunchServices negaba pantalla. El interruptor de macOS aparecía
activado; cerrar/reabrir y actualizarlo por el flujo normal no bastó. El registro
de TCC identifica la causa: la autorización existente de pantalla exigía una
firma Apple Development y C4 era ad-hoc. No se borró ni editó la base TCC.

C5 usa la identidad Apple Development que ya existía en esta Mac, sin crear
certificados, cambiar el keychain o publicar. La versión local es 21.5; el bundle
portable release ARM64 está en `target/h21/Motive-H21-C5.app`. Se reutilizan los
inputs compilados para C4 y se empaquetan/firman de nuevo mediante el builder
existente, con notices completos obligatorios. No se activa hardened runtime
por conjetura ni se afirma notarización.

Ejecutable SHA-256:
`612d898d6bfa843fb384ddae1a35035b6fde7c454428013f0973eb0ed3a5eb97`.

`var/evidence/H21-C5-package/` conserva comando, log, firma, inventario de hashes
y comparación de secciones Mach-O. La auditoría portable estática pasa. Todas
las secciones de los ejecutables y módulos nativos comparados son idénticas a
C4; las firmas y la versión del bundle cambian. Esto no es una afirmación de
build reproducible. Los 130 tests Rust, 136 Show Control y Clippy del build C4
corresponden al mismo código; las pruebas de proceso/captura se repiten sobre C5.

## Permisos de la aplicación real

`H21-C5-launchservices-permission/report.json` observa C5 lanzada por `open`,
con pantalla autorizada desde el inicio. Se solicitaron cámara/micrófono desde
la UI de Motive por el flujo normal, dentro de la autorización explícita del
usuario. Al terminar, los tres permisos son `true`, outputs idle y el PID propio
está ausente tras shutdown normal; cleanup vacío. Los registros privados de TCC
permanecen en `var/`, fuera de la documentación pública.

Esto verifica permiso y ciclo de proceso. No acredita por sí solo frames de
cámara, sonido, continuidad o sincronización: esos gates requieren medios reales.

## Repeticiones

El coordinador `var/evidence/H21-C5-regression-stages/` ejecuta los contratos
históricos sin reducir duraciones ni sustituir sus asserts. Cada grupo conserva
su manifest H13, reports originales, backups y restauración por bytes/modo.
Se excluye el ensayo de mutación del Keychain del alcance local autorizado.

Las suites y sesiones posteriores deben identificar C5 por su hash. Ningún PASS
físico C4 se convierte automáticamente en evidencia C5. Los FAIL de C4 por
sesión gráfica bloqueada, foco no observado y permisos siguen disponibles.

### Resultados obtenidos

| Evidencia privada en `var/evidence/` | Resultado observado |
|---|---|
| `H21-C5-regressions-1` | PASS: control, entrega, verificación básica, cuatro encodings de 60 s, fallback de encoder, recuperación, RTMP/RTMPS, conexión-stop |
| `H21-C5-regressions-2-r2`, `-3` | PASS: perfiles/reinicio, H8 lifecycle, H9 fallos, H11 runtime/visual/lifecycle y H12 performance |
| `H21-C5-core-stages` | Diez comandos completados: respaldos Window/Application, proyectos v1–v6, política de output, dos lifecycle con medios, siete etapas de audio y matriz de outputs |
| `H21-C5-system-audio-owner` | PASS; siete pares A/V de aplicación a −36.125 ms, rango observado 0 ms. No demuestra deriva horaria |
| `H21-C5-output-matrix` | Nueve casos funcionales PASS; entrega terminal sigue PARTIAL |
| `H21-C5-regressions-physical-r3` | PASS: transiciones H9, audio H10 y mixer H10, con dispositivos físicos autorizados |
| `H21-C5-game-pilot` + `-analysis/analysis.json` | Runtime y análisis PASS, 60.785 s, juego Arkanoid propio, Display, micrófono y audio de aplicaciones, dual 1080p60 |
| `H21-C5-podcast-pilot` + `-analysis/analysis.json` | Runtime y análisis PASS, 61.159 s, cámara/micrófono reales, invitado controlado y dual 1080p30. El marcador mide la aplicación; sincronía física aún NOT_MEASURED |
| `H21-C5-charlas-pilot-r2` + `-analysis/analysis.json` | Runtime y análisis PASS, 60.791 s, Window/Application/Display, cierre de ventana y respaldo. Navegador BLOCKED |
| `H21-C5-fullscreen-r2` | FAIL real: salir de fullscreen consume una segunda suspensión después del retorno explícito; ambas salidas se detienen |

Los pilotos no sustituyen las tres sesiones de una hora. Los reports de runtime
usan PARTIAL hasta la decodificación separada; se conserva ambos documentos.

### Fallos conservados y diagnóstico

- `H21-C5-regressions-2`: el test histórico de B-frames recibe
  `FRAME_REORDERING_UNSUPPORTED`, de acuerdo con la política vigente. No se
  habilitan B-frames ni se modifica el assert antiguo para obtener PASS.
- `H21-C5-regressions-physical`: H1 esperaba `SOURCE_UNAVAILABLE` tras pérdida
  de ventana. La prueba diagnóstica nueva `H21-C5-loss-admission` observa
  `CAPTURE_STOPPED` y confirma que el siguiente start se deniega. El FAIL
  histórico y la diferencia del contrato quedan registrados.
- `H21-C5-regressions-physical-r2`: scenes pasa; crear una cámara en H9 devuelve
  TIMEOUT a los cinco segundos, aunque la fuente termina apareciendo una vez.
  La repetición r3 sin alterar código ni esperas pasa. No se declara reparado
  este fallo intermitente ni se atribuye una causa sin perfil causal.
- El primer piloto Charlas usa una ventana elevada excluida del inventario SCK.
  V6 coloca la presentación en la pantalla integrada a nivel normal y conserva
  una cobertura independiente en el Display externo; r2 pasa. Es un cambio de
  fixture, no una reparación del producto.
- El primer fullscreen falla por interpretar un NSNumber 0/1 como booleano
  estricto. El runner original se conserva. r2 corrige esa observación y revela
  el fallo real de continuidad del núcleo descrito abajo.

### Causa del fallo de fullscreen

Entrar en fullscreen genera una suspensión SCK confirmada: C5 hace Cut al
respaldo y conserva MKV/RTMP. La misma fuente vuelve a entregar superficies y
el verificador selecciona explícitamente la escena capturada. Al salir del
fullscreen se confirma otra suspensión. El presupuesto de un intento por
sesión ya está agotado y la política detiene ambas salidas. El source mantiene
su identidad; owner, receptor y fixture terminan normalmente, con cleanup vacío.

C6 intenta renovar una oportunidad únicamente tras un retorno explícito desde
la escena segura a fuentes existentes que entregan superficies completas y
recientes. No se renueva por polling, no se reinicia SCK y no se admite un stop
intencional. La corrección necesita sus propios tests y medios antes de aceptarse.
