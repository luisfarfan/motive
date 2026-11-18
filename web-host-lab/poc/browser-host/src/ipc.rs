//! A private host envelope around the unchanged Element Lab v1 visual message.
use crate::{Identity, Result};
use serde::de::{self, MapAccess, SeqAccess, Visitor};
use serde::{Deserialize, Deserializer};
use serde_json::{Map, Number, Value};
use std::{
    collections::VecDeque,
    fmt,
    io::{Read, Write},
    os::unix::net::UnixStream,
    time::{Duration, Instant},
};

pub const MAX_WIRE: usize = 16_384 + 512;
pub const SAFE_INTEGER: u64 = 9_007_199_254_740_991;

/// Reject duplicate object keys at every nesting level before they disappear in Value.
struct Strict(Value);
impl<'de> Deserialize<'de> for Strict {
    fn deserialize<D: Deserializer<'de>>(d: D) -> std::result::Result<Self, D::Error> {
        struct V;
        impl<'de> Visitor<'de> for V {
            type Value = Strict;
            fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result {
                f.write_str("JSON without duplicate keys")
            }
            fn visit_bool<E: de::Error>(self, v: bool) -> std::result::Result<Strict, E> {
                Ok(Strict(Value::Bool(v)))
            }
            fn visit_i64<E: de::Error>(self, v: i64) -> std::result::Result<Strict, E> {
                Ok(Strict(v.into()))
            }
            fn visit_u64<E: de::Error>(self, v: u64) -> std::result::Result<Strict, E> {
                Ok(Strict(v.into()))
            }
            fn visit_f64<E: de::Error>(self, v: f64) -> std::result::Result<Strict, E> {
                Number::from_f64(v)
                    .map(|v| Strict(v.into()))
                    .ok_or_else(|| E::custom("nonfinite"))
            }
            fn visit_str<E: de::Error>(self, v: &str) -> std::result::Result<Strict, E> {
                Ok(Strict(v.into()))
            }
            fn visit_unit<E: de::Error>(self) -> std::result::Result<Strict, E> {
                Ok(Strict(Value::Null))
            }
            fn visit_none<E: de::Error>(self) -> std::result::Result<Strict, E> {
                Ok(Strict(Value::Null))
            }
            fn visit_seq<A: SeqAccess<'de>>(
                self,
                mut a: A,
            ) -> std::result::Result<Strict, A::Error> {
                let mut out = Vec::new();
                while let Some(Strict(v)) = a.next_element()? {
                    out.push(v);
                }
                Ok(Strict(out.into()))
            }
            fn visit_map<A: MapAccess<'de>>(
                self,
                mut a: A,
            ) -> std::result::Result<Strict, A::Error> {
                let mut out = Map::new();
                while let Some((k, Strict(v))) = a.next_entry::<String, Strict>()? {
                    if out.insert(k, v).is_some() {
                        return Err(de::Error::custom("duplicate key"));
                    }
                }
                Ok(Strict(out.into()))
            }
        }
        d.deserialize_any(V)
    }
}
pub fn strict_json(data: &[u8], limit: usize) -> Result<Value> {
    if data.is_empty() || data.len() > limit {
        return Err("MESSAGE_SIZE");
    }
    serde_json::from_slice::<Strict>(data)
        .map(|v| v.0)
        .map_err(|_| "MESSAGE_JSON")
}
fn object(v: &Value) -> Result<&Map<String, Value>> {
    v.as_object().ok_or("MESSAGE_SCHEMA")
}
fn exact(v: &Value, keys: &[&str]) -> Result<()> {
    let o = object(v)?;
    if o.len() != keys.len() || keys.iter().any(|k| !o.contains_key(*k)) {
        return Err("MESSAGE_SCHEMA");
    }
    Ok(())
}
fn uint(v: &Value) -> Result<u64> {
    v.as_u64()
        .filter(|x| *x <= SAFE_INTEGER)
        .ok_or("MESSAGE_INTEGER")
}
fn validate_field(v: &Value, s: &Value) -> Result<()> {
    match s["type"].as_str().ok_or("FIELD_SPEC")? {
        "string" | "color" => {
            let text = v.as_str().ok_or("FIELD_TYPE")?;
            let max = s.get("max_length").map(uint).transpose()?.unwrap_or(160);
            if text.encode_utf16().count() as u64 > max || text.chars().any(|c| (c as u32) < 32) {
                return Err("FIELD_RANGE");
            }
            if s["type"] == "color"
                && (text.len() != 7
                    || !text.starts_with('#')
                    || !text[1..].bytes().all(|b| b.is_ascii_hexdigit()))
            {
                return Err("FIELD_COLOR");
            }
        }
        "boolean" => {
            if !v.is_boolean() {
                return Err("FIELD_TYPE");
            }
        }
        "integer" | "number" => {
            let n = v.as_f64().filter(|n| n.is_finite()).ok_or("FIELD_TYPE")?;
            let min = s["minimum"].as_f64().ok_or("FIELD_SPEC")?;
            let max = s["maximum"].as_f64().ok_or("FIELD_SPEC")?;
            if min > max || n < min || n > max || (s["type"] == "integer" && n.fract() != 0.0) {
                return Err("FIELD_RANGE");
            }
        }
        _ => return Err("FIELD_SPEC"),
    }
    if let Some(options) = s.get("options") {
        if !options.as_array().ok_or("FIELD_SPEC")?.contains(v) {
            return Err("FIELD_OPTION");
        }
    }
    Ok(())
}

