# H20 — verificación real por candidata

Worktree `motive-h20`, rama `codex/h20-capture-reliability`. Todas las tandas usan
el lock canónico compartido con H19; ASTRA cedió ventanas de recursos y no se
modificó su worktree. No publicación, push, merge ni cambios globales.

## C1 — comparación mac-capture

Bundles privados debug ARM64 ad-hoc, mismo owner/libobs/encoder/output. Los
inventarios `target/h20/Motive-H20-{upstream,motive}-C1r2.comparison.json`
acreditan mismos bytes de owner tras retirar firma y ninguna otra diferencia
nativa salvo mac-capture. La firma del owner cambia con el envelope de recursos.
La primera preparación rechazó correctamente esa diferencia de firma; el segundo
inventario conserva hashes firmados y normalizados. No se afirma reproducibilidad
bit a bit de una compilación ni equivalencia con OBS Qt.

Los ensayos usan la misma fixture H14 propia y probe independiente H15, 1080p30,
VideoToolbox, tono interno, MKV y RTMP loopback. Tres tramos de foco de 15 s.

| Ensayo | Resultado | Observación |
|---|---|---|
| C1 upstream inicial | FAIL del harness | `capture_diagnostics:null` no contemplado; corregido, evidencia conservada |
| C1r2 upstream | PASS acotado | Foco y contador decodificado válidos |
| C1r2 Motive | BLOCKED | Startup agotó 15 s; shutdown normal, fixture no se lanzó |
| C1r3 Motive | BLOCKED de foco | Orca fue PID frontal tras dos solicitudes; no comparar con upstream |
| C1r4 upstream / Motive | PASS acotado | Repetición supervisada por el propietario, foco A→B→A corroborado y contador fresco en ambos medios |

El ensayo C1r3 conservó medios aunque faltaban marcadores. No se reinterpretó como
captura aceptada. Durante la tanda C1r2 se ejecutaron 54 unit tests Python
(0,025 s); la comparación aceptada es C1r4, reservada exclusivamente a captura
y análisis secuenciales. No hubo compilación concurrente con C1r4.

| C1r4 | Frames MKV | Frames RTMP | Máximo salto PTS | Mayor repetición del contador, muestreo 5 Hz |
|---|---:|---:|---:|---:|
| OBS original | 1339 | 1328 | 34 ms | 0 s |
| Motive H20 | 1321 | 1309 | 34 ms | 0 s |

Las duraciones útiles difieren por admisión/arranque; no se comparan tasas usando
solo el total de frames. Se conservaron brackets de clocks y límites de fases.
Estos PASS no borran B7 ni establecen una causa: CAP-01 **no se reprodujo** en esta
secuencia. `observed` y `admission` se compilaron pero no se ensayaron físicamente.

Los cuatro medios C1r4 reportan `STOP_BOUNDARY_PACKETS_NOT_DELIVERED`. En Motive
faltó un paquete AAC del tail observado por destino; en upstream faltaron 2 video
y 3 audio en MKV, y 1 video en RTMP. El correlador los clasifica compatibles con
el corte documentado de stop. No son prueba de entrega terminal completa ni una
mejora causal H20. No se cambió buffering, interleaver ni clock.

Evidencia local íntegra: `var/evidence/H20-C1r4-upstream-focus/` y
`var/evidence/H20-C1r4-motive-focus/`: `report.json`, `capture/report.json`, logs,
marcadores/probes, trazas de paquetes, `analysis/analysis.json` y contadores
decodificados. Los reports enlazan MKV y receiver conservados. Cada owner terminó
con código 0 y cada fixture propia se cerró tras él; no quedó un owner de prueba.

Reproducción, sin otro owner abierto y con la Mac reservada bajo lock:

```sh
python3 scripts/with_physical_lock.py --timeout 180 --purpose 'H20 focus upstream' -- \
  python3 scripts/verify_h15_focus_capture.py --lock-held --unobserved-upstream \
  --app target/h20/Motive-H20-upstream-C1r2.app --output var/evidence/NEW-upstream
```

Para Motive usar su bundle y omitir `--unobserved-upstream`. El análisis usa
`verify_h14_collection.py analyze --lock-held --report .../capture/report.json
--output .../analysis --ffmpeg APP/Contents/MacOS/ffmpeg
--ffprobe APP/Contents/MacOS/ffprobe --verify-vt-framing`, también bajo lock.
Nunca reutilizar directorios ni eliminar fallos anteriores.

