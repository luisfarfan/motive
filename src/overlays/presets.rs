use super::*;
use crate::scene::{Layouts, Transform};
use serde_json::{Value, json};
pub fn catalogue() -> Value {
    json!({"version":1,"presets":[
        {"id":"professional_lower_third","name":"Professional Lower Third","entry":"native 300 ms fade","exit":"native 300 ms fade","parameters":{"title":"Alex Rivera","subtitle":"Creative producer","background":1121833,"accent":3401909,"color":15988730,"duration_ms":0}},
        {"id":"starting_soon","name":"Starting Soon","parameters":{"title":"Starting soon","subtitle":"Make something worth sharing","background":726809,"accent":3401909,"color":15988730,"duration_ms":60000}},
        {"id":"be_right_back","name":"Be Right Back","parameters":{"title":"Be right back","subtitle":"A short pause. Stay with us.","background":726809,"accent":3401909,"color":15988730,"duration_ms":0},"decoration_animation":{"version":1,"source_name":"Accent","animation":{"kind":"scale_in","easing":"ease_in_out","duration_ms":1200,"distance":0,"scale_from":0.7}}}
    ]})
}
pub fn instantiate(
    preset: Preset,
    p: PresetParameters,
) -> anyhow::Result<Vec<(String, Definition, Layouts)>> {
    text(&p.title)?;
    text(&p.subtitle)?;
    for c in [p.background, p.accent, p.color] {
        color(c)?;
    }
    let mut result = vec![];
    if !matches!(preset, Preset::ProfessionalLowerThird) {
        result.push((
            "Background".into(),
            Definition::Shape {
                shape: Shape::Rectangle,
                width: 960,
                height: 540,
                color: p.background,
                opacity: 1.,
                border_color: None,
                border_width: 0,
            },
            Layouts::full(),
        ));
    }
    let (kind, width, height, layouts) = match preset {
        Preset::ProfessionalLowerThird => (
            WidgetKind::LowerThird,
            640,
            140,
            Layouts {
                horizontal: Transform::rect(32., 368., 640., 140., 4),
                vertical: Transform::rect(32., 758., 476., 170., 4),
            },
        ),
        Preset::StartingSoon => (
            WidgetKind::Countdown,
            480,
            400,
            Layouts {
                horizontal: Transform::rect(240., 70., 480., 400., 4),
                vertical: Transform::rect(30., 280., 480., 400., 4),
            },
        ),
        Preset::BeRightBack => (
            WidgetKind::LowerThird,
            720,
            180,
            Layouts {
                horizontal: Transform::rect(120., 180., 720., 180., 4),
                vertical: Transform::rect(30., 340., 480., 240., 4),
            },
        ),
    };
    let definition = Definition::Widget {
        widget: Widget {
            kind,
            title: p.title,
            subtitle: p.subtitle,
            width,
            height,
            background: p.background,
            accent: p.accent,
            color: p.color,
            opacity: 1.,
            duration_ms: p.duration_ms,
        },
    };
    definition.validate()?;
    result.push(("Message".into(), definition, layouts));
    if matches!(preset, Preset::BeRightBack) {
        result.push((
            "Accent".into(),
            Definition::Shape {
                shape: Shape::Circle,
                width: 64,
                height: 64,
                color: p.accent,
                opacity: 0.8,
                border_color: None,
                border_width: 0,
            },
            Layouts {
                horizontal: Transform::rect(448., 80., 64., 64., 3),
                vertical: Transform::rect(238., 230., 64., 64., 3),
            },
        ));
    }
    Ok(result)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn presets_are_versioned_and_adapted_without_changing_landscape() {
        let catalogue = catalogue();
        assert_eq!(catalogue["version"], 1);
        for (i, preset) in [
            Preset::ProfessionalLowerThird,
            Preset::StartingSoon,
            Preset::BeRightBack,
        ]
        .into_iter()
        .enumerate()
        {
            let p: PresetParameters =
                serde_json::from_value(catalogue["presets"][i]["parameters"].clone()).unwrap();
            for (_, definition, layouts) in instantiate(preset, p).unwrap() {
                definition.validate().unwrap();
                layouts.horizontal.validate().unwrap();
                layouts.vertical.validate().unwrap();
            }
        }
    }
    #[test]
    fn brb_decoration_recipe_resolves_to_a_source_and_valid_typed_animation() {
        let catalogue = catalogue();
        let brb = catalogue["presets"]
            .as_array()
            .unwrap()
            .iter()
            .find(|preset| preset["id"] == "be_right_back")
            .unwrap();
        let recipe = &brb["decoration_animation"];
        assert_eq!(recipe["version"], 1);
        let animation: Animation = serde_json::from_value(recipe["animation"].clone()).unwrap();
        animation.validate().unwrap();
        assert_eq!(animation.kind, AnimationKind::ScaleIn);
        assert_eq!(animation.easing, Easing::EaseInOut);
        assert_eq!(animation.duration_ms, 1200);
        assert_eq!(animation.distance, 0.);
        assert!((animation.scale_from - 0.7).abs() < f32::EPSILON);
        let parameters = serde_json::from_value(brb["parameters"].clone()).unwrap();
        let sources = instantiate(Preset::BeRightBack, parameters).unwrap();
        let targets: Vec<_> = sources
            .iter()
            .filter(|(name, _, _)| name == recipe["source_name"].as_str().unwrap())
            .collect();
        assert_eq!(targets.len(), 1);
        assert!(matches!(
            targets[0].1,
            Definition::Shape {
                shape: Shape::Circle,
                ..
            }
        ));
        for layout in [&targets[0].2.horizontal, &targets[0].2.vertical] {
            assert_eq!((layout.width, layout.height), (64., 64.));
        }
    }
}
