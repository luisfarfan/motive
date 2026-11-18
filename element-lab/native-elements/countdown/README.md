# Countdown Card

Elemento individual v1; recurso PNG original con procedencia y licencia.
`element.json` contiene anatomía, propiedades, estados, acciones, variantes warm/cool
y ambos layouts. `compiled/` es un candidato CreatorPack v1 validado con Rust.
`preview/index.html` muestra una aproximación estática, no frames de Motive.

Desde la raíz del worktree:

```sh
python3 element-lab/sdk/motive_elements.py validate element-lab/native-elements/countdown
python3 element-lab/sdk/motive_elements.py pack element-lab/native-elements/countdown --variant cool --set 'title="Mi título"' -o element-lab/.scratch/countdown-custom
python3 element-lab/sdk/motive_elements.py compose element-lab/native-elements/countdown --single-scene --id countdown-example -o element-lab/.scratch/countdown-composition
```

| Propiedad | Etiqueta | Alcance |
|---|---|---|
| title | Título | creatorpack_property |
| description | Mensaje | creatorpack_property |
| background | Fondo | compile_time |
| accent | Acento | compile_time |
| opacity | Opacidad | compile_time |
| horizontal-x | Posición X horizontal | compile_time |
| vertical-y | Posición Y vertical | compile_time |
| duration | Tiempo (ms) | compile_time |

Las reglas exportadas comienzan deshabilitadas. Animaciones entry/exit y eventos
son intenciones reales del contrato, validadas offline. Requieren IDs resueltos,
escena activa, instalación oficial y observación nativa posterior. `animation_ref`
resuelve la animación después de aplicar sus propiedades. No hay scheduler local.

- Preview esquemático, no equivalencia de píxeles con libobs.
- El motivo decorativo es una capa independiente y permanece visible.
- Las propiedades compile_time generan otra definición; no amplían las cuatro properties de CreatorPack v1.
