from collections import OrderedDict
from dataclasses import dataclass
import os
from typing import Any, Optional
import hou  # type:ignore
import coptoolutils  # type:ignore
import requests
import json
from itertools import chain
from .compound_graph_core import get_output_index_from_input, CompoundGraphSource


# it seeems that houdini treats ints in parms as floats?
#  it completely breaks near 2^63 value as if float roundings are happening
#  therefore bounds are chosen arbitrarily here
#  and min/max in parmTemplates are even lower,
#  and even with these vals they kinda not quite work correctly, producing rounding errors
hou_parm_template_maxint = pow(2, 31) - 1
hou_parm_template_minint = -pow(2, 31)


class MissingNodeDefinitionError(RuntimeError):
    def __init__(self, node_type: str, *, pack_name: str|None = None, node_id: str|None = None):
        super().__init__()
        self.node_type = node_type
        self.pack_name = pack_name
        self.node_id = node_id


@dataclass
class DefinitionOverrideConnectionData:
    type: Optional[str]
    val: Any = None
    has_connection: bool = False


@dataclass
class DefinitionOverrideData:
    inputs: OrderedDict[str, DefinitionOverrideConnectionData]
    outputs: Optional[OrderedDict[str, DefinitionOverrideConnectionData]]
    class_type: str


