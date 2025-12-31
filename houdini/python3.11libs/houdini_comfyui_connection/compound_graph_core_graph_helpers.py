import hou  # type: ignore
from typing import Callable


def follow_input_till_deadend(subnode: hou.Node, input_index: int) -> tuple[hou.Node, int]|None:
    """
    given a subnode and it's input_index - follows the input until reaches a node without inputs, 
    return that node and the input index that corresponds to output index connection went in.
    
    if a wire goes into "inputs" of a subnet and that subnet's corresponding input is not connected
    then subnet node will be returned with the input number equal to it's "inputs" output where wire came in
    
    if a wire goes into a subnet, and corresponding input in the subnet's "outputs" is not connected
    then that "outputs" node will be returned with the input number equal to the subnet's output where wire came in

    return None when nothing is connected to input_index of subnode at all
    """
    input_connectors = subnode.inputConnectors()
    input_node = input_connectors[input_index][0].inputNode() if len(input_connectors) > input_index and input_connectors[input_index] else None
    if input_node is None:
        return None
    return follow_input_till_deadend_condition(subnode, input_index)


def follow_input_till_deadend_condition(subnode: hou.Node, input_index: int, stop_condition: Callable[[hou.Node], bool] | None = None) -> tuple[hou.Node, int]:
    """
    helper for follow_input_till_deadend, but instead of None returns current subnode, input_index
    """
    # TODO: there is some similar logic to get_output_index_from_input, maybe can refactor, reuse
    if stop_condition and stop_condition(subnode):
        return subnode, input_index
    input_connectors = subnode.inputConnectors()
    input_node = input_connectors[input_index][0].inputNode() if len(input_connectors) > input_index and input_connectors[input_index] else None
    if input_node is None:
        return subnode, input_index
    input_node_output_index = input_connectors[input_index][0].outputIndex()

    if input_node.type().name() == 'input':  # if we are in a subnet and reached input node
        return follow_input_till_deadend_condition(input_node.parent(), input_node_output_index, stop_condition)
    if input_node.subnetOutputs() and input_node.childTypeCategory() == hou.nodeTypeCategories()['Cop']:
        # TODO: figure out how to treat multiple output nodes
        subnet_outputs_node = input_node.subnetOutputs()[0]
        return follow_input_till_deadend_condition(subnet_outputs_node, input_node_output_index, stop_condition)
    if input_node.type().name() == 'switch':  # switch is a special case
        return follow_input_till_deadend_condition(input_node, input_node.evalParm('input'), stop_condition)

    # else it's just a normal node, here we treat all as passthrough
    return follow_input_till_deadend_condition(input_node, input_node_output_index, stop_condition)


def follow_output_till_deadend_condition(subnode: hou.Node, output_index: int, stop_condition: Callable[[hou.Node], bool] | None = None) -> tuple[hou.Node, int]:
    """
    helper
    """
    # TODO: there is some similar logic to get_output_index_from_input, maybe can refactor, reuse
    if stop_condition and stop_condition(subnode):
        return subnode, output_index
    output_connectors = subnode.outputConnectors()
    # TODO: we only follor first connector now!
    output_node = output_connectors[output_index][0].outputNode() if len(output_connectors) > output_index and output_connectors[output_index] else None
    if output_node is None:
        return subnode, output_index
    output_node_input_index = output_connectors[output_index][0].inputIndex()

    if output_node.type().name() == 'output':  # if we are in a subnet and reached output node
        return follow_output_till_deadend_condition(output_node.parent(), output_node_input_index, stop_condition)
    if output_node.type().name() == 'subnet' and output_node.childTypeCategory() == hou.nodeTypeCategories()['Cop']:
        # TODO: figure out how to treat multiple input nodes
        candidates = [n for n in output_node.children() if n.type().name() == 'input']
        if candidates:
            subnet_inputs_node = candidates[0]
            return follow_output_till_deadend_condition(subnet_inputs_node, output_node_input_index, stop_condition)
    if output_node.type().name() == 'switch':  # switch is a special case
        return follow_output_till_deadend_condition(output_node, 0, stop_condition)

    # else it's just a normal node, here we treat all as passthrough
    return follow_output_till_deadend_condition(output_node, output_node_input_index, stop_condition)
    