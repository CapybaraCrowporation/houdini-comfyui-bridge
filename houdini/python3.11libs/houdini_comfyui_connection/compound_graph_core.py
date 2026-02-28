import os
import hou  # type:ignore
from enum import Enum
from dataclasses import dataclass, field
from pathlib import Path
import json
import re
import uuid
from houdini_comfyui_connection.graph_submission import BadInputSubstituteError, ResultNotFound, GraphValidationError, delete_input_image, delete_output_image, delete_prompt_history, download_result, submit_graph_and_get_result, FunctionalityNotAvailable, FailedToDeleteImage
from .compound_graph_core_graph_helpers import follow_input_till_deadend


class SubmitVariableNotFoundError(KeyError):
    """
    error represents error when substituting submission-time variables in string expressions
    """
    pass


class ImageType(Enum):
    RGBA = 0


@dataclass
class GraphPartData:
    graph: dict
    outputs: dict[int, tuple[str, int]]  # input_index -> (node KEY, node output index)
    inputs: dict[tuple[str, str], tuple[hou.Node, int]]  # (node KEY, input) -> source (node, graph part output index)
    params: dict[tuple[str, str], int|float|str]  # (node KEY, input) -> override value


@dataclass
class UploadInfo:
    filename: str
    frame: int|float|None
    was_uploaded: bool = field(default=False, init=False)


@dataclass
class ImageInfo(UploadInfo):
    bake_cc: bool


@dataclass
class GeometryUploadInfo(UploadInfo):
    pass


@dataclass
class GenericFileInfo(UploadInfo):
    source_path: Path


@dataclass(frozen=True)
class GraphProcessingContext:
    frame: float
    bake_cc: bool


@dataclass(frozen=True)
class GraphPorcessingInputKey:
    node: hou.Node
    output_index: int
    context: GraphProcessingContext


@dataclass
class CompoundGraphSource:
    node: hou.Node
    output: int

@dataclass
class NonGraphSource:
    node: hou.Node
    output: int
    image_type: ImageType


debug = lambda *args, **kwargs: ()
def _debug(msg, *args):
    from pprint import pprint
    print(f'[CUI_DEBUG] {msg}')
    if args:
        if len(args) == 1:
            args = args[0]
        pprint(args)

if os.environ.get('HCUI_DEBUG', '0') == '1':
    debug = _debug


def get_output_index_from_input(subnode: hou.Node, input_index: int) -> CompoundGraphSource|NonGraphSource|None:
    """
    returns either partial graph node and output index that corresponds to given node and input index,
    or image type connected,
    or None if nothing valuable is connected
    """
    input_connectors = subnode.inputConnectors()
    input_node = input_connectors[input_index][0].inputNode() if len(input_connectors) > input_index and input_connectors[input_index] else None
    if input_node is None:
        return None
    input_node_output_index = input_connectors[input_index][0].outputIndex()

    if input_node.isBypassed():  # bypass bypassed nodes
        return get_output_index_from_input(input_node, input_node_output_index)
        
    if not is_custom_partial_graph_processing_node(input_node) and input_node.type().nameComponents()[2] != 'comfyui_partial_graph':
        # check if we reached input node in a subnet/asset
        if input_node.type().name() == 'input':  # if we are in a subnet and reached input node
            return get_output_index_from_input(input_node.parent(), input_node_output_index)
        if input_node.type().name() in ('null',):  # bypassed some nodes, such as nulls
            return get_output_index_from_input(input_node, input_node_output_index)
        if input_node.type().name() == 'switch':  # switch is a special case
            return get_output_index_from_input(input_node, input_node.evalParm('input'))
        # first dive in and check child network
        if input_node.subnetOutputs() and input_node.childTypeCategory() == hou.nodeTypeCategories()['Cop']:
            # there may be more than single, but not sure how we should treat this case
            # TODO: figure out how to treat multiple output nodes
            return get_output_index_from_input(input_node.subnetOutputs()[0], input_node_output_index)
        # otherwise treat it as RGBA input
        return NonGraphSource(
            input_node,
            input_node_output_index,
            ImageType.RGBA,
        )

    return CompoundGraphSource(
        input_node,
        input_node_output_index,
    )


