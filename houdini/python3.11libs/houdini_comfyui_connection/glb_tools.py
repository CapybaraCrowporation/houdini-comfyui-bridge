"""
helpers for 3D results coming back from comfy

houdini's glTF importer cannot use images embedded in a .glb as material textures
("The texture must be saved on disk so the material can be provided a filename").
comfy's mesh nodes (ApplyTextureToMesh etc) embed all maps inside the glb,
so after download we unpack them next to the file and point the glb at them.
the result is still a valid glb, it just references external image files.
"""
import json
import re
import struct
from pathlib import Path

_GLB_MAGIC = 0x46546C67  # b'glTF'
_CHUNK_JSON = 0x4E4F534A  # b'JSON'
_CHUNK_BIN = 0x004E4942  # b'BIN\0'

_MIME_TO_EXT = {
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/webp': 'webp',
    'image/ktx2': 'ktx2',
}


def _read_glb(path: Path) -> tuple[dict, bytes]:
    data = path.read_bytes()
    if len(data) < 20:
        raise ValueError(f'{path} is too small to be a glb')
    magic, version, _length = struct.unpack_from('<III', data, 0)
    if magic != _GLB_MAGIC:
        raise ValueError(f'{path} is not a glb file')
    if version != 2:
        raise ValueError(f'{path}: glb version {version} is not supported')

    offset = 12
    gltf = None
    bin_chunk = b''
    while offset + 8 <= len(data):
        chunk_length, chunk_type = struct.unpack_from('<II', data, offset)
        offset += 8
        chunk = data[offset:offset + chunk_length]
        offset += chunk_length
        if chunk_type == _CHUNK_JSON:
            gltf = json.loads(chunk.decode('utf-8'))
        elif chunk_type == _CHUNK_BIN:
            bin_chunk = chunk
    if gltf is None:
        raise ValueError(f'{path}: no JSON chunk found')
    return gltf, bin_chunk


def _write_glb(path: Path, gltf: dict, bin_chunk: bytes) -> None:
    json_bytes = json.dumps(gltf, separators=(',', ':')).encode('utf-8')
    json_bytes += b' ' * (-len(json_bytes) % 4)  # json chunk is padded with spaces
    bin_bytes = bin_chunk + b'\x00' * (-len(bin_chunk) % 4)  # bin chunk is padded with zeros

    total = 12 + 8 + len(json_bytes) + (8 + len(bin_bytes) if bin_bytes else 0)
    out = bytearray(struct.pack('<III', _GLB_MAGIC, 2, total))
    out += struct.pack('<II', len(json_bytes), _CHUNK_JSON) + json_bytes
    if bin_bytes:
        out += struct.pack('<II', len(bin_bytes), _CHUNK_BIN) + bin_bytes
    path.write_bytes(bytes(out))


def _texture_roles(gltf: dict) -> dict[int, str]:
    """
    image index -> readable role name, taken from how materials use the textures
    """
    textures = gltf.get('textures', [])

    def image_of(texture_info: dict|None) -> int|None:
        if not texture_info or 'index' not in texture_info:
            return None
        texture_index = texture_info['index']
        if texture_index >= len(textures):
            return None
        texture = textures[texture_index]
        # webp / basisu extensions keep the image in their own "source"
        for ext_data in texture.get('extensions', {}).values():
            if isinstance(ext_data, dict) and 'source' in ext_data:
                return ext_data['source']
        return texture.get('source')

    roles: dict[int, str] = {}
    for material in gltf.get('materials', []):
        pbr = material.get('pbrMetallicRoughness', {})
        for role, info in (
            ('basecolor', pbr.get('baseColorTexture')),
            ('metallicroughness', pbr.get('metallicRoughnessTexture')),
            ('normal', material.get('normalTexture')),
            ('occlusion', material.get('occlusionTexture')),
            ('emissive', material.get('emissiveTexture')),
        ):
            image_index = image_of(info)
            if image_index is None:
                continue
            if image_index in roles and role not in roles[image_index].split('_'):
                roles[image_index] += f'_{role}'  # e.g. a packed ORM map used for occlusion and metal/rough
            else:
                roles.setdefault(image_index, role)
    return roles


def extract_glb_textures(glb_path: str|Path) -> list[Path]:
    """
    writes every image embedded in glb_path next to it as <stem>_<role>.<ext>
    and rewrites the glb so its images reference those files.
    returns the written texture paths (empty if the glb had no embedded images)
    """
    glb_path = Path(glb_path)
    gltf, bin_chunk = _read_glb(glb_path)
    images = gltf.get('images', [])
    buffer_views = gltf.get('bufferViews', [])
    roles = _texture_roles(gltf)

    written: list[Path] = []
    used_names: set[str] = set()
    for i, image in enumerate(images):
        if 'bufferView' not in image:
            continue  # already external (or a data uri, which houdini handles the same way as external)
        view = buffer_views[image['bufferView']]
        start = view.get('byteOffset', 0)
        image_bytes = bin_chunk[start:start + view['byteLength']]

        ext = _MIME_TO_EXT.get(image.get('mimeType', ''), 'png')
        role = roles.get(i) or re.sub(r'[^\w-]+', '_', image.get('name') or '') or f'texture{i}'
        name = f'{glb_path.stem}_{role}'
        while name in used_names:
            name += f'_{i}'
        used_names.add(name)

        texture_path = glb_path.with_name(f'{name}.{ext}')
        texture_path.write_bytes(image_bytes)
        written.append(texture_path)

        image['uri'] = texture_path.name  # relative to the glb, as gltf expects
        del image['bufferView']
        # image bytes stay in the bin chunk unreferenced; harmless, keeps buffer offsets intact

    if written:
        _write_glb(glb_path, gltf, bin_chunk)
    return written
