use super::forms::{field, integer};
use super::*;
use crate::core::{
    RecordingEncoder,
    output::{OutputTarget, Transport, valid_credential_ref},
    video::Resolution,
};
impl Studio {
    pub(super) fn video_configuration_busy(&self, status: &Value) -> bool {
        self.production.engine.output_state() != 0
            || status["output_lifecycle"]["native_busy"] == true
            || status["output_lifecycle"]["shutdown_pending"] == true
            || self.production.engine.scene_state().busy()
            || self.production.engine.overlay_animation_busy()
    }
    fn video_settings(&self, cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        let status = self.production.status();
        let video = self.production.project.video.unwrap_or_default();
        let busy = self.video_configuration_busy(&status);
        let stale = self.forms.revision != self.production.revision;
        let disabled = busy || stale;
        let available = status["video"]["available"] == true;
        let (layout_width, layout_height) = self.production.layout_dimensions();
        col()
            .gap(px(8.))
            .child(label("Video de producción", p.ink).font_weight(FontWeight::SEMIBOLD))
            .child(label(
                if available {
                    format!("Composición y salida: {} × {} · {} FPS", status["video"]["width"], status["video"]["height"], status["video"]["fps"])
                } else {
                    "Video no disponible: restaura la configuración antes de iniciar una salida.".into()
                },
                if available { p.secondary } else { p.warn },
            ))
            .child(label("Resolución", p.secondary))
            .child(row().children([
                (Resolution::Legacy540, "540p"),
                (Resolution::Hd720, "720p"),
                (Resolution::FullHd1080, "1080p"),
            ].into_iter().enumerate().map(|(index, (resolution, name))| {
                quiet(("video-resolution", index), name)
                    .selected(video.resolution == resolution)
                    .disabled(disabled)
                    .on_click(cx.listener(move |v, _, _, cx| {
                        let mut current = v.production.project.video.unwrap_or_default();
                        current.resolution = resolution;
                        v.form_submit(Command::ConfigureVideo { video: current }, cx);
                    }))
            })))
            .child(label("Fotogramas por segundo", p.secondary))
            .child(row().children([(30, "30 FPS"), (60, "60 FPS · candidato")]
                .into_iter().enumerate().map(|(index, (fps, name))| {
                    quiet(("video-fps", index), name)
                        .selected(video.fps == fps)
                        .disabled(disabled)
                        .on_click(cx.listener(move |v, _, _, cx| {
                            let mut current = v.production.project.video.unwrap_or_default();
                            current.fps = fps;
                            v.form_submit(Command::ConfigureVideo { video: current }, cx);
                        }))
                })))
            .when(busy, |d| d.child(label("Espera a que terminen las salidas, transiciones y animaciones para cambiar el video.", p.warn)))
            .when(!available, |d| d.child(
                quiet("recover-video-settings", "Restaurar video")
                    .disabled(disabled)
                    .on_click(cx.listener(|v, _, _, cx| {
                        let video = v.production.project.video.unwrap_or_default();
                        v.form_submit(Command::ConfigureVideo { video }, cx);
                    })),
            ))
            .when(status["video"]["error"].is_string(), |d| d.child(label(
                format!("Video: {}", status["video"]["error"].as_str().unwrap_or("Error de configuración")), p.warn,
            )))
            .child(label("Los presets son configuraciones disponibles; seleccionarlos no acredita el rendimiento. 60 FPS requiere verificar una grabación real y la cadencia de cada fuente.", p.muted))
            .child(label(format!("Edición: {layout_width} × {layout_height} unidades. Cambiar resolución conserva posiciones, tamaños y los dos layouts."), p.secondary))
            .child(label("Cámara: se solicita 720p y conserva su propia cadencia. Cambiar FPS renueva las capturas de ventana con las salidas detenidas.", p.muted))
            .child(label("Textos, widgets y archivos conservan su resolución de origen; subir el canvas no añade detalle a esas fuentes.", p.muted))
            .child(quiet("save-video-project", "Guardar proyecto con este video")
                .disabled(disabled)
                .on_click(cx.listener(|v, _, _, cx| v.form_submit(Command::SaveProject, cx))))
            .child(label("Los cambios se aplican al estudio. Guardar proyecto los conserva en v5; los proyectos anteriores mantienen su configuración original de 540p30. Los perfiles de salida se guardan por separado.", p.muted))
    }