def title_to_key(graph: dict, title: str) -> str:
    for node_key, node_data in graph.items():
        if node_data.get('_meta', {}).get('title') == title:
            return node_key
    raise KeyError(f'node with title {title} not found')


def get_image_load_graph(cui_image_path: str) -> dict:
    return {
        "0": {
            "inputs": {
                "image": cui_image_path
            },
            "class_type": "LoadImage",
            "_meta": {
                "title": "Load Image"
            }
        }
    }


def get_mask_load_graph(cui_image_path: str) -> dict:
    return {
        "1": {
            "inputs": {
                "image": cui_image_path
            },
            "class_type": "LoadImage",
            "_meta": {
                "title": "Load Image"
            }
        },
        "0": {
            "inputs": {
                "image": [
                    "1", 0
                ],
                "channel": "red"
            },
            "class_type": "ImageToMask",
            "_meta": {
                "title": "Convert Image to Mask"
            }
        }
    }


def get_image_save_graph(cui_image_prefix: str, node_key: str = "0", sort_order: int = 0) -> dict:
    return {
        node_key: {
            "inputs": {
                "filename_prefix": cui_image_prefix
            },
            "class_type": "SaveImage",
            "_meta": {
                "_sort_order": sort_order,
                "title": "Save Image",
            }
        }
    }

def get_mask_save_graph(cui_image_prefix: str, node_key: str = "0", sort_order: int = 0) -> dict:
    return {
        node_key: {
            'class_type': 'MaskToImage',
            '_meta': {
                'title': 'masktoimage',
            }
        },
        (node_key + "0"): {
            "inputs": {
                'images': [node_key, 0],
                "filename_prefix": cui_image_prefix
            },
            "class_type": "SaveImage",
            "_meta": {
                "_sort_order": sort_order,
                "title": "Save Image",
            }
        }
    }

def get_string_save_graph(node_key: str = "0", sort_order: int = 0) -> dict:
    return {
        node_key: {
            "inputs": {
            },
            "class_type": "HouCuiStringAsImage",
            "_meta": {
                "_sort_order": sort_order,
                "title": "Preview Mesh As Image",
            }
        }
    }

def get_hy3d_save_graph(cui_image_prefix: str, input_node_key: str = "1", node_key: str = "0", sort_order: int = 0) -> dict:
    return {
        input_node_key: {
            "inputs": {
                "filename_prefix": cui_image_prefix,
                "file_format": "glb",
                "save_file": False,
            },
            "class_type": "Hy3DExportMesh",
            "_meta": {
                "title": "Save Mesh"
            }
        },
        node_key: {
            "inputs": {
                "image_path": [
                    input_node_key, 0
                ]
            },
            "class_type": "HouCuiStringAsImage",
            "_meta": {
                "_sort_order": sort_order,
                "title": "Preview Mesh As Image",
            }
        }
    }


def get_mesh_save_graph(cui_image_prefix: str, node_key: str = "0", sort_order: int = 0) -> dict:
    return {
        node_key: {
            "inputs": {
                "filename_prefix": cui_image_prefix,
            },
            "class_type": "SaveGLB",
            "_meta": {
                "_sort_order": sort_order,
                "title": "where am I who are you"
            }
        }
    }


def get_graph_input_num_from_node_input(node: hou.Node, node_input: int) -> int|None:
    for i in range(1, 1 + node.evalParm('cui_inputs')):
        input_type = node.evalParm(f'cui_i_value_type_{i}')
        if not input_type.startswith('input'):
            continue
        if int(input_type[5:]) - 1 == node_input:
            return i
    return None


def is_custom_partial_graph_processing_node(subnode):
    return hasattr(subnode.hdaModule(), 'comfyui_partial_graph_is_custom_node') and subnode.hdaModule().comfyui_partial_graph_is_custom_node


