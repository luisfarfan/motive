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
    let mut line = String::new();
    let count = reader.take(MAX_MESSAGE + 1).read_line(&mut line)?;
    if count == 0 {
        return Ok(None);
    }
    if count as u64 > MAX_MESSAGE || !line.ends_with('\n') {
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
                        let _ = stream.set_read_timeout(Some(Duration::from_secs(5)));
                        let _ = stream.set_write_timeout(Some(Duration::from_secs(5)));
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
                                    Err(e) => error("INVALID_ARGUMENT", e),
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
    let query = matches!(command["op"].as_str(), Some("status" | "devices"));
    let mut payload = json!({"command":command,"origin":origin}).to_string();
    payload.push('\n');
    let attempt = || -> anyhow::Result<Value> {
        let mut stream = UnixStream::connect(socket_path())?;
        stream.set_read_timeout(Some(Duration::from_secs(7)))?;
        stream.set_write_timeout(Some(Duration::from_secs(5)))?;
        stream.write_all(payload.as_bytes())?;
        read_message(&mut BufReader::new(stream))?
            .ok_or_else(|| anyhow::anyhow!("Conexión cerrada"))
    };
    let action = match attempt() {
        Err(_) if query => attempt(),
        other => other,
    };
    action.unwrap_or_else(|e| error("STUDIO_UNAVAILABLE", format!("Abre Motive. {e}")))
}

fn tool(
    name: &str,
    description: &str,
    properties: Value,
    required: &[&str],
    readonly: bool,
) -> Value {
    json!({"name":name,"description":description,"inputSchema":{"type":"object","properties":properties,"required":required,"additionalProperties":false},"annotations":{"readOnlyHint":readonly,"destructiveHint":false,"openWorldHint":false}})
}
pub fn tools() -> Vec<Value> {
    vec![
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
    ]
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
                Err(e) => error("INVALID_ARGUMENT", e),
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
}
