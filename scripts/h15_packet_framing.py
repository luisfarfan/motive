"""Exact pinned VideoToolbox Annex B → AVCC size accounting; no size tolerance.

This explains metadata framing, not cryptographic identity of native payloads.
The first packet and its PTS remain the origin; no searching or shifting it.
"""
import hashlib

VT_SOURCE_SHA256 = '0cb16ae01c8b8ad1b62bb532fef0144559d63875fcf9076abe42d21d19e7b1b3'


def unhex_dump(text):
    return bytes.fromhex(''.join(line.split(':', 1)[1].lstrip().split('  ', 1)[0]
                                for line in text.splitlines() if ':' in line))


def avcc_nals(data):
    result, offset = [], 0
    while offset < len(data):
        if offset+4 > len(data):
            raise ValueError('Truncated AVCC length')
        count = int.from_bytes(data[offset:offset+4], 'big')
        offset += 4
        if not count or offset+count > len(data):
            raise ValueError('Invalid AVCC NAL size')
        result.append(data[offset:offset+count])
        offset += count
    return result


def parameter_sets(extra):
    if len(extra) < 7 or extra[0] != 1 or extra[4] & 3 != 3:
        raise ValueError('Expected AVC configuration with four-byte NAL lengths')
    result, offset = [], 6
    for group in range(2):
        if group == 0:
            count = extra[5] & 31
        else:
            if offset >= len(extra):
                raise ValueError('Missing PPS count')
            count = extra[offset]
            offset += 1
        if not count:
            raise ValueError('Missing AVC parameter sets')
        for _ in range(count):
            if offset+2 > len(extra):
                raise ValueError('Truncated parameter length')
            size = int.from_bytes(extra[offset:offset+2], 'big')
            offset += 2
            if not size or offset+size > len(extra):
                raise ValueError('Truncated parameter data')
            nal = extra[offset:offset+size]
            if nal[0] & 31 != (7 if group == 0 else 8):
                raise ValueError('Unexpected parameter NAL type')
            result.append(nal)
            offset += size
    # AVC high-profile extension may follow PPS; it does not enter the packet.
    return result


def vt_first_packet_proof(native, actual, stream, upstream_source):
    if hashlib.sha256(upstream_source).hexdigest() != VT_SOURCE_SHA256:
        raise ValueError('VideoToolbox source differs from reviewed OBS 33.0.1')
    if stream['codec_name'] != 'h264' or not native['keyframe'] or 'K' not in actual['flags']:
        raise ValueError('Expected initial H.264 keyframe')
    payload = unhex_dump(actual['data'])
    if len(payload) != int(actual['size']):
        raise ValueError('Packet hexdump does not match declared size')
    nals = avcc_nals(payload)
    parameters = parameter_sets(unhex_dump(stream['extradata']))
    if nals[:len(parameters)] != parameters or len(nals) <= len(parameters):
        raise ValueError('Packet parameter prefix differs from CodecPrivate')
    rest = nals[len(parameters):]
    if any(n[0] & 31 not in (5, 6) for n in rest) or not any(n[0] & 31 == 5 for n in rest):
        raise ValueError('Unexpected initial VideoToolbox NAL types')
    # handle_keyframe emits four bytes per parameter; convert_block_nals_to_annexb
    # emits three bytes per remaining NAL. AVCC emits four bytes for each NAL.
    annexb_size = sum(len(n)+4 for n in parameters) + sum(len(n)+3 for n in rest)
    if annexb_size != native['size']:
        raise ValueError('Exact Annex B reconstruction does not match native size')
    return {'status': 'PASS_FRAMING_METADATA', 'native_size': native['size'],
            'container_size': len(payload), 'annexb_size': annexb_size,
            'nal_types': [n[0] & 31 for n in nals], 'source_sha256': VT_SOURCE_SHA256,
            'container_payload_sha256': hashlib.sha256(payload).hexdigest(),
            'native_payload_identity': 'NOT_MEASURED', 'origin_shifted': False}
