import os
from inspect import cleandoc
import shutil
import folder_paths


class HouConnectController:
    """
    A example node

    Class methods
    -------------
    INPUT_TYPES (dict):
        Tell the main program input parameters of nodes.
    IS_CHANGED:
        optional method to control when the node is re executed.

    Attributes
    ----------
    RETURN_TYPES (`tuple`):
        The type of each element in the output tulple.
    RETURN_NAMES (`tuple`):
        Optional: The name of each output in the output tulple.
    FUNCTION (`str`):
        The name of the entry-point method. For example, if `FUNCTION = "execute"` then it will run Example().execute()
    OUTPUT_NODE ([`bool`]):
        If this node is an output node that outputs a result/image from the graph. The SaveImage node is an example.
        The backend iterates on these output nodes and tries to execute all their parents if their parent graph is properly connected.
        Assumed to be False if not present.
    CATEGORY (`str`):
        The category the node should appear in the UI.
    execute(s) -> tuple || None:
        The entry point method. The name of this method must be the same as the value of property `FUNCTION`.
        For example, if `FUNCTION = "execute"` then this method's name must be `execute`, if `FUNCTION = "foo"` then it must be `foo`.
    """
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        """
            Return a dictionary which contains config for all input fields.
            Some types (string): "MODEL", "VAE", "CLIP", "CONDITIONING", "LATENT", "IMAGE", "INT", "STRING", "FLOAT".
            Input types "INT", "STRING" or "FLOAT" are special values for fields on the node.
            The type can be a list for selection.

            Returns: `dict`:
                - Key input_fields_group (`string`): Can be either required, hidden or optional. A node class must have property `required`
                - Value input_fields (`dict`): Contains input fields config:
                    * Key field_name (`string`): Name of a entry-point method's argument
                    * Value field_config (`tuple`):
                        + First value is a string indicate the type of field or a list for selection.
                        + Secound value is a config for type "INT", "STRING" or "FLOAT".
        """
        return {
            "required": {
                "server": ("STRING", {
                    "default": "localhost:8769",
                    "multiline": False,
                    "display": "houdini host"
                }),
            },
        }

    RETURN_TYPES = ("INT",)
    RETURN_NAMES = ("dummy",)
    DESCRIPTION = cleandoc(__doc__)
    FUNCTION = "dummy_exec"

    #OUTPUT_NODE = False
    #OUTPUT_TOOLTIPS = ("",) # Tooltips for the output node

    CATEGORY = "Houdini"

    def dummy_exec(self, server,):
        if print_to_screen == "enable":
            print(f"""Houdini server
                  using {server}
            """)
        #do some processing on the image, in this example I just invert it
        return (1.0,)

    """
        The node will always be re executed if any of the inputs change but
        this method can be used to force the node to execute again even when the inputs don't change.
        You can make this node return a number or a string. This value will be compared to the one returned the last time the node was
        executed, if it is different the node will be executed again.
        This method is used in the core repo for the LoadImage node where they return the image hash as a string, if the image hash
        changes between executions the LoadImage node is executed again.
    """
    #@classmethod
    #def IS_CHANGED(s, image, string_field, int_field, float_field, print_to_screen):
    #    return ""

class HouCuiStringAsImage:
    """
    treat input string as image path and provide given image as output
    """
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image_path": ("STRING", {"tooltip": "The image path to output."}),
            },
        }

    RETURN_TYPES = ()
    RETURN_NAMES = ()
    DESCRIPTION = cleandoc(__doc__ if __doc__ is not None else '')
    FUNCTION = "process"
    OUTPUT_NODE = True

    def process(self, image_path):
        results = [{
            "filename": os.path.basename(image_path),
            "subfolder": os.path.dirname(image_path),
            "type": "output"
        }]
        return { "ui": { "images": results } }