def create_single_tool(graph: hou.Node, node_type: dict, interactive_kwargs=None, extra_workflow_data: Optional[DefinitionOverrideData] = None):
    """
    extra_workflow_data - data from corresponding workflow that provides additional information on how
        things are connected.
        this should cover:
            - widgets that became inputs
            - nodes with dynamically created inputs/outputs
    """
    if interactive_kwargs:
        graph_node = coptoolutils.genericTool(interactive_kwargs, 'comfyui_partial_graph', exact_node_type=False)
    else:
        graph_node = graph.createNode('comfyui_partial_graph')

    required_input_order = node_type['input_order'].get('required', [])
    optional_input_order = node_type['input_order'].get('optional', [])
    graph_node.parm('cui_inputs').set(len(required_input_order) + len(optional_input_order))
    node_type_name = node_type['name']
    node_display_name = node_type.get('display_name') or node_type_name
    node_title = node_type_name

    # set some global metadata
    if parm := graph_node.parm('cui_meta_python_module'):  # check for compat
        parm.set(node_type.get('python_module', ''))
    if parm := graph_node.parm('cui_meta_category'):  # check for compat
        parm.set(node_type.get('category', ''))

    workflow_inputs = OrderedDict()
    if extra_workflow_data:
        workflow_inputs = OrderedDict(extra_workflow_data.inputs)

    next_free_input = 0
    i = -1
    for i, input_name in enumerate(chain(required_input_order, optional_input_order)):
        # since input names are unique among required and optional - we can do the trick below
        input_data = node_type.get('input', {}).get('required', {}).get(
            input_name,
            node_type.get('input', {}).get('optional', {}).get(input_name)
        )
        assert input_data is not None

        graph_node.parm(f'cui_i_node_title_{i+1}').set(node_title)
        graph_node.parm(f'cui_i_node_input_{i+1}').set(input_name)

        meta_hint = None
        meta_min = None
        meta_max = None
        meta_default = None
        meta_multiline = None    

        # input_data is a list of 1 or 2 values
        input_type = input_data[0]

        if isinstance(input_type, str):
            graph_node.parm(f'cui_i_meta_intype_{i+1}').set(input_type)
        elif isinstance(input_type, list) or input_type == 'COMBO':  # we consider that STRING
            graph_node.parm(f'cui_i_meta_intype_{i+1}').set('STRING')
        else:
            raise NotImplementedError(f'handling of input_type of type "{type(input_type)}" ({repr(input_type)}) is not implemented')

        value_parm_name = None
        value_processor = lambda x: x
        force_input_to_be_wire = input_name in workflow_inputs and workflow_inputs[input_name].has_connection
        if not force_input_to_be_wire:
            force_input_to_be_wire = input_data[1].get('forceInput', False) if input_data and len(input_data) > 1 and isinstance(input_data[1], dict) else False
        
        input_metadata_unknown = False
        if input_type == 'INT':
            big_vals_string_workaround_needed = False
            if len(input_data) > 1:
                meta_hint = input_data[1].get('tooltip')
                meta_min = input_data[1].get('min', 0)
                meta_max = input_data[1].get('max', 100)  # default min/max are arbitrary
                if meta_min < hou_parm_template_minint or meta_max > hou_parm_template_maxint:
                    big_vals_string_workaround_needed = True
                meta_default = input_data[1].get('default')
                if isinstance(meta_default, list):  # not sure yet what default being a list means
                    meta_default = meta_default[0]
            if big_vals_string_workaround_needed:
                # houdini's interface works with ints as with floats,
                #  so it cannot properly represent i64 ints, so we have to use a string workaround
                graph_node.parm(f'cui_i_value_type_{i+1}').set('textint')
                value_parm_name = f'cui_i_value_textint_{i+1}'
                value_processor = lambda x: str(x)
                if meta_default is not None:
                    meta_default = str(meta_default)
                else:
                    meta_default = '0'
            else:
                graph_node.parm(f'cui_i_value_type_{i+1}').set('int')
                value_parm_name = f'cui_i_value_int_{i+1}'

            if meta_default is not None:
                graph_node.parm(value_parm_name).set(meta_default)
            if meta_min is not None:
                graph_node.parm(f'cui_i_meta_intrange_{i+1}x').set(meta_min)
            if meta_max is not None:
                graph_node.parm(f'cui_i_meta_intrange_{i+1}y').set(meta_max)
        #
        elif input_type == 'FLOAT':
            graph_node.parm(f'cui_i_value_type_{i+1}').set('float')
            if len(input_data) > 1:
                meta_hint = input_data[1].get('tooltip')
                meta_min = input_data[1].get('min')
                meta_max = input_data[1].get('max')
                meta_default = input_data[1].get('default')
                if isinstance(meta_default, list):  # not sure yet what default being a list means
                    meta_default = meta_default[0]
            value_parm_name = f'cui_i_value_float_{i+1}'
            if meta_default is not None:
                graph_node.parm(value_parm_name).set(meta_default)
            if meta_min is not None:
                graph_node.parm(f'cui_i_meta_floatrange_{i+1}x').set(meta_min)
            if meta_max is not None:
                graph_node.parm(f'cui_i_meta_floatrange_{i+1}y').set(meta_max)
        #
        elif input_type == 'STRING':
            graph_node.parm(f'cui_i_value_type_{i+1}').set('text')
            graph_node.parm(f'cui_i_meta_textvals_{i+1}').set(0)
            
            if len(input_data) > 1:
                meta_hint = input_data[1].get('tooltip')
                meta_multiline = input_data[1].get('multiline', False)
                meta_default = input_data[1].get('default')
                if isinstance(meta_default, list):  # not sure yet what default being a list means
                    meta_default = meta_default[0]
            value_parm_name = f'cui_i_value_text_{i+1}'
            if meta_default is not None:
                graph_node.parm(value_parm_name).set(meta_default)
            if meta_multiline is not None:
                graph_node.parm(f'cui_i_meta_textmultiline_{i+1}').set(meta_multiline)
        #
        elif input_type == 'BOOLEAN':
            graph_node.parm(f'cui_i_value_type_{i+1}').set('bool')
            if len(input_data) > 1:
                meta_hint = input_data[1].get('tooltip')
                meta_default = input_data[1].get('default')
                if isinstance(meta_default, list):  # not sure yet what default being a list means
                    meta_default = meta_default[0]
            value_parm_name = f'cui_i_value_bool_{i+1}'
            if meta_default is not None:
                graph_node.parm(value_parm_name).set(meta_default)
        #
        elif isinstance(input_type, list) or input_type == 'COMBO':
            # as far as i know, this can only be a list of strings
            if isinstance(input_type, list):
                value_options = input_type
                value_options_default = value_options[0] if value_options else ''
            else:
                value_options = input_data[1].get('options', [])
                value_options_default = value_options[0] if value_options else ''
                value_options_default = input_data[1].get('default', value_options_default)

            graph_node.parm(f'cui_i_value_type_{i+1}').set('text')
            if parm := graph_node.parm(f'cui_i_meta_usetextvals_{i+1}'):  # check for compat
                parm.set(True)
            if parm := graph_node.parm(f'cui_i_meta_userdatatextvals_{i+1}'):  # check for compat
                parm.set(True)  # by default use userdata to store items, but fill static vals too
                graph_node.setUserData(f'_hou_cui_input_{i+1}_textvals', json.dumps(value_options))
            graph_node.parm(f'cui_i_meta_textvals_{i+1}').set(len(value_options))
            graph_node.parm(f'cui_i_meta_textmultiline_{i+1}').set(False)
            for j, val in enumerate(value_options):
                graph_node.parm(f'cui_i_meta_textval_{i+1}_{j+1}').set(val)
            value_parm_name = f'cui_i_value_text_{i+1}'
            graph_node.parm(value_parm_name).set(value_options_default)
        #
        elif isinstance(input_type, str):
            # otherwise force input to be a wire
            force_input_to_be_wire = True
            input_metadata_unknown = True
        #
        else:
            raise NotImplementedError(f'unknown input type "{input_type}"')

        # remember original value_type in metadata (actual may be changed to input in future)
        if not input_metadata_unknown:
            graph_node.parm(f'cui_i_meta_orig_value_type_{i+1}').set(graph_node.evalParm(f'cui_i_value_type_{i+1}'))
        
        if force_input_to_be_wire:
            # everything else we treat as input type
            graph_node.parm(f'cui_i_value_type_{i+1}').set(f'input{next_free_input+1}')
            next_free_input = next_free_input + 1
            _extra_input_proc(graph_node, i, input_type)
            graph_node.parm(f'cui_i_node_input_{i+1}').set(input_name)
        elif value_parm_name:
            if extra_workflow_data \
                    and (extra_input_data := extra_workflow_data.inputs.get(input_name)) \
                    and (val := extra_input_data.val):
                graph_node.parm(value_parm_name).set(value_processor(val))

        if input_name in workflow_inputs:
            workflow_inputs.pop(input_name)
    
    # note, we continue from existing i value
    if workflow_inputs:
        graph_node.parm('cui_inputs').set(graph_node.parm('cui_inputs').eval() + len(workflow_inputs))
        for i, (input_name, extra_input_data) in enumerate(workflow_inputs.items(), start=i+1):
            input_type = extra_input_data.type
            graph_node.parm(f'cui_i_value_type_{i+1}').set(f'input{next_free_input+1}')
            next_free_input = next_free_input + 1
            _extra_input_proc(graph_node, i, input_type)
            graph_node.parm(f'cui_i_node_input_{i+1}').set(input_name)

    # now outputs
    if extra_workflow_data and extra_workflow_data.outputs is not None:
        # for now we consider outputs from extra data to fully override outputs from definition
        #  as it is unclear how to handle ordering of a mixed conflicting set of outputs
        #  and it does not seem to be a possible situation anyway
        output_data = [(v.type, k) for k, v in extra_workflow_data.outputs.items()]
    else:
        output_data = list(zip(node_type['output'], node_type['output_name']))

    graph_node.parm('cui_outputs').set(len(output_data))
    for i, (output_type, output_name) in enumerate(output_data):
        graph_node.parm(f'cui_o_node_title_{i+1}').set(node_title)
        graph_node.parm(f'cui_o_node_output_{i+1}').set(i)
        graph_node.parm(f'cui_o_meta_outputname_{i+1}').set(output_name)
        graph_node.parm(f'cui_o_meta_isimage_{i+1}').set(output_type in ('IMAGE', 'MASK'))
        graph_node.parm(f'cui_o_meta_outtype_{i+1}').set(output_type)

    graph_node.parm('cui_graph').set(json.dumps(
        {
            '0': {
                "inputs": {},  # no need to set any inputs here - they all will be overriden
                "class_type": node_type_name,
                "_meta": {
                    "title": node_title
                }
            }
        },
        indent=2
    ))

    subnet = graph_node.hdaModule().wrap_in_subnet(graph_node)
    # if interactive_kwargs:
    #     pane = interactive_kwargs['pane']
    #     #pane.setPwd(pane.pwd().parent())
    subnet.setName(hou.text.variableName(node_display_name), unique_name=True)
    subnet.setUserData('comfyui_wrapper_type', 'output' if node_type.get('output_node') else 'normal')
    subnet.setUserData('comfyui_wrapped_node_type', node_type_name)
    # add reqire event callback
    #  read reasoning in compound_graph_child_created_callback
    subnet.addEventCallback((hou.nodeEventType.InputRewired,), partial_node_rewire_callback)

    return subnet


