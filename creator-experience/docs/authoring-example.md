# Ejemplo concreto de generación por agente

El recorrido de autoría tiene ahora un material reproducible además de la guía:
[podcast con dos cámaras reservadas](../agent-authoring/example/README.md).
Es un ejemplo pequeño de contrato, separado de las dos colecciones premium.

| Paso solicitado | Entregable verificable |
|---|---|
| Consultar capacidades | `agent-authoring/capabilities-baseline.json`, hashes y commit de código; runtime no consultado |
| Recibir intención | `agent-authoring/example/brief.json` |
| Diseñar composiciones | Conversation + BRB en ambos espacios design960; recetas para dos cámaras |
| Generar recursos originales | Texto y formas nativas; no se necesita media externa para este ejemplo |
| Emitir manifiesto | CreatorPack v1 con 2 escenas, 6 fuentes, 7 capas y 8 propiedades |
| Validar restricciones | Parser Rust real, referencias/Deck/reglas, 12 negativos, reserva de capturas y geometría |
| Generar previews | Cuatro SVG documentales sin fuentes capturadas ni recursos remotos |
| Presentar resultados | README, manifest, Deck, reglas, eventos, informes y limitaciones |
| Revisión de la persona | Paso explícito antes de la instalación; no sustituido por una aprobación simulada |
| Instalación oficial | Pendiente de importador genérico; H14 observado sigue limitado a MATCHDAY |

`generate_example.py` usa Python estándar y genera doce archivos de contenido,
licencia y preview. `verify_example.py` repite la generación y valida con el mismo
harness autoritativo de la entrega. La segunda generación fue idéntica byte a byte.
No se añadió un framework de agentes, servidor MCP, proveedor de IA ni instalador.

Las cámaras son roles y espacios reservados. Tras dos selecciones reales del
usuario, el plan teórico suma 8 fuentes y 9 capas. No se confunde una guía visual,
un modelo validado o un evento simulado con una cámara conectada.
