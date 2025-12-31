import hou  # type: ignore


def propagate_single_parameter(node: hou.Node, ptg_i: int, i: int,
    *,
    also_connect_node_to_it: bool,
    ignore_unkonwn_types: bool = False,
    ptg_owner: hou.Node | None = None,
) -> hou.ParmTemplate | None:
    """
    node - innermost partial graph node
    """
    assert node.type().nameComponents()[2] == 'comfyui_partial_graph'
    if ptg_owner is None:
        ptg_owner = node.parent()
    assert ptg_owner is not None

    parm = node.parm(f'cui_i_node_input_{i}')
    extra_tags = {'hou_comfyui_inner_input_i': str(i)}

    inp_type = node.evalParm(f'cui_i_meta_orig_value_type_{i}')

    if inp_type == 'int':
        val_parm = node.parm(f'cui_i_value_int_{i}')
        range_min, range_max = node.parmTuple(f'cui_i_meta_intrange_{i}').eval()
        if range_max <= range_min:
            # if invalid - set default range
            range_max = range_min + 10
        pt = hou.IntParmTemplate(f'input_parm_{ptg_i}', parm.eval(), 1, min=range_min, max=range_max, default_value=(val_parm.eval(),), tags=extra_tags)
        conn_expr = f'ch("../input_parm_{ptg_i}")'
    elif inp_type == 'textint':
        val_parm = node.parm(f'cui_i_value_textint_{i}')
        pt = hou.StringParmTemplate(
            f'input_parm_{ptg_i}',
            parm.eval(),
            1,
            default_value=(val_parm.eval(),),
            script_callback=r'''import re;kwargs['parm'].set(re.sub(r'(?<!^)\D|(?<=^)[^-\d]', '', kwargs['parm'].eval()))''',
            script_callback_language=hou.scriptLanguage.Python,
            tags=extra_tags,
        )
        conn_expr = f'chs("../input_parm_{ptg_i}")'
    elif inp_type == 'float':
        val_parm = node.parm(f'cui_i_value_float_{i}')
        range_min, range_max = node.parmTuple(f'cui_i_meta_floatrange_{i}').eval()
        if range_max <= range_min:
            # if invalid - set default range
            range_max = range_min + 1.0
        pt = hou.FloatParmTemplate(f'input_parm_{ptg_i}', parm.eval(), 1, min=range_min, max=range_max, default_value=(val_parm.eval(),), tags=extra_tags)
        conn_expr = f'ch("../input_parm_{ptg_i}")'
    elif inp_type == 'text':
        val_parm = node.parm(f'cui_i_value_text_{i}')
        is_multiline = bool(node.parm(f'cui_i_meta_textmultiline_{i}').eval())
        
        use_menuvals = node.evalParm(f'cui_i_meta_usetextvals_{i}')
        
        item_generator_script = None
        if use_menuvals:
            item_generator_script = (
                'import json\n'
                'from houdini_comfyui_connection.node_data import get_node_data\n'
                'node = kwargs["node"]\n'
                'items = []\n'
                f'inner = node.node({repr(ptg_owner.relativePathTo(node))})\n'
                f'if inner.evalParm("cui_i_meta_userdatatextvals_{i}"):\n'
                f'    items_data = get_node_data(inner, "_hou_cui_input_{i}_textvals") or "[]"\n'
                '    items = [x for y in json.loads(items_data) for x in (y, y)]\n'
                'else:\n'
                f'    count = inner.evalParm("cui_i_meta_textvals_{i}")\n'
                '    for i in range(count):\n'
                f'        item = inner.evalParm(f"cui_i_meta_textval_{i}_{{i+1}}")\n'
                '        items.append(item)\n'
                '        items.append(item)\n'
                'return items\n'
            )
        

        action_tags = {}
        if use_menuvals:
            action_tags = {
                'script_action_help': 'update values from the server',
                'script_action': 
                    'from houdini_comfyui_connection.compound_graph_tools import subnet_wrapper_wrapped_node, is_subnet_wrapper\n'
                    'node = kwargs["node"]\n'
                    'parm, = kwargs["parmtuple"]\n'
                    'not_myself = False\n'
                    'if not is_subnet_wrapper(node):\n'
                    '    ref_parms = kwargs["parmtuple"][0].parmsReferencingThis()\n'
                    '    if len(ref_parms) == 1 and is_subnet_wrapper(ref_parms[0].node()):\n'
                    '        parm = ref_parms[0]\n'
                    '        node = parm.node()\n'
                    '        not_myself = True\n'
                    'inner_i = parm.parmTemplate().tags()["hou_comfyui_inner_input_i"]\n'
                    'inner_node = subnet_wrapper_wrapped_node(node)\n'
                    'inner_node.hdaModule().update_input_text_values_callback(inner_node, inner_i, update_tool_also=not not_myself)\n',
                'script_action_icon': 'BUTTONS_page_reload',
            }
        # hou bug, item_generator_script cannot be given None value, so we have to workaround
        _kwargs = {}
        if item_generator_script is not None:
            _kwargs['item_generator_script'] = item_generator_script
        if metaparm := node.parm(f'cui_i_meta_textvalseditable_{i}'):  # check for compat
            if metaparm.eval():
                _kwargs['menu_type'] = hou.menuType.StringReplace
        pt = hou.StringParmTemplate(
            f'input_parm_{ptg_i}',
            parm.eval(),
            1,
            default_value=(val_parm.eval(),),
            tags={
                'editor': '1' if is_multiline else '0', 
                **action_tags,
                **extra_tags,
            },
            **_kwargs,
        )
        conn_expr = f'chs("../input_parm_{ptg_i}")'
    elif inp_type == 'bool':
        val_parm = node.parm(f'cui_i_value_bool_{i}')
        pt = hou.ToggleParmTemplate(f'input_parm_{ptg_i}', parm.eval(), default_value=bool(val_parm.eval()), tags=extra_tags)
        conn_expr = f'ch("../input_parm_{ptg_i}")'
    else:
        if ignore_unkonwn_types:
            return None
        else:
            raise NotImplementedError(f'unknown input type "{inp_type}"')

    if also_connect_node_to_it:
        val_parm.setExpression(conn_expr, language=hou.exprLanguage.Hscript)

    return pt