def _extra_input_proc(graph_node, i, input_type):
    graph_node.parm(f'cui_i_meta_isimage_{i+1}').set(input_type in ('IMAGE', 'MASK'))
    # ffs, i don't qute understand, do we need mask transform or no?
    #  judjing from some tests - no, masks need to go raw
    if input_type == 'MASK':
        graph_node.parm(f'cui_i_meta_bakecc_{i+1}').set(False)


def get_node_definitions(host: str) -> dict:
    resp = requests.get(f'{host}/object_info')

    if resp.status_code != 200:
        raise RuntimeError(f'oh no, server said nono {resp.status_code}')

    return resp.json()


def get_single_node_definition(host: str, node_type: str) -> dict:
    resp = requests.get(f'{host}/object_info/{node_type}')

    if resp.status_code != 200:
        raise RuntimeError(f'oh no, server said nono {resp.status_code}')

    data = resp.json()
    if node_type not in data:  # this is how comfy returns data
        raise MissingNodeDefinitionError(node_type)
    
    return data[node_type]


def find_nearest_compound_graph_parent(node: hou.Node) -> hou.Node|None:
    while node and node.type().nameComponents()[2] != 'comfyui_compound_graph_submit':
        node = node.parent()
    return node


def update_comfy_nodes_definitions(host: str, long_op=None, *, 
        tool_name_prefix='xxx::Cop/comfyui_compound_graph_submit::1.2::',
        network_op_type='xxx::Cop/comfyui_compound_graph_submit::1.2::xxx::Cop/comfyui_partial_graph::1.2',
        network_output_op_type='xxx::Cop/comfyui_compound_graph_submit::1.2::xxx::Cop/comfyui_partial_graph_outputs::1.0',
        explicit_node_types: list[str]|None = None,
    ):
    if explicit_node_types is None:  # get all definitions
        node_definitions = get_node_definitions(host)
    else:
        node_definitions = {x: get_single_node_definition(host, x) for x in explicit_node_types}
    definitions_count = len(node_definitions)

    shelf_filepath = os.path.join(hou.text.expandString('$HOUDINI_USER_PREF_DIR'), 'toolbar', 'comfyui_crap.shelf')

    try:
        hou.shelves.beginChangeBlock()
        for def_i, (node_type_name, node_type) in enumerate(node_definitions.items()):
            if long_op:
                long_op.updateLongProgress(def_i / definitions_count, f"generating {node_type_name}")
            
            op_type = network_op_type
            if node_type.get('output_node', False) and len(node_type['output']) == 0:
                # output nodes that are just output nodes with nothing to pass to other nodes
                #  allow them only inside special subgraph
                op_type = network_output_op_type

            tool_code = (
                'from houdini_comfyui_connection.compound_graph_tools import create_single_tool\n'
                f'node_type_data = {repr(node_type)}\n'
                'pane = kwargs["pane"]\n'
                'create_single_tool(pane.pwd(), node_type_data, interactive_kwargs=kwargs)\n'
            )

            tool_name = tool_name_prefix + hou.text.alphaNumeric(node_type_name)

            if existing_tool := hou.shelves.tool(tool_name):
                existing_tool.destroy()

            category = node_type.get('category', '')
            hou.shelves.newTool(
                file_path=shelf_filepath,
                name=tool_name,
                label=node_type.get('display_name') or hou.text.alphaNumeric(node_type_name),
                script=tool_code,
                network_op_type=op_type,
                locations=('ComfyUI/Compound Graph Nodes' + (f'/{category}' if category else ''),),
            )
    finally:
        hou.shelves.endChangeBlock()


