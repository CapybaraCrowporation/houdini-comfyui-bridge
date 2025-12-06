# Installation 1

## Install Houdini

1. Go to sidefx [download section](https://www.sidefx.com/download/) and download **H21.0.465+** or **H20.5** build with **python 3.11**
2. Install it

## Install ComfyUI

You can install ComfyUI in any way you want really. It can also be installed on a different machine from houdini, as long as it is network accessible from the machine with houdini.

Here is a recommended way if you do not have ComfyUI and you have never installed it before:

### Windows

1. Go to comfyui [download section](https://www.comfy.org/download) and click "Download for Windows"

   ![ComfyUI Download Button](images/comfyui_download_button.png)

   > **Note:** Requires NVIDIA graphics card

2. Run the installer

3. Disable automatic updates in the installation wizard, at least for the duration of the beta testing, to prevent things from breaking unexpectedly.

4. You may want to go into `settings->server config` and change the port (default `8000`) to something else as 8000 can be commonly used by other things.
   
   Non-Desktop Comfy uses port `8188` by default, and that is the default value on **all houdini nodes too**.
   
   So you should change port 8000 to 8188 in comfyui settings:

   ![ComfyUI Settings - Server Config](images/comfyui_settings_screenshot.png)
   
   a. **Alternatively,** change default 8188 port on comfy nodes in houdini to 8000.

5. If you installed ComfyUI desktop on a different machine - you want to change the listening address of the server from `127.0.0.1` to the address of your external interface, or to catch-all address `0.0.0.0`

### Linux

On Linux there is no easy one-button solution like ComfyUI Desktop on Windows.

Users need a bit more technical knowledge to install ComfyUI.

[Official documentation](https://docs.comfy.org/get_started/manual_install) provides nice step-by-step instruction on how to install Comfy within a miniconda environment, [here](https://docs.comfy.org/get_started/manual_install)

### MacOS

Same as for Linux, you should look into the manual installation section from the [official Comfy documentation](https://docs.comfy.org/get_started/manual_install), it provides step-by-step guide to how to install Comfy within a miniconda environment, [here](https://docs.comfy.org/get_started/manual_install)

---

## Additional Notes

- **Port Configuration:** The default port for ComfyUI Desktop is `8000`, while standalone ComfyUI uses `8188`. All Houdini nodes default to port `8188`.
- **Network Access:** Ensure ComfyUI is network accessible if running on a different machine than Houdini.
- **Beta Testing:** Disable automatic updates during beta testing to maintain stability.
