from .requester import Requester
from .logging import debug
from pathlib import Path


def upload_image(requester: Requester, file_path: Path, subdir: str, image_name: str|None) -> tuple[str, str]:
    if image_name is None:
        image_name = file_path.name
        
    with open(file_path, 'rb') as f:
        file_data = f.read()
    
    resp = requester.post(
        f'upload/image',
        files = {'image': (image_name, file_data)},
        data = {'subfolder': subdir, 'overwrite': '1'},
    )

    if resp.status_code != 200:
        raise RuntimeError(f'oh no, server said nono {resp.status_code}')
    # reply may contain actual image+subdir  {'name': 'f54ee43cac68376a2e898caf6a31b0dd81da69a71139ea127920699d9bdc9156.png', 'subfolder': '', 'type': 'input'}
    resp_data = resp.json()
    return resp_data.get('name', image_name), resp_data.get('subfolder', subdir)
