//! Native form drafts. Their revision guard prevents stale UI writes over MCP.
use super::*;
use crate::core::{
    RecordingEncoder,
    output::{LocalEndpoint, OutputProfile, ProfileStore, RateControl, Transport},
};
use gpui_kit::component::{
    Sizable, WindowExt,
    dialog::{DialogAction, DialogButtonProps, DialogClose, DialogFooter},
    input::{Input, InputState},
};

pub(super) struct Forms {
    pub scene_name: Entity<InputState>,
    pub fade_ms: Entity<InputState>,
    pub profile_id: Entity<InputState>,
    pub bitrate: Entity<InputState>,
    pub keyframes: Entity<InputState>,
    pub overlay_color: Entity<InputState>,
    pub port: Entity<InputState>,
    pub credential: Entity<InputState>,
    pub encoder: RecordingEncoder,
    pub reorder: bool,
    pub transport: Transport,
    pub profiles: Vec<OutputProfile>, // read-only query snapshot, never authoritative
    pub revision: u64,
}
impl Forms {
    pub fn new(w: &mut Window, cx: &mut Context<Studio>) -> Self {
        let mut input = || cx.new(|cx| InputState::new(w, cx));
        Self {
            scene_name: input(),
            fade_ms: input(),
            profile_id: input(),
            bitrate: input(),
            keyframes: input(),
            overlay_color: input(),
            port: input(),
            credential: input(),
            encoder: RecordingEncoder::Auto,
            reorder: true,
            transport: Transport::Rtmp,
            profiles: vec![],
            revision: 0,
        }
    }
    pub fn profile(&self, cx: &App) -> Result<OutputProfile, &'static str> {
        let p = OutputProfile {
            id: self.profile_id.read(cx).value().to_string(),
            encoder: self.encoder,
            bitrate_kbps: integer(&self.bitrate.read(cx).value())?,
            rate_control: RateControl::Cbr,
            keyframe_seconds: integer(&self.keyframes.read(cx).value())?,
            frame_reordering: self.reorder,
        };
        p.validate()
            .map_err(|_| "Perfil inválido: ID a-z/0-9/-/_, bitrate 250–20000, keyframes 1–10 s")?;
        Ok(p)
    }
    pub fn endpoint(&self, cx: &App) -> Result<LocalEndpoint, &'static str> {
        let port = u16::try_from(integer(&self.port.read(cx).value())?)
            .map_err(|_| "Puerto fuera de rango")?;
        let e = LocalEndpoint {
            transport: self.transport,
            port,
        };
        e.validate().map_err(|_| "Puerto local: 1024–65535")?;
        Ok(e)
    }
}
pub(super) fn integer(s: &str) -> Result<u32, &'static str> {
    if s.is_empty() || !s.bytes().all(|b| b.is_ascii_digit()) {
        return Err("Usa un entero sin signos ni decimales");
    }
    s.parse().map_err(|_| "Número fuera de rango")
}
pub(super) fn field(name: &'static str, input: &Entity<InputState>, p: Palette) -> Div {
    property_group(name, p).child(Input::new(input).aria_label(name).small().w_full())
}
impl Studio {
    pub(super) fn refresh_profiles(&mut self) {
        let r = self.production.apply(Command::OutputProfiles, "UI");
        self.forms.profiles = serde_json::from_value::<ProfileStore>(r["store"].clone())
            .map(|s| s.profiles)
            .unwrap_or_default();
    }
    pub(super) fn load_profile_draft(
        &mut self,
        p: &OutputProfile,
        w: &mut Window,
        cx: &mut Context<Self>,
    ) {
        for (field, value) in [
            (&self.forms.profile_id, p.id.clone()),
            (&self.forms.bitrate, p.bitrate_kbps.to_string()),
            (&self.forms.keyframes, p.keyframe_seconds.to_string()),
        ] {
            field.update(cx, |s, cx| s.set_value(value, w, cx));
        }
        self.forms.encoder = p.encoder;
        self.forms.reorder = p.frame_reordering;
        self.forms.revision = self.production.revision;
    }
    pub(super) fn prepare_forms(&mut self, w: &mut Window, cx: &mut Context<Self>) {
        self.refresh_profiles();
        let state = self.production.status();
        let scene = self
            .production
            .graph()
            .scene(&self.production.graph().active_scene)
            .unwrap();
        for (field, value) in [
            (&self.forms.scene_name, scene.name.clone()),
            (
                &self.forms.fade_ms,
                state["transition_configuration"]["duration_ms"]
                    .as_u64()
                    .filter(|n| *n >= 100)
                    .unwrap_or(300)
                    .to_string(),
            ),
            (
                &self.forms.port,
                state["output_configuration"]["endpoint"]["port"]
                    .as_u64()
                    .unwrap_or(19351)
                    .to_string(),
            ),
            (
                &self.forms.credential,
                state["output_configuration"]["credential_ref"]
                    .as_str()
                    .unwrap_or("")
                    .to_string(),
            ),
        ] {
            field.update(cx, |s, cx| s.set_value(value, w, cx));
        }
        self.forms.transport = if state["output_configuration"]["endpoint"]["transport"] == "rtmps"
        {
            Transport::Rtmps
        } else {
            Transport::Rtmp
        };
        let profile = serde_json::from_value(state["output_configuration"]["recording"].clone())
            .unwrap_or_default();
        let color = self
            .selected_layer
            .as_ref()
            .and_then(|id| scene.layers.iter().find(|l| &l.id == id))
            .and_then(|l| {
                self.production
                    .graph()
                    .sources
                    .iter()
                    .find(|s| s.id == l.source_id)
            })
            .and_then(|s| {
                if let SourceKind::Overlay { color } = s.spec {
                    Some(color)
                } else {
                    None
                }
            })
            .unwrap_or(0x33e8b5);
        self.forms
            .overlay_color
            .update(cx, |s, cx| s.set_value(format!("{color:06x}"), w, cx));
        self.load_profile_draft(&profile, w, cx);
    }
    pub(super) fn form_submit(&mut self, command: Command, cx: &mut Context<Self>) {
        if self.forms.revision != self.production.revision {
            self.message =
                "El núcleo cambió. Reabre el panel para revisar los valores actuales.".into();
            cx.notify();
            return;
        }
        let r = self.command(command, "UI", cx);
        if r["ok"] == true {
            self.forms.revision = self.production.revision;
            self.refresh_profiles();
        }
    }
    pub(super) fn confirm_command(
        &mut self,
        command: Command,
        w: &mut Window,
        cx: &mut Context<Self>,
    ) {
        self.panel = None;
        self.picker = None;
        cx.notify();
        let revision = self.production.revision;
        let weak = cx.entity().downgrade();
        let description = match &command {
            Command::RemoveAudioInput { input_id } => {
                format!("Eliminar entrada {input_id} y liberar su captura.")
            }
            Command::DisconnectAudioInput { input_id } => {
                format!("Desconectar {input_id}; las otras entradas continúan.")
            }
            Command::LoadAudioMixer => {
                "Restaurar el mixer guardado y reemplazar las entradas actuales.".into()
            }
            Command::RemoveScene { scene_id } => format!(
                "Eliminar escena {scene_id} y sus capas. Las fuentes compartidas se conservan."
            ),
            Command::RemoveLayer { layer_id, .. } => {
                format!("Eliminar capa {layer_id}. Su fuente seguirá disponible para reutilizar.")
            }
            Command::RemoveSource { source_id } => {
                format!("Liberar fuente sin uso {source_id} y sus recursos.")
            }
            Command::Overlay(crate::core::overlays::OverlayCommand::RemoveAsset { asset_id }) => {
                format!(
                    "Eliminar el recurso administrado {asset_id}. El archivo original no se modifica. Las escenas que lo utilicen impedirán eliminarlo."
                )
            }
            Command::RemoveOutputProfile { id } => {
                format!("Eliminar perfil {id}. El núcleo rechazará un perfil en uso.")
            }
            Command::UpsertOutputProfile { profile } => {
                format!("Reemplazar la definición del perfil {}.", profile.id)
            }
            Command::LoadProject => {
                "Restaurar el proyecto guardado y reemplazar la composición actual.".into()
            }
            Command::LoadOutputProfiles => {
                "Restaurar los perfiles guardados y reemplazar las definiciones actuales.".into()
            }
            Command::StopOutputTarget { target } | Command::CancelOutputTarget { target } => {
                match target {
                    crate::core::output::OutputTarget::Recording =>
                        "Finalizar solo la grabación MKV. La transmisión continúa si está activa.",
                    crate::core::output::OutputTarget::Streaming =>
                        "Finalizar solo la transmisión. La grabación continúa si está activa.",
                }.into()
            }
            Command::CancelAllOutputs => {
                "Solicitar la finalización de grabación y transmisión. Una conexión pendiente puede tardar en terminar. El estudio permanece abierto.".into()
            }
            _ => "Finalizar la salida actual de forma controlada.".into(),
        };
        w.open_dialog(cx,move|d,_,_|{let weak=weak.clone();let command=command.clone();d.title("Confirmar operación")
                .footer(DialogFooter::new().child(DialogClose::new().trigger(|b|b.label("Cancelar"))).child(DialogAction::new().child(control("confirm-action","Confirmar")))).child(description.clone()).button_props(DialogButtonProps::default().ok_text("Confirmar").cancel_text("Cancelar").show_cancel(true).on_ok(move|_,_,cx|{let _=weak.update(cx,|v,cx|{if v.production.revision!=revision{v.message="La producción cambió; confirma de nuevo sobre el estado actual.".into();cx.notify();}else{v.command(command.clone(),"UI",cx);v.forms.revision=v.production.revision;v.refresh_profiles();}});true}))});
    }
}
#[cfg(test)]
mod tests {
    use super::integer;
    #[test]
    fn strict_integer_fields() {
        assert_eq!(integer("19351"), Ok(19351));
        for s in ["", "-1", "1.2", "+3", " 4", "4294967296", "NaN"] {
            assert!(integer(s).is_err());
        }
    }
}