pub struct Gate {
    identity: Identity,
    manifest: Value,
    properties: Map<String, Value>,
    last_sequence: u64,
    last_now: u64,
    attempts: VecDeque<u64>,
    max_message: usize,
    rate: usize,
}
#[derive(Debug, PartialEq)]
pub enum Visual {
    Event {
        sequence: u64,
        name: String,
        payload: Value,
    },
    Properties(Value),
    Cancel,
    Resume,
    Dispose,
}
impl Gate {
    /// Input comes from the existing schema/import broker. This validates the
    /// fields used by this gate, not a replacement Web Element schema.
    pub fn from_validated_manifest(identity: Identity, manifest: Value) -> Result<Self> {
        if manifest["schema_version"] != 1 || manifest["kind"] != "web_element" {
            return Err("CONTRACT_VERSION");
        }
        let permissions = object(&manifest["permissions"])?;
        for k in [
            "network",
            "storage",
            "devices",
            "clipboard",
            "production",
            "mcp",
            "shell",
        ] {
            if permissions.get(k) != Some(&Value::Bool(false)) {
                return Err("PERMISSION");
            }
        }
        if permissions.len() != 7 {
            return Err("PERMISSION");
        }
        let max_message = uint(&manifest["limits"]["max_message_bytes"])? as usize;
        let rate = uint(&manifest["limits"]["events_per_second"])? as usize;
        if !(256..=16384).contains(&max_message) || !(1..=60).contains(&rate) {
            return Err("CONTRACT_LIMIT");
        }
        let specs = object(&manifest["properties"])?;
        if specs.len() > 32 || object(&manifest["events"])?.len() > 16 {
            return Err("CONTRACT_LIMIT");
        }
        let mut properties = Map::new();
        for (k, s) in specs {
            let v = s.get("default").ok_or("FIELD_SPEC")?;
            validate_field(v, s)?;
            properties.insert(k.clone(), v.clone());
        }
        Ok(Self {
            identity,
            manifest,
            properties,
            last_sequence: 0,
            last_now: 0,
            attempts: VecDeque::new(),
            max_message,
            rate,
        })
    }
    pub fn properties(&self) -> &Map<String, Value> {
        &self.properties
    }
    pub fn accept(&mut self, data: &[u8], now_ms: u64) -> Result<Visual> {
        let e = strict_json(data, self.max_message + 512)?;
        exact(
            &e,
            &[
                "protocol",
                "instance",
                "generation",
                "expires_ms",
                "message",
            ],
        )?;
        if e["protocol"] != 1
            || uint(&e["instance"])? != self.identity.instance
            || uint(&e["generation"])? != self.identity.generation
        {
            return Err("STALE_GENERATION");
        }
        if now_ms < self.last_now {
            return Err("CLOCK_REGRESSION");
        }
        self.last_now = now_ms;
        let m = &e["message"];
        if serde_json::to_vec(m).map_err(|_| "MESSAGE_JSON")?.len() > self.max_message {
            return Err("MESSAGE_SIZE");
        }
        let seq = uint(&m["seq"])?;
        if m["version"] != 1 || seq <= self.last_sequence {
            return Err("MESSAGE_SEQUENCE");
        }
        // Consume sequence even if a later policy check rejects the attempt.
        self.last_sequence = seq;
        let expires = uint(&e["expires_ms"])?;
        if expires < now_ms || expires - now_ms > 30_000 {
            return Err("MESSAGE_DEADLINE");
        }
        let kind = m["kind"].as_str().ok_or("MESSAGE_SCHEMA")?;
        if matches!(kind, "event" | "properties") {
            while self.attempts.front().is_some_and(|v| now_ms - *v >= 1000) {
                self.attempts.pop_front();
            }
            if self.attempts.len() >= self.rate {
                return Err("RATE_LIMIT");
            }
            self.attempts.push_back(now_ms);
        }
        match kind {
            "event" => {
                exact(m, &["version", "seq", "kind", "name", "payload"])?;
                let name = m["name"].as_str().ok_or("MESSAGE_SCHEMA")?;
                let spec = object(&self.manifest["events"])?
                    .get(name)
                    .ok_or("UNKNOWN_EVENT")?;
                let fields = object(&spec["fields"])?;
                let payload = object(&m["payload"])?;
                if payload.len() != fields.len() {
                    return Err("EVENT_FIELDS");
                }
                for (k, s) in fields {
                    validate_field(payload.get(k).ok_or("EVENT_FIELDS")?, s)?;
                }
                Ok(Visual::Event {
                    sequence: seq,
                    name: name.to_owned(),
                    payload: m["payload"].clone(),
                })
            }
            "properties" => {
                exact(m, &["version", "seq", "kind", "properties"])?;
                let patch = object(&m["properties"])?;
                let specs = object(&self.manifest["properties"])?;
                for (k, v) in patch {
                    validate_field(v, specs.get(k).ok_or("UNKNOWN_PROPERTY")?)?;
                }
                // No partial patch if any value is invalid.
                self.properties.extend(patch.clone());
                Ok(Visual::Properties(m["properties"].clone()))
            }
            "cancel" | "resume" | "dispose" => {
                exact(m, &["version", "seq", "kind"])?;
                Ok(match kind {
                    "cancel" => Visual::Cancel,
                    "resume" => Visual::Resume,
                    _ => Visual::Dispose,
                })
            }
            _ => Err("UNAUTHORIZED_MESSAGE"),
        }
    }
}