def is_subgraph_wrapper(node) -> bool:
    return node.type().name() == 'subnet' and not is_subnet_wrapper(node)


def is_subnet_wrapper(node) -> bool:
    return node.type().name() == 'subnet' and node.parm('__hidden_cui_subnet_mark__') is not None


def subnet_wrapper_wrapped_node(node) -> hou.Node:
    if not is_subnet_wrapper(node):
        raise ValueError(f'node {node} is not a comfyui wrapped subnet')
    candidates = [x for x in node.children() if x.type().nameComponents()[2] == 'comfyui_partial_graph']
    if len(candidates) != 1:
        raise RuntimeError(f'node {node} seem to be a comfyui subnet wrapper, but it\'s contents is unexpected')
    return candidates[0]


def subnet_input_to_wrapped_node_parm_i(node, input_id: int) -> int:
    if not is_subnet_wrapper(node):
        raise ValueError(f'node {node} is not a comfyui wrapped subnet')
    inner_node = subnet_wrapper_wrapped_node(node)
    input_node = [n for n in node.children() if n.type().name() == 'input'][0]
    inner_input_id = input_node.outputConnectors()[input_id][0].inputIndex()
    return partial_graph_input_to_parm_i(inner_node, inner_input_id)


def partial_graph_input_to_parm_i(node, input_id: int) -> int:
    for i in range(1, node.evalParm('cui_inputs') + 1):
        if (value_type := node.evalParm(f'cui_i_value_type_{i}')).startswith('input'):
            parm_i = int(value_type[5:])
            if input_id == parm_i - 1:  # inputN starts with 1, not 0, while input_id is 0-based
                return i
    raise RuntimeError('no param in {node} corresponds to input {input_id}')
