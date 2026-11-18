# Goal Celebration — Web Edition

Arte y animación originales. HTML/CSS/JS locales sin CDN. Título, equipo,
marcador, fondo, acento, permanencia, modo de prueba y movimiento reducido se
configuran según `web-element.json`. Horizontal/vertical responden al viewport.
Entrada geométrica, hold con barra de progreso y salida se implementan con Web
Animations API; reducción elimina desplazamientos y conserva fades de 100 ms.

```js
MotiveElement.on('goal.scored', async (event, {signal}) => {
  // event: {team: string <=60, home: integer 0..99, away: integer 0..99}
  // Solo estado visual; señal cancelable. Sin control del estudio.
});
```

La implementación completa está en `goal.mjs`. `runtime.mjs` es una copia
reproducible del SDK visual, no una dependencia descargada. Después de editar:

```sh
python3 element-lab/web-elements/build_example.py
python3 element-lab/sdk/motive_elements.py web-validate element-lab/web-elements/goal-celebration
python3 element-lab/sdk/motive_elements.py package element-lab/web-elements/goal-celebration --web -o element-lab/dist/goal.motiveweb
```

El entry espera al harness con su contrato y canal; abrir el HTML solo no crea un
host ni carga eventos. Usar `serve` y pulsar Probar gol. Los paquetes llevan
checksums reales y licencia, pero no prueban identidad/autenticidad del autor.
No hay Browser Source, captura WKWebView/CEF ni frames libobs en esta entrega.