/// Length-prefix checked BEFORE allocation; one absolute deadline for the packet.
/// Nonblocking contract transport; native supervisor should use its event loop.
/// A framing error is terminal: caller closes the channel rather than resyncing.
pub fn read_packet(stream: &mut UnixStream, limit: usize, timeout: Duration) -> Result<Vec<u8>> {
    if limit > MAX_WIRE || timeout.is_zero() || timeout > Duration::from_secs(30) {
        return Err("TRANSPORT_LIMIT");
    }
    stream
        .set_nonblocking(true)
        .map_err(|_| "TRANSPORT_CONFIG")?;
    let deadline = Instant::now() + timeout;
    fn read_until(s: &mut UnixStream, mut out: &mut [u8], deadline: Instant) -> Result<()> {
        while !out.is_empty() {
            if Instant::now() >= deadline {
                return Err("TRANSPORT_TIMEOUT");
            }
            let n = match s.read(out) {
                Ok(n) => n,
                Err(e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                    std::thread::sleep(Duration::from_millis(1));
                    continue;
                }
                Err(_) => return Err("TRANSPORT_IO"),
            };
            if n == 0 {
                return Err("TRANSPORT_EOF");
            }
            if Instant::now() >= deadline {
                return Err("TRANSPORT_TIMEOUT");
            }
            out = &mut out[n..];
        }
        Ok(())
    }
    let mut header = [0; 4];
    read_until(stream, &mut header, deadline)?;
    let size = u32::from_be_bytes(header) as usize;
    if size == 0 || size > limit {
        return Err("MESSAGE_SIZE");
    }
    let mut data = vec![0; size];
    read_until(stream, &mut data, deadline)?;
    Ok(data)
}
pub fn write_packet(stream: &mut UnixStream, data: &[u8]) -> Result<()> {
    if data.is_empty() || data.len() > MAX_WIRE {
        return Err("MESSAGE_SIZE");
    }
    stream
        .set_nonblocking(true)
        .map_err(|_| "TRANSPORT_CONFIG")?;
    let deadline = Instant::now() + Duration::from_millis(250);
    let mut bytes = (data.len() as u32).to_be_bytes().to_vec();
    bytes.extend_from_slice(data);
    let mut remaining = bytes.as_slice();
    while !remaining.is_empty() {
        if Instant::now() >= deadline {
            return Err("TRANSPORT_TIMEOUT");
        }
        match stream.write(remaining) {
            Ok(0) => return Err("TRANSPORT_EOF"),
            Ok(n) => remaining = &remaining[n..],
            Err(e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                std::thread::sleep(Duration::from_millis(1))
            }
            Err(_) => return Err("TRANSPORT_IO"),
        }
    }
    Ok(())
}
