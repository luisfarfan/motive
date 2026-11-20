# H22 — Keychain y fronteras nativas

**C: BLOCKED.** No se autorizan paquetes de terceros, credenciales de producción
ni una integración de CEF que dependa de `use-mock-keychain`. Todas las ejecuciones
H22 identifican expresamente ese backend de laboratorio. No se ejecutaron
herramientas ni sondas de credenciales reales para enumerarlas, leerlas,
modificarlas o borrarlas. Seleccionar el proveedor mock no constituye una
observación OS completa de todas las APIs Keychain del árbol; ese alcance
no está medido ni se convierte en un PASS de producción.

La [auditoría posterior del caché](../evidence/H22-background-component-audit.json)
encontró componentes instalados en perfiles privados recién creados: los
callbacks de widgets no cubrían todo el trabajo de servicios de Chromium.
Se detuvieron los siguientes lanzamientos con esos perfiles. Los endpoints
históricos no están observados; no se afirma ausencia de tráfico externo.
La primera candidata de red conservó FAIL: permitió cuatro intentos UDP
de reachability IPv6 fuera del proxy. La siguiente candidata rechaza la
resolución de todos los hosts, incluido el proxy local propio, y desactiva
actualización de componentes/discovery. El piloto nativo de 12 s pasó;
la validación prolongada y de capacidad conserva sus resultados por separado. Mantiene sandbox CEF, verificación TLS
y protecciones de contenido. No usa disable-background-networking ni desactiva
Safe Browsing. Es control de carga propia, **no una frontera OS ni solución C**.

## CEF fijado y alternativa de versión

Se conserva CEF 150.0.19 / Chromium 150.0.7871.252. H19 ya trazó la inicialización
anticipada de OSCryptAsync desde BrowserProcessImpl y su proveedor macOS hasta
KeychainV2/SecItemCopyMatching. Contextos en memoria y cookies deshabilitadas no
eliminan esa inicialización de proceso. Los archivos originales y sus fallos
siguen en H19.

