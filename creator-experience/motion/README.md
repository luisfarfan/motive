# Motive Motion · lenguaje 1.0

Movimiento de contenido acotado, original y realizable con H11. El catálogo no
es un motor: describe cómo configurar `PackAnimation` y transiciones existentes.
La galería del prototipo ilustra estos valores en el navegador, sin conectar a
libobs. Los IDs de aplicación real se indexan en `catalogue.json` al generar los
packs; los previews estáticos ilustran las composiciones con widgets activados
cuando corresponde, nunca su estado runtime después de importar.

| Patrón | Propósito | Duración / easing | Editables | Compatibilidad |
|---|---|---|---|---|
| Editorial reveal | Presentar título con calma | 280 ms / linear | duración | fade_in H11 |
| Name slide | Identificar sin cubrir el contenido | 320 ms / ease_out; salida 220 / ease_in | duración, distancia X 32 | slide_in/out H11 |
| Alert arrival | Llamar atención sin rebote | 240 ms / ease_out | duración, escala inicial .92 | scale_in H11; Trigger del widget por separado |
| Arena celebration | Celebración expresiva y breve | 420 ms / ease_out; salida 240 / ease_in | duración, escala inicial .82 | scale_in/out H11 |
| Chapter cue | Marcar un nuevo bloque | TECH 320 ms / ease_out / X 24; ARENA 260 / ease_out / X 40 | duración, distancia; título via property | slide_in H11 |
| Pause bridge | Cambiar a BRB | 350 ms / linear | duración 100–5000 | Fade de escena H9, no animación de capa |
| Closing breath | Retirar el título al terminar | 400 ms / linear | duración | fade_out H11; no detiene salidas |
| Event acknowledgement | Señalar la aparición de un elemento | 180 ms / linear | duración | fade_in H11; no acredita ejecución de regla |
| Reduced motion | Evitar desplazamiento y zoom | Fade 100 ms / linear; escena Cut | selección explícita de alternativa | H11/H9 existentes, preferencia todavía no vinculada por pack |

Aplicaciones concretas: Editorial reveal → `tech-title-in`; Name slide →
`tech-lower-in/out`; Alert arrival → `tech-alert-in`; Arena celebration →
`reward-in/out`; Chapter cue → `tech-label-in`/`arena-label-in`; Pause bridge →
botón `brb` de ambos Decks; Closing breath → `tech-title-out`; Event
acknowledgement → `tech-indicator-in`/`arena-indicator-in`. Reduced motion es
la receta alternativa del catálogo y el selector de la galería, no un nuevo
tipo serializado. Cada composición puede inspeccionarse desde esa galería.

## Semántica exacta

Fuente: `native/overlays/animation.inc`, contrato H11/H12 y `packs.rs` de la base
auditada. Normalizando el tiempo `t` entre cero y uno:

- `linear`: t.
- `ease_in`: t².
- `ease_out`: 1−(1−t)².
- `ease_in_out`: 2t² antes de .5; 1−2(1−t)² después.

No son los cubic-bezier de interfaz de GPUI. Fade usa la transición oficial y
solo linear. Slide modifica **X**: al entrar parte de `x−distance`, al salir
termina hacia `x−distance`. Un valor negativo entra desde la derecha. No hay
campo de eje Y. Scale usa `scale_from` como factor inicial al entrar y destino
al salir; no añade overshoot ni spring. Mantener posición/encaje oficiales y no
prometer un pivote arbitrario. H13 multiplica distancia por la escala de salida.

Todas las animaciones incluyen `distance` y `scale_from` incluso si el tipo no
los utiliza. 100–10000 ms, distancia finita −1920…1920, escala .1…2. Una operación
por capa, ocho simultáneas máximo; el presupuesto del pack puede ser más bajo.
No encadenar operaciones por un `setTimeout` de la UI: esperar recibo terminal y
barrera del propietario. IDs de operación, pending_ack y cancelación son del
motor. Fuente visible y capa visible son estados diferentes.

Trigger/Show del widget y animación de su capa son acciones distintas. Las
reglas deben resolver ambas cuando corresponda; una animación no dispara una
alerta oculta ni habilita un proveedor. Las salidas requieren su flujo normal.

## Aplicación a las colecciones

CREATOR TECH prioriza fade y desplazamientos cortos para lower thirds y capítulos.
NEON ARENA reserva escala para celebraciones; el gameplay queda quieto. Ambas
colecciones deberían limitar elementos de atención durante el contenido como
recomendación editorial; Community ilustra alerta y recompensa juntas y las
reglas no imponen exclusividad automática.
No se introducen bucles continuos, destellos ni partículas que el motor no tenga.

Cada entrada del catálogo enlaza al manifest, scene/layer e ID de animación real.
La galería reproduce seis ejemplos representativos y una transición a BRB;
el selector permite inspeccionar la composición de las 22 entradas. Ofrece
movimiento reducido. Ese ensayo
no es prueba nativa ni implementación de una preferencia del producto.

## Movimiento reducido

En el prototipo: respetar `prefers-reduced-motion` y el selector explícito;
presentar los cambios sin movimiento. En Motive actual: usar Show/Hide o Fade
100 ms linear; Cut para escena. No serializar duración cero (inválida), ni
afirmar que un flag de catálogo ya controla runtime. Un futuro adaptador puede
resolver esa preferencia antes de la revisión, mostrando la variante elegida.

## Futuro separado

Keyframes, curvas custom, slide vertical, animaciones por máscara, pivotes libres,
transiciones de video alpha y recolor de imagen requieren contratos nuevos y
evidencia nativa. No están en manifests ni reglas de esta entrega.
