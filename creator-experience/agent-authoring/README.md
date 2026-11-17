# Autoría de Creator Packs por personas y agentes

Estas reglas sirven para cualquier editor, script o agente. No requieren IA,
proveedor, framework ni servidor MCP adicional. El resultado es contenido
declarativo; las herramientas de generación no forman parte del pack instalable.

## Recorrido

1. **Consultar capacidades.** Leer la versión fijada de `CreatorPack`, contratos
   H11–H13 y, cuando una sesión esté autorizada, consultas de capacidades del
   propietario. No confundir `h12_contracts()` con detección runtime. En esta
   entrega no se consulta ni ejecuta Motive.
2. **Capturar intención.** Audiencia, seis momentos del directo, contenido que
   debe quedar visible, nombre/subtítulo, paleta, orientación y movimiento reducido.
   Pedir fotos/logos solo si necesarios y verificar su autorización/licencia.
3. **Presupuestar antes de dibujar.** Sumar escenas/fuentes/capas a todo el proyecto.
   Reservar capacidad para capturas. Reutilizar fuentes cuyo contenido sea común;
   crear títulos separados cuando editarlos deba afectar una sola composición.
4. **Diseñar ambas orientaciones.** Usar coordenadas design960, márgenes seguros
   y contain real. No estirar PNG ni rasterizar textos editables. Las guías de
   captura son instrucciones de composición, no cámaras ya configuradas.
5. **Generar arte original.** Conservar fuente editable y exportar PNG compatible;
   registrar procedencia/licencia. No descargar fuentes ni recursos propietarios.
6. **Emitir manifest v1 estricto.** Separar metadatos de catálogo, reglas y Deck.
   Mantener IDs ASCII estables y referencias resolubles. Recursos con basename,
   tamaño, dimensiones y SHA-256 reales, nunca rutas del checkout.
7. **Validar.** Parser autoritativo, plan, propiedades, recursos decodificados,
   hashes, geometrías, presupuesto y casos negativos. Consultar `validation/`.
   Un script que solo hace `json.load` no es validación semántica.
8. **Renderizar y revisar.** Previews reproducibles de todas las escenas y ambas
   orientaciones. Revisar textos largos, capas ocluidas, estado alerta/timer,
   motion y reducción. Etiquetar claramente los renders aproximados.
9. **Presentar.** Arte, fuentes, manifests, informes y pendientes por separado.
   La persona revisa contenido y plan. No proclamar éxito nativo por screenshots.
10. **Instalar después.** Solo el instalador oficial, con autorización y estado
    vigente, crea recursos/bindings. No usar este workflow para emitir, arrancar
    temporizadores ni activar proveedores automáticamente.

## Ejemplo de brief entregable

«Podcast de software, tono editorial sobrio, nombre Alex Rivera, capítulo
Arquitectura local, dos cámaras seleccionadas por el usuario, lower third,
pausa y ending, 16:9/9:16, movimiento reducido disponible».

Antes de expandir CREATOR TECH: reservar dos fuentes de cámara y una capa por
cámara por escena donde aparezcan. Si el total supera 32 capas, reducir escenas
o usar una receta alternativa. Dos cámaras en cinco escenas consumen diez capas;
el espacio sobrante de un pack no garantiza esa composición. Presentar el cálculo.

Usar `packs/creator-tech/manifest.json` como ejemplo de estructura y
`packs/neon-arena/rules.json` como ejemplo de eventos manuales tipados. No copiar
IDs de una instalación. El ejemplo de authoring es una receta, no un manifest
extra que se declara validado sin pasar el harness.

## Fallos frecuentes

| Error | Corrección |
|---|---|
| Añadir `description` al manifest v1 | Moverlo a metadata; unknown fields se rechazan |
| Cambiar RGB de widget con `shape_color` | El target exige shape; conservar acento o proponer futura capacidad |
| Empaquetar SVG/HTML como runtime | SVG solo fuente de autoría; exportar PNG |
| Usar SF Pro en el enum nativo | Helvetica/Arial/Menlo; SF es solo UI |
| Confundir fuente con capa | Evento afecta todas las instancias; animación solo la capa vinculada |
| Fade con ease_out | Fade nativo exige linear |
| Slide vertical o overshoot/spring | Solo desplazamiento X y easing enumerado; no inventar keyframes |
| Contador de comunidad dibujado como widget nuevo | Usar acciones de contador existentes sin prometer binding visual automático |
| Reproducir sonido del video | Video local es visual, sin audio |
| Dos packs caben individualmente | Sumar al grafo existente; seis más seis excede ocho escenas |
| Hash correcto implica autor confiable | Integridad y autenticidad son propiedades distintas |
| Reiniciar una mutación tras timeout | Consultar recibo/estado antes; puede haber ocurrido |

## Checklist de revisión

- [ ] Licencia y procedencia por recurso; sin secretos ni rutas privadas.
- [ ] JSON estricto validado por la versión declarada del contrato.
- [ ] Todos los assets existen, decodifican y coinciden con tamaño/hash/dimensiones.
- [ ] Seis composiciones y ambas variantes revisadas; capturas descritas como pendientes.
- [ ] Texto editable legible con saltos explícitos y valores largos probados.
- [ ] Capas/recursos/capacidades/presupuesto y espacio para captura calculados.
- [ ] Reglas/Deck resuelven referencias; ninguna acción o proveedor se activa al abrir.
- [ ] Movimiento acotado, sin bucle continuo; fallback reducido documentado.
- [ ] Previews identificados como diseño, no grabación nativa.
- [ ] Informe final separa validación, prototipo e integración pendiente.
