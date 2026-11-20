# H21/C8 — protocolo de A/V físico y presupuesto de incertidumbre

**PARTIAL; no hay certificación de ≤40 ms/h.** El offset central exploratorio
de C7 r3 no basta: su intervalo de deriva llega a 61,73/63,83 ms/h. La repetición
C8 de un minuto contiene contactos visibles pero no una serie acústica
identificada sin ambigüedad. No se declara un defecto de sincronía por estos
datos. Los archivos privados y la revisión se enlazan desde el informe C8.

## Montaje propuesto, todavía no ejecutado

Usar una referencia física rígida con cambio óptico y acústico de un mismo
evento, por ejemplo una claqueta cuyo contacto pueda verse lateralmente.
Una referencia LED/click accionada por un mismo pulso necesita calibrar por
separado los retardos LED/transductor; compartir una orden eléctrica no prueba
simultaneidad física. No sustituirla por un tono interno de Motive.

Preparar cámara y micrófono seleccionados explícitamente, sin contenido privado
incidental; fijar posición, iluminación, exposición y distancia. Medir la
distancia entre contacto y micrófono y conservar su incertidumbre. Registrar
el modo de procesamiento de micrófono observado, frecuencia y configuración;
no cambiar preferencias globales automáticamente. Verificar antes de la hora
que cada evento produce un transitorio identificable sin clipping ni un segundo
evento acústico ambiguo. Si no ocurre, corregir el montaje antes de grabar.

Registrar una hora real con 10–20 eventos en bloques inicial, medio y final,
espaciados de forma identificable y no perfectamente periódica. Conservar la
referencia completa visible y audio físico sin tonos que enmascaren contactos.
Realizar la sesión de uso en paralelo sólo cuando el montaje sea válido. Un
invitado generado no sustituye una conversación remota.

## Medición y criterio previamente fijados

1. Decodificar ambos medios completos, conservar SHA-256, PTS de frames y PCM.
   No usar número de frame/FPS nominal para sustituir el PTS observado.
2. Revisar cada contacto a ciegas respecto del offset esperado. Anotar el último
   frame inequívocamente abierto y el primero inequívocamente cerrado; incluir
   exposición, rolling shutter y oclusión. No interpolar subframe por conveniencia.
3. Seleccionar un transitorio acústico único por evento. Registrar intervalo de
   comienzo, ruido de base, alternativas y criterio de rechazo antes de emparejar.
   Corregir propagación sólo con distancia medida y su incertidumbre.
4. Para video `V=[v_lo,v_hi]` y audio `A=[a_lo,a_hi]`, usar
   `D=[a_lo-v_hi, a_hi-v_lo]`, ampliado con los errores de calibración. Mantener
   el signo audio menos video. Aceptar offset absoluto sólo si el intervalo
   completo está dentro de `[-0,080,+0,080] s`.
5. Para bloques inicial/final con intervalos `D0,D1` y separación real `T`,
   la deriva compatible es `[(D1.lo-D0.hi),(D1.hi-D0.lo)] × 3600/T`.
   Aceptar sólo si todo el intervalo está dentro de `[-0,040,+0,040] s/h` y
   el bloque medio no muestra un salto que ese extremo oculte.
   Si `T` tiene incertidumbre, conservar un intervalo positivo y evaluar los
   cuatro cocientes entre extremos antes de obtener el mínimo y máximo;
   no sustituir la separación observada por una hora nominal.
6. Separar error sistemático de variación aleatoria. Muchos eventos pueden
   reducir la estimación aleatoria bajo un modelo justificado; no eliminan por
   sí solos exposición, propagación desconocida o sesgo del detector. Una cámara
   30 FPS puede dejar un presupuesto insuficiente; registrar PARTIAL o utilizar
   una referencia temporal mejor calibrada, sin relajar los límites.

La tabla de eventos debe incluir ID, PTS/intervalos, confianza y causa de rechazo;
los rechazados permanecen. No emparejar sólo el pico más cercano si hay eventos
repetidos, voz o golpes de mesa. El offset de AAC/recipiente se deriva de PTS reales,
sin aplicar un desplazamiento elegido para que el resultado pase.

## Ganancia y cierre

Comprobar señal pre-fader, post-fader y mix por separado. Si la entrada alcanza
clipping, parar/reajustar físicamente o usar un cambio temporal autorizado del
dispositivo; bajar el fader no recupera una forma de onda ya recortada. Conservar
todos los bloques rechazados. Habla normal y contactos de referencia necesitan
SNR suficiente, no una ganancia tan baja que la medida desaparezca.

Restaurar el scalar exacto, cerrar cámara/micrófono, comprobar owner y receptor
terminados, retirar assertions temporales y liberar el lock sólo después de
probar que no quedan procesos propios. La aceptación necesita el montaje y
participación física; un agente sin ellos puede preparar y analizar el protocolo,
pero no producir evidencia física nueva ni certificar sus resultados.