class HouCuiTrimeshUnwrapProperly:
    """
    just call trimesh.unwrap()
    temporary helper for Hy3D Wrapper node pack
    """
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "trimesh": ("TRIMESH", {"tooltip": "Yeah, the trimesh goes here."}),
            },
        }

    RETURN_TYPES = ("TRIMESH",)
    RETURN_NAMES = ("trimesh",)
    DESCRIPTION = cleandoc(__doc__ if __doc__ is not None else '')
    FUNCTION = "process"
    OUTPUT_NODE = False

    def process(self, trimesh):
        try:
            import trimesh as _trimesh
        except ImportError:
            print('no trimesh module! acting as a noop')
            return (trimesh,)

        if isinstance(trimesh, _trimesh.Scene):
            trimesh = trimesh.to_geometry()

        return (trimesh.unwrap(),)


class HouCuiInputPathToAbsolute:
    """
    expand given path relative to input dir to absolute path
    """
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "rel_path": ("STRING", {"tooltip": "relative input path"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("rel", "abs")
    DESCRIPTION = cleandoc(__doc__ if __doc__ is not None else '')
    FUNCTION = "process"
    OUTPUT_NODE = False

    def process(self, rel_path):
        abs_path = os.path.join(folder_paths.get_input_directory(), rel_path)
        print('wahoooooo', (rel_path, abs_path))
        return (rel_path, abs_path)


class HouCuiCopyInputToOutput:
    """
    copy relative input to relative output
    """
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "in_rel_path": ("STRING", {"tooltip": "relative input path"}),
            },
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("rel",)
    DESCRIPTION = cleandoc(__doc__ if __doc__ is not None else '')
    FUNCTION = "process"
    OUTPUT_NODE = False

    def process(self, in_rel_path):
        out_abs_path = os.path.join(folder_paths.get_output_directory(), in_rel_path)

        os.makedirs(os.path.dirname(out_abs_path), exist_ok=True)

        shutil.copy2(
            os.path.join(folder_paths.get_input_directory(), in_rel_path),
            out_abs_path,
        )
        return (in_rel_path,)


class HouStringPassThrough:
    """
    noop
    """
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "str_in": ("STRING", {"forceInput": True, "tooltip": "a string"}),
            },
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("str_out",)
    DESCRIPTION = cleandoc(__doc__ if __doc__ is not None else '')
    FUNCTION = "process"
    OUTPUT_NODE = False

    def process(self, str_in):
        return (str_in,)


class HouStringToFile:
    """
    save string to output
    """
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"tooltip": "text to save"}),
                "name_prefix": ("STRING", {"tooltip": "prefix for filename"}),
            },
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("rel_path",)
    DESCRIPTION = cleandoc(__doc__ if __doc__ is not None else '')
    FUNCTION = "process"
    OUTPUT_NODE = False

    def process(self, text, name_prefix):
        full_output_folder, filename, counter, subfolder, filename_prefix = folder_paths.get_save_image_path(name_prefix, folder_paths.get_output_directory(), 0, 0)
        full_out_path = os.path.join(full_output_folder, f"{filename}_{counter:05}_.txt")
        with open(full_out_path, 'w') as f:
            f.write(text)
        
        return (os.path.relpath(full_out_path, folder_paths.get_output_directory()),)


# A dictionary that contains all nodes you want to export with their names
# NOTE: names should be globally unique

NODE_CLASS_MAPPINGS = {
    # "HouConnectController": HouConnectController
    "HouCuiStringAsImage": HouCuiStringAsImage,
    "HouCuiTrimeshUnwrapProperly": HouCuiTrimeshUnwrapProperly,
    "HouCuiInputPathToAbsolute": HouCuiInputPathToAbsolute,
    "HouCuiCopyInputToOutput": HouCuiCopyInputToOutput,
    "HouStringPassThrough": HouStringPassThrough,
    "HouStringToFile": HouStringToFile,
}

# A dictionary that contains the friendly/humanly readable titles for the nodes
NODE_DISPLAY_NAME_MAPPINGS = {
    # "HouConnectController": "Houdini Connector"
    "HouCuiStringAsImage": "String To Image Helper",
    "HouCuiTrimeshUnwrapProperly": "Trimesh UV Unwrap",
    "HouCuiInputPathToAbsolute": "Input Path To Absolute",
    "HouCuiCopyInputToOutput": "Copy Input to Output",
    "HouStringPassThrough": "String Pass Through",
    "HouStringToFile": "String Save",
}