#

def convert_parm_to_input(node: hou.Node, parm_name: str):
    """
    node is expected to be a subnet wrapper, created by create_single_tool node

    """
    inner_node = subnet_wrapper_wrapped_node(node)
    
    parm = node.parm(parm_name)
    if parm is None:
        raise ValueError(f'invalid parm name "{parm_name}" for node {node}')
    
    inner_input_i = parm.parmTemplate().tags().get('hou_comfyui_inner_input_i')
    if inner_input_i is None:
        raise ValueError(f'parm "{parm_name}" cannot be converted to input')
    inner_input_i = int(inner_input_i)

    if inner_node.evalParm(f'cui_i_value_type_{inner_input_i}').startswith('input'):
        # so it's already an input, not a parm
        return

    # find input number to assign, shifting inputs of lower parms down
    next_input = 1
    subnet_input_id_to_shift = -1  # note, this is 0-based index, unlike next_input
    for i in range(1, inner_node.evalParm('cui_inputs') + 1):
        if (value_type := inner_node.evalParm(f'cui_i_value_type_{i}')).startswith('input'):
            if i < inner_input_i:
                next_input = int(value_type[5:]) + 1
            elif i > inner_input_i:
                # shift input index
                inner_node.parm(f'cui_i_value_type_{i}').set(f'input{int(value_type[5:]) + 1}')
                if subnet_input_id_to_shift < 0:
                    subnet_input_id_to_shift = inner_node.inputConnectors()[int(value_type[5:])-1][0].outputIndex()
            else: # this case is impossible
                raise AssertionError('cannot be!')
    
    inner_node.parm(f'cui_i_value_type_{inner_input_i}').set(f'input{next_input}')

    # must rewrap in subnet
    #  note, all tags and callbacks originally set on subnet should be preserved here
    subnet = inner_node.hdaModule().wrap_in_subnet(inner_node)
    
    # inputs must be shifted
    if subnet_input_id_to_shift >= 0:
        for cons in reversed(tuple(subnet.inputConnectors())[subnet_input_id_to_shift:-1]):
            for con in cons:
                con.outputNode().setInput(con.inputIndex()+1, con.inputNode(), con.outputIndex())
                con.outputNode().setInput(con.inputIndex(), None)


