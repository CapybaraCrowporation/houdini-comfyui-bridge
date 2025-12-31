from server import PromptServer, nodes
import folder_paths
from aiohttp import web
from pathlib import Path
import time

prompt_server = PromptServer.instance
routes = prompt_server.routes

route_base = 'sidefx_houdini'
messages = []


def add_message(message: str, param=None):
    messages.append((time.time(), message, param))


def prune_messages(delete_older_than=30):
    global messages
    thres = time.time() - delete_older_than
    messages = [msg for msg in messages if msg[0] >= thres]


@routes.post(f'/{route_base}/command/refresh_all_images')
async def refresh_all(request):
    global messages

    add_message('refresh_all')
    prune_messages()
    
    return web.json_response({'status': 'ok'})


@routes.post(f'/{route_base}/command/refresh_image')
async def refresh_image(request):
    global messages
    data = await request.json()

    add_message('refresh', {'image': data['image']})
    prune_messages()

    return web.json_response({'status': 'ok'})


@routes.post(f'/{route_base}/command/create_loader')
async def create_loader(request):
    global messages
    data = await request.json()

    add_message('create_loader', {'image': data['image']})
    prune_messages()

    return web.json_response({'status': 'ok'})


@routes.post(f'/{route_base}/messages/get')
async def get_messages(request):
    global messages
    data = await request.json()

    timestamp = data.get('since', 0)

    ret_messages = [m for m in messages if m[0] > timestamp]

    return web.json_response({
        'status': 'ok',
        'messages': ret_messages,
    })


@routes.delete(f'/{route_base}/image')
async def delete_image(request):
    data = await request.json()
    image_type = data.get('type')
    if image_type == 'input':
        base_dir = Path(folder_paths.get_input_directory())
    elif image_type == 'output':
        base_dir = Path(folder_paths.get_output_directory())
    else:
        return web.Response(status=400)

    # Note: no path validation!
    image_path = base_dir / data.get('subfolder', '') /  data.get('image_name', '')
    print(f'DEBUG {image_path}')

    if not image_path.exists():
        return web.Response(status=400)
    
    # ok, just a little validation
    if not image_path.resolve(True).is_relative_to(base_dir.resolve(True)):
        return web.Response(status=400)

    image_path.unlink()

    return web.json_response({
        'status': 'ok',
    })

@routes.post(f'/{route_base}/interrupt')
async def interrupt(request):
    """
    unlike standard interrupt, this TRIES to make sure it interrupts the right thing
    though there seem to be no race-free way to stop EXACTLY what user wants

    THIS IS NOT RACE FREE !!
    """
    data = await request.json()
    prompt_id = data.get('prompt_id')

    if not prompt_id:
        return web.Response(400)

    current_running = prompt_server.prompt_queue.get_current_queue()[0]
    
    if len(current_running) != 1 or current_running[0][1] != prompt_id:
        # not running, is it in queue?
        # if multiple things are running - just ignore instead of cancelling all anyway
        prompt_server.prompt_queue.delete_queue_item(lambda a: a[1] == prompt_id)
        # i guess we can report that everything is good
        return web.json_response({
            'status': 'ok',
        })
    nodes.interrupt_processing()

    return web.json_response({
            'status': 'ok',
        })
