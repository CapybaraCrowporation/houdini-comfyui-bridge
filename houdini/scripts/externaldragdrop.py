import hou
import json
import os
import traceback
import PIL
from houdini_comfyui_connection.workflow_deserialization_tools import create_network_from_prompt, create_network_from_workflow, MissingNodeDefinitionError


class UndoPerformer:
    def __init__(self):
        self.do_undo_on_exit = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.do_undo_on_exit:
            hou.undos.performUndo()


def dropAccept(file_list):
    # check pane and context
    pane = hou.ui.paneTabUnderCursor()
    if not isinstance(pane, hou.NetworkEditor):
        return False
    parent_node = pane.pwd()
    if (gnode := parent_node.node('..')) is None or gnode.type().nameComponents()[2] != 'comfyui_compound_graph_submit':
        return False
    host = gnode.evalParm('base_url').rstrip('/ ')

    # we only accept single png file
    if len(file_list) != 1 or not file_list:
        return False

    file_ext = os.path.splitext(file_list[0])[1]

    if file_ext == '.png':
        try:
            img = PIL.Image.open(file_list[0])
        except:
            print(f'failed to open image {file_list[0]}')
            return True  # we don't want houdini to open that image as hip file, do we

        try:
            if not isinstance(img.text, dict) or 'prompt' not in img.text:
                print('this image does not contain prompt')
                return True
            prompt = json.loads(img.text['prompt'])
            workflow = json.loads(img.text['workflow']) if 'workflow' in img.text else None
        except json.JSONDecodeError:
            hou.ui.displayMessage('Image has corrupted or wrong metadata', title='Failed to build graph from image', severity=hou.severityType.Error, details=traceback.format_exc())
            return True
        finally:
            img.close()
    elif file_ext == '.json':
        with open(file_list[0], 'r') as f:
            # TODO: distinguish between workflow and api workflow formats better, not just by 'nodes' key
            workflow = None
            prompt = None
            something = json.load(f)
            if 'nodes' in something and isinstance(something['nodes'], list):
                workflow = something
            else:
                prompt = something
    else:
        return False

    with UndoPerformer() as udp, hou.undos.group('create comfyui compound graph from drag&drop'):
        # we prefer prompt if present as it's better supported for now
        if prompt:
            try:
                nodes = create_network_from_prompt(host, parent_node, prompt)
            except MissingNodeDefinitionError as e:
                pack_name = None
                if workflow and e.node_id is not None:
                    for node_data in workflow.get('nodes', []):
                        print(node_data)
                        if str(node_data['id']) == e.node_id:
                            pack_name = node_data.get('properties', {}).get('cnr_id', node_data.get('properties', {}).get('aux_id'))
                            break
                hou.ui.displayMessage(f'Missing node type definition for "{e.node_type}"' + (f' from node pack "{pack_name}"' if pack_name else ''))                
                udp.do_undo_on_exit = True
                return True
            except OSError:
                hou.ui.displayMessage('Unable to connect to comfyui server. Check host url.', title='Failed to build graph from image', severity=hou.severityType.Error, details=traceback.format_exc())
                udp.do_undo_on_exit = True
                return True
            except Exception:
                hou.ui.displayMessage('Unexpected error occured! see details', title='Failed to build graph from image', severity=hou.severityType.Error, details=traceback.format_exc())
                udp.do_undo_on_exit = True
                return True
            # now we can try to layout nodes according to workflow data
            if workflow:
                for node in workflow.get('nodes', []):
                    node_id = str(node.get('id', ''))
                    if node_id in nodes and (node_pos := node.get('pos')):
                        nodes[node_id].setPosition(hou.Vector2(node_pos) * 0.01)
            else:
                parent_node.layoutChildren(list(nodes.values()))
        else:
            # so no prompt provided, just the workflow
            try:
                nodes = create_network_from_workflow(host, parent_node, workflow)
            except MissingNodeDefinitionError as e:
                hou.ui.displayMessage(f'Missing node type definition for "{e.node_type}" from node pack "{e.pack_name}"')
                udp.do_undo_on_exit = True
                return True
            except OSError:
                hou.ui.displayMessage('Unable to connect to comfyui server. Check host url.', title='Failed to build graph from image', severity=hou.severityType.Error, details=traceback.format_exc())
                udp.do_undo_on_exit = True
                return True
            except Exception:
                hou.ui.displayMessage('Unexpected error occured! see details', title='Failed to build graph from image', severity=hou.severityType.Error, details=traceback.format_exc())
                udp.do_undo_on_exit = True
                return True

        # center around mouse point
        mouse_pos = pane.cursorPosition()
        centroid = hou.Vector2()
        for node in nodes.values():
            centroid += node.position()
        if len(nodes) > 0:
            centroid = centroid / len(nodes)
        for node in nodes.values():
            node.setPosition(node.position() - centroid + mouse_pos)

        parent_node.setSelected(False, clear_all_selected=True)
        for node in nodes.values():
            node.setSelected(True)

        output_nodes = {n for n in nodes.values() if n.userData('comfyui_wrapper_type') == 'output'}
        # fixed number of types we consider "inputs" 
        input_nodes = {n for n in nodes.values() if n.userData('comfyui_wrapped_node_type') in ('LoadImage', 'LoadImageMask')}
        save_image_nodes = [n for n in output_nodes if n.userData('comfyui_wrapped_node_type') == 'SaveImage']
        preview_image_nodes = [n for n in output_nodes if n.userData('comfyui_wrapped_node_type') == 'PreviewImage']

        nodes_to_pay_user_attention_to = set(input_nodes)
        nodes_to_pay_user_attention_to.update(output_nodes)

        subnet_output_nodes = [x for x in parent_node.subnetOutputs() if x.type().name() == 'output']
        if len(save_image_nodes) == 1 and (len(subnet_output_nodes) == 0 or len(subnet_output_nodes) == 1 and subnet_output_nodes[0].inputConnectors()[0] == ()):
            # find subnet output
            # we check type here cuz houdini bugs and returns inputs when no outputs are present
            if len(subnet_output_nodes) == 1:
                subnet_output_node = subnet_output_nodes[0]
            else:
                subnet_output_node = parent_node.createNode('output')

            # connec
            for conn in save_image_nodes[0].inputConnectors()[0]:
                subnet_output_node.setInput(0, conn.inputNode(), conn.inputIndex())
                subnet_output_node.moveToGoodPosition(relative_to_inputs=True, move_inputs=False, move_outputs=False, move_unconnected=False)
            nodes_to_pay_user_attention_to.remove(save_image_nodes[0])
            save_image_nodes[0].destroy()
        else:
            # treat them as preview nodes
            preview_image_nodes.extend(save_image_nodes)

        for preview_node in preview_image_nodes:
            our_preview_node = parent_node.createNode('comfyui_graph_preview')
            our_preview_node.setPosition(preview_node.position())
            for conn in preview_node.inputConnectors()[0]:
                our_preview_node.setInput(0, conn.inputNode(), conn.inputIndex())
            if preview_node in nodes_to_pay_user_attention_to:
                nodes_to_pay_user_attention_to.remove(preview_node)
            preview_node.destroy()
            our_preview_node.setColor(hou.Color((0.85, 0.5, 0.1)))
            our_preview_node.setSelected(True)

        for node in nodes_to_pay_user_attention_to:
            node.setColor(hou.Color((1, 0, 0)))

    if nodes_to_pay_user_attention_to:
            hou.ui.displayMessage(
                'Pay attention to the following nodes, they may need adjustments (marked with color):\n\n' + '\n'.join(x.name() for x in nodes_to_pay_user_attention_to),
                title='User Attention Needed!',
                severity=hou.severityType.Warning
            )

    return True
