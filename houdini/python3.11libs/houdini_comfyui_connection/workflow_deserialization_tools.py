import hou  # type:ignore
from dataclasses import dataclass
from itertools import chain, zip_longest
from collections import OrderedDict

from .compound_graph_tools import create_single_tool, get_node_definitions, DefinitionOverrideData, DefinitionOverrideConnectionData, MissingNodeDefinitionError, is_subgraph_wrapper, is_subnet_wrapper, subnet_wrapper_wrapped_node, convert_parm_to_input, partial_graph_input_to_parm_i
from .subnet_wrapper_helper import propagate_single_parameter
from .compound_graph_core import debug
from .compound_graph_core_graph_helpers import follow_output_till_deadend_condition

@dataclass
class InputDef:
    id: str|None
    type: str
    name: str
    required: bool
    tags: dict[str, bool|int|float|str]
    link_ids: list[int]
    has_widget: bool

@dataclass
class OutputDef:
    id: str|None
    type: str
    name: str
    is_list: bool
    tags: dict[str, bool|int|float|str]
    link_ids: list[int]

@dataclass
class NodeDefinition:
    compat_orig_data: dict  # TODO: remove me!
    type_id: str
    input_defs: list[InputDef]
    output_defs: list[OutputDef]
    display_name: str|None
    category: str
    python_module: str

@dataclass
class Link:
    id: int
    origin_id: str
    origin_slot: int
    target_id: str
    target_slot: int
    type: str

@dataclass
class SubgraphDefinition(NodeDefinition):
    input_node_id: str
    output_node_id: str
    nodes: list
    links_dict: dict[int, Link]


def create_network_from_workflow(host: str, parent_node: hou.Node, workflow: dict) -> dict[str, hou.Node]:
    node_definitions = _parse_node_data(get_node_definitions(host))
    subgraph_definitions = _parse_subgraph_data(workflow.get('definitions', {}).get('subgraphs', []))
    return _create_network_from_workflow_nodes(
        node_definitions,
        subgraph_definitions,
        parent_node,
        workflow.get('nodes', []),
        _parse_links(workflow.get('links', [])),
        set(),
    )


def _parse_links(raw_links: list) -> dict[int, Link]:
        # # sometimes links are a dict, sometimes a list... convert all to dict
        links = {}
        for i, link in enumerate(raw_links[:]):
            if isinstance(link, dict):
                links[link['id']] = Link(
                    link['id'],
                    link['origin_id'],
                    link['origin_slot'],
                    link['target_id'],
                    link['target_slot'],
                    link['type'],
                )
            elif isinstance(link, list):
                links[link[0]] = Link(
                    link[0],
                    link[1],
                    link[2],
                    link[3],
                    link[4],
                    link[5],
                )
        return links

def _infer_haswidget_from_type(type_name: str|list) -> bool:
    return type_name in ('INT', 'FLOAT', 'STRING', 'BOOLEAN', 'COMBO') or isinstance(type_name, list)


def _parse_subgraph_data(data: list[dict]) -> dict[str, SubgraphDefinition]:
    defs = {}
    for sub_data in data:
        if sub_data['version'] != 1:
            raise RuntimeError(f'subgraph definition of version {sub_data["version"]} is not supported')
        gid = sub_data['id']
        name = sub_data['name']
        input_node_id = sub_data['inputNode']['id']
        output_node_id = sub_data['outputNode']['id']
        input_defs = []
        for int_data in sub_data['inputs']:
            input_defs.append(InputDef(
                int_data['id'],
                int_data['type'],
                int_data['name'],
                True,
                {},
                int_data['linkIds'],
                _infer_haswidget_from_type(int_data['type']),
            ))
        output_defs = []
        for out_data in sub_data['outputs']:
            output_defs.append(OutputDef(
                out_data['id'],
                out_data['type'],
                out_data['name'],
                False,
                {},
                out_data['linkIds'],
            ))
        nodes = sub_data['nodes']
        links = _parse_links(sub_data['links'])

        defs[gid] = SubgraphDefinition(
            sub_data,
            gid,
            input_defs,
            output_defs,
            sub_data.get('name', 'unknown subgraph'),
            '',  # TODO: put something reasonable here
            '',  # TODO: put something reasonable here
            input_node_id,
            output_node_id,
            nodes,
            links,
        )
    return defs


