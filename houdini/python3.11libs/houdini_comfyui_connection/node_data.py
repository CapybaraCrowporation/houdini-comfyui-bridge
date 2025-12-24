import hou


def set_node_data(node: hou.Node, key: str, data: str):
    """
    this is just like Node.setUserData, but sets it recursively on first unlocked parent
    """
    if '::' in key:
        raise ValueError('key cannot contain ::')
    _set_node_data(node, node, key, data)


def get_node_data(node: hou.Node, key: str):
    if '::' in key:
        raise ValueError('key cannot contain ::')
    return _get_node_data(node, node, key)


def _get_suffix(orig_node: hou.Node, node: hou.Node) -> str:
    suffix = '::' + node.relativePathTo(orig_node)
    if suffix == '::.':
        # for compat with simple userdata self uses empty suffix
        suffix = ''
    return suffix


def _set_node_data(orig_node: hou.Node, node: hou.Node, orig_key: str, data: str):
    if node is None:
        raise RuntimeError(f'cannot set data on "{orig_node}"')

    if not node.isInsideLockedHDA():
        suffix = _get_suffix(orig_node, node)
        node.setUserData(orig_key + suffix, data)
    else:
        _set_node_data(orig_node, node.parent(), orig_key, data)


def _get_node_data(orig_node: hou.Node, node: hou.Node, orig_key: str) -> str|None:
    """
    logic is - to get data on first outer unlocked node. If no data there - then go in till data is there
    """
    if node is None:
        raise RuntimeError(f'cannot get data on "{orig_node}"')

    if not node.isInsideLockedHDA():
        suffix = _get_suffix(orig_node, node)
        return node.userData(orig_key + suffix)
    else:
        data = _get_node_data(orig_node, node.parent(), orig_key)
        if data is None:  # data on parent not set
            suffix = _get_suffix(orig_node, node)
            data = node.userData(orig_key + suffix)
        return data
