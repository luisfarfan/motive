use crate::core::{Command, data_dir, error, parse_command};
use serde_json::{Value, json};
use std::{
    fs,
    io::{self, BufRead, BufReader, Read, Write},
    os::unix::{
        fs::{DirBuilderExt, PermissionsExt},
        net::{UnixListener, UnixStream},
    },
    path::PathBuf,
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
        mpsc::{self, Receiver, SyncSender},
    },
    thread,
    time::Duration,
};

const MAX_MESSAGE: u64 = 65536;
// Requests stay narrow; status can contain a v4 project plus overlay/runtime
// metadata. A lost oversized mutation reply must not become a false failure.
const MAX_RESPONSE: u64 = 1024 * 1024;
pub struct Request {
    pub command: Command,
    pub reply: SyncSender<Value>,
    pub origin: &'static str,
}
pub struct Server {
    stop: Arc<AtomicBool>,
    thread: Option<thread::JoinHandle<()>>,
    path: PathBuf,
}
pub fn socket_path() -> PathBuf {
    data_dir().join("run/motive.sock")
}

pub fn read_message(reader: &mut impl BufRead) -> io::Result<Option<Value>> {
    read_frame(reader, MAX_MESSAGE)
}

fn read_response(reader: &mut impl BufRead) -> io::Result<Option<Value>> {
    read_frame(reader, MAX_RESPONSE)
}

fn read_frame(reader: &mut impl BufRead, limit: u64) -> io::Result<Option<Value>> {
    let mut line = String::new();
    let count = reader.take(limit + 1).read_line(&mut line)?;
    if count == 0 {
        return Ok(None);
    }
    if count as u64 > limit || !line.ends_with('\n') {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "Mensaje demasiado grande o incompleto",
        ));
    }
    serde_json::from_str(&line)
        .map(Some)
        .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))
}

impl Server {
    pub fn start() -> anyhow::Result<(Self, Receiver<Request>)> {
        let dir = data_dir().join("run");
        fs::DirBuilder::new()
            .recursive(true)
            .mode(0o700)
            .create(&dir)?;
        fs::set_permissions(&dir, fs::Permissions::from_mode(0o700))?;
        let path = socket_path();
        // Never unlink another instance's socket. A stale socket requires explicit cleanup.
        let listener = UnixListener::bind(&path)
            .map_err(|e| anyhow::anyhow!("CONTROL_UNAVAILABLE: {} ({e})", path.display()))?;
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600))?;
        listener.set_nonblocking(true)?;
        let (tx, rx) = mpsc::sync_channel::<Request>(32);
        let stop = Arc::new(AtomicBool::new(false));
        let shutdown = stop.clone();
        let thread = thread::spawn(move || {
            while !shutdown.load(Ordering::Relaxed) {
                match listener.accept() {
                    Ok((mut stream, _)) => {
                        // Darwin accepts inherit the listener's nonblocking flag.
                        // A valid frame may arrive after accept or in fragments;
                        // use bounded blocking IO on this control worker only.
                        if stream
                            .set_nonblocking(false)
                            .and_then(|_| stream.set_read_timeout(Some(Duration::from_secs(5))))
                            .and_then(|_| stream.set_write_timeout(Some(Duration::from_secs(5))))
                            .is_err()
                        {
                            continue;
                        }
                        let result = match read_message(&mut BufReader::new(&stream)) {
                            Ok(Some(value)) => {
                                let origin = if value["origin"] == "mcp" {
                                    "MCP"
                                } else {
                                    "CLI"
                                };
                                match parse_command(value["command"].clone()) {
                                    Ok(command) => {
                                        let (reply, answer) = mpsc::sync_channel(1);
                                        if tx
                                            .try_send(Request {
                                                command,
                                                reply,
                                                origin,
                                            })
                                            .is_err()
                                        {
                                            error("BUSY", "Cola de control ocupada")
                                        } else {
                                            answer.recv_timeout(Duration::from_secs(5)).unwrap_or_else(|_|error("TIMEOUT","Estado de operación desconocido; consulta status antes de reintentar"))
                                        }
                                    }
                                    Err(_) => error(
                                        "INVALID_ARGUMENT",
                                        "Invalid command fields or values",
                                    ),
                                }
                            }
                            Ok(None) => continue,
                            Err(e) => error("INVALID_REQUEST", e),
                        };
                        let _ = writeln!(stream, "{result}");
                    }
                    Err(e) if e.kind() == io::ErrorKind::WouldBlock => {
                        thread::sleep(Duration::from_millis(10))
                    }
                    Err(_) => break,
                }
            }
        });
        Ok((
            Self {
                stop,
                thread: Some(thread),
                path,
            },
            rx,
        ))
    }
}
impl Drop for Server {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Relaxed);
        if let Some(t) = self.thread.take() {
            let _ = t.join();
        }
        let _ = fs::remove_file(&self.path);
    }
}