    pub(super) fn scene_settings(&self, cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        let scene = self.production.graph().active_scene.clone();
        let t = self.production.status()["transition"].clone();
        col()
            .gap(px(10.))
            .child(field("Nombre de escena", &self.forms.scene_name, p))
            .child(
                row()
                    .child(quiet("create-named", "Crear escena").on_click(cx.listener(
                        |v, _, _, cx| {
                            let name = v.forms.scene_name.read(cx).value().to_string();
                            v.form_submit(Command::CreateScene { name }, cx);
                        },
                    )))
                    .child(
                        quiet("rename-scene", "Renombrar actual").on_click(cx.listener(
                            move |v, _, _, cx| {
                                let name = v.forms.scene_name.read(cx).value().to_string();
                                v.form_submit(
                                    Command::RenameScene {
                                        scene_id: scene.clone(),
                                        name,
                                    },
                                    cx,
                                );
                            },
                        )),
                    ),
            )
            .child(field(
                "Duración de Fade (100–5000 ms)",
                &self.forms.fade_ms,
                p,
            ))
            .child(
                row()
                    .child(self.action(
                        "transition-cut",
                        "Cut",
                        Command::ConfigureTransition {
                            transition: TransitionConfig {
                                kind: TransitionKind::Cut,
                                duration_ms: 0,
                            },
                        },
                        cx,
                    ))
                    .child(
                        quiet("transition-fade", "Aplicar Fade").on_click(cx.listener(
                            |v, _, _, cx| match integer(&v.forms.fade_ms.read(cx).value()) {
                                Ok(duration_ms) => v.form_submit(
                                    Command::ConfigureTransition {
                                        transition: TransitionConfig {
                                            kind: TransitionKind::Fade,
                                            duration_ms,
                                        },
                                    },
                                    cx,
                                ),
                                Err(e) => {
                                    v.message = e.into();
                                    cx.notify();
                                }
                            },
                        )),
                    ),
            )
            .child(label(
                format!(
                    "Transición: {} · destino {} · {:.0}%",
                    t["phase"].as_str().unwrap_or("idle"),
                    t["target_scene"].as_str().unwrap_or("—"),
                    t["progress"].as_f64().unwrap_or(0.) * 100.
                ),
                p.secondary,
            ))
            .when(
                matches!(t["phase"].as_str(), Some("preparing" | "running")),
                |d| {
                    d.child(self.action(
                        "cancel-transition",
                        "Cancelar transición",
                        Command::CancelTransition {
                            operation_id: t["operation_id"].as_u64().unwrap_or(0),
                        },
                        cx,
                    ))
                },
            )
            .when(t["phase"] == "failed", |d| {
                d.child(label(
                    format!(
                        "{} · se conserva la escena segura",
                        t["error"].as_str().unwrap_or("Error")
                    ),
                    p.warn,
                ))
            })
            .child(self.action(
                "delete-scene",
                "Eliminar escena actual…",
                Command::RemoveScene {
                    scene_id: self.production.graph().active_scene.clone(),
                },
                cx,
            ))
    }
    pub(super) fn profile_settings(&self, cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        let state = self.production.status();
        col()
            .gap(px(10.))
            .child(label("Perfiles de grabación y streaming", p.secondary))
            .children(self.forms.profiles.iter().enumerate().map(|(i, profile)| {
                let draft = profile.clone();
                row()
                    .child(label(profile.id.clone(), p.ink).flex_1())
                    .child(quiet(("edit-profile", i), "Editar").on_click(cx.listener(
                        move |v, _, w, cx| {
                            v.refresh_profiles();
                            if let Some(current) =
                                v.forms.profiles.iter().find(|p| p.id == draft.id).cloned()
                            {
                                v.load_profile_draft(&current, w, cx);
                            }
                            cx.notify();
                        },
                    )))
                    .child(self.action(
                        ("record-profile", i),
                        if state["output_configuration"]["recording_profile"] == profile.id {
                            "✓ Grabación"
                        } else {
                            "Grabación"
                        },
                        Command::SelectOutputProfile {
                            target: OutputTarget::Recording,
                            profile_id: profile.id.clone(),
                        },
                        cx,
                    ))
                    .child(self.action(
                        ("stream-profile", i),
                        if state["output_configuration"]["streaming_profile"] == profile.id {
                            "✓ RTMP"
                        } else {
                            "RTMP"
                        },
                        Command::SelectOutputProfile {
                            target: OutputTarget::Streaming,
                            profile_id: profile.id.clone(),
                        },
                        cx,
                    ))
                    .child(self.action(
                        ("delete-profile", i),
                        "Eliminar…",
                        Command::RemoveOutputProfile {
                            id: profile.id.clone(),
                        },
                        cx,
                    ))
            }))
            .child(field(
                "ID del perfil (a-z, 0-9, -, _)",
                &self.forms.profile_id,
                p,
            ))
            .child(
                row().children(
                    [
                        (RecordingEncoder::Auto, "Auto"),
                        (RecordingEncoder::Videotoolbox, "VideoToolbox"),
                        (RecordingEncoder::X264, "x264"),
                    ]
                    .map(|(encoder, name)| {
                        quiet(name, name)
                            .selected(self.forms.encoder == encoder)
                            .on_click(cx.listener(move |v, _, _, cx| {
                                v.forms.encoder = encoder;
                                cx.notify();
                            }))
                    }),
                ),
            )
            .child(field(
                "Bitrate CBR (250–20000 kb/s)",
                &self.forms.bitrate,
                p,
            ))
            .child(field("Keyframes (1–10 segundos)", &self.forms.keyframes, p))
            .child(
                quiet(
                    "reorder",
                    if self.forms.reorder {
                        "Desactivar reordenamiento para producir"
                    } else {
                        "Reordenamiento: desactivado"
                    },
                )
                .disabled(!self.forms.reorder)
                .on_click(cx.listener(|v, _, _, cx| {
                    v.forms.reorder = false;
                    cx.notify();
                })),
            )
            .children(
                self.forms
                    .profile(cx)
                    .map(|profile| profile.warnings())
                    .unwrap_or_default()
                    .into_iter()
                    .map(|warning| {
                        label(
                            format!("{} {}", warning.message, warning.recommendation),
                            p.warn,
                        )
                    }),
            )
            .child(
                quiet("apply-profile", "Crear / actualizar perfil").on_click(cx.listener(
                    |v, _, w, cx| {
                        if v.forms.revision != v.production.revision {
                            v.message =
                                "El núcleo cambió; reabre el panel antes de aplicar.".into();
                            cx.notify();
                            return;
                        }
                        match v.forms.profile(cx) {
                            Ok(profile) => {
                                if v.forms.profiles.iter().any(|p| p.id == profile.id) {
                                    v.confirm_command(
                                        Command::UpsertOutputProfile { profile },
                                        w,
                                        cx,
                                    );
                                } else {
                                    v.form_submit(Command::UpsertOutputProfile { profile }, cx);
                                }
                            }
                            Err(e) => {
                                v.message = e.into();
                                cx.notify();
                            }
                        }
                    },
                )),
            )
            .child(
                row()
                    .child(self.action(
                        "save-profiles",
                        "Guardar perfiles",
                        Command::SaveOutputProfiles,
                        cx,
                    ))
                    .child(self.action(
                        "load-profiles",
                        "Restaurar perfiles…",
                        Command::LoadOutputProfiles,
                        cx,
                    )),
            )
            .child(label(
                format!(
                    "{}×{} · {} FPS · H.264/AAC · CBR. Ajusta el video en Preferencias.",
                    state["width"], state["height"], state["fps"]
                ),
                p.muted,
            ))
            .child(label(
                "Auto prefiere hardware y conserva el fallback a x264.",
                p.muted,
            ))
    }
    pub(super) fn output_settings(&self, cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        let s = self.production.status();
        let disabled = s["output_lifecycle"]["native_busy"] == true
            || s["output_lifecycle"]["shutdown_pending"] == true
            || self.forms.revision != self.production.revision;
        col().gap(px(10.))
            .child(label("Receptor de transmisión",p.ink).font_weight(FontWeight::SEMIBOLD))
            .child(label("127.0.0.1 · /live/motive · configura con ambas salidas detenidas",p.secondary))
            .child(label(if s["output_configuration"]["endpoint"].is_object() { format!("Configurado: {} · puerto {}",s["output_configuration"]["endpoint"]["transport"].as_str().unwrap_or("—"),s["output_configuration"]["endpoint"]["port"]) } else { "Falta configurar el receptor local antes de transmitir.".into() },p.secondary))
            .child(row().children([(Transport::Rtmp,"RTMP"),(Transport::Rtmps,"RTMPS")].map(|(transport,name)|quiet(name,name).selected(self.forms.transport==transport).disabled(disabled).on_click(cx.listener(move|v,_,_,cx|{v.forms.transport=transport;cx.notify();})))))
            .child(field("Puerto local (1024–65535)",&self.forms.port,p))
            .child(quiet("apply-endpoint","Configurar receptor local").disabled(disabled).on_click(cx.listener(|v,_,_,cx|{match v.forms.endpoint(cx){Ok(endpoint)=>v.form_submit(Command::ConfigureStream{endpoint},cx),Err(e)=>{v.message=e.into();cx.notify();}}})))
            .child(label(format!("Perfil de streaming: {}",s["output_configuration"]["streaming_profile"].as_str().unwrap_or("—")),p.secondary))
            .child(label("Selecciona el perfil con Perfiles de salida en la barra superior.",p.muted))
            .child(label("RTMPS verifica el certificado y el nombre del receptor.",p.muted))
            .child(field("Referencia Keychain (kc_…; nunca la clave)",&self.forms.credential,p))
            .child(row().child(quiet("bind-credential","Vincular referencia").disabled(disabled).on_click(cx.listener(|v,_,_,cx|{let credential_ref=v.forms.credential.read(cx).value().to_string();if valid_credential_ref(&credential_ref){v.form_submit(Command::SelectStreamCredential{credential_ref:Some(credential_ref)},cx)}else{v.message="Referencia opaca inválida; no se envió ningún valor al núcleo.".into();cx.notify();}})))
                .child(self.action("clear-credential","Desvincular",Command::SelectStreamCredential{credential_ref:None},cx).disabled(disabled)))
            .child(quiet("credential-status","Consultar acceso Keychain").on_click(cx.listener(|v,_,_,cx|{let credential_ref=v.forms.credential.read(cx).value().to_string();if valid_credential_ref(&credential_ref){let r=v.command(Command::CredentialStatus{credential_ref},"UI",cx);v.message=format!("Keychain: {}",r["access"].as_str().unwrap_or("Error de consulta"));}else{v.message="Referencia opaca inválida".into();}cx.notify();})))
            .child(label("Gestiona los secretos con el asistente local de credenciales. Aquí solo se vinculan sus referencias.",p.muted))
    }
    pub(super) fn studio_settings(&self, cx: &mut Context<Self>) -> Div {
        let p = Palette::new(self.dark);
        let s = self.production.status();
        col().gap(px(10.)).child(self.video_settings(cx))
            .child(label("Apariencia y diagnóstico",p.ink).font_weight(FontWeight::SEMIBOLD))
            .child(label("Proyecto y apariencia se guardan por separado.",p.secondary))
            .child(quiet("theme-setting",if self.dark{"Cambiar a tema claro"}else{"Cambiar a tema oscuro"}).on_click(cx.listener(|v,_,w,cx|{v.dark = !v.dark;Palette::apply(v.dark,Some(w),cx);cx.notify();})))
            .child(quiet("safe-setting","Mostrar / ocultar margen seguro (⇧S)").on_click(cx.listener(|v,_,_,cx|{v.toggle_safe();cx.notify();})))
            .child(quiet("save-ui-preferences","Guardar apariencia y guías").on_click(cx.listener(|v,_,_,cx|{let prefs=crate::ui::preferences::Preferences{version:1,dark:v.dark,safe_margin:v.safe_margin()};v.message=match prefs.save(){Ok(())=>"Preferencias visuales guardadas".into(),Err(_)=>"No se pudieron guardar las preferencias visuales".into()};cx.notify();})))
            .child(label("Arrastre: una confirmación al soltar. ⌘ desactiva snapping; ⇧ restringe eje. ⌘Z / ⇧⌘Z: transformaciones compatibles.",p.secondary))
            .child(label(format!("libobs {} · {}×{} · {} FPS · revisión {}",s["libobs"].as_str().unwrap_or("—"),s["width"],s["height"],s["fps"],self.production.revision),p.secondary))
            .child(label(format!("Permisos · pantalla {} · cámara {} · micrófono {}",self.devices["screen_permission"],self.devices["camera_permission"],self.devices["microphone_permission"]),p.secondary))
            .children(s["sources"].as_array().into_iter().flatten().filter(|source| source["active"]==true && source["freshness_notice"].as_str().is_some_and(|notice| !notice.is_empty())).map(|source| {
                let id=source["id"].as_str().unwrap_or("");
                let name=self.production.graph().sources.iter().find(|item|item.id==id).map(|item|item.name.as_str()).unwrap_or(id);
                let age=source["frame_age_ms"].as_u64().map(|ms|format!(" Último buffer hace {:.1} s.",ms as f64/1000.)).unwrap_or_default();
                label(format!("{name} · La ventana no entrega buffers recientes; comprueba el contenido y su visibilidad.{age}"),p.warn)
            }))
            .child(label(format!("Render {} · retrasados {} · descartes preview {}",s["stats"]["rendered_frames"],s["stats"]["lagged_frames"],s["stats"]["preview_busy_drops"]),p.secondary))
            .child(self.action("record-preflight","Comprobar grabación",Command::PreflightOutput{target:OutputTarget::Recording},cx))
            .child(label(self.output_encoder_summary(&s),p.secondary))
            .child(label("Duración, descartes y errores por destino en Salidas.",p.muted))
            .child(label(format!("Destino de la última grabación: {}",s["outputs"]["recording"]["path"].as_str().unwrap_or("ninguno")),p.secondary))
    }
}