def process_graph_node(
    subnode,
    node_to_graph: dict[hou.Node, GraphPartData],
    nodes_to_upload: dict[GraphPorcessingInputKey, tuple[hou.Node, UploadInfo]],
    context_vars: dict[str, str|float|int],
    *,
    long_op: hou.InterruptableOperation|None = None,
):
    if subnode is None:  # convenient case handling
        return None
    if subnode in node_to_graph:
        return

    debug('process_graph_node', subnode)

    if is_custom_partial_graph_processing_node(subnode):
        # custom nodes may reimplement graph processing
        subnode.hdaModule().process_graph_node(subnode, node_to_graph, nodes_to_upload, context_vars, long_op=long_op)
        return
    elif subnode.type().nameComponents()[2] != 'comfyui_partial_graph':
        # treat other nodes as bypassed ones
        return process_graph_node(subnode.inputs()[0] if len(subnode.inputs()) else None, node_to_graph, nodes_to_upload, context_vars, long_op=long_op)
        
    graph = json.loads(subnode.evalParm('cui_graph'))
    # process all input nodes
    input_nodes = []
    for i, input_node_maybe in enumerate(subnode.inputConnectors()):
        input_nodes.append(None)  # extend list straight away
        if not input_node_maybe:  # if nothing is plugged - skip
            continue
        #input_node = input_node_maybe[0].inputNode()
        #process_graph_node(input_node, node_to_graph, nodes_to_upload)
        # we don't use on houdini's notion of inputs, as our inputs can be hidden inside assets, and connected through nulls
        in_node_source_data = get_output_index_from_input(subnode, i)
        if in_node_source_data is None:  # not connected to anything meaningful
            continue
        elif isinstance(in_node_source_data, NonGraphSource):  # means there is no comfyui_partial_graph node, so we treat it as color input
            if in_node_source_data.image_type != ImageType.RGBA:
                raise NotImplementedError('only single type is supported for now')
            # treat it as color input
            input_parm_i_corresponding_to_this_node_input = get_graph_input_num_from_node_input(subnode, i)
            if input_parm_i_corresponding_to_this_node_input is None:
                # connected input is not used in the graph
                continue
            needs_cc_parm = subnode.parm(f'cui_i_meta_bakecc_{input_parm_i_corresponding_to_this_node_input}')
            needs_cc = bool(needs_cc_parm.eval()) if needs_cc_parm else True  # default True - compatible with older asset version
            input_type_parm = subnode.parm(f'cui_i_meta_intype_{input_parm_i_corresponding_to_this_node_input}')
            input_type = input_type_parm.evalAsString() if input_type_parm else 'IMAGE'  # default IMAGE for compat

            upload_node = subnode.node(f'input_upload{i+1}')
            # first check if we already are uploading required input
            source_context = GraphPorcessingInputKey(in_node_source_data.node, in_node_source_data.output, GraphProcessingContext(hou.frame(), needs_cc))
            if source_context in nodes_to_upload:
                image_name = nodes_to_upload[source_context][1].filename
            else:
                image_name = f"houdini_comfyui_connection/{uuid.uuid4()}.png"
                nodes_to_upload[source_context] = (upload_node, ImageInfo(image_name, source_context.context.frame, needs_cc))
            # need to create loader for that new image
            if input_type in ('IMAGE', ''):  # treat empty as image for compat for now
                img_load_graph = get_image_load_graph(image_name)
            elif input_type == 'MASK':
                img_load_graph = get_mask_load_graph(image_name)
            else:
                raise NotImplementedError(f'don\'t know how to upload input type "{input_type}"')

            node_to_graph[upload_node] = GraphPartData(
                img_load_graph,
                {
                    0: ("0", 0)
                },
                {},
                {},
            )
            input_nodes[-1] = (upload_node, 0)
            continue
        assert isinstance(in_node_source_data, CompoundGraphSource)
        process_graph_node(in_node_source_data.node, node_to_graph, nodes_to_upload, context_vars, long_op=long_op)
        input_nodes[-1] = (in_node_source_data.node, in_node_source_data.output)
        
    inputs = {}
    params = {}
    for i in range(1, 1+subnode.evalParm('cui_inputs')):
        inp_node_title = subnode.evalParm(f'cui_i_node_title_{i}')
        inp_node_input = subnode.evalParm(f'cui_i_node_input_{i}')
        inp_node_vtype = subnode.evalParm(f'cui_i_value_type_{i}')
        inp_node_orig_vtype = subnode.evalParm(f'cui_i_meta_orig_value_type_{i}')
        if not inp_node_vtype.startswith('input'):
            if inp_node_vtype == 'int':
                value = subnode.evalParm(f'cui_i_value_int_{i}')
            elif inp_node_vtype == 'textint':
                value = int(subnode.evalParm(f'cui_i_value_textint_{i}'))
                if value > 2<<63-1 or value < -2<<63:
                    raise ValueError('comfy backend cannot process such big/small numbers! ({value})')
            elif inp_node_vtype == 'float':
                value = subnode.evalParm(f'cui_i_value_float_{i}')
            elif inp_node_vtype == 'text':
                value = subnode.evalParm(f'cui_i_value_text_{i}')
                contype = subnode.evalParm(f'cui_i_meta_convertedtype_{i}')
                if contype == 'int':
                    value = int(value)
                elif contype == 'float':
                    value = float(value)
                elif contype == 'text':
                    pass
                elif contype == 'bool':
                    value = bool(value)
                else:
                    raise AssertionError('unreachable')
            elif inp_node_vtype == 'bool':
                value = bool(subnode.evalParm(f'cui_i_value_bool_{i}'))
            else:
                raise RuntimeError(f'unknown value type "{inp_node_vtype}"')
                
            params[(title_to_key(graph, inp_node_title), inp_node_input)] = value
            continue
        
        input_idx = int(inp_node_vtype[5:]) - 1
        if input_idx >= len(input_nodes) or input_nodes[input_idx] is None:
            # we know that a node is not connected to another comfyui node, 
            #  but it may sitll have a houdini-level node connection that might lead to a value substitution
            if not inp_node_orig_vtype or inp_node_orig_vtype.startswith('input'):  # not set or is an input
                continue

            maybe_connection_data = follow_input_till_deadend(subnode, input_idx)
            if maybe_connection_data is None:
                # nothing important connected? who cares!
                continue
            deadend_node, deadend_node_input = maybe_connection_data
            maybe_value = _try_get_input_value(deadend_node, inp_node_orig_vtype, deadend_node_input)
            if maybe_value is None:
                continue
            params[(title_to_key(graph, inp_node_title), inp_node_input)] = maybe_value
            continue

        inputs[(title_to_key(graph, inp_node_title), inp_node_input)] = input_nodes[input_idx]
        
    node_to_graph[subnode] = GraphPartData(
        graph,
        {
            i: (title_to_key(graph, subnode.evalParm(f'cui_o_node_title_{i+1}')), subnode.evalParm(f'cui_o_node_output_{i+1}'))
            for i in range(subnode.evalParm('cui_outputs'))
        },
        inputs,
        params,
    )


