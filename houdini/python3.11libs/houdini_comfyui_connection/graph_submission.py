import requests
import json
from pathlib import Path
import time
import hou

poll_interval = 1


class BadInputSubstituteError(RuntimeError):
    pass


class FunctionalityNotAvailable(RuntimeError):
    pass


class FailedToDeleteImage(RuntimeError):
    pass


class GraphValidationError(RuntimeError):
    def __init__(self, error_json, orig_graph, *args: object) -> None:
        super().__init__(f'graph is invalid: "{json.dumps(error_json, indent=4)}"')  # for those handling this as simple RuntimeError
        self.raw_error = error_json
        self.__orig_graph = orig_graph
    
    def format_error_summary(self) -> str:
        # first check if we know how to format given error
        if main_error := self.raw_error.get('error'):
            main_error_type = main_error.get('type')
            if main_error_type == 'invalid_prompt':
                return main_error.get('message', 'Unknown error ??!')
            elif main_error_type == 'prompt_outputs_failed_validation':
                # here we expect to find node errors
                if node_errors := self.raw_error.get('node_errors'):
                    error_parts = [
                        'Errors found in nodes',
                        '',
                    ]
                    for node_key, node_error_data in node_errors.items():
                        if node_data := self.__orig_graph.get(node_key):
                            node_title = node_data.get('_meta', {}).get('title', 'unknown node title') + f' (#{node_key})'
                        else:
                            node_title = f'#{node_key}'
                        
                        for node_error in node_error_data.get('errors', []):
                            node_error_type = node_error.get('type')
                            if node_error_type == 'return_type_mismatch':
                                message = f'You managed to connect an output into an incompativle input type! {node_error.get("details", "")}'
                            elif node_error_type == 'value_not_in_list':
                                message = (
                                    f'You provided an invalid value. maybe model not downloaded?\n'
                                    f'value of input "{node_error.get("extra_info", {}).get("input_name", "unknown")}":\n'
                                    f'    {node_error.get("extra_info", {}).get("received_value", "unknown")}\n'
                                    f'while accepted values are:\n'
                                ) + '\n'.join(f'    {x}' for x in node_error.get('extra_info', {}).get('input_config', [[], {}])[0])
                            else:
                                message = f'{node_error.get("message", "")}:\n  {node_error.get("details", "")}'
                            message = message.replace('\n', '\n  ')
                            error_parts.append(f'{node_title}:\n  {message}\n')
                    return '\n'.join(error_parts)
                else:
                    return main_error.get('message', 'Unknown error ??!')

        return json.dumps(self.raw_error, indent=4)


class ResultNotFound(RuntimeError):
    def __init__(self, key, res, *args: object) -> None:
        super().__init__(*args)
        self.key = key
        self.res = res


def submit_graph(host: str, graph_json_data: dict):
    resp = requests.post(
        f'{host}/prompt',
        json = {
            'prompt': graph_json_data,
        },
    )
    
    if resp.status_code != 200:
        if resp.status_code == 400:
            resp_data = resp.json()
            raise GraphValidationError(resp_data, graph_json_data)
        else:
            raise RuntimeError(f'oh no, server said nono {resp.status_code}')
    
    resp_data = resp.json()
    
    if 'error' in resp_data:
        raise RuntimeError(f'bad prompt: {resp_data}')
        
    return resp_data['prompt_id'], resp_data['node_errors']

        
def check_if_prompt_done_and_get_result(host: str, prompt_id: str, output_ids=None):
    # otherwise check if it's running or queued
    resp = requests.get(f'{host}/queue')
    if resp.status_code != 200:
        raise RuntimeError(f'oh no, server said nono {resp.status_code}')
    data = resp.json()
    for prompt in data['queue_running'] + data['queue_pending']:
        if prompt[1] == prompt_id:
            return None
    
    # check if it's done
    # note, check order matters, the other way around we might get a race
    resp = requests.get(f'{host}/history/{prompt_id}')
    if resp.status_code != 200:
        raise RuntimeError(f'oh no, server said nono {resp.status_code}')
    data = resp.json()
    if len(data) > 0:  # means it's in history, therefore done
        results = {}
        outputs = data[prompt_id]['outputs']
        if output_ids is None:
            results = {k: v for k, v in outputs.items()}
        else:
            for output_id in output_ids:
                results[output_id] = outputs[output_id]
        return results
        
    raise RuntimeError('cannot find given prompt id on server')            



def submit_graph_and_get_result(host: str, graph_data: dict, long_op=None) -> tuple[dict, str]:
    try:
        prompt_id, errors = submit_graph(host, graph_data)
    except RuntimeError as e:
        raise

    if errors:
        raise RuntimeError(f'some nodes have errors: {errors}')
    
    res = None
    try:
        if long_op:
            long_op.updateLongProgress(-1, "waiting for ComfyUI to finish")
        while True:
            if (res := check_if_prompt_done_and_get_result(host, prompt_id)) is not None:
                break
            time.sleep(poll_interval)
            if long_op:
                long_op.updateProgress()
    
    except hou.OperationInterrupted:
        cancel_prompt(host, prompt_id)
        raise

    return res, prompt_id


def download_result(host: str, filename: str, subfolder: str, dest_path: Path):
    resp = requests.get(
        f'{host}/view',
        params = {
            'filename': filename,
            'subfolder': subfolder,
        }
    )
    if resp.status_code != 200:
        raise RuntimeError(f'oh no, server said nono {resp.status_code}')
    
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, 'wb') as f:
        f.write(resp.content)


def delete_input_image(host: str, filename: str, subfolder: str):
    return delete_image(host, filename, subfolder, 'input')


def delete_output_image(host: str, filename: str, subfolder: str):
    return delete_image(host, filename, subfolder, 'output')


def delete_image(host: str, filename: str, subfolder: str, img_role: str):
    resp = requests.delete(
        f'{host}/sidefx_houdini/image',
        json = {
            'type': img_role,
            'image_name': filename,
            'subfolder': subfolder,
            }
        )

    if resp.status_code == 405:
        raise FunctionalityNotAvailable('your version of houdini-connection extension does not provide this functionality')
    if resp.status_code == 400:  # image do not exist or cannot be deleted
        raise FailedToDeleteImage(img_role, filename, subfolder)
    if resp.status_code != 200:
        raise RuntimeError(f'oh no, server said nono {resp.status_code}')


def delete_prompt_history(host: str, prompt: str):
    resp = requests.post(
        f'{host}/history',
        json = {
            'delete': [prompt],
        }
    )

    if resp.status_code != 200:
        raise RuntimeError(f'oh no, server said nono {resp.status_code}')

def cancel_prompt(host: str, prompt: str):
    resp = requests.post(
        f'{host}/sidefx_houdini/interrupt',
        json = {
            'prompt_id': prompt
        }
    )

    if resp.status_code == 405:
        raise FunctionalityNotAvailable('your version of houdini-connection extension does not provide this functionality')
    if resp.status_code != 200:
        raise RuntimeError(f'oh no, server said nono {resp.status_code}')