La revisión adicional de upstream CEF `e6035cfb35235e19ea5d5eae62c989b9ef0818dc`
expone `keychain_service_name` y `keychain_account_name` en API 15600. Estas
opciones seleccionan una entrada distinta, potencialmente nueva; no ofrecen
un proveedor sin Keychain. Un namespace propio de Motive podría evitar la
colisión con una entrada compartida, pero todavía requiere política explícita
de consentimiento, autorización para crear/acceder a esa entrada y verificación
con un SDK concreto. No es una solución efímera demostrada ni resuelve el broker
Mach/sandbox. No se justifica cambiar el pin sólo para declarar cerrado ese
gate; no se compiló ni ejecutó otra versión.
Fuentes y hashes: [inventario](../research/h22-security-sources.json),
[API upstream](https://github.com/chromiumembedded/cef/blob/e6035cfb35235e19ea5d5eae62c989b9ef0818dc/include/internal/cef_types.h),
[proveedor Chromium fijado](https://github.com/chromium/chromium/blob/150.0.7871.252/components/os_crypt/async/browser/keychain_key_provider.mm).

## XPC mínimo: frontera observada, no despliegue CEF

[H22-xpc-r1](../evidence/H22-xpc-r1/report.json) ejecutó un servicio XPC propio,
firmado ad-hoc, con **solo** `com.apple.security.app-sandbox=true`. Un archivo
señuelo legible por el owner y un listener loopback vivo fueron controles
positivos. El servicio recibió EPERM al abrir la ruta directamente y al conectar
por TCP. Sí leyó los 28 bytes esperados a través de un descriptor explícitamente
cedido por el owner. La respuesta no transportó el contenido del archivo.
Los procesos observados terminaron y no quedaron PID/birth propios vivos.

El informe original conserva FAIL: `NSNumber` serializó la comparación C como
entero `0`, pero el clasificador exigía el booleano Python `False` por identidad.
La [reclasificación independiente](../evidence/H22-xpc-r1/boundary-reclassification.json)
acepta únicamente `False` o entero exacto cero, conserva el hash del informe y
del stdout originales, y tiene negativos para valores ausentes/falsos ambiguos.
Su PASS está limitado a esas operaciones del servicio; no certifica credenciales,
CEF, GPU, renderer comprometido ni autenticación de Developer ID/Team ID.

## Compatibilidad CEF + App Sandbox: fallo nativo reproducido

[H22-cef-appsandbox-r1](../evidence/H22-cef-appsandbox-r1/report.json) usó una
candidata separada con el mismo CEF fijado, sandbox CEF habilitado, backend mock
explícito, main con App Sandbox y helpers con App Sandbox + inherit. No añadió
entitlements de red, archivos, Mach exceptions, JIT inseguro o permisos globales.
La salida propia se creó dentro del contenedor privado de esa identidad.

El host llegó a `initialize_enter`, cargó el framework y terminó por SIGTRAP
(retorno −5) en `CefInitialize`. El
[stderr conservado](../evidence/H22-cef-appsandbox-r1/supervisor-stderr.log)
identifica `base/apple/mach_port_rendezvous_mac.cc:159`: `bootstrap_check_in`
del servicio Mach de Chromium fue denegado con error 1100. No llegó a producir
frames. El supervisor observó un único host, 108,91 MiB de RSS pico y cierre
completo. Esto demuestra el fallo de **esta configuración**, no una imposibilidad
matemática de cualquier integración modificada.

El [código Chromium fijado](https://github.com/chromium/chromium/blob/150.0.7871.252/base/apple/mach_port_rendezvous_mac.cc)
exige ese registro durante el arranque. La prueba confirma la hipótesis estática;
no se añadieron excepciones para obtener un PASS. Un XPCService mínimo funcional
no elimina la dependencia interna de Chromium de su broker Mach.

## Alcance de App Sandbox y ruta arquitectónica

Las APIs públicas de XPC y App Sandbox permiten separar capacidades; la prueba
mínima acredita parte de esa frontera. No existe aquí una configuración soportada
y verificada que simultáneamente aloje este CEF, evite el Keychain real y confine
todas sus autoridades. App Sandbox tampoco implica por sí solo prohibición de
todo Keychain: macOS distingue modelos de Keychain y grupos de acceso.
Referencias: [servicios XPC](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingXPCServices.html),
[entitlements e herencia](https://developer.apple.com/library/archive/documentation/Miscellaneous/Reference/EntitlementKeyReference/Chapters/EnablingAppSandbox.html),
[modelos de Keychain](https://developer.apple.com/documentation/technotes/tn3137-on-mac-keychains).

La autorización actual cubre el laboratorio H22. Una conexión futura con
Production requiere el handoff explícito de H23 y una decisión sobre el bloqueo
de credenciales; este documento no concede esa autorización. Para terceros se
requiere otra revisión: soporte upstream para un
proveedor efímero sin Keychain y un broker compatible con confinamiento OS, o
un motor web con aislamiento administrado por el sistema cuya salida de frames
y semántica se verifiquen independientemente. Un fork que cambie OSCrypt/Mach
necesita mantenimiento y auditoría propios; no es la solución entregada aquí.
No se enviaron mensajes/issues a upstream ni se modificó la política del sistema.

## Frontera por proceso en el CEF nativo

La [sonda nativa](../evidence/H22-native-boundary-r1/boundary-analysis.json)
observa un archivo señuelo propio de 0600 y el endpoint loopback propio 18719.
Main actúa como control positivo. Los helpers prueban después de
`CefScopedSandboxContext::Initialize()` y antes de cargar el framework; esto
no equivale a ejecutar JavaScript con esas capacidades. No toca credenciales.

| Rol observado | Archivo directo | Conexión propia | Argumento Seatbelt |
|---|---|---|---|
| Browser | Permitido | Permitida | No, control positivo |
| Renderer, dos procesos | EPERM | EPERM | Sí |
| GPU | EPERM | EPERM | Sí |
| Network service | EPERM | Permitida | Sí |
| Storage service | EPERM | EPERM | Sí |
| Utility | Permitido | Permitida | No |

La inicialización del helper devolvió éxito también para Utility. Ese éxito
no acredita confinamiento. La sonda sólo imprime roles finitos, PID, booleanos
y errno; el auditor cruza PID/birth cuando el supervisor alcanzó a observarlo.
Un helper de vida corta puede conservar únicamente la atribución del ejecutable
instrumentado y su stderr privado. No se inventa una identidad ni un subtipo.
Las denegaciones observadas no certifican todos los archivos, destinos o IPC.

El servicio de red y el browser siguen siendo autoridades compartidas. HMAC
en el transporte H22 autentica al poseedor del canal, pero no confina un host
comprometido ni vuelve confiable el contenido que ese host produjo. Un broker
de capacidades debe diseñarse para el árbol completo y su IPC, no sólo para
los RequestContexts. El resultado de esta auditoría es **PASS de observación,
BLOCKED de seguridad de terceros**.

## Diagnóstico del primer perfil de red

[H22-network-pilot-r1](../evidence/H22-network-pilot-r1/diagnosis.json)
retiene NetLog Default, hash y FAIL. El canary proxy recibió diez conexiones;
el destino directo propio ninguna. Hubo cuatro UDP_CONNECT a la dirección
IPv6 de reachability de Chromium, todos con net_error −109. No hubo captura
de paquetes y no se afirma ausencia general de egress.

El [MappedHostResolver fijado](https://chromium.googlesource.com/chromium/src/+/150.0.7871.252/net/dns/mapped_host_resolver.cc)
reconoce `^NOTFOUND`. La receta antigua con `~NOTFOUND` no aplica a este pin:
NetLog conserva su resolución como hostname. Excluir el literal del proxy
también pasa por StartIPv6ReachabilityCheck.
[HostResolverManager fijado](https://chromium.googlesource.com/chromium/src/+/150.0.7871.252/net/dns/host_resolver_manager.cc)
conecta un socket UDP y consulta la dirección local; ese fragmento no llama
Send. No se habilitó un flag especulativo de IPv6 ni se cambió la ruta del SO.

`closed-resolver-v2` usa `MAP * ^NOTFOUND` sin excepciones. El control propio
exige el error concreto ERR_PROXY_CONNECTION_FAILED en CEF y NetLog, proxy
resuelto explícitamente al endpoint propio, cero eventos TCP_CONNECT_ATTEMPT/
UDP_CONNECT, cero hits en ambos listeners propios y ningún manifest instalado.
Un log vacío o sin el control no pasa. La política es reproducibilidad del
laboratorio, no firewall ni sandbox de red del árbol. Los lanzadores H22
rechazan candidatos anteriores, incluso si contienen `network_lab=true`.

El [segundo piloto](../evidence/H22-network-pilot-r2/analysis-current.json)
observó el control con error −130, 550 eventos NetLog, cero eventos de socket,
cero hits a los listeners propios y ningún manifest. El host produjo frames
reales y cerró con cero leases; RSS pico 656,08 MiB. Su PASS de 12 s no sustituye
la observación prolongada ni cambia C: BLOCKED. El backend permanece mock.

El [contraste instrumentado de 600 s](../evidence/H22-cold4-memory600-r1/network-analysis.json)
extiende esa observación: 986 eventos, control −130, cero eventos de socket,
cero conexiones a listeners propios y ningún manifest. No amplía el alcance
a otros stacks de red o a código nativo comprometido.

Los 39 casos de la [matriz final](../evidence/H22-capacity-final-v2.json)
pasan su control de red de laboratorio, incluidos los tres soaks de 600 s.
Cada caso conserva su propio NetLog y control positivo; no se infiere un PASS
por reutilizar el mismo binario. Esto no modifica C: BLOCKED ni la distinción
entre observación Chromium y confinamiento OS del árbol.

El campo histórico `third_party_execution=false` de la fixture declara el
inventario de widgets solicitado; no es una auditoría de todo el código o
componentes de Chromium. El hallazgo posterior de manifests conserva esa
distinción y no permite afirmar que se haya observado su origen de red o
si llegaron a ejecutarse. No se incorporan binarios de esos componentes a
la entrega; sus perfiles locales y hallazgos permanecen como evidencia.