def _parse_node_data(data: dict[str, dict]) -> dict[str, NodeDefinition]:
    defs = {}
    for type_name, def_data in data.items():
        # parse inputs
        input_defs = []
        for input_name, input_cat in chain(
            zip_longest(def_data.get('input_order', {}).get('required', []), [], fillvalue='required'),
            zip_longest(def_data.get('input_order', {}).get('optional', []), [], fillvalue='optional'),
        ):
            input_defs.append(InputDef(
                None,  # this definition of inputs has no id
                def_data['input'][input_cat][input_name][0],
                input_name,
                input_cat == 'required',
                def_data['input'][input_cat][input_name][1] if len(def_data['input'][input_cat][input_name]) > 1 else {},
                [],  # simple nodes has no internal connections in definitions
                _infer_haswidget_from_type(def_data['input'][input_cat][input_name][0]),
            ))
        #parse outputs
        output_defs = []
        for output_name, output_type, output_is_list in zip(
            def_data.get('output_name', []),
            def_data.get('output', []),
            def_data.get('output_is_list', []),
        ):
            output_defs.append(OutputDef(
                None,
                output_type,
                output_name,
                output_is_list,
                {},
                [],
            ))

        defs[type_name] = NodeDefinition(
            def_data,
            def_data['name'],
            input_defs,
            output_defs,
            def_data.get('display_name'),
            def_data.get('category', 'uncategorized'),
            def_data.get('python_module', ''),
        )
        
    return defs


def _create_subgraph(
    name: str|None,
    subgraph_type_id: str,
    node_definitions: dict[str, NodeDefinition],
    subgraph_definitions: dict[str, SubgraphDefinition],
    parent_node: hou.Node,
) -> hou.Node:
    subgraph_def = subgraph_definitions[subgraph_type_id]
    subnet = parent_node.createNode('subnet')
    subnet.setName(hou.text.variableName(name or subgraph_def.display_name), unique_name=True)

    id_to_nodes = _create_network_from_workflow_nodes(
        node_definitions, 
        subgraph_definitions,
        subnet,
        subgraph_def.nodes,
        subgraph_def.links_dict,
        {k for k, v in subgraph_def.links_dict.items() 
            if v.origin_id in {subgraph_def.input_node_id, subgraph_def.output_node_id}
            or v.target_id in {subgraph_def.input_node_id, subgraph_def.output_node_id}
        },
    )
    node_id_to_data = {node_data['id']: node_data for node_data in subgraph_def.nodes}
    # connect contents to subnet inputs/outputs
    input_node = [x for x in subnet.children() if x.type().name() == 'input'][0]  # expect one default
    output_node = subnet.subnetOutputs()[0]  # expect one default

    subnet.parm('inputs').set(len(subgraph_def.input_defs))
    subnet.parm('outputs').set(len(subgraph_def.output_defs))
    for i, input_def in enumerate(subgraph_def.input_defs):
        subnet.parm(f'inputlabel{i+1}').set(input_def.name)
        inp_type = 'vector2'
        if input_def.type == 'IMAGE':
            inp_type = 'vector4'
        elif input_def.type == 'MASK':
            inp_type = 'float'
        subnet.parm(f'inputtype{i+1}').set(inp_type)
        for link_id in input_def.link_ids:
            link_data = subgraph_def.links_dict[link_id]
            if link_data.target_id == subgraph_def.output_node_id:
                continue  # let output connection logic handle this
            debug(f'create_subgraph: connecting link:{link_id}', link_data)
            target_node = id_to_nodes[link_data.target_id]
            # TODO!: when target is output
            
            _connect_nodes(
                input_node,
                link_data.origin_slot,
                target_node,
                node_id_to_data[link_data.target_id]['inputs'][link_data.target_slot]['name']
            )
    for i, output_def in enumerate(subgraph_def.output_defs):
        subnet.parm(f'outputlabel{i+1}').set(output_def.name)
        out_type = 'vector2'
        if output_def.type == 'IMAGE':
            out_type = 'vector4'
        elif output_def.type == 'MASK':
            out_type = 'float'
        subnet.parm(f'outputtype{i+1}').set(out_type)
        for link_id in output_def.link_ids:
            link_data = subgraph_def.links_dict[link_id]
            if link_data.origin_id == subgraph_def.input_node_id:
                orig_node = input_node
            else:
                orig_node = id_to_nodes[link_data.origin_id]
            output_node.setInput(link_data.target_slot, orig_node, link_data.origin_slot)


    # create extra param after everything is connected
    ptg = subnet.parmTemplateGroup()
    standard_templates = ptg.parmTemplates()
    ptg.addParmTemplate(hou.FolderParmTemplate('graph_inputs', 'Inputs'))
    ptg.addParmTemplate(hou.FolderParmTemplate('standard', 'Standard'))
    for pt in standard_templates:  # move default subnet parms to Inputs tab
        ptg.remove(pt)
        ptg.appendToFolder('Standard', pt)

    for i, input_def in enumerate(subgraph_def.input_defs):
        ptg.appendToFolder('Standard', hou.StringParmTemplate(f'input_meta_typename_{i+1}', f'type name {i+1}', 1))

        inner_pg_node_data = find_connected_partial_graph_node(input_node, i)
        if inner_pg_node_data is None:  # rarely, but may happen (likely by user mistake), skip parameters for such connections
            continue
        inner_pg_node, inner_i = inner_pg_node_data
        parm_template = propagate_single_parameter(inner_pg_node, i+1, inner_i, also_connect_node_to_it=False, ignore_unkonwn_types=True, ptg_owner=subnet)
        if parm_template is None:
            continue
        parm_template.setConditional(hou.parmCondType.HideWhen, "{ hasinput(0) == 1 }")
        ptg.appendToFolder('Inputs', parm_template)

    subnet.setParmTemplateGroup(ptg)

    # finally set typename metadata
    for i, input_def in enumerate(subgraph_def.input_defs):
        subnet.parm(f'input_meta_typename_{i+1}').set(input_def.type)

    return subnet


