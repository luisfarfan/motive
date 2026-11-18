# Compositor declarativo

Implementación en `../sdk/compiler.py` y `../sdk/modular.py`. El schema admite
primitivas del contrato Rust y grupos con referencias locales. DFS detecta
ciclos (también desconectados), nodos ausentes y no alcanzables. No se descargan
dependencias: v1 solo acepta dependencias embebidas, fijadas por versión.

```sh
python3 element-lab/sdk/motive_elements.py select creator-experience/packs/creator-tech --scenes tech-starting -o element-lab/.scratch/tech-min
python3 element-lab/sdk/motive_elements.py select creator-experience/packs/neon-arena --scenes arena-starting -o element-lab/.scratch/arena-min
python3 element-lab/sdk/motive_elements.py compose element-lab/.scratch/tech-min element-lab/.scratch/arena-min -o element-lab/.scratch/two-starting
```

`--sources` selecciona elementos existentes por ID de fuente; si una fuente no
aparece en las escenas seleccionadas, se rechaza. Se conservan solo dependencias
alcanzables. Las reglas con cualquier referencia fuera de la selección se quitan
enteras y se informan. Las animaciones y properties huérfanas también se informan.
No se reescribe una regla parcialmente para cambiar su significado.

La combinación namespacea escenas/fuentes/capas/animaciones/properties/reglas;
las condiciones button_id/name también reciben namespace, listado en el informe.
Toda regla queda desarmada. Deduplicación de recursos por hash + tipo + dimensiones
+ duración + bytes. Fuentes independientes siguen independientes. Colisiones o
cuotas excedidas fallan; no se eliminan escenas para hacer caber el resultado.
Variables de reglas y mezclas de licencias diferentes exigen un adaptador futuro
revisado: se rechazan explícitamente. No se trasladan Decks; los nuevos bindings
se revisarán en el instalador oficial. No se inventan botones con referencias
inválidas ni se instala un plan.