def _try_get_input_value(node: hou.Node, value_type: str, input_number: int) -> int|float|str|bool|None:
    parm = node.parm(f'input_parm_{input_number+1}')
    if parm is None:
        return None
    if value_type == 'textint':
        value = int(parm.eval())
        if value > 2<<63-1 or value < -2<<63:
            raise ValueError('comfy backend cannot process such big/small numbers! ({value})')
    elif value_type == 'bool':
        return bool(parm.evalAsInt())
    return parm.eval()


def combine_graph_parts(node_to_graph: dict[hou.Node, GraphPartData]) -> tuple[dict, dict[str, dict[str, int|float|str|list]]]:
    offset = 0
    
    new_graph = {}
    for part_data in node_to_graph.values():

        old_to_new_key_mapping: dict[str, str] = {}
        for node_key in part_data.graph:
            # node_key is most likely a string representing int, but just in case we won't rely on that
            new_key = f'{offset}_{node_key}'
            old_to_new_key_mapping[node_key] = new_key

        for node_key, node_data in part_data.graph.items():
            for input_name, input_val in node_data.get('inputs', {}).items():
                if isinstance(input_val, list):  # this means it is a connection (as far as i understand)
                    input_val[0] = old_to_new_key_mapping[input_val[0]]
            new_graph[old_to_new_key_mapping[node_key]] = node_data
        
        part_data.graph = {old_to_new_key_mapping[k]: v for k, v in part_data.graph.items()}
        part_data.outputs = {k: (old_to_new_key_mapping[v[0]], v[1]) for k, v in part_data.outputs.items()}
        part_data.inputs = {(old_to_new_key_mapping[k[0]], k[1]): v for k, v in part_data.inputs.items()}
        part_data.params = {(old_to_new_key_mapping[k[0]], k[1]): v for k, v in part_data.params.items()}

        offset += 1

    param_overrides: dict[str, dict[str, int|float|str|list]] = {}
    for part_data in node_to_graph.values():
        for (input_node, input_name), val in part_data.params.items():
            param_overrides.setdefault(input_node, {})[input_name] = val
        for (input_node, input_name), (hou_node, out_idx) in part_data.inputs.items():
            param_overrides.setdefault(input_node, {})[input_name] = list(node_to_graph[hou_node].outputs[out_idx])
    
    return new_graph, param_overrides


