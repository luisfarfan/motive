# H11 — Investigación comparativa y elección mínima

Consulta documental: **17 de noviembre de 2026, America/Lima**. Se consultaron
documentación oficial y código abierto; no se abrió Meld, no se extrajeron
recursos propietarios y no se descargaron widgets de terceros. Esta comparación
describe capacidades documentadas, no una prueba de paridad ni un benchmark.
Las páginas comerciales pueden cambiar; la implementación de Motive se contrasta
con el árbol y los binarios **OBS 33.0.1** ya fijados por el proyecto.

## Capacidades y experiencia

| Área | StreamElements | Meld Studio | OBS / decisión para Motive |
|---|---|---|---|
| Composición | Editor de overlays con resolución, widgets y vista previa; se entrega a la aplicación de emisión mediante una URL de Browser Source. [SE: inicio](https://docs.streamelements.com/overlays/getting-started), [emisión](https://docs.streamelements.com/overlays/broadcast-software). | Canvas con capas, Inspector, orden, visibilidad, grupos y duplicadores de capas/escenas. [Meld: capas](https://meldstudio.co/docs/layers/). | Escenas y scene items ya resuelven composición, referencias y transformaciones. Extender las definiciones de Motive y mantener el único grafo libobs. [Scene API](https://docs.obsproject.com/reference-scenes). |
| Texto, imágenes y video | Los widgets admiten HTML/CSS/JS y referencias a recursos mediante campos tipados. [SE: estructura](https://docs.streamelements.com/overlays/widget-structure). | Documenta texto con fuentes/colores/fondo, imágenes PNG/JPEG/GIF/WebP y medios MP4/MOV/WebM. El Inspector configura reproducción y visibilidad. [Meld: capas](https://meldstudio.co/docs/layers/). | Reutilizar `text_ft2_source`, `image_source`, `ffmpeg_source`; restringir el producto a formatos y propiedades realmente verificados. [Texto](https://obsproject.com/kb/text-sources), [imagen](https://obsproject.com/kb/image-sources), [medios](https://obsproject.com/kb/media-sources). |
| Propiedades editables | Los campos JSON generan controles, incluidos texto, color, listas, sliders y referencias a imagen/video/sonido; el usuario configura sin editar código. [SE: campos](https://docs.streamelements.com/overlays/widget-structure). | Inspector para propiedades; Spark también permite refinarlas conversacionalmente. [Capas](https://meldstudio.co/docs/layers/), [Spark](https://meldstudio.co/docs/spark/). | Tipos y límites en Rust, un único comando validado por propiedad/acción, controles GPUI futuros sobre `Production`. No aceptar nombres de plugins ni settings OBS arbitrarios desde MCP. |
| Eventos y estado | `onWidgetLoad`, `onEventReceived` y `onSessionUpdate`; chat, follows, subs, tips, contadores y cambios de sesión. La API permite almacenamiento y control de cola. [SE: eventos](https://docs.streamelements.com/overlays/events), [SE_API](https://docs.streamelements.com/overlays/custom-widget). | Widgets de chat, alertas y temporizadores; eventos y disponibilidad dependen de la plataforma. Se pueden configurar entrada animada y ocultación. [Meld: widgets](https://meldstudio.co/docs/widget/). | Empezar con eventos locales tipados y estados limitados de countdown/alerta/lower third. Los adaptadores externos futuros traducen al mismo contrato; el compositor no conoce Twitch ni otro proveedor. |
| Animación y escenas | CSS soporta animaciones/transiciones; widgets pueden administrar la cola de alertas. No se deduce una garantía de continuidad al recrear un Browser Source. [Estructura](https://docs.streamelements.com/overlays/widget-structure), [SE_API](https://docs.streamelements.com/overlays/custom-widget). | Documenta Cut, Fade, Morph, Move, Stinger y easing; transiciones de canvas principal/vertical configurables. [Meld: transiciones](https://meldstudio.co/docs/settings/). | Conservar H9 Cut/Fade. Evaluar transiciones de visibilidad de scene items; para posición/escala, interpolación acotada mediante tick nativo y transforms existentes, sin renderer ni reloj MCP adicionales. [API de escena](https://docs.obsproject.com/reference-scenes). |
| Reutilización y distribución | Galería de temas, duplicación de widgets y un Browser Source reutilizado entre escenas. La guía recomienda eliminar AlertBoxes duplicados para evitar audio repetido. Las URLs contienen tokens privados. [SE: guía](https://support.streamelements.com/hc/en-us/articles/10474479981074-Overlays-The-Complete-Guide-Gallery-OBS-Setup-Widgets-Alerts-Data), [seguridad URL](https://docs.streamelements.com/selive/guides/overlays-and-alerts). | Galería de Spark, enlaces para insertar elementos y personalización posterior. [Meld: Spark](https://meldstudio.co/docs/spark/). | Presets originales versionados y editables; assets administrados por ID, fuentes compartidas por referencia. No tratar una URL privada de overlay como un archivo público exportable. |
| Creación mediante agentes | Custom Widgets son una superficie programable, pero no constituyen por sí solos un contrato local de control de producción. [SE_API](https://docs.streamelements.com/overlays/custom-widget). | Spark genera HTML/CSS/JS en servidores y lo presenta como capas de navegador; ofrece chat, galería, iteración y eventos. Su documentación distingue el espacio web del control de escenas del escritorio. [Meld: Spark](https://meldstudio.co/docs/spark/). | El agente produce definiciones/recursos; Motive valida y ejecuta. Mantener CLI/MCP como interfaz del núcleo, sin dependencia de un proveedor de modelos ni participación del LLM por frame. |
| Audio de medios/web | Una alerta puede aportar sonido; varias instancias pueden duplicarlo. [SE: guía](https://support.streamelements.com/hc/en-us/articles/10474479981074-Overlays-The-Complete-Guide-Gallery-OBS-Setup-Widgets-Alerts-Data). | Browser permite añadir una pista; media crea una pista asociada. [Meld: capas](https://meldstudio.co/docs/layers/). | `ffmpeg_source` puede producir video y audio. H11 debe bloquear explícitamente su ruteo audible hasta integrarlo con el contrato H10; ninguna segunda política de mezcla. [API de fuentes](https://docs.obsproject.com/reference-sources). |

## Dependencias, rendimiento y coste técnico

Coste **relativo de integración en Motive**, inferido del código y de las
dependencias, no horas estimadas ni precios comerciales. No se midió CPU/RSS de
StreamElements o Meld. Sus afirmaciones promocionales sobre rendimiento no son
evidencia de que un overlay cueste cero recursos.

| Ruta | Dependencias y estado | Coste relativo | Medición necesaria |
|---|---|---|---|
| Texto/imagen/color OBS | Plugins ARM64 existentes, FreeType/decodificadores y gráficos libobs. | Bajo/medio: validación y ciclo de vida; no escribir rasterizador de texto propio. | Primera carga, actualizaciones, memoria por dimensiones y comportamiento oculto. |
| Video local OBS | `ffmpeg_source`, decodificador, timestamps y callbacks de medios. | Medio: admisión segura del archivo, estados, EOF/reinicio y audio explícito. | Tiempo al primer frame, CPU/RSS, alpha, pausa, loop y recuperación sin recrear encoder. |
| Widgets nativos declarativos | Fuentes OBS + estado temporal pequeño propio, sin servicio de red. | Medio: límites, cancelación, concurrencia, persistencia de definición frente a runtime. | Carga por widgets activos/inactivos y expiración sin cliente conectado. |
| HTML mediante obs-browser | CEF, procesos auxiliares, recursos de Chromium, empaquetado/firma y control de capacidades. El módulo existe en el bundle, pero su carga en Motive no se deduce de esa presencia. | Alto: spike separado; no condicionar los overlays nativos a su éxito. | Carga real, transparencia, FPS, procesos, cierre, RSS/CPU e intentos de acceso no permitido. |
| Overlay alojado de StreamElements / Spark | Browser Source más servicio remoto, credenciales/eventos y políticas del proveedor. | Alto para importación segura/interoperabilidad; fuera del ruteo público de H11. | Dependencia de red, recuperación, propiedad de recursos y duplicación de eventos/audio. |

La documentación de OBS identifica Browser Source como navegador completo con
archivos locales, URL, tamaño y FPS configurables. El proyecto `obs-browser`
añade CEF y bindings JavaScript propios; no es una sandbox específica para agentes
que pueda asumirse segura sin revisión. [Browser Source](https://obsproject.com/kb/browser-source),
[repositorio oficial](https://github.com/obsproject/obs-browser).
Un importador futuro necesita un manifiesto acotado de recursos/capacidades,
identidad propia y política explícita de red, navegación, audio y APIs locales.
La exportación por enlace de terceros no proporciona automáticamente esas garantías.

## Qué está realmente disponible en esta distribución

Inspección estática de `.deps/OBS.app/Contents/PlugIns`, usando `file` sobre cada
binario; **no se cargaron plugins ni se abrieron dispositivos en esta investigación**:

| Plugin | Resultado | Fuente/API relevante |
|---|---|---|
| `text-freetype2` | Mach-O arm64 presente | `text_ft2_source`, implementación versionada 2; GDI+ es Windows y no está presente como `obs-text`. |
| `image-source` | Mach-O arm64 presente | `image_source` y `color_source` versionada 3. |
| `obs-ffmpeg` | Mach-O arm64 presente y ya cargado por Motive | `ffmpeg_source`, capacidades de video asíncrono y audio. |
| `obs-filters` | Mach-O arm64 presente | Evaluar solo filtros visuales necesarios; su presencia no obliga a exponer filtros arbitrarios. |
| `obs-browser` | Mach-O arm64 presente | Evidencia de distribución; carga, aislamiento y compatibilidad con host Motive pendientes del spike. |

El texto FreeType ofrece font, contenido, dos colores con alpha, contorno,
sombra, ancho y wrapping. No aparecen propiedades de fondo ni alineación de
párrafo en sus properties 33.0.1: componer un fondo como otra fuente y distinguir
alineación del scene item de alineación de líneas. La tipografía disponible y
sus glifos requieren verificación local. [Implementación fijada](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/text-freetype2/text-freetype2.c).

`ffmpeg_source` registra play/pause, restart, stop, duration, time y state, además
de activación/desactivación y opciones de loop/reinicio. No confundir conservar
la instancia con conservar la posición si `restart_on_activate` sigue habilitado.
[Implementación fijada](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/obs-ffmpeg/obs-ffmpeg-source.c).

`image_source` y `color_source` resuelven imagen y relleno rectangular; se debe
comprobar la versión registrada de cada fuente antes de crearla. Los límites de
admisión de Motive deben ser más estrictos que los que permite el plugin.
[Imagen](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/image-source/image-source.c),
[color](https://github.com/obsproject/obs-studio/blob/33.0.1/plugins/image-source/color-source.c).

## Decisiones para comenzar a implementar

1. Reutilizar fuentes, filtros visuales acotados, scene items y referencias OBS.
   Usar `obs_source_update` cuando cambian propiedades compatibles, en lugar de
   recrear fuentes y encoders. Verificar los IDs de versión disponibles.
2. Separar definiciones/validación, assets administrados y ejecución temporal.
   `Production` sigue siendo el único punto de mutación; ni GPUI ni un widget
   adquieren un segundo estado autoritativo.
3. Hacer la importación una capacidad explícita y limitada. IDs estables en
   documentos; rutas internas resueltas por Motive, nunca una API MCP de lectura
   arbitraria del filesystem. Verificar contenido/dimensiones antes de OBS.
4. Las animaciones usan el reloj/tick nativo, transforms y transiciones oficiales.
   Duración, concurrencia, repetición y cancelación tienen reglas finitas.
   Widgets y timers no necesitan un bus distribuido ni un motor de workflows.
5. Mantener video local funcional sin audio audible implícito. Cualquier audio
   futuro se debe registrar y controlar por la misma política H10.
6. Evaluar CEF en un experimento original sin contenido ni URLs de terceros.
   Una página local puede intentar red y lectura local: es un dato de entrada
   no confiable, no una autorización. Si requiere cambios extensos o no hay
   aislamiento verificable, documentar el bloqueo y mantener cerrado el contrato.

La matriz informa la elección; solo grabaciones decodificadas, RTMP local y
pruebas de ciclo de vida pueden establecer que la implementación funciona.
Ninguna función de la competencia se declara ausente universalmente por no
aparecer en estas fuentes, y ninguna capacidad de Motive se declara implementada
por esta investigación.
