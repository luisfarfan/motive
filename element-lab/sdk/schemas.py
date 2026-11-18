"""Authoring schema v1. Native leaves remain owned by the real Rust crate."""
from common import LAB, write_json

def obj(fields, optional=()):
    return {"type":"object", "properties":fields, "required":[k for k in fields if k not in optional], "additionalProperties":False}
def arr(item, maximum=64, minimum=0):
    return {"type":"array", "items":item, "minItems":minimum, "maxItems":maximum}
def string(maximum=160):
    return {"type":"string", "maxLength":maximum}
def number(lo, hi, integer=False):
    return {"type":"integer" if integer else "number", "minimum":lo, "maximum":hi}
ID = {"type":"string", "pattern":"[A-Za-z0-9][A-Za-z0-9_-]{0,47}"}
VERSION = {"type":"string", "pattern":"[0-9]{1,6}\\.[0-9]{1,6}\\.[0-9]{1,6}"}
LICENSE = {"enum":["GPL-3.0-or-later","CC0-1.0","MIT","CC-BY-4.0"]}
PATH = {"type":"string", "maxLength":240, "minLength":1}
HASH = {"type":"string", "pattern":"[0-9a-f]{64}"}
SCALAR = {"oneOf":[string(4096),number(-4096,0xffffff),{"type":"boolean"}]}
VALUE_SPEC = obj({"type":{"enum":["string","number","integer","boolean","color"]},"default":{},
    "minimum":number(-4096,3600000),"maximum":number(-4096,3600000),"max_length":number(1,4096,True)},
    ("minimum","maximum","max_length"))
LAYOUT = obj({"x":number(-4096,4096),"y":number(-4096,4096),"width":number(1,4096),"height":number(1,4096),
              "visible":{"type":"boolean"},"order":number(0,31,True)})
ANIMATION = obj({"id":ID,"layer_id":ID,"kind":{"enum":["fade_in","fade_out","slide_in","slide_out","scale_in","scale_out"]},
    "easing":{"enum":["linear","ease_in","ease_out","ease_in_out"]},"duration_ms":number(100,10000,True),
    "distance":number(-1920,1920),"scale_from":number(.1,2)})
EVENT_KINDS = ["manual.button_pressed","keyboard.shortcut","viewer.follow","viewer.subscribe","viewer.donation",
               "viewer.reward_redeemed","timer.completed","motive.custom_event"]
CAPABILITIES = ["text","shape","widget","layer_animation","scene_transition","image_asset","video_asset"]
RESOURCE = obj({"id":ID,"path":PATH,"kind":{"enum":["image","video"]},"sha256":HASH,"bytes":number(1,64*1024**2,True),
    "width":number(1,2048,True),"height":number(1,2048,True),"duration_ms":{"oneOf":[{"type":"null"},number(1,60000,True)]},
    "license":LICENSE})
NODE = {"oneOf":[obj({"id":ID,"name":string(80),"type":{"const":"primitive"},
            "native":{"type":"object","description":"Validated by motive_show_control::packs::VisualDefinition, not a second primitive schema."}}),
    obj({"id":ID,"name":string(80),"type":{"const":"composed"},"children":arr(ID,32,1)})]}
PROPERTY = obj({"id":ID,"label":string(),"value":VALUE_SPEC,"bindings":arr(obj({
    "scope":{"enum":["node","layout","animation"]},"ref":ID,
    "field":{"enum":["text","color","opacity","size","background","background_opacity","border_color","border_width",
        "widget.title","widget.subtitle","widget.background","widget.accent","widget.color","widget.opacity","widget.duration_ms",
        "horizontal.x","horizontal.y","horizontal.width","horizontal.height","horizontal.visible","horizontal.order",
        "vertical.x","vertical.y","vertical.width","vertical.height","vertical.visible","vertical.order","duration_ms","distance","scale_from"]}
    }),16,1),"export":{"enum":["compile_time","creatorpack_property"]}})
STATE = obj({"id":ID,"description":string(512),"backend":{"enum":["native_widget","authoring_only","future"]}})
BINDING = obj({"id":ID,"event_kind":{"enum":EVENT_KINDS},"match":string(64),"actions":arr({"type":"object"},16,1),
    "description":string(512)})
ELEMENT = obj({"schema_version":{"const":1},"kind":{"const":"native_element"},"id":ID,"name":string(80),"version":VERSION,
    "author":string(128),"license":LICENSE,"root":ID,"nodes":arr(NODE,64,1),"resources":arr(RESOURCE,16),
    "layers":arr(obj({"id":ID,"node":ID,"horizontal":LAYOUT,"vertical":LAYOUT}),32,1),
    "properties":arr(PROPERTY),"states":arr(STATE,16),"animations":arr(ANIMATION),"events":arr(BINDING,32),
    "dependencies":arr(obj({"id":ID,"version":VERSION,"status":{"enum":["embedded","future"]}}),16),
    "capabilities":obj({"required":arr({"enum":CAPABILITIES},16),"future":arr(string(128),16)}),
    "variants":arr(obj({"id":ID,"properties":{"type":"object","additionalProperties":SCALAR,"maxProperties":64}}),16),
    "budget":obj({"max_sources":number(1,16,True),"max_layers":number(1,32,True),"max_texture_bytes":number(1,256*1024**2,True),
                  "max_resource_bytes":number(0,128*1024**2,True)}),
    "metadata":obj({"description":string(1024),"category":string(64),"tags":arr(string(32),16),"limitations":arr(string(512),16)})})

def export():
    write_json(LAB/'element-spec/element.schema.json', {"$schema":"https://json-schema.org/draft/2020-12/schema", **ELEMENT})

if __name__ == '__main__':
    export()
