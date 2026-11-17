# Cobertura de elementos de las dos colecciones

Revisión de manifests, recursos y recetas finales. «Implementado» aquí describe
contenido declarativo o un recurso utilizable; no significa instalado en H14 ni
aceptado en una emisión. Las pruebas están en `evidence/contracts-native.json`,
`evidence/contracts-validation.json` y los contact sheets de cada pack.

## CREATOR TECH

| Elemento solicitado | Material existente | Alcance real |
|---|---|---|
| Starting Soon / Live Coding / Camera Focus / Screen Presentation / BRB / Ending | Seis escenas `tech-starting/live/camera/presentation/brb/ending`; doce previews | Dos transforms por capa, design960 |
| Lower thirds y presentación del creador | `tech-lower-third`; properties presenter/presenter-detail | Widget nativo compartido; Show explícito, inicialmente oculto |
| Títulos de capítulos | `tech-chapter`; property chapter; `tech-label-in/out` | Texto editable + Slide X; no auto-wrap |
| Marcos de webcam | `assets/tech-frame.png` + SVG editable; slots en recipes | PNG alpha real; cámara elegida aparte |
| Contadores | `tech-timer` | Countdown de cinco minutos; no count-up ni binding a espectadores |
| Alertas | `tech-alert`, regla `tech-deck-alert`, previews `alert-*` | Trigger manual; proveedor follow deshabilitado |
| Identificadores | `tech-identity`, property identifier | Texto nativo; compartido donde corresponde |
| Paneles informativos | `tech-info`, property note, escena presentation | Panel editorial de texto; no datos externos automáticos |
| Elementos decorativos | `tech-motif.png` + SVG original | Isometría rasterizada sin texto personalizable |
| Transiciones | Deck BRB Fade 350 ms; regreso Cut | Intenciones tipadas, integración nativa pendiente |
| Entradas y salidas | Diez animaciones reales de manifest | Fade/Slide/Scale, sin bucles ni keyframes |

## NEON ARENA

| Elemento solicitado | Material existente | Alcance real |
|---|---|---|
| Starting Soon / Gameplay / Camera Focus / Community / BRB / Ending | Seis escenas `arena-starting/live/camera/community/brb/ending`; doce previews | Ambos layouts; gameplay conserva área principal libre |
| Alertas de comunidad | `arena-alert`, regla `arena-deck-alert`, previews `alert-*` | Manual; follow/reward de proveedor permanecen deshabilitados |
| Marcos de cámara | `assets/arena-frame.png` + SVG editable | PNG alpha; no cámara ni recorte implícito |
| Celebraciones | `arena-reward`, `reward-in/out`, `arena-deck-celebrate` | Widget de alerta y escala de capa; Trigger/animación son operaciones distintas |
| Lower thirds | `arena-lower-third`, `arena-lower-in/out` | Identidad editable compartida, Show explícito |
| Contadores | `arena-timer` y acción `increment_counter` de community_rewards | Countdown visual; contador de reglas interno sin binding visual automático |
| Recompensas | Widget `arena-reward`, property reward-text | Presentación manual; no conexión real con plataforma |
| Indicadores | `arena-label`, `arena-identity`, `arena-indicator-in` | Texto/entrada visual, sin inferir audiencia o estado de emisión |
| Pantallas de pausa | `arena-brb` y título independiente | Countdown compartido con Starting; no reset implícito |
| Animaciones | Doce animaciones de manifest | Fade/Slide/Scale nativos acotados |
| Elementos interactivos | Deck de diez botones, cinco reglas y eventos manuales tipados | Ensayo independiente; no acciones multimedia reales |

## Límites que no se deben ocultar

No falta un campo requerido en los manifests validados. Descripción, categoría,
tags, previews, recetas y migración viven en sidecars porque no son campos del
schema v1. La licencia/procedencia y hashes acompañan cada recurso.

No existen en el contrato: cámara declarativa, contador de espectadores conectado,
audio de video, sonido de celebración, Browser Source, fuente externa, animación
por keyframes, recolor de PNG o propiedad global de widget accent. La entrega no
presenta ninguno como implementado. Las acciones manuales y las recetas resuelven
los casos compatibles; proveedores e importación de packs generales quedan pendientes.

Cada colección tiene 6 escenas, 12 fuentes y 27 capas, con reserva de 4 fuentes y
5 capas sobre un proyecto vacío. CREATOR TECH propone cuatro slots de captura;
NEON ARENA propone dos. Dos packs completos juntos exceden límites globales.
Se requiere preflight real y bindings devueltos por el importador oficial.
