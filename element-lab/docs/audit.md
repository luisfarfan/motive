# Auditoría · checkpoint A

Baseline real `6019ad0acac4b52dcf1ebc44f2006406fde533f8`, 17 de noviembre de
2026 (Lima). El inventario reproducible y hashes están en `../evidence/audit.json`.
Solo lectura del producto; no se inició Motive, hardware, grabación ni streaming.

| Capacidad | Estado observado | Autoridad |
|---|---|---|
| Texto, forma, imagen, video visual, lower third, alerta, countdown | Implementados, vocabulario cerrado | `src/overlays/mod.rs`, `protocol.rs` |
| Transform horizontal/vertical, escenas, fuentes compartidas | Implementados; design960; 8/16/32 globales | `src/scene.rs` |
| Fade, slide X, scale por capa | Implementados, reloj nativo; fade lineal; 8 operaciones | H11/H12, `actions.rs` |
| Trigger animado | Acción tipada real; exige escena activa y binding único | `actions.rs`, H14 |
| CreatorPack v1 | Parser estricto, propiedades limitadas, plan no ejecutable | `show-control/src/packs.rs` |
| Reglas y Deck | Contratos reales + simulación offline; owner H14 separado | `actions.rs`, `deck.rs`, `simulation.rs` |
| Creator Tech / Neon Arena | Cada uno: 6 escenas / 12 fuentes / 27 capas, PNG propios | `creator-experience/packs/` |
| Instalación arbitraria de packs | No disponible en el adaptador observado: MATCHDAY embebido, recursos rechazados | `src/creator_packs.rs` |
| `.motivepack` distribuible | Propuesta de contenedor, no importador oficial | `creator-experience/docs/motivepack-proposal.md` |
| Autoría de elementos individuales/composición modular | Nueva capacidad de este laboratorio | Element Schema → adaptador v1 |
| HTML/CSS/JS en libobs | No disponible; spike H11 detenido antes de ejecutar CEF | `docs/h11-browser-spike.md` |
| Preview HTML | Prototipo de autoría, no fuente de video ni prueba de sandbox | Creator Experience |
| Marketplace, proveedores reales, WASM | Fuera del runtime implementado | Contratos futuros |

El schema de autoría no duplica CreatorPack. Conserva `VisualDefinition` y
`Action` del crate como subcontratos y delega su validación al crate real por
path de solo lectura. Cada exportación verifica parser, plan, referencias y
preparación de acciones. No hay copia del renderer, owner ni reloj audiovisual.

Las cuatro properties v1 son text_content, widget_title, widget_subtitle y
shape_color. Cambios adicionales de color, opacidad, duración o geometría se
hornean en nuevas definiciones durante autoría; no amplían ese enum. Un marcador
es texto editable, no un binding automático de contador de Show Control.
Estados de autoría son documentación, no máquinas de estados ejecutadas en OBS.

Dos presupuestos: heurística de packs y estimación H11 (8 bytes/píxel + 8 MiB
por texto / 16 MiB por widget). Ninguno limita RSS. Un pack validado aislado
todavía necesita sumar el grafo y capturas existentes, importar con el broker,
resolver IDs, revisar capacidades/revisión y obtener recibos del propietario.

Diseño: copia de Claude Design consultada sin editar, sala clara/escenario
oscuro según `design/direction.md`. Arte nuevo original, sin recursos de Meld.
La regla de navegador es proxima-browser exclusivamente. La skill local
`proxima-verificar-ui` no estaba disponible en los directorios de skills
consultados; se aplica directamente la restricción de AGENTS y del pedido.