def find_connected_partial_graph_node(node: hou.Node, output_id: int) -> tuple[hou.Node, int]|None:
    """
    returns  wrapped partial graph node AND param_i corresponding to the input
    (not input index)
    """
    condition = lambda node: node.type().nameComponents()[2] == 'comfyui_partial_graph'
    node, new_out_id = follow_output_till_deadend_condition(node, output_id, stop_condition=condition)
    if node is None or not condition(node):
        return None
    
    return node, partial_graph_input_to_parm_i(node, new_out_id)


def _create_network_from_workflow_nodes(
    node_definitions: dict[str, NodeDefinition],
    subgraph_definitions: dict[str, SubgraphDefinition],
    parent_node: hou.Node,
    workflow_nodes: list,
    workflow_links: dict[int, Link],
    ignored_links: set[int],
) -> dict[str, hou.Node]:
    nodes = {}
    links_to_ignore = set()
    node_ids_to_ignore = set()
    node_id_to_data = {node_data['id']: node_data for node_data in workflow_nodes}
    
    # filter connections to subgraph inputs/outputs
    debug('ignored links:', ignored_links)
    link_id_to_nodes = {
        link_id: (
            (link.origin_id, node_id_to_data[link.origin_id]['outputs'][link.origin_slot].get('slot_index', 0)),
            (link.target_id, node_id_to_data[link.target_id]['inputs'][link.target_slot]['name'])
        ) for link_id, link in workflow_links.items() if link_id not in ignored_links
    }

    new_node = None
    for node_data in workflow_nodes:
        # first check special values
        if node_data['type'] == 'Reroute':
            node_ids_to_ignore.add(node_data['id'])
            new_node = parent_node.createNetworkDot()
            # trick to match setInput signatures with OpNode
            new_node.setInput = lambda self, _, item_to_become_input, output_index=0: self.setInput(item_to_become_input, output_index)
        elif node_data['type'] in ('PrimitiveNode',):
            node_ids_to_ignore.add(node_data['id'])
            # for now we ignore those,
            #  they SEEEM to not do any graph activity, 
            #  as values on their connections are already set to the same values
            #  just ignore their links for future
            # TODO: this is a workaround for now, implement this properly!
            for output in node_data['outputs']:
                for link in output.get('links', []):
                    links_to_ignore.add(link)
            continue
        elif node_data['type'] in ('MarkdownNote', 'Note'):
            node_ids_to_ignore.add(node_data['id'])
            note = parent_node.createStickyNote('note')
            note.setText(node_data.get('widgets_values', [])[0])
            note.setPosition(hou.Vector2([x*m for x, m in zip(node_data['pos'], (0.01, -0.01))]))
            note.setSize(hou.Vector2([x*0.01 for x in node_data['size']]))
        elif node_data['type'] in node_definitions:
            # then process general node type
            extra_data = DefinitionOverrideData(
                OrderedDict((x['name'], DefinitionOverrideConnectionData(x['type'])) for x in node_data['inputs']),
                OrderedDict((x['name'], DefinitionOverrideConnectionData(x['type'])) for x in node_data['outputs']),
                node_data['type'],
            )
            new_node = create_single_tool(
                parent_node,
                node_definitions[node_data['type']].compat_orig_data,
                extra_workflow_data=extra_data
            )
        elif node_data['type'] in subgraph_definitions:
            # name=None to create node with default name, we set actual name after creation
            new_node = _create_subgraph(None, node_data['type'], node_definitions, subgraph_definitions, parent_node)
        else:
            raise MissingNodeDefinitionError(
                node_data['type'],
                pack_name=node_data.get('properties', {}).get('cnr_id', node_data.get('properties', {}).get('aux_id')),
                node_id=str(node_data['id'])
            )

        if new_node:
            if 'title' in node_data:
                new_node.setName(hou.text.variableName(node_data['title']), unique_name=True)
            new_node.setPosition(hou.Vector2([x*m for x, m in zip(node_data['pos'], (0.01, -0.01))]))
            nodes[node_data['id']] = new_node
    
    # set values and links
    for node_data in workflow_nodes:
        if node_data['id'] in node_ids_to_ignore:
            continue
        # TODO: there can be soo many specifics to how comfy's web interface interprets workflow json
        #  we here do it in a SIMPLIFIED way, so things MAY go wrong
        input_name_to_link_id = {inp['name']: inp['link'] for inp in node_data['inputs'] if inp['link'] is not None}
        values = node_data.get('widgets_values', {})
        if node_data.get('mode') == 4:  # TODO: no idea if this is a const value or a bit mask
            nodes[node_data['id']].bypass(True)
        
        # chain(node_definition['input_order'].get('required', ()), node_definition['input_order'].get('optional', ()))
        if node_data['type'] in node_definitions:
            node_def = node_definitions[node_data['type']]
        elif node_data['type'] in subgraph_definitions:
            node_def = subgraph_definitions[node_data['type']]
        else:
            raise RuntimeError(f'{node_data["type"]} is neither a known node definition, nor a subgraph definition')
        
        for input_def in node_def.input_defs:
            input_name = input_def.name
            vals_to_post_skip = 0
            special_names = ('seed',)  # these param names seem to be hardcoded to be treated to have control_after_generate
            if input_def.tags.get('control_after_generate', False) or input_name in special_names:
                # that means extra widget is created for the value that we ignore, if that input is not connected that is
                vals_to_post_skip = 1

            if input_name in input_name_to_link_id:
                if input_def.has_widget:
                    if isinstance(values, list):  # widget values are still present and need to be skipped
                        for i in range(1 + vals_to_post_skip):
                            values.pop(0)
                link_id = input_name_to_link_id[input_name]
                if link_id is None or link_id in ignored_links:
                    continue
                (node1_id, node1_out), (node2_id, node2_inname) = link_id_to_nodes[link_id]
                _connect_nodes(nodes[node1_id], node1_out, nodes[node2_id], node2_inname)
            elif input_def.has_widget:
                if isinstance(values, list):
                    val = values.pop(0)
                    for i in range(vals_to_post_skip):
                        values.pop(0)
                elif isinstance(values, dict):
                    val = values[input_name]
                else:
                    raise NotImplementedError(f'don\'t know how to treat widgets_values of type "{type(values)}"')
                _set_node_input_value(nodes[node_data['id']], input_name, val)

    return nodes


