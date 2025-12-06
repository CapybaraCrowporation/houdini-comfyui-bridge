# Installation 2

## Install/Upgrade Houdini ComfyUI Plugins

1. Download the repo release

2. Download houdini plugin (`houdini.zip`) and comfyui plugin (`comfy.zip`)

3. Install houdini plugin. There are several options how to do that:

   - **Simplest way** to do it is to just extract the contents of `houdini.zip` into your houdini userdir (ex. `C:\Users\<username>\Documents\houdini20.5`)

     ![Houdini Installation - Extract to Userdir](images/install2_houdini_extract.png)

   - **If you organized a personal way of working with packages:**

     i. Treat `houdini-comfyui` dir from the archive as the contents of the package, copy it wherever you store your packages

     ii. Pick `houdini-comfyui.json` from `packages` dir in the archive, place it where you keep all your package definitions, and do not forget to **change path inside houdini-comfyui.json to point where you have saved** `houdini-comfyui` **dir**

   - **If you know what you are doing** - you can install it however you want. The main point is for `houdini-comfyui` from the archive to be part of `HOUDINI_PATH` variable

4. Install ComfyUI plugin:

   a. Find `custom_nodes` subdir inside and put the contents of the `comfy.zip` archive there, so in the end you will have something like this: `...\ComfyUI\custom_nodes\houdini-comfyui-connection\`
   
      For ComfyUI Desktop on Windows, your `custom_nodes` dir by default should be located in `C:\Users\<username>\Documents\ComfyUI\custom_nodes\`

      ![ComfyUI Installation - Custom Nodes Directory](images/install2_comfyui_custom_nodes.png)

      If you are **updating** to a new version of the plugin - it is safer to first remove the existing dir (houdini-comfyui-connection), then copy over the new version, instead of merging two folders.

   b. Restart ComfyUI server for it to see the plugin

## Next steps:

- [first workflow](link-to-first-workflow)