def _expand_val(text: str, context_vars: dict[str, str|float|int], upload_nodes: dict[GraphPorcessingInputKey, tuple[hou.Node, UploadInfo]]) -> str:
    magic_string = ':#:cuiinputfrom:#:'
    if not text.startswith(magic_string):
        try:
            text = re.sub(r'@{{(.*?)}}', lambda m: str(context_vars[m.group(1)]), text)
        except KeyError as e:
            raise SubmitVariableNotFoundError(e.args[0])
        return text

    ref_path, in_idx = text[len(magic_string):].rsplit(':', 1)
    in_idx = int(in_idx)
    in_node_data = get_output_index_from_input(hou.node(ref_path), in_idx)
    if in_node_data is None:
        raise ValueError('expression referenced node not found!')
    if not isinstance(in_node_data, NonGraphSource):
        raise ValueError('expression referenced node is not a source!')
    
    in_node = in_node_data.node
    out_idx = in_node_data.output
    for key, (_, info) in upload_nodes.items():
        if (key.node != in_node
            or key.output_index != out_idx
            or key.context.frame != hou.frame()
        ):
            continue
        return info.filename
    raise ValueError('expression referenced node not found!')


def replace_params_in_graph_by_key(
    graph_data: dict,
    inputs_to_replace: dict,
    upload_nodes: dict[GraphPorcessingInputKey, tuple[hou.Node, UploadInfo]],
    context_vars: dict[str, str|float|int],
):
    for node_key, node_data in inputs_to_replace.items():
        for input_name, value in node_data.items():
            # special cases of values
            if isinstance(value, str):
                value = _expand_val(value, context_vars, upload_nodes)
            graph_data[node_key].setdefault('inputs', {})[input_name] = value


