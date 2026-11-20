# H21 — captura real en C4

Checkpoint 2026-11-19. Todos los ensayos identifican el ejecutable C4
`6e9d91341ffd77e29751bd0a1b459e2f1c266d8fb64084ddff9bd00df5ad33ad`.
No se han cambiado el runtime, el módulo oficial, sus parches, el reloj ni el
buffering de audio. Builds, ensayos y decodificación usan turnos separados del
lock físico canónico compartido con H22.

## Application multiventana

`var/evidence/H21-C4-mult-window-r2/report.json` registra ejecución PASS;
`...-analysis/analysis.json` registra decodificación PASS para MKV y RTMP.
Dos ventanas AppKit propias dibujan contadores binarios independientes a 10 Hz.
La prueba observa foco, resize, minimizar/restaurar, cerrar la primera ventana
y perder la aplicación. Verifica avance del contenido de ambas ventanas tras
restaurar y continuidad de la segunda mientras la primera está minimizada o
cerrada. La pérdida final recibe el respaldo seguro sin cambiar los intentos
de outputs ni el mixer. Composición/encoding: 1080p60; eso no prueba un productor
de 60 imágenes distintas por segundo.

El primer intento `H21-C4-mult-window` falló en el harness al encontrar geometría
propia aún no publicada. Se conserva. El segundo espera de forma acotada datos
reales positivos antes de admitir la captura; no inventa dimensiones.

## Window: suspensión y retorno

`H21-C4-window-lifecycle-r2` y `...-analysis` pasan a 1080p30. Minimizar produce
`suspended`, una condición de fallo confirmada por el contrato H20. Se observa
el Cut a la escena segura. Restaurar la ventana permite recibir superficies
nuevas; solo entonces el harness solicita explícitamente un Cut a la misma
fuente. Sus píxeles decodificados vuelven a avanzar y ambas salidas continúan.
No se destruye ni recrea SCK durante outputs activos. El cierre final se cubre
con un Cut manual: el único intento automático de esa sesión ya se consumió.

`H21-C4-window-lifecycle` conserva el FAIL original de expectativa del harness:
esperaba permanecer en la captura al minimizar, contrario al contrato de
respaldo configurado. No se presenta como defecto corregido en Production.

## Display físico autorizado

El primer intento `H21-C4-display` rechazó el UUID del monitor externo ausente
antes de iniciar una captura. Tras la autorización del propietario y su libertad
de elección, `H21-C4-display-r2` seleccionó explícitamente la pantalla integrada
observada, 1728 × 1117 puntos. Una ventana propia borderless cubrió exactamente
sus límites. No se cambiaron resolución, Spaces, Stage Manager, volumen ni
preferencias globales. No se utilizó ningún navegador.

La captura duró **60.39 s**, seguida de una escena segura y stops independientes.
El fixture siguió cubriendo la pantalla hasta detener ambas salidas y eliminar
la fuente Display. Fixture y owner terminaron con exit 0, sin errores de cleanup.
La verificación visual de preview y los archivos decodificados contienen el
contador propio. El análisis independiente conserva hashes, probes y contadores.

- MKV y RTMP: H.264 1920 × 1080 a 60 FPS, AAC estéreo 48 kHz.
- VideoToolbox hardware observado en ambos destinos; sin fallback a software.
- Más de 100 valores de contador distintos por archivo, tono continuo y patrón
  seguro final. Máximo intervalo PTS observado: video 17 ms; audio 22 ms.
- Durante el intervalo controlado: cero drops de output, cero frames lagged y
  cero video_skipped. Los 19 descartes de copia de preview son otra métrica.
- 58 muestras de memoria: RSS máximo 237.83 MiB; footprint máximo 421.11 MiB.
  CPU mediana 28.24 %, máximo 30.37 %, con un núcleo equivalente a 100 %.
  GPU no observada. El trabajo de otros procesos no se atribuye a Motive.

Es un ensayo corto de contenido propio a 10 Hz, no gaming real, ni prueba de
deriva A/V, ni diagnóstico de fugas. Los inventarios de dispositivos permanecen
en evidencia local privada; no forman parte del resumen público.

## Límites vigentes

CAP-01 sigue como riesgo histórico mientras se repite el ensayo independiente
de foco. Estos resultados no acreditan fullscreen nativo, múltiples Spaces,
Stage Manager, cambio de resolución o revocación real de permisos. Tampoco
demuestran reconstrucción SCK segura en vivo: véase [lifetime](h21-sck-lifecycle.md).
No se hereda aceptación de las versiones anteriores ni se edita su evidencia.