def _connect_nodes(in_node: hou.Node, in_output_id: int, out_node: hou.Node, out_input_name):
    # output ids in comfy terms are same as in hou wrapper terms, so we can just use in_output_id
    if is_subgraph_wrapper(out_node):
        for i in range(out_node.evalParm('inputs')):
            if out_node.evalParm(f'inputlabel{i+1}') == out_input_name:
                out_node.setInput(i, in_node, in_output_id)
    elif is_subnet_wrapper(out_node):
        _connect_compound_nodes(in_node, in_output_id, out_node, out_input_name)
    else:
        raise RuntimeError('cannot connect to node', out_node)


def _set_node_input_value(node: hou.Node, input_name: str, value):
    if is_subgraph_wrapper(node):
        for i in range(node.evalParm('inputs')):
            if node.evalParm(f'inputlabel{i+1}') == input_name:
                #input_type = node.evalParm(f'input_meta_typename_{i+1}')
                debug(f'setting subgraph parm: {node.path()}, {i+1} to {repr(value)}')
                parm = node.parm(f'input_parm_{i+1}')
                # ints may be represented with string parms, like in texting case
                if isinstance(parm.parmTemplate(), hou.StringParmTemplate) and isinstance(value, (int, float)):
                    value = str(value)
                node.parm(f'input_parm_{i+1}').set(value)
                #f'input{i}_{input_type}_widget'
                break
        else:
            raise KeyError(f'cannot find input "{input_name}" to set value {repr(value)}')
    elif is_subnet_wrapper(node):
        _set_compound_node_input_value(node, input_name, value)
    else:
        raise RuntimeError('')

