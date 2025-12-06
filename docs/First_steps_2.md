# First Steps 2

## Our first simplest workflow

Right after the first installation of ComfyUI you will have no models and no plugins for it.

Let's download our first model then, one very commonly used for image manipulations: SDXL

Though we try to provide a full comfy frontend within houdini, some tasks, such as server configuration and plugin/model management we leave for the classic web UI, as it is something you will not do too often, but something that would take significant amount of effort to recreate within houdini.

## Download our first model

So, let's do it, let's download our first model:

1. Open up ComfyUI interface

2. Open Manager. This tool manages plugins and models.

   ![ComfyUI Manager Interface](images/first_steps_2_manager.png)

3. Click `Model Manager`

4. Search for `sd_xl`

5. Immediately you will notice how much stuff there is in comfy ecosystem, this amount of stuff is very overwhelming, so it's better to follow templates and tutorials at first.

6. Select `sd_xl_base_1.0.safetensors` and install it (yes, this is just one model and it's almost 7GB. you need a LOT of extra disk space to work with these models)

   ![Select and Install SDXL Model](images/first_steps_2_install_model.png)

7. After installation is complete - you will be prompted to restart comfy, do it.

> **Note:** This simple demo workflow does not rely on any ComfyUI plugins or nodes, but for things you find on the internet you will most likely need to install some custom nodes through the ComfyUI Manager

## Create a simple workflow in Houdini

Now we will start working in houdini.

Remember, you need your ComfyUI server to be running in order to work with it from Houdini. (in case of ComfyUI Desktop - you need to app to be running, you cannot separate web interface from the server as they are bundled together, you can just minimize it)

1. Open Houdini

2. Go into a COP context

3. Create `Comfyui compound graph submit` node

4. In that node's parameters ensure server address is correctly pointing to the ComfyUI server address you've seen/changed during installation

   ![ComfyUI Server Address](images/first_steps_2_server_config.png)

5. Since we have downloaded new models or plugins in ComfyUI, we need to update Houdini's knowledge about ComfyUI server nodes and models.

   So, we need to Update Node Definitions. Just like in the "making sure things work" section above:

   a. Expand collapsed "Node Definitions" tab in the parameters

      ![Expand Node Definitions](images/first_steps_2_expand_node_def.png)

   b. Press the button "Update Node Definitions"

      ![Update Node Definitions Button](images/first_steps_2_update_node_def.png)

6. Now dive into the compound graph node.
   You will notice here that in the tab menu you have all the nodes that ComfyUI has!

7. Download this image
   This image has metadata about the ComfyUI graph that has created it, just like any ComfyUI created image has!

   ![Shiba Inu in Flower Pot](images/first_steps_2_shiba.png)

8. Drag and drop this image into Houdini's node editor
   The graph will be created automatically!

   ![Drag and Drop Image to Create Graph](images/first_steps_2_drag_drop.png)

9. Now go up, to the compound graph node, and press "Compute" button

   ![Compute Button](images/first_steps_2_compute.png)

10. Now you have generated the exact same shiba!

    ![Generated Shiba Result](images/first_steps_2_result.png)

What we just did is - we recreated the ComfyUI graph that was used to generate a shiba inu in a flower pot inside the Houdini, and then we generated the exact same image!

You can now tweak some parameters to see how they affect the process. See [Improvements](First_steps_3.md) section
