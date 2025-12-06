# First Steps 1

## First steps with ComfyUI and Houdini connector

Right after [installation](Installation_2_Plugin.md), if you have little-to-no comfyui experience, you should take a look at these simple first steps.

There is a number of pre-configured HDAs, but in this section we will go over the basics of working in houdini as if you were working in comfyui.

## Making sure things work

After installation we should make sure everything works as expected.

Let's go through a checklist:

- Houdini should start, and in COP context you should see `ComfyUI` nodes (such as `comfyui_compound_graph_submit1`)

- ComfyUI should start, and you should see anything but an error there

- In houdini:

  - Go into a COP context and create a `Comfyui compound graph submit` node.

    ![Create ComfyUI Compound Graph Submit Node](images/first_steps_1_create_node.png)

  - In that node's parameters ensure server address is correctly pointing to the ComfyUI server address you've seen/changed during installation

    ![ComfyUI Server Address Configuration](images/first_steps_1_server_address.png)

  - Expand collapsed "Node Definitions" tab in the parameters

    ![Expand Node Definitions Tab](images/first_steps_1_expand_definitions.png)

  - Press the button "Update Node Definitions"

    ![Update Node Definitions Button](images/first_steps_1_update_button.png)

  - There should be no errors popping up

- Open ComfyUI interface (ComfyUI Desktop, or web interface)

  - Double mouse click in the node editor will bring up node creation menu

  - Start typing "unwrap" into the node type finder

  - You should see this node type present
    You do not need to create it, we are only checking that ComfyUI has that node's definition.
    You can cancel the operation

    ![Trimesh UV Unwrap Node in ComfyUI](images/first_steps_1_unwrap_node.png)

Now if you have encountered no errors and everything worked as expected - that means the installation was likely a success.

You can now proceed to the next section: [Our first simplest workflow](First_steps_2.md)
