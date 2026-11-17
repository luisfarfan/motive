//! Schemas share the same validated Production commands as UI and CLI.
use serde_json::{Value, json};
fn object(fields: Value) -> Value {
    let required = fields
        .as_object()
        .unwrap()
        .keys()
        .cloned()
        .collect::<Vec<_>>();
    json!({"type":"object","properties":fields,"required":required,"additionalProperties":false})
}
fn tagged(kind: &str, mut fields: Value) -> Value {
    fields["kind"] = json!({"const":kind});
    object(fields)
}
pub fn definition_schema() -> Value {
    let color = json!({"type":"integer","minimum":0,"maximum":16777215});
    let opacity = json!({"type":"number","minimum":0,"maximum":1});
    let width = json!({"type":"integer","minimum":1,"maximum":1920});
    let height = json!({"type":"integer","minimum":1,"maximum":1080});
    let text = json!({"type":"string","maxLength":4096});
    let asset = json!({"type":"string","pattern":"^asset-[0-9a-f]{64}$"});
    json!({"oneOf":[
        tagged("text",json!({"text":text,"font":{"enum":["Helvetica","Arial","Menlo"]},"size":{"type":"integer","minimum":8,"maximum":192},"color":color,"opacity":opacity,"align":{"enum":["left","center","right"]},"width":width,"height":height,"background":{"anyOf":[color,{"type":"null"}]},"background_opacity":opacity,"outline":{"type":"boolean"}})),
        tagged("image",json!({"asset_id":asset,"opacity":opacity})),
        tagged("video",json!({"asset_id":asset,"opacity":opacity,"looping":{"type":"boolean"}})),
        tagged("shape",json!({"shape":{"enum":["rectangle","circle"]},"width":width,"height":height,"color":color,"opacity":opacity,"border_color":{"anyOf":[color,{"type":"null"}]},"border_width":{"type":"integer","minimum":0,"maximum":32}})),
        tagged("widget",json!({"widget":object(json!({"kind":{"enum":["lower_third","countdown","alert"]},"title":text,"subtitle":text,"width":width,"height":height,"background":color,"accent":color,"color":color,"opacity":opacity,"duration_ms":{"type":"integer","minimum":0,"maximum":3600000}}))}))
    ]})
}
pub fn is_query(op: &str) -> bool {
    matches!(
        op,
        "overlay_capabilities"
            | "overlay_state"
            | "list_assets"
            | "asset_inventory"
            | "overlay_presets"
    )
}
pub fn tools() -> Vec<Value> {
    let id = json!({"type":"string","minLength":1,"maxLength":70});
    let name = json!({"type":"string","minLength":1,"maxLength":80});
    let animation = object(
        json!({"kind":{"enum":["fade_in","fade_out","slide_in","slide_out","scale_in","scale_out"]},"easing":{"enum":["linear","ease_in","ease_out","ease_in_out"]},"duration_ms":{"type":"integer","minimum":100,"maximum":10000},"distance":{"type":"number","minimum":-1920,"maximum":1920},"scale_from":{"type":"number","minimum":0.1,"maximum":2}}),
    );
    let mut incoming_animation = animation.clone();
    incoming_animation["properties"]["kind"]["enum"] = json!(["fade_in", "slide_in", "scale_in"]);
    let parameters = object(
        json!({"title":{"type":"string","maxLength":4096},"subtitle":{"type":"string","maxLength":4096},"background":{"type":"integer","minimum":0,"maximum":16777215},"accent":{"type":"integer","minimum":0,"maximum":16777215},"color":{"type":"integer","minimum":0,"maximum":16777215},"duration_ms":{"type":"integer","minimum":0,"maximum":3600000}}),
    );
    let entries = [
        (
            "overlay_capabilities",
            "Capacidades reales, schema de definiciones y límites; Browser Source permanece bloqueado por aislamiento.",
            json!({}),
        ),
        (
            "overlay_state",
            "Definiciones compartidas, runtime nativo de widgets/animaciones y operación asíncrona de importación.",
            json!({}),
        ),
        (
            "list_assets",
            "Metadatos de recursos administrados y verificados. No lee rutas externas ni devuelve bytes.",
            json!({}),
        ),
        (
            "import_asset",
            "Importa una copia explícita ya autorizada en var/imports; solo basename. Operación asíncrona, consulta overlay_state. Idle.",
            json!({"file_name":{"type":"string","pattern":"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$"}}),
        ),
        (
            "asset_inventory",
            "Inventario de metadatos con errores por recurso, incluso si falta un archivo. No lee rutas externas. La validación para renderizar permanece estricta.",
            json!({}),
        ),
        (
            "remove_asset",
            "Elimina recurso administrado no referenciado por ninguna escena. Idle.",
            json!({"asset_id":id}),
        ),
        (
            "create_overlay",
            "Crea fuente visual libobs y una capa, reutilizable mediante add_layer. Requiere idle; proyecto pasa a v4.",
            json!({"scene_id":id,"name":name,"definition":definition_schema()}),
        ),
        (
            "update_overlay",
            "Actualiza contenido/estilo sin recrear fuente ni encoder. Kind/asset inmutables; video solo idle.",
            json!({"source_id":id,"definition":definition_schema()}),
        ),
        (
            "overlay_event",
            "Acción tipada sobre widget/video; reloj monotónico nativo, sin agente por frame; audio de video deshabilitado.",
            json!({"source_id":id,"event":{"enum":["show","hide","trigger","timer_start","timer_stop","timer_reset","play","pause","restart","stop"]}}),
        ),
        (
            "animate_overlay",
            "Animación acotada de una capa activa con reloj OBS. Fade lineal; slide/scale con easing. Excluye Cut/Fade concurrente.",
            json!({"scene_id":id,"layer_id":id,"animation":animation}),
        ),
        (
            "cancel_overlay_animation",
            "Solicita cancelación por token; estado cancelled cuando el tick restaure la capa.",
            json!({"operation_id":{"type":"integer","minimum":1}}),
        ),
        (
            "trigger_animated_widget",
            "Activa alert/lower_third junto a su animación de entrada en un tick OBS atómico. Devuelve operation_id; cancelar restaura geometría y conserva un widget ya activado.",
            json!({"source_id":id,"scene_id":id,"layer_id":id,"animation":incoming_animation}),
        ),
        (
            "overlay_presets",
            "Tres presets originales v1 y parámetros editables para composiciones horizontales/verticales.",
            json!({}),
        ),
        (
            "instantiate_overlay_preset",
            "Instancia definiciones editables de un preset v1 en una escena mientras idle; devuelve IDs de fuentes.",
            json!({"scene_id":id,"preset":{"enum":["professional_lower_third","starting_soon","be_right_back"]},"parameters":parameters}),
        ),
    ];
    entries
        .into_iter()
        .map(|(op, description, fields)| {
            let required = fields
                .as_object()
                .unwrap()
                .keys()
                .map(String::as_str)
                .collect::<Vec<_>>();
            crate::control::tool(op, description, fields.clone(), &required, is_query(op))
        })
        .collect()
}