pub fn send(command: Value, origin: &str) -> Value {
    // Assemble one complete frame before connecting. Never retry a mutation:
    // the core may already have applied it when a response is lost.
    let query = crate::core::overlays::protocol::is_query(command["op"].as_str().unwrap_or(""))
        || matches!(
            command["op"].as_str(),
            Some(
                "status"
                    | "audio_mixer"
                    | "scenes"
                    | "devices"
                    | "encoders"
                    | "output_capabilities"
                    | "output_profiles"
                    | "preflight_output"
                    | "credential_status"
            )
        );
    let mut payload = json!({"command":command,"origin":origin}).to_string();
    payload.push('\n');
    let attempt = || -> anyhow::Result<Value> {
        let mut stream = UnixStream::connect(socket_path())?;
        stream.set_read_timeout(Some(Duration::from_secs(7)))?;
        stream.set_write_timeout(Some(Duration::from_secs(5)))?;
        stream.write_all(payload.as_bytes())?;
        read_response(&mut BufReader::new(stream))?
            .ok_or_else(|| anyhow::anyhow!("Conexión cerrada"))
    };
    let action = match attempt() {
        Err(_) if query => attempt(),
        other => other,
    };
    action.unwrap_or_else(|e| error("STUDIO_UNAVAILABLE", format!("Abre Motive. {e}")))
}