## C2/C3 — continuidad ante pérdida de aplicación propia

C2 comprobó admisión real Application, buffers y ambos outputs activos. Al cerrar
la fixture, falló la continuidad: `SCENE_CURRENT_FAILED` abortaba el Cut antes de
su señal de completion y cerraba ambos outputs. El runner original escribió
BLOCKED por timeout, pero el gate de producto se clasifica **FAIL**; no faltaba
un permiso ni recurso externo. Logs/medios permanecen en
`var/evidence/H20-C2-application-recovery/`.

C3 cambia esa condición: Cut puede abandonar un origen fallido y sigue exigiendo
destino saludable; Fade mantiene su guard. El núcleo limita a un intento por
sesión y a 2 s mientras persiste el fallo. No reconstruye SCK en vivo. Se añadió
persistencia v6 y pruebas que rechazan respaldo con captura o canvas sin cubrir.

El runner `scripts/verify_h20_capture_recovery.py` selecciona solo la fixture
propia por Window o Application; jamás Display. Resuelve el display que contiene
el centro de su ventana observada, cierra ese PID propio, exige mismo intento de
ambos outputs y mismo número de recursos nativos, conserva mixer y comprueba stop
independiente. Después del cierre de procesos decodifica pixels propios iniciales,
el patrón de respaldo final, tono y cadencia. No prueba multi-window, A/V humano,
reconexión SCK en vivo ni sesiones de una hora.

**C3 Application y Window: PASS acotado.** Ambos ensayos conservaron los mismos
intentos de recording/streaming, el mixer y tres recursos nativos; ninguna fuente
se creó durante el respaldo. El patrón seguro se identificó en píxeles MKV y
RTMP después de la pérdida; la fixture propia también se identificó antes.
El tono decodificado permaneció presente sin clipping; saltos máximos de PTS:
34 ms video y 22 ms AAC. Parar streaming mantuvo recording activo. Owners salieron
con código 0, fixtures propias con SIGTERM esperado, sin errores de cleanup.

El observador vio la escena segura 425,39 ms (Application) y 336,02 ms (Window)
después de solicitar el cierre de la fixture. Es una cota observada que incluye
terminación del proceso, polling/RPC y scheduling; no mide la latencia exacta del
primer píxel de respaldo ni constituye SLA.

Evidencia: `var/evidence/H20-C3-{application,window}-recovery/report.json`, medios y
logs asociados. Resumen con hashes: [results.json](evidence/h20/results.json).
Bundle `target/h20/Motive-H20-C3.app`, audit portable PASS, versión local 20.3.
130 tests raíz y Clippy con warnings denegados pasan. Fuentes exactas C3,
inventario SHA-256 y patch en `var/evidence/H20-C3-build/`; el bundle sigue siendo
debug/ad-hoc local, no una release ni una distribución certificada.

Reproducción con directorio nuevo y sin otro owner abierto:

```sh
python3 scripts/with_physical_lock.py --timeout 240 --purpose 'H20 safe capture' -- \
  python3 scripts/verify_h20_capture_recovery.py --lock-held \
  --app target/h20/Motive-H20-C3.app --mode application \
  --output var/evidence/NEW-application-recovery
```

Repetir con `--mode window` y otro directorio. Mantener el lock durante análisis;
las herramientas no toman una ausencia de lock como prueba de Mac disponible.

## Límites abiertos

- Display está implementado, pero falta superficie íntegramente controlada para
  validación física; no se grabó el escritorio personal para conseguir un PASS.
- App con múltiples ventanas, minimización, fullscreen, Spaces/Stage Manager,
  cambios de resolución, permisos y dispositivos requieren matriz adicional.
- Reconstrucción SCK en vivo queda cerrada hasta probar su lifetime asíncrono.
- Juegos, cámara/micrófono, invitados y tres sesiones supervisadas de 60 min no se
  han ejecutado. No hay RTMPS externo ni afirmación de A/V de una hora.
- CPU/GPU/memoria prolongadas, ausencia de fugas y entrega terminal completa no
  se deducen de estos smoke tests. PERSONAL STREAM READY sigue **BLOCKED**.