def construct_full_graph(
    output_node: hou.Node|None,
    *,
    context_vars: dict[str, str|float|int]|None = None,
    upload_nodes: dict[GraphPorcessingInputKey, tuple[hou.Node, UploadInfo]]|None = None,
    explicit_cui_roots: list[hou.Node]|None = None,
    long_op: hou.InterruptableOperation|None = None,
) -> tuple[dict, dict[GraphPorcessingInputKey, tuple[hou.Node, UploadInfo]], list[str]]:
    """
    construct final graph from inner pieces with all inputs already replaced
    """
    if output_node is None and explicit_cui_roots is None:
        raise ValueError('either output_node or explicit_cui_roots must be provided')
    
    node_to_graph = {}
    if upload_nodes is None:
        upload_nodes = {}
    if context_vars is None:
        context_vars = {}
    saving_graph = {}
    saving_inputs = {}
    if output_node:
        for i, input_node_maybe in enumerate(output_node.inputConnectors()):
            if not input_node_maybe:
                continue
            in_source = get_output_index_from_input(output_node, i)
            if in_source is None or isinstance(in_source, NonGraphSource):
                # means there is no graph parts connected
                continue
            process_graph_node(in_source.node, node_to_graph, upload_nodes, context_vars, long_op=long_op)

            output_type_name = None
            if typeparm := in_source.node.parm(f'cui_o_meta_outtype_{in_source.output + 1}'):
                output_type_name = typeparm.eval()
            
            if output_type_name == 'TRIMESH':
                saving_graph.update(get_hy3d_save_graph(f'houdini-connection-todo-change-this-{i}', f'input1_{i}', f'{i}', i))
                saving_inputs[(f'input1_{i}', 'trimesh')] = (in_source.node, in_source.output)
            elif output_type_name == 'MESH':
                saving_graph.update(get_mesh_save_graph(f'houdini-connection-todo-change-this-{i}', f'{i}', i))
                saving_inputs[(f'{i}', 'mesh')] = (in_source.node, in_source.output)
            elif output_type_name == 'MASK':
                saving_graph.update(get_mask_save_graph(f'houdini-connection-todo-change-this-{i}', f'{i}', i))
                saving_inputs[(f'{i}', 'mask')] = (in_source.node, in_source.output)
            elif output_type_name == 'STRING':
                saving_graph.update(get_string_save_graph(f'{i}', i))
                saving_inputs[(f'{i}', 'image_path')] = (in_source.node, in_source.output)
            elif output_type_name in ('IMAGE', ''):  # for backwards compat treat empty type as image too
                saving_graph.update(get_image_save_graph(f'houdini-connection-todo-change-this-{i}', f'{i}', i))
                saving_inputs[(f'{i}', 'images')] = (in_source.node, in_source.output)
            else:
                raise TypeError(f'saving of input type "{output_type_name}" is not implemented')

        
        node_to_graph[output_node] = GraphPartData(
            saving_graph,
            {},
            saving_inputs,
            {}
        )
    else:
        assert explicit_cui_roots is not None  # we check in func beginning
        for explicit_root in explicit_cui_roots:
            assert explicit_root.type().nameComponents()[2] == 'comfyui_partial_graph', 'explicit roots MUST be comfyui_partial_graph'
            process_graph_node(explicit_root, node_to_graph, upload_nodes, context_vars, long_op=long_op)
        for i, explicit_root in enumerate(explicit_cui_roots):
            # TODO: CBB, construct graph_keys only from output nodes
            graph_keys = list(node_to_graph[explicit_root].graph.keys())
            if len(graph_keys) != 1:
                raise RuntimeError('graph root must consist of a single output node')
            node_to_graph[explicit_root].graph[graph_keys[0]]['_meta']['_sort_order'] = i

    new_graph, param_overrides = combine_graph_parts(node_to_graph)
    replace_params_in_graph_by_key(new_graph, param_overrides, upload_nodes, context_vars)

    outputs = []
    if output_node:
        output_nodes_from_sort_order = {x[1]['_meta']['_sort_order']: x[0] for x in node_to_graph[output_node].graph.items() if '_sort_order' in x[1].get('_meta', {})}
        for i in range(len(output_node.inputConnectors())):
            if i in output_nodes_from_sort_order:
                outputs.append(output_nodes_from_sort_order[i])
            else:
                outputs.append(None)
    else:
        assert explicit_cui_roots is not None  # we check in func beginning
        output_nodes_from_sort_order = {
            x[1]['_meta']['_sort_order']: x[0]
            for root in explicit_cui_roots for x in node_to_graph[root].graph.items()
            if '_sort_order' in x[1].get('_meta', {})
        }
        # at this point we asserted that there is a SINGLE key for each root, but that may change with the TODO above
        outputs = [list(node_to_graph[root].graph.keys())[0] for root in explicit_cui_roots]

    return new_graph, upload_nodes, outputs