pub(crate) fn tool(
    name: &str,
    description: &str,
    properties: Value,
    required: &[&str],
    readonly: bool,
) -> Value {
    let destructive = matches!(
        name,
        "disconnect_audio_input"
            | "reconnect_audio_input"
            | "save_audio_mixer"
            | "load_audio_mixer"
            | "remove_audio_input"
            | "remove_scene"
            | "remove_source"
            | "remove_layer"
            | "save_project"
            | "load_project"
            | "snapshot"
            | "shutdown"
            | "set_test_window"
            | "upsert_output_profile"
            | "remove_output_profile"
            | "save_output_profiles"
            | "load_output_profiles"
            | "stop_output"
            | "cancel_output"
            | "request_shutdown"
            | "cancel_transition"
            | "remove_asset"
            | "update_overlay"
            | "overlay_event"
            | "cancel_overlay_animation"
    );
    let development = matches!(
        name,
        "snapshot" | "shutdown" | "request_shutdown" | "set_test_window"
    );
    json!({"name":name,"description":description,"inputSchema":{"type":"object","properties":properties,"required":required,"additionalProperties":false},
        "annotations":{"readOnlyHint":readonly,"destructiveHint":destructive,"idempotentHint":readonly,"openWorldHint":false},
        "_meta":{"motive/category":if development {"development"} else {"production"}}})
}
pub fn tools() -> Vec<Value> {
    let mut result = vec![
        tool(
            "disconnect_audio_input",
            "Desconecta solo esta captura, conserva ID/ganancia/mute y la mezcla continua de las demás entradas. No simula hot-unplug.",
            json!({"input_id":{"type":"string"}}),
            &["input_id"],
            false,
        ),
        tool(
            "reconnect_audio_input",
            "Libera/reabre exclusivamente esta entrada. Recuperación explícita, también en vivo; no inicia/reinicia salida.",
            json!({"input_id":{"type":"string"}}),
            &["input_id"],
            false,
        ),
        tool(
            "save_audio_mixer",
            "Guarda audio-mixer.json v1 separado de escenas v3 y perfiles. No persiste desconexiones runtime ni medidores.",
            json!({}),
            &[],
            false,
        ),
        tool(
            "load_audio_mixer",
            "Restaura explícitamente el mezclador v1 mientras idle; reutiliza capturas presentes y conserva entradas ausentes en estado failed.",
            json!({}),
            &[],
            false,
        ),
        tool(
            "audio_mixer",
            "Mezclador global compartido: canales, ganancia/mute, peak/RMS post-fader/pre-mute y suma final pre-clamp. Monitoring desactivado.",
            json!({}),
            &[],
            true,
        ),
        tool(
            "add_audio_input",
            "Añade micrófono por UID o tono controlado; reutiliza el ID existente sin duplicar captura. Requiere salida detenida.",
            json!({"name":{"type":"string","minLength":1,"maxLength":80},"source":{"oneOf":[{"type":"object","properties":{"kind":{"const":"tone"}},"required":["kind"],"additionalProperties":false},{"type":"object","properties":{"kind":{"const":"microphone"},"device_id":{"type":"string","minLength":1,"maxLength":511}},"required":["kind","device_id"],"additionalProperties":false}]}}),
            &["name", "source"],
            false,
        ),
        tool(
            "remove_audio_input",
            "Libera un canal del mezclador; requiere salida detenida.",
            json!({"input_id":{"type":"string"}}),
            &["input_id"],
            false,
        ),
        tool(
            "set_audio_gain",
            "Ganancia del canal en libobs, -60..24 dB, también en vivo. No reinicia fuentes ni encoders.",
            json!({"input_id":{"type":"string"},"gain_db":{"type":"number","minimum":-60,"maximum":24}}),
            &["input_id", "gain_db"],
            false,
        ),
        tool(
            "set_audio_mute",
            "Mute/unmute en libobs sin parar la captura ni las demás entradas.",
            json!({"input_id":{"type":"string"},"muted":{"type":"boolean"}}),
            &["input_id", "muted"],
            false,
        ),
        tool(
            "scenes",
            "Escenas, revisión, configuración y transición nativa: preparar/running/completed/cancelled/failed. El progreso sigue el reloj de OBS.",
            json!({}),
            &[],
            true,
        ),
        tool(
            "configure_transition",
            "Configura Cut (0 ms) o Fade (100–5000 ms). Preferencia de sesión, fuera de proyecto v3. Rechaza cambios durante una transición.",
            json!({"transition":{"type":"object","properties":{"kind":{"type":"string","enum":["cut","fade"]},"duration_ms":{"type":"integer","minimum":0,"maximum":5000}},"required":["kind","duration_ms"],"additionalProperties":false}}),
            &["transition"],
            false,
        ),
        tool(
            "cancel_transition",
            "Cancela la operación indicada. Preparación conserva programa; Fade en marcha corta a la escena anterior. No altera la salida. Repetir el mismo token finalizado es inocuo; token antiguo se rechaza.",
            json!({"operation_id":{"type":"integer","minimum":0}}),
            &["operation_id"],
            false,
        ),
        tool(
            "encoders",
            "Encoders H.264 registrados, capacidad hardware y selección efectiva de grabación.",
            json!({}),
            &[],
            true,
        ),
        tool(
            "set_encoder",
            "Cambia encoder del perfil de grabación seleccionado mientras idle; afecta streaming si comparte ese perfil. auto permite fallback antes de empezar. Persistir perfiles es explícito; proyecto v3 y UDP no cambian.",
            json!({"encoder":{"type":"string","enum":["auto","videotoolbox","x264"]}}),
            &["encoder"],
            false,
        ),
        tool(
            "status",
            "Estado de la producción abierta, revisión y métricas reales.",
            json!({}),
            &[],
            true,
        ),
        tool(
            "devices",
            "Ventanas, cámaras, entradas de audio y permisos.",
            json!({}),
            &[],
            true,
        ),
        tool(
            "set_overlay",
            "Activa o desactiva el overlay del video.",
            json!({"visible":{"type":"boolean"}}),
            &["visible"],
            false,
        ),
        tool(
            "set_variant",
            "Cambia composición cuando no hay salida activa.",
            json!({"variant":{"type":"string","enum":["horizontal","vertical"]}}),
            &["variant"],
            false,
        ),
        tool(
            "select_source",
            "Selecciona un ID de ventana de devices; null restaura patrón libobs.",
            json!({"window_id":{"type":["integer","null"],"minimum":0,"maximum":4294967295u64}}),
            &["window_id"],
            false,
        ),
        tool(
            "select_audio",
            "none, tone o un ID de devices. Micrófono requiere permiso del usuario.",
            json!({"id":{"type":"string","minLength":1,"maxLength":512}}),
            &["id"],
            false,
        ),
        tool(
            "select_camera",
            "Selecciona una cámara por UID de devices, con permiso de macOS.",
            json!({"id":{"type":"string","minLength":1,"maxLength":511}}),
            &["id"],
            false,
        ),
        tool(
            "reconnect_sources",
            "Reconecta las fuentes seleccionadas sin iniciar una salida.",
            json!({}),
            &[],
            false,
        ),
        tool(
            "start_recording",
            "Graba localmente a un archivo nuevo; falla si ya hay una salida activa.",
            json!({}),
            &[],
            false,
        ),
        tool(
            "stop_output",
            "Solicita finalizar salida; consulta status hasta idle.",
            json!({}),
            &[],
            false,
        ),
        tool(
            "save_project",
            "Guarda ajustes en el proyecto local fijo.",
            json!({}),
            &[],
            false,
        ),
        tool(
            "load_project",
            "Restaura ajustes validados del proyecto local.",
            json!({}),
            &[],
            false,
        ),
    ];
    let target = json!({"type":"string","enum":["recording","streaming"]});
    let profile_id =
        json!({"type":"string","minLength":1,"maxLength":48,"pattern":"^[a-z0-9_-]+$"});
    let profile = json!({"type":"object","additionalProperties":false,"properties":{
        "id":profile_id,"encoder":{"type":"string","enum":["auto","videotoolbox","x264"]},
        "bitrate_kbps":{"type":"integer","minimum":250,"maximum":20000},"rate_control":{"const":"cbr"},
        "keyframe_seconds":{"type":"integer","minimum":1,"maximum":10},"frame_reordering":{"type":"boolean"}},
        "required":["id","encoder","bitrate_kbps","rate_control","keyframe_seconds","frame_reordering"]});
    for (op, description, properties, required, readonly) in [
        (
            "output_capabilities",
            "Capacidades y límites reales; resolución/FPS fijos por canvas.",
            json!({}),
            vec![],
            true,
        ),
        (
            "output_profiles",
            "Perfiles versionados y selección runtime separada del proyecto v3.",
            json!({}),
            vec![],
            true,
        ),
        (
            "upsert_output_profile",
            "Crea/reemplaza un perfil mientras idle; aplica a ambas salidas si comparten ID. Guardado explícito.",
            json!({"profile":profile}),
            vec!["profile"],
            false,
        ),
        (
            "remove_output_profile",
            "Elimina un perfil no seleccionado mientras idle.",
            json!({"id":profile_id}),
            vec!["id"],
            false,
        ),
        (
            "select_output_profile",
            "Selecciona un perfil para grabación o streaming mientras idle.",
            json!({"target":target,"profile_id":profile_id}),
            vec!["target", "profile_id"],
            false,
        ),
        (
            "save_output_profiles",
            "Guarda definiciones en output-profiles.json v1; no incluye escenas, selección ni endpoints.",
            json!({}),
            vec![],
            false,
        ),
        (
            "load_output_profiles",
            "Reemplaza perfiles desde archivo local validado mientras idle; una selección ausente pasa al primer perfil cargado.",
            json!({}),
            vec![],
            false,
        ),
        (
            "configure_stream",
            "Configura solo protocolo y puerto de 127.0.0.1 /live/motive. Sin claves, URLs ni hosts arbitrarios; RTMPS exige confianza TLS del sistema.",
            json!({"endpoint":{"type":"object","properties":{"transport":{"type":"string","enum":["rtmp","rtmps"]},"port":{"type":"integer","minimum":1024,"maximum":65535}},"required":["transport","port"],"additionalProperties":false}}),
            vec!["endpoint"],
            false,
        ),
        (
            "preflight_output",
            "Valida estado, fuentes, perfil y módulos. No conecta a red ni inicializa encoders; no garantiza disponibilidad del receptor.",
            json!({"target":target}),
            vec!["target"],
            true,
        ),
        (
            "start_stream",
            "Inicia conexión RTMP(S) al receptor local configurado. Consulta connecting/streaming/error; sin reintentos automáticos.",
            json!({}),
            vec![],
            false,
        ),
        (
            "recover_output",
            "Reconoce fallo de salida únicamente cuando terminó; conserva recuperación de fuentes y no reinicia automáticamente.",
            json!({}),
            vec![],
            false,
        ),
    ] {
        result.push(tool(op, description, properties, &required, readonly));
    }
    result.push(tool("cancel_output", "Solicita parada; durante handshake devuelve cancel_pending sin interrumpir red ni liberar recursos. Consultar status hasta idle/error.", json!({}), &[], false));
    let credential_ref = json!({"type":"string","pattern":"^kc_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"});
    result.push(tool("credential_status", "Comprueba acceso no interactivo a una referencia de Keychain. Nunca devuelve valor, longitud ni atributos del secreto.", json!({"credential_ref":credential_ref}), &["credential_ref"], true));
    result.push(tool("select_stream_credential", "Selecciona referencia de Keychain vinculada al puerto RTMPS local; null la deselecciona. Registro/reemplazo/borrado solo mediante asistente local, nunca MCP. Cambiar endpoint deselecciona la referencia.", json!({"credential_ref":{"anyOf":[credential_ref,{"type":"null"}]}}), &["credential_ref"], false));
    result.push(tool("request_shutdown", "Desarrollo: solicita parada diferida y cierra únicamente después de terminar todos los workers. Puede esperar el timeout del receptor.", json!({}), &[], false));
    let id = json!({"type":"string","minLength":1,"maxLength":48});
    let name = json!({"type":"string","minLength":1,"maxLength":80});
    let variant = json!({"type":"string","enum":["horizontal","vertical"]});
    let source = json!({"oneOf":[
        {"type":"object","properties":{"kind":{"const":"pattern"}},"required":["kind"],"additionalProperties":false},
        {"type":"object","properties":{"kind":{"const":"overlay"},"color":{"type":"integer","minimum":0,"maximum":16777215}},"required":["kind","color"],"additionalProperties":false},
        {"type":"object","properties":{"kind":{"const":"window"},"window_id":{"type":"integer","minimum":1,"maximum":4294967295u64}},"required":["kind","window_id"],"additionalProperties":false},
        {"type":"object","properties":{"kind":{"const":"camera"},"device_id":{"type":"string","minLength":1,"maxLength":511}},"required":["kind","device_id"],"additionalProperties":false}
    ]});
    let transform = json!({"type":"object","properties":{
        "x":{"type":"number","minimum":-4096,"maximum":4096},"y":{"type":"number","minimum":-4096,"maximum":4096},
        "width":{"type":"number","minimum":1,"maximum":4096},"height":{"type":"number","minimum":1,"maximum":4096},
        "visible":{"type":"boolean"},"order":{"type":"integer","minimum":0,"maximum":31}},
        "required":["x","y","width","height","visible","order"],"additionalProperties":false});
    for (op, description, properties, required) in [
        (
            "create_scene",
            "Crea y selecciona una escena vacía mientras idle.",
            json!({"name":name}),
            vec!["name"],
        ),
        (
            "rename_scene",
            "Renombra una escena existente.",
            json!({"scene_id":id,"name":name}),
            vec!["scene_id", "name"],
        ),
        (
            "remove_scene",
            "Elimina una escena mientras idle; conserva las fuentes.",
            json!({"scene_id":id}),
            vec!["scene_id"],
        ),
        (
            "select_scene",
            "Cambia de escena durante grabación/RTMP sin reiniciar la salida. Preparación acotada a 8 s; fallo conserva programa. Mismo destino pendiente es idempotente; otro devuelve TRANSITION_BUSY. Consultar scenes/status para resultado. Cut idle permite editar escenas vacías/frías.",
            json!({"scene_id":id}),
            vec!["scene_id"],
        ),
        (
            "add_source",
            "Crea una fuente y una capa en la escena; IDs nuevos en state.project.graph.",
            json!({"scene_id":id,"name":name,"source":source}),
            vec!["scene_id", "name", "source"],
        ),
        (
            "remove_source",
            "Libera una fuente sin capas que la referencien.",
            json!({"source_id":id}),
            vec!["source_id"],
        ),
        (
            "add_layer",
            "Reutiliza una fuente en una nueva capa.",
            json!({"scene_id":id,"source_id":id}),
            vec!["scene_id", "source_id"],
        ),
        (
            "remove_layer",
            "Elimina una capa, conservando su fuente.",
            json!({"scene_id":id,"layer_id":id}),
            vec!["scene_id", "layer_id"],
        ),
        (
            "set_transform",
            "Rectángulo contain en píxeles, visibilidad y orden por orientación. Geometría editable durante grabación.",
            json!({"scene_id":id,"layer_id":id,"variant":variant,"transform":transform}),
            vec!["scene_id", "layer_id", "variant", "transform"],
        ),
        (
            "set_overlay_color",
            "Cambia el acento RGB del overlay propio (entero 0xRRGGBB).",
            json!({"source_id":id,"color":{"type":"integer","minimum":0,"maximum":16777215}}),
            vec!["source_id", "color"],
        ),
        (
            "reconnect_source",
            "Recrea una fuente explícita mientras idle; espera datos antes de recuperarla.",
            json!({"source_id":id}),
            vec!["source_id"],
        ),
        (
            "snapshot",
            "Desarrollo: guarda un PNG de la composición en la ubicación local fija; MCP no devuelve video.",
            json!({}),
            vec![],
        ),
        (
            "shutdown",
            "Desarrollo: cierra el estudio solo cuando la salida ha finalizado.",
            json!({}),
            vec![],
        ),
        (
            "set_test_window",
            "Desarrollo: abre/cierra la ventana nativa controlada para pruebas locales.",
            json!({"open":{"type":"boolean"}}),
            vec!["open"],
        ),
    ] {
        result.push(tool(op, description, properties, &required, false));
    }
    result.extend(crate::core::overlays::protocol::tools());
    result
}

