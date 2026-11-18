# H17 — selección temporal del observador de foco

Corrección del verificador: **PASS** offline. Ensayo físico B7 original:
**BLOCKED**, sin modificación retrospectiva.

`var/evidence/h17-focus-b7-default/report.json` conserva 54 observaciones con
acuerdo entre el proceso independiente y la fixture. Falló al crear el marcador
`fixture_return`. El probe termina en uptime `122277.00137704167`; la observación
que guardó `observe()` tiene uptime `122276.02096120834`, PID 37620, Window ID
15289, `app_active=true` y `key_window=true`. Su edad al final del probe es
0,980416 s y pasa el gate original.

La fixture publicó después otro estado en `122277.05869804167`, 57,321 ms tras
el final del probe. Es la misma identidad y el foco también concuerda, pero
`corroborate()` lo rechaza porque su timestamp está en el futuro respecto al
probe. `mark()` releía el log creciente y seleccionaba `states[-1]`, de modo que
podía cambiar la pareja observada aunque la evidencia original era válida.
`observe()` tenía el mismo problema si el log crecía antes de su primera lectura.

El proceso `mark()` que falló no conservó su argumento seleccionado ni el anchor.
Por eso la fila de +57,321 ms demuestra el mecanismo con evidencia real, sin
afirmar que se observó directamente cuál fila usó ese proceso. La extracción,
hashes de informes/fixture/markers originales y ambas evaluaciones están en
`var/evidence/h17-focus-verifier-audit-01/report.json`.

Ambas rutas usan ahora `fixture_at_probe_end()`: el estado con timestamp mayor
que no exceda `probe.after_s`; en empates, el último registro del log. No filtra
por identidad ni por concordancia para encontrar una muestra favorable. Después
se ejecutan los mismos gates: PID, Window ID, observador independiente, app/key,
intervalo del probe ≤0,5 s y muestra desde `probe.before_s - 1,5 s` hasta su fin.
El marcador además conserva el límite de 1,5 s entre probe y anchor actual.

Sin muestra anterior o con tiempo ausente/no finito, la evaluación queda BLOCKED.
La muestra más reciente con identidad o foco contradictorios tampoco puede ser
sustituida por una anterior favorable. No se amplían umbrales, duración del
ensayo, ventanas de cobertura ni gates de píxeles.

Pruebas offline:

- `test_h15_focus.py`: **PASS**, 4 tests; crecimiento del log, selección temporal,
  bordes de frescura, evidencia ausente/malformada y contradicciones.
- `test_h14_collection.py`: **PASS**, 13 tests históricos de colección/foco,
  identidad, medios y ownership.
- `test_h17_show_recovery.py`: **PASS**, 5 tests del runner independiente.
- Compilación Python y `git diff --check`: **PASS**.

No se ejecutó otro ensayo físico para esta corrección. La nueva selección
temporal no acredita frescura de captura ni entrega de medios; hace reproducible
la asociación entre dos observaciones existentes.
