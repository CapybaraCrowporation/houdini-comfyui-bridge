"""
helpers for reasoning about ComfyUI socket types

ComfyUI types can be:
  - a single concrete type: "IMAGE"
  - a comma separated multi-type: "IMAGE,MASK", "FILE_3D,FILE_3D_SPLAT_ANY,..."
  - a generic type: "*" or "COMFY_MATCHTYPE_V3" (V3 MatchType, used by Switch, Resize Image/Mask, loops)
  - a V3 container that nests other inputs: autogrow, dynamic combo, dynamic group
"""

ANY = '*'
MATCHTYPE = 'COMFY_MATCHTYPE_V3'
AUTOGROW = 'COMFY_AUTOGROW_V3'
DYNAMICCOMBO = 'COMFY_DYNAMICCOMBO_V3'
DYNAMICGROUP = 'COMFY_DYNAMICGROUP_V3'

GENERIC_TYPES = frozenset((ANY, MATCHTYPE))
CONTAINER_TYPES = frozenset((AUTOGROW, DYNAMICCOMBO, DYNAMICGROUP))


def split_type(type_name) -> frozenset[str]:
    """
    "IMAGE,MASK" -> {"IMAGE", "MASK"}
    non-strings (old style list COMBOs) and empty values give an empty set
    """
    if not type_name or not isinstance(type_name, str):
        return frozenset()
    return frozenset(x.strip() for x in type_name.split(',') if x.strip())


def is_generic(type_name) -> bool:
    return bool(split_type(type_name) & GENERIC_TYPES)


def is_compatible(out_type, in_type) -> bool:
    """
    mirrors how comfy frontend allows links:
    generic on either side matches anything, otherwise multi-type sets must intersect.
    unknown (empty) types never block a connection
    """
    out_set = split_type(out_type)
    in_set = split_type(in_type)
    if not out_set or not in_set:
        return True
    if (out_set | in_set) & GENERIC_TYPES:
        return True
    return bool(out_set & in_set)


def is_3d_type(type_name) -> bool:
    """
    MESH or any FILE_3D* flavour, all of which SaveGLB accepts
    """
    return any(x == 'MESH' or x.startswith('FILE_3D') for x in split_type(type_name))


def is_image_like(type_name) -> bool:
    """
    types that houdini should treat as image sockets
    """
    return bool(split_type(type_name) & {'IMAGE', 'MASK'})


def houdini_image_upload_kind(in_type) -> str|None:
    """
    when a plain houdini image (COP) is wired into a comfy input of in_type,
    decide how it should be loaded on comfy side.
    returns 'IMAGE', 'MASK' or None if an image cannot go there
    """
    types = split_type(in_type)
    if not types or 'IMAGE' in types or types & GENERIC_TYPES:  # empty treated as image for compat
        return 'IMAGE'
    if 'MASK' in types:
        return 'MASK'
    return None


# V3 dynamic inputs
#
# Comfy sends nested dynamic inputs in the prompt with dot-qualified names:
#   DynamicCombo "sign_mode" with option "udf" adding "qef"  ->  "sign_mode": "udf", "sign_mode.qef": False
#   Autogrow "images" with prefix "image"                    ->  "images.image0", "images.image1", ...
# Houdini side we flatten everything into plain inputs using those same names,
# and remember which combo selection each nested input depends on.


def iter_section_inputs(inputs_dict: dict):
    """
    yields (name, input_data, is_required) from a {"required": {...}, "optional": {...}} dict, preserving order
    """
    for cat in ('required', 'optional'):
        for name, data in ((inputs_dict or {}).get(cat) or {}).items():
            yield name, data, cat == 'required'


def _input_meta(data) -> dict:
    return data[1] if isinstance(data, (list, tuple)) and len(data) > 1 and isinstance(data[1], dict) else {}


def _autogrow_entries(name: str, data, existing_names: list[str]) -> list[tuple[str, list]]|None:
    """
    returns flattened (name, input_data) for an autogrow input, or None if template is not supported
    """
    template = _input_meta(data).get('template', {})
    template_inputs = list(iter_section_inputs(template.get('input', {})))
    if len(template_inputs) != 1:
        return None  # multi-input templates are not supported yet
    template_name, template_data, _ = template_inputs[0]

    if existing_names:  # workflow already tells us which slots exist
        names = existing_names
    elif template.get('names'):
        names = [f'{name}.{x}' for x in template['names']]
    else:
        prefix = template.get('prefix')
        if prefix is None:
            prefix = template_name
        min_count = template.get('min', 1) or 0
        max_count = template.get('max', 8)
        count = min(max_count, max(min_count, 2))  # a couple of free slots by default
        names = [f'{name}.{prefix}{i}' for i in range(count)]
    return [(x, template_data) for x in names]


def expand_inputs(node_type: dict, workflow_input_names=()) -> tuple[list[tuple[str, list]], dict[str, list[list[list[str]]]]]:
    """
    flattens V3 dynamic inputs of a node definition (object_info entry).

    returns:
        ordered list of (flat_name, input_data); DynamicCombo selectors become plain COMBOs
        conditions: {flat_name: [[[combo_name, key], ...], ...]}
            a flat input is active if ANY of its condition lists fully holds,
            inputs that are not in this dict are always active
    """
    flat: dict[str, list] = {}
    conditions: dict[str, list] = {}
    always_active: set[str] = set()
    workflow_input_names = list(workflow_input_names or ())

    def add(name, data, cond):
        if name not in flat:
            flat[name] = data
        if cond:
            conditions.setdefault(name, []).append([list(x) for x in cond])
        else:
            always_active.add(name)

    def walk(name, data, cond):
        input_type = data[0] if data else None
        if input_type == DYNAMICCOMBO:
            meta = _input_meta(data)
            options = meta.get('options', [])
            keys = [o.get('key') for o in options]
            combo_meta = {k: v for k, v in meta.items() if k != 'options'}
            combo_meta['options'] = keys
            if 'default' not in combo_meta and keys:
                combo_meta['default'] = keys[0]
            add(name, ['COMBO', combo_meta], cond)
            for option in options:
                for nested_name, nested_data, _ in iter_section_inputs(option.get('inputs', {})):
                    walk(f'{name}.{nested_name}', nested_data, cond + [(name, option.get('key'))])
        elif input_type == AUTOGROW:
            existing = [x for x in workflow_input_names if x.startswith(name + '.')]
            entries = _autogrow_entries(name, data, existing)
            if entries is None:
                add(name, data, cond)  # fallback: single opaque wire, like before
                return
            for entry_name, entry_data in entries:
                walk(entry_name, entry_data, cond)
        else:
            add(name, data, cond)

    order = node_type.get('input_order', {})
    inputs = node_type.get('input', {})
    for cat in ('required', 'optional'):
        for name in order.get(cat, []):
            data = (inputs.get('required') or {}).get(name, (inputs.get('optional') or {}).get(name))
            if data is None:
                continue
            walk(name, data, [])

    for name in always_active:
        conditions.pop(name, None)
    return list(flat.items()), conditions