def convert_enum_to_editable_enum(node: hou.Node, parm_name: str, *, editable=True) -> hou.Node:
    """
    node is expected to be a subnet wrapper, created by create_single_tool node

    """
    inner_node = subnet_wrapper_wrapped_node(node)
    
    parm = node.parm(parm_name)
    if parm is None:
        raise ValueError(f'invalid parm name "{parm_name}" for node {node}')
    
    inner_input_i = parm.parmTemplate().tags().get('hou_comfyui_inner_input_i')
    if inner_input_i is None:
        raise ValueError(f'parm "{parm_name}" cannot be converted to input')
    inner_input_i = int(inner_input_i)

    if parm := inner_node.parm(f'cui_i_meta_textvalseditable_{inner_input_i}'):  # compat
        if parm.eval() == editable:
            return
        parm.set(editable)

    return inner_node.hdaModule().wrap_in_subnet(inner_node)


# callbacks


def parm_menu_parm_to_input_callback_should_show(kwargs) -> bool:
    parms = kwargs['parms']
    if len(parms) != 1:
        return False
    parm = parms[0]
    node = parm.node()

    if not is_subnet_wrapper(node):
        return False
    
    return 'hou_comfyui_inner_input_i' in parm.parmTemplate().tags()


def parm_menu_parm_to_input_callback(kwargs):
    if not parm_menu_parm_to_input_callback_should_show(kwargs):
        return

    parm = kwargs['parms'][0]
    node = parm.node()

    convert_parm_to_input(node, parm.name())


def parm_enum_editable_set_callback_should_show(kwargs) -> bool:
    parms = kwargs['parms']
    if len(parms) != 1:
        return False
    parm = parms[0]
    node = parm.node()

    if not is_subnet_wrapper(node):
        return False
    
    return isinstance(parm.parmTemplate(), hou.StringParmTemplate) and parm.parmTemplate().menuType() == hou.menuType.Normal


def parm_enum_editable_set_callback(kwargs):
    parm = kwargs['parms'][0]
    node = parm.node()

    convert_enum_to_editable_enum(node, parm.name(), editable=True)


def compound_graph_child_created_callback(node, event_type, child_node, **kwargs):
    # logic is: we ONLY put callbacks on subnets with __hidden_cui_subnet_mark__
    #  as this happens on load/paste of nodes
    #  and newly created tools leave extra events, as wrapping happens in a tool script in 2 steps,
    #  so that script puts a callback on itself when it's ready
    #
    # NOTE: this event is called AFTER node is created, BUT BEFORE spare parms are applied to it!! 
    #       which is super strange, but this is how it is
    #       So we add events to all children. And event itself will delete itself from nodes where it's not supposed to be on
    if node.type().name() != 'subnet':
        return

    if event_type == hou.nodeEventType.ChildCreated:
        child_node.addEventCallback((hou.nodeEventType.InputRewired,), partial_node_rewire_callback)


def partial_node_rewire_callback(node, event_type, input_index, **kwargs):
    """
    this is an event to be set on every partial graph node inside compound graph node
    """
    if event_type != hou.nodeEventType.InputRewired:
        # we do not process other events
        return

    if not is_subnet_wrapper(node) and not is_subgraph_wrapper(node):
        # remove self from node
        try:
            node.removeEventCallback((hou.nodeEventType.InputRewired,), partial_node_rewire_callback)
        except hou.OperationFailed:
            # silently ignore if event was already deleted, maybe in another handler
            pass
        return

    con = node.inputConnectors()[input_index]
    if not con:  # not connected
        return
    
    if parm := node.parm(f'input_meta_typename_{input_index+1}'):
        input_type = parm.eval()
        if not input_type:
            # type not set, ignore
            return
    else:
        # no type metadata parm, just ignore
        return

    maybe_out = get_output_index_from_input(node, input_index)
    if isinstance(maybe_out, CompoundGraphSource):
        innode, out_index = (maybe_out.node, maybe_out.output)
        # now check input type
        # note, we always get partial graph node with this method, not subnet, so we access it's parms directly
        if parm := innode.parm(f'cui_o_meta_outtype_{out_index+1}'):
            out_type = parm.eval()
            if not out_type:
                # type not set, ignore
                return
        else:
            # no type metadata parm, just ignore
            return
        
        if out_type != input_type:
            # disconnec!
            node.setInput(input_index, None)
