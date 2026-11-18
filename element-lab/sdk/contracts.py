"""Delegate native semantics to Show Control; measure only offline estimates here."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import struct
import subprocess
import zlib
from common import LAB, LabError, encode, loads, read_bytes, require

_built = False

def contract(pack: dict, rules: dict) -> dict:
    global _built
    project = LAB/'sdk/contract-validator'
    if not _built:
        result = subprocess.run(['cargo','build','--offline','--locked','--quiet','--manifest-path',str(project/'Cargo.toml')],
                                env={**os.environ,'CARGO_TARGET_DIR':str(project/'target')}, capture_output=True, text=True, timeout=180)
        require(result.returncode == 0, 'CONTRACT_BUILD', result.stderr[-4000:])
        _built = True
    result = subprocess.run([str(project/'target/debug/motive-element-contract')],
                            input=encode({'pack':pack,'rules':rules}), capture_output=True, timeout=15)
    report = loads(result.stdout)
    if result.returncode:
        raise LabError(report['error']['code'], report['error']['message'])
    require(not report['plan']['unavailable'], 'CAPABILITY_UNAVAILABLE', str(report['plan']['unavailable']))
    return report

def config(rules=None):
    return {'schema_version':1,'variables':{},'max_actions_per_event':32,'queue_capacity':8,
            'rate_limit':20,'rate_window_ms':1000,'rules':rules or []}

def estimate(pack: dict, occupied: dict | None = None) -> dict:
    occupied = occupied or {'scenes':0,'sources':0,'layers':0,'texture_bytes':0,'video_sources':0}
    require(set(occupied) == {'scenes','sources','layers','texture_bytes','video_sources'} and
            all(type(x) is int and x >= 0 for x in occupied.values()), 'BUDGET', 'Explicit nonnegative occupied graph counts required')
    resources = {r['id']:r for r in pack['resources']}
    native, plan, videos = 0, 0, 0
    for source in pack['overlays']:
        d = source['definition']; kind = d['kind']
        box = d['widget'] if kind == 'widget' else resources[d['resource_id']] if kind in ('image','video') else d
        native += box['width'] * box['height'] * 8 + {'text':8*1024**2,'widget':16*1024**2}.get(kind,0)
        plan += (16*1024**2 if kind == 'image' else 1920*1080*16 if kind == 'video' else
                 box['width']*box['height']*{'text':12,'shape':4,'widget':16}[kind])
        videos += kind == 'video'
    counts = {'scenes':len(pack['scenes']),'sources':len(pack['overlays']),
              'layers':sum(len(s['layers']) for s in pack['scenes']),'texture_bytes':native,'video_sources':videos}
    limits = {'scenes':8,'sources':16,'layers':32,'texture_bytes':256*1024**2,'video_sources':4}
    total = {k:counts[k]+occupied[k] for k in counts}
    require(all(total[k] <= limits[k] for k in total), 'GLOBAL_BUDGET', f'Composition does not fit: {total}; limits: {limits}. No truncation performed.')
    require(plan <= pack['budget']['max_estimated_texture_bytes'], 'PACK_BUDGET', 'Pack texture budget exceeded')
    return {'counts':counts,'occupied':occupied,'total':total,'remaining':{k:limits[k]-total[k] for k in total},
            'pack_texture_bytes':plan,'native_texture_estimate_bytes':native,'rss_measured':False}

def png_info(data: bytes) -> dict:
    """Restricted 8-bit noninterlaced PNG scanline/CRC gate, not the native decoder."""
    require(data[:8] == b'\x89PNG\r\n\x1a\n', 'ASSET_CONTENT', 'PNG signature required')
    offset, payload, seen = 8, bytearray(), []
    w = h = channels = 0
    while offset < len(data):
        require(offset+12 <= len(data), 'ASSET_CONTENT', 'Truncated PNG')
        size = struct.unpack_from('>I',data,offset)[0]; kind = data[offset+4:offset+8]; end = offset+12+size
        require(end <= len(data), 'ASSET_CONTENT', 'Truncated PNG chunk')
        body = data[offset+8:end-4]
        require(zlib.crc32(kind+body) & 0xffffffff == struct.unpack_from('>I',data,end-4)[0], 'ASSET_CONTENT', 'PNG CRC mismatch')
        if not seen:
            require(kind == b'IHDR' and size == 13, 'ASSET_CONTENT', 'IHDR required')
        if kind == b'IHDR':
            require(not seen, 'ASSET_CONTENT', 'Duplicate IHDR')
            w,h,depth,color,compression,filtering,interlace = struct.unpack('>IIBBBBB',body)
            require(0 < w <= 2048 and 0 < h <= 2048 and depth == 8 and color in (0,2,4,6) and
                    compression == filtering == interlace == 0, 'ASSET_CONTENT', 'Unsupported PNG encoding or dimensions')
            channels = {0:1,2:3,4:2,6:4}[color]
        elif kind == b'IDAT':
            require(not (b'IDAT' in seen and seen[-1] != b'IDAT'), 'ASSET_CONTENT', 'Nonconsecutive IDAT')
            payload.extend(body)
        elif kind == b'IEND':
            require(size == 0 and end == len(data), 'ASSET_CONTENT', 'PNG trailing bytes')
        else:
            require(kind not in (b'acTL',b'fcTL',b'fdAT') and (kind[0] & 32 or kind == b'PLTE'), 'ASSET_CONTENT', 'Unsupported PNG chunk')
        seen.append(kind); offset = end
    require(seen and seen[-1] == b'IEND' and payload, 'ASSET_CONTENT', 'Incomplete PNG')
    expected = h*(1+w*channels); decoder = zlib.decompressobj()
    try:
        pixels = decoder.decompress(payload, expected+1)
    except zlib.error as e:
        raise LabError('ASSET_CONTENT', 'Invalid PNG compression') from e
    require(len(pixels) == expected and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,
            'ASSET_CONTENT', 'PNG decompression bounds')
    require(all(pixels[row*(1+w*channels)] <= 4 for row in range(h)), 'ASSET_CONTENT', 'Invalid PNG filter')
    return {'width':w,'height':h,'checks':'CRC + bounded scanlines; not native decoding'}

def check_asset(resource: dict, data: bytes) -> None:
    require(len(data) == resource['bytes'] and hashlib.sha256(data).hexdigest() == resource['sha256'], 'ASSET_HASH', resource['id'])
    # Fail closed for unimplemented decoders, even though the native schema supports more.
    require(resource['kind'] == 'image' and resource['file_name'].lower().endswith('.png'),
            'ASSET_DECODER_UNAVAILABLE', 'This SDK verifies PNG only; JPEG/WebP/video need an added offline decoder gate')
    info = png_info(data)
    require((info['width'],info['height']) == (resource['width'],resource['height']), 'ASSET_DIMENSIONS', resource['id'])

def check_assets(pack: dict, root: Path) -> dict[str,bytes]:
    assets = {}
    for r in pack['resources']:
        key = r['file_name']
        require(key.casefold() not in {s.casefold() for s in assets}, 'ASSET_COLLISION', key)
        data = read_bytes(root, 'assets/'+key)
        check_asset(r,data); assets[key] = data
    return assets