pub fn rpc(request: Value, initialized: &mut bool) -> Option<Value> {
    let id = request.get("id").cloned();
    let method = request["method"].as_str().unwrap_or("");
    if id.is_none() && method.starts_with("notifications/") {
        return None;
    }
    let id = id.unwrap_or(Value::Null);
    let failure = |code: i32, message: &str| json!({"jsonrpc":"2.0","id":id,"error":{"code":code,"message":message}});
    if request["jsonrpc"] != "2.0" || method.is_empty() {
        return Some(failure(-32600, "Invalid Request"));
    }
    let result = match method {
        "initialize" => {
            *initialized = true;
            json!({"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"serverInfo":{"name":"motive-local-control","version":"0.1.0"}})
        }
        "ping" => json!({}),
        _ if !*initialized => return Some(failure(-32002, "Initialize first")),
        "tools/list" => json!({"tools":tools()}),
        "tools/call" => {
            let name = request["params"]["name"].as_str().unwrap_or("");
            if !tools().iter().any(|t| t["name"] == name) {
                return Some(failure(-32602, "Unknown tool"));
            }
            let mut args = request["params"]
                .get("arguments")
                .cloned()
                .unwrap_or(json!({}));
            let Some(object) = args.as_object_mut() else {
                return Some(failure(-32602, "Arguments must be an object"));
            };
            if object.contains_key("op") {
                return Some(failure(-32602, "Unexpected op argument"));
            }
            object.insert("op".into(), json!(name));
            let response = match parse_command(args.clone()) {
                Ok(_) => send(args, "mcp"),
                Err(_) => error("INVALID_ARGUMENT", "Invalid command fields or values"),
            };
            json!({"content":[{"type":"text","text":response.to_string()}],"isError":response["ok"]!=true})
        }
        _ => return Some(failure(-32601, "Method not found")),
    };
    Some(json!({"jsonrpc":"2.0","id":id,"result":result}))
}

pub fn run_mcp() -> anyhow::Result<()> {
    let stdin = io::stdin();
    let mut input = stdin.lock();
    let mut output = io::stdout().lock();
    let mut initialized = false;
    loop {
        let response = match read_message(&mut input) {
            Ok(Some(request)) => rpc(request, &mut initialized),
            Ok(None) => break,
            Err(_) => Some(
                json!({"jsonrpc":"2.0","id":null,"error":{"code":-32700,"message":"Parse error"}}),
            ),
        };
        if let Some(response) = response {
            writeln!(output, "{response}")?;
            output.flush()?;
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_protocol_errors_and_unknown_tools() {
        let mut init = false;
        let r = rpc(
            json!({"jsonrpc":"2.0","id":1,"method":"tools/list"}),
            &mut init,
        )
        .unwrap();
        assert_eq!(r["error"]["code"], -32002);
        rpc(
            json!({"jsonrpc":"2.0","id":2,"method":"initialize"}),
            &mut init,
        );
        let r = rpc(
            json!({"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"shell"}}),
            &mut init,
        )
        .unwrap();
        assert_eq!(r["error"]["code"], -32602);
        assert!(
            rpc(
                json!({"jsonrpc":"2.0","method":"notifications/initialized"}),
                &mut init
            )
            .is_none()
        );
    }
    #[test]
    fn bounds_input_size() {
        let input = vec![b'x'; MAX_MESSAGE as usize + 2];
        assert!(read_message(&mut &input[..]).is_err());
    }

    fn response_frame(size: usize) -> Vec<u8> {
        let overhead = serde_json::to_vec(&json!({"text":""})).unwrap().len() + 1;
        let mut frame = serde_json::to_vec(&json!({"text":"x".repeat(size-overhead)})).unwrap();
        frame.push(b'\n');
        assert_eq!(frame.len(), size);
        frame
    }

    #[test]
    fn large_responses_use_separate_limit_over_fragmented_socket() {
        for size in [MAX_MESSAGE as usize + 1, MAX_RESPONSE as usize] {
            let frame = response_frame(size);
            assert!(read_message(&mut &frame[..]).is_err());
            let (mut writer, reader) = UnixStream::pair().unwrap();
            let send = thread::spawn(move || {
                for chunk in frame.chunks(4093) {
                    writer.write_all(chunk).unwrap();
                }
                writer.write_all(b"{\"next\":true}\n").unwrap();
            });
            let mut reader = BufReader::new(reader);
            let value = read_response(&mut reader).unwrap().unwrap();
            assert!(value["text"].as_str().unwrap().len() > 65000);
            assert_eq!(
                read_response(&mut reader).unwrap().unwrap(),
                json!({"next":true})
            );
            assert!(read_response(&mut reader).unwrap().is_none());
            send.join().unwrap();
        }
    }

    #[test]
    fn response_limit_rejects_oversize_and_incomplete_frames() {
        let frame = response_frame(MAX_RESPONSE as usize + 1);
        let (mut writer, reader) = UnixStream::pair().unwrap();
        let send = thread::spawn(move || writer.write_all(&frame).unwrap());
        assert!(read_response(&mut BufReader::new(reader)).is_err());
        send.join().unwrap();
        assert!(read_response(&mut &b"{\"ok\":true}"[..]).is_err());
    }
}