def submit_compound_graph(
    host: str,
    output_node: hou.Node,
    long_op: hou.InterruptableOperation|None = None,
    *,
    context_vars: dict[str, str|float|int]|None = None,
    reuse_upload_nodes: dict[GraphPorcessingInputKey, tuple[hou.Node, UploadInfo]]|None = None,
    explicit_roots: list[hou.Node]|None = None,
    api_key: str|None = None,
) -> tuple[dict, str, dict[GraphPorcessingInputKey, tuple[hou.Node, UploadInfo]], list[str]]:

    graph, upload_nodes, outputs = construct_full_graph(output_node, upload_nodes=reuse_upload_nodes, explicit_cui_roots=explicit_roots, context_vars=context_vars, long_op=long_op)
    debug('full graph:', graph)

    for upload_node, image_info in (x for x in upload_nodes.values()):
        if image_info.was_uploaded:
            continue
        image_info.was_uploaded = True
        if long_op:
            long_op.updateLongProgress(-1, "Cooking and Uploading inputs...")
        subdir, filename = image_info.filename.rsplit('/', 1) if '/' in image_info.filename else ('', image_info.filename)
        kwargs = {}
        if isinstance(image_info, ImageInfo):
            kwargs = {
                'bake_cc': image_info.bake_cc,
                'frame': image_info.frame,
            }
        elif isinstance(image_info, GeometryUploadInfo):
            kwargs = {}
        elif isinstance(image_info, GenericFileInfo):
            # NOTE: we rely on image uploader here
            kwargs = {
                'override_source_filepath': image_info.source_path,
            }
        else:
            raise NotImplementedError(f'upload for type "{image_info}" is not implemented')

        upload_node.hdaModule().upload_input_to(
            upload_node,
            host,
            subdir,
            filename,
            **kwargs,
        )

    # TODO: provide output_ids!
    res, prompt_id = submit_graph_and_get_result(host, graph, long_op=long_op, api_key=api_key)
    debug(f'result {prompt_id}:', res)
    return res, prompt_id, upload_nodes, outputs


def compute_compound_graph_node(node, long_op=None, override_output_node=None, override_result_loader_nodes=None):
    host = node.evalParm('base_url').rstrip('/ ')
    
    do_cleanup = node.parm('cleanup_server_images').eval()

    if override_output_node:
        output_node = override_output_node
    else:
        output_node = node.node('graph').node('outputs')
        if output_node is None:
            raise RuntimeError('not node "outputs" found in the graph')
    api_key = node.evalParm('comfyui_api_key')
    res, prompt_id, upload_nodes, outputs = submit_compound_graph(host, output_node, long_op=long_op, api_key=api_key or None)
    
    # get result
    for i in range(len(override_result_loader_nodes) if override_result_loader_nodes else 2):
        if long_op:
            long_op.updateLongProgress(-1, "Downloading result...")
        outnode = override_result_loader_nodes[i] if override_result_loader_nodes else node.node(f'result{i+1}')
        outpath = Path(outnode.evalParm('filename'))
        key = outputs[i]
        if key is None:  # not connected
            continue
        
        if key not in res:
            raise ResultNotFound(key, res)
        
        if node.parm('image_batch_index') is None:
            # 1.2 compatibility
            download_result(host, res[key]['images'][0]['filename'], res[key]['images'][0]['subfolder'], outpath)
        else:
            for i, data in enumerate(res[key].get('images', res[key].get('3d', ()))):
                # we rely on batch id being last \.\d+\. in the filename
                base_name, _, _ = outpath.name.rsplit('.', 2)
                incoming_ext = data['filename'].rsplit('.', 1)[1] if '.' in data['filename'] else ''
                local_path = outpath.with_name('.'.join((base_name, str(i), incoming_ext)))
                debug(f'removing {local_path}')
                local_path.unlink(missing_ok=True)  # remove existing before downloading new file
                debug(f'downloading image {i} of batch: {local_path}')
                download_result(host, data['filename'], data['subfolder'], local_path)
        outnode.parm('reload').pressButton()

    if do_cleanup:
        image_infos = [x[1] for x in upload_nodes.values()]
        for i, upload_data in enumerate(image_infos):
            if long_op:
                long_op.updateLongProgress(-1, "Cleaning up temporary images")
                long_op.updateProgress(i / len(image_infos))

            try:
                if '/' in upload_data.filename:  # not os.path.split cuz it's not os-specific
                    upload_subdir, upload_filename = upload_data.filename.rsplit('/', 1)
                else:
                    upload_subdir = ''
                    upload_filename = upload_data.filename
                delete_input_image(
                    host,
                    upload_filename,
                    upload_subdir,
                )
            except FailedToDeleteImage as e:
                # we don't fail on cleanup error
                print(f'[WARNING] server failed to remove input: {e}')
            except FunctionalityNotAvailable:
                print('[WARNING] failed to remove temp input image from comfyui: server does not support deletion')

        if long_op:
            long_op.updateLongProgress(-1, "Cleaning up prompt history")
        delete_prompt_history(host, prompt_id)
        #  comfy backend cache does not check image existance, and there is no clear stable way of cleaning cache,
        #  so we have to leave output images as is for now

