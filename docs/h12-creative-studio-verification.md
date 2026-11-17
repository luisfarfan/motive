# H12 — integración creativa (en curso)

Rama local `codex/h12-creative-studio`, worktree `motive-h12`; base integrada
`d2fb22e574dcb8d9cccb8b8409fceda93d81fa43`. Sin push, merge ni release.
La evidencia privada vive en `var/evidence/`; no se publica contenido capturado.

## Baseline integrado exacto

Bundle construido con fuente limpia y firma existente. Ejecutable SHA-256
`9e519f749f56eecfef3070e63941e59145c47c7fd66a622f4406c47b5853c42e`.
Manifiesto: `var/evidence/h12-baseline/build-manifest.json`; copia preservada del
bundle en `var/evidence/h12-baseline/Motive.app`.

Sesión observada desbloqueada, permisos normales; sin cambios globales. Todos
los ensayos físicos son seriales bajo el lock compartido de Motive.

- **Verificado:** 15 suites H1–H10 independientes de cámara, incluyendo captura
  de ventana propia, H9 faults, H8 lifecycle/keychain, CLI/MCP, entrega de control,
  perfiles, recuperación, RTMP/RTMPS local y H10 pilot. Manifiesto original:
  `var/evidence/h11-regressions-1794920805458950000/manifest.json`.
- **Verificado:** encoding ABBA, cuatro grabaciones completas de 60 s
  (x264/VideoToolbox/VideoToolbox/x264), gate original de cero lag intacto.
  H9 faults pasó en 30,1 s y encoding en 252,6 s. Esto verifica el main integrado
  en esta sesión; no demuestra por sí solo la causa de los fallos del bundle H11
  anterior en una sesión bloqueada.
- **Verificado:** H11 runtime con grabación y RTMP, visuales con video, lifecycle
  con pérdida/recuperación/persistencia. Manifiesto con hashes de los informes:
  `var/evidence/h12-baseline/h11-manifest.json`. Suites originales sin cambios.
- **Bloqueado por preparación de fixture:** H1 cámara, scenes y H9 transitions.
  Se solicitó cámara descubierta apuntando a contenido controlado; aún sin
  respuesta. No se sustituyó la cámara ni se declaró aceptación de esos gates.
- **Fallido:** H10 mixer, RMS de micrófono aislado. Primer ensayo pasó grabación
  (error RMS 0,226 dB); RTMP falló con 4,273 dB frente al margen de 2 dB. Segundo
  ensayo falló en grabación (5,665 dB). Ambos informes y medios se conservan;
  segundo manifiesto `h11-regressions-1794921883020606000/manifest.json`.
  No se repite a ciegas ni se modifica el umbral. Diagnóstico adicional del
  primer fallo: señal física variable (aprox. −32 a −47 dB); la mediana temporal
  de dB y el segundo de audio comparado difieren. Al agregar energía sobre un
  intervalo común, diferencia 0,187 dB. Esto apoya una hipótesis sobre muestreo,
  no reemplaza el gate ni prueba toda la implementación. Evidencia:
  `h12-baseline/h10-rms-diagnostic.json`.

No hay aceptación completa mientras esos gates permanezcan pendientes/fallidos.

## Incremento 1 — biblioteca e importación nativa

Implementado: selector nativo GPUI, copia en worker a inbox privado, importación
por el mismo `ImportAsset` y su operation ID, confirmación solo al observar
`completed`, limpieza por RAII al finalizar/rechazar/cancelar, inventario con
uso por escenas y eliminación protegida por referencias. Aún pendiente de
verificación interactiva con el bundle firmado.

`AssetCatalog::stage_selected_file` es una capacidad Rust de la UI, no un comando
serializable. Solo recibe la selección explícita del panel nativo. Lectura
no-follow/no-block del archivo final, regular y hasta 64 MiB, copia acotada,
comparación de metadatos antes/después, permisos 0600, nombre interno exclusivo.
El guard conserva descriptores y no elimina un inode reemplazado; nunca elimina
el original. No constituye aislamiento entre procesos del mismo UID. Un cierre
abrupto del proceso puede dejar una copia huérfana: no se borra por PID inferido.

Nueva consulta compartida `asset_inventory` (CLI/MCP/UI), sin argumentos:
`result.assets[] = {asset: Asset, error: string | null}`. Permite recuperar un
objeto perdido sin ocultar los demás. `list_assets`, `resolve` y la validación del
render siguen siendo estrictos. Importar bytes idénticos repara el mismo asset ID;
la reconexión de fuentes continúa siendo explícita y requiere salida detenida.

Validación incremental: 54 tests Rust PASS (51 previos + 3 de staging), incluyendo
original intacto, importación/recuperación real de PNG, symlink/FIFO/directorio,
archivo vacío/grande y limpieza que preserva una entrada reemplazada.

Verificación nativa incremental: selector NSOpenPanel -> PNG controlado 96×96 ->
«Recurso disponible · importación 1» observado en GPUI; consulta pasiva confirma
worker `completed`, `last_action` UI y cero copias `picked-*` restantes. Informe
`h12-baseline/increment1-native-import.json` con hash del bundle. Clippy PASS.
Una captura inmediata al cerrar NSOpenPanel devolvió SCK −3812; el árbol AX y
la siguiente captura de la ventana principal funcionaron. La selección genérica
por nombre de app resolvió accidentalmente el bundle H10: se cerró su proceso
idle enseguida, sin pruebas físicas concurrentes. Las siguientes selecciones
usan la ruta completa del bundle H12.
