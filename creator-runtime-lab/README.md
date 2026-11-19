# Motive Creator Runtime Lab — H18

Implementación aislada sobre `15ffbad`, rama `codex/h18-creator-runtime`.
**Preparación verificable; no es instalación ni render de elementos en Motive.**
Production, GPUI, libobs, Show Control y los formatos del producto siguen bajo H17.

El SDK local revisa los `.motivepack` experimentales existentes y propone añadir
instancias a escenas existentes con propiedades, layouts H/V, recursos compartidos,
cuotas y recibos tipados. El host CEF está compilado/enlazado y ejecutado con
contenido propio: BGRA real, alpha premultiplicado, variantes H/V a 30/60 FPS y
cierre limpio. Goal Celebration conserva su API y assets originales; el puente
nativo entregó propiedades/evento y produjo la animación transparente en CEF.
Las primeras ejecuciones con el Keychain normal se atascaron al cerrar; los
fallos quedan conservados. Las fixtures actuales usan el backend en memoria de
pruebas de Chromium, sin modificar permisos globales ni acreditar un sandbox.

```sh
python3 creator-runtime-lab/sdk/runtime.py catalog
python3 creator-runtime-lab/sdk/runtime.py review element-lab/marketplace-contract/packages/lower-third.motivepack
python3 creator-runtime-lab/sdk/runtime.py plan element-lab/marketplace-contract/packages/lower-third.motivepack --set 'lower-third-title="Samira"'
python3 creator-runtime-lab/tools/verify_runtime.py
```

[SDK y ejemplos](sdk/README.md), [importador](importer/README.md),
[binding y bootstrap](binding/README.md), [arquitectura](docs/architecture.md),
[compatibilidad](docs/compatibility.md), [handoff](docs/native-integration.md)
y [matriz de aceptación](docs/acceptance.md).

La mezcla requerida se conserva en
[evidencia offline](evidence/H18-sdk-examples.json): Creator Tech, Lower Third,
Community Alert y Goal Celebration dentro de una sola escena, con dos reservas
de captura previas. Total **14 fuentes / 14 capas**, cuatro assets y 112.291.104
bytes de estimación visual. No se abrió ninguna cámara ni captura; no es RSS.
Los siete paquetes declarativos originales conservan sus hashes.

`StrictOwnerModel` genera IDs `sim-*` y recibos de prueba. Nunca se deben importar
como identidades reales. Un fallo parcial conserva sus recibos y estado sin replay;
el sidecar se restaura solo para evaluación, desarmado y con revisión local pendiente.
El contenedor `motive-element-lab-review` mantiene su condición experimental.

Para CEF, consultar [bundle y gates](../web-host-lab/docs/h18-native-host.md).
El propietario autorizó las pruebas propias supervisadas y pidió reflejarlo en
`AGENTS.md`. Los resultados de frames, cierre, aislamiento y rendimiento se
clasifican por separado en la matriz; no hay integración libobs.
No se hizo push, merge, rebase, release ni streaming.