def create_network_from_prompt(host: str, parent_node: hou.Node, prompt) -> dict[str, hou.Node]:
    node_definitions = get_node_definitions(host)

    nodes = {}
    for node_id, node_data in prompt.items():
        if node_data['class_type'] not in node_definitions:
            raise MissingNodeDefinitionError(node_data['class_type'], node_id=node_id)
        extra_data = DefinitionOverrideData(
            OrderedDict((k, DefinitionOverrideConnectionData(None, v, isinstance(v, list))) for k, v in node_data['inputs'].items()),
            None,
            node_data['class_type'],
        )
        new_node = create_single_tool(
            parent_node,
            node_definitions[node_data['class_type']],
            extra_workflow_data=extra_data,
        )
        # color some nodes that will probably need user attention
        if node_definitions[node_data['class_type']].get('output_node'):
            new_node.setColor(hou.Color((1.0, 0, 0)))
        if node_data['class_type'] in ('LoadImage', 'LoadImageMask'):
            new_node.setColor(hou.Color((1.0, 1.0, 0)))

        nodes[node_id] = new_node
        if title := node_data.get('_meta', {}).get('title'):
            new_node.setName(hou.text.variableName(title), unique_name=True)

    # another loop for connections
    for node_id, node_data in prompt.items():
        for input_name, input_data in node_data.get('inputs', {}).items():
            if isinstance(input_data, list):  # list of 2 items represents a connection
                input_node_id, input_output_id = input_data
                _connect_nodes(nodes[input_node_id], input_output_id, nodes[node_id], input_name)

    return nodes


def _connect_compound_nodes(in_node: hou.Node, in_output_id: int, out_node: hou.Node, out_input_name):
    debug('connecting compound nodes:', in_node, in_output_id, out_node, out_input_name)
    out_node_inner = subnet_wrapper_wrapped_node(out_node)
    for i in range(out_node_inner.evalParm('cui_inputs')):
        if out_input_name != out_node_inner.evalParm(f'cui_i_node_input_{i+1}'):
            continue
        input_val = out_node_inner.evalParm(f'cui_i_value_type_{i+1}')
        
        # may be possible if input exist only in UI, not on prompt level (when we create graph from workflow)
        if not input_val.startswith('input'):
            convert_parm_to_input(out_node, f'input_parm_{i+1}')
            # easier to just call ourselves again instead of adapting to changes in parameters
            return _connect_compound_nodes(in_node, in_output_id, out_node, out_input_name)

        inner_input_num = int(input_val[5:]) - 1
        # expect input of inner_input_num to exist and have a single connection to input
        input_num = out_node_inner.inputConnectors()[inner_input_num][0].inputIndex()

        out_node.setInput(input_num, in_node, in_output_id)
        break
    else:
        raise RuntimeError(f'failed to find now to connect nodes: {in_node}, {out_node}, out:{in_output_id} to in:{out_input_name}')


def _set_compound_node_input_value(node: hou.Node, input_name: str, value):
    debug('setting compound nodes value:', node, input_name, value)
    node_inner = subnet_wrapper_wrapped_node(node)
    for i in range(node_inner.evalParm('cui_inputs')):
        if input_name != node_inner.evalParm(f'cui_i_node_input_{i+1}'):
            continue
        val_type = node_inner.evalParm(f'cui_i_value_type_{i+1}')
        # found i, now actually set the value
        if val_type == 'int':
            node_inner.parm(f'cui_i_value_int_{i+1}').set(int(value))
        elif val_type == 'textint':
            node_inner.parm(f'cui_i_value_textint_{i+1}').set(str(value))
        elif val_type == 'float':
            node_inner.parm(f'cui_i_value_float_{i+1}').set(float(value))
        elif val_type == 'text':
            node_inner.parm(f'cui_i_value_text_{i+1}').set(str(value))
        elif val_type == 'bool':
            node_inner.parm(f'cui_i_value_bool_{i+1}').set(value)
        else:
            raise RuntimeError(f'unknown value type "{val_type}"')
        break
    else:
        raise RuntimeError(f'failed to find input "{input_name}" on "{node.patn()}"')
