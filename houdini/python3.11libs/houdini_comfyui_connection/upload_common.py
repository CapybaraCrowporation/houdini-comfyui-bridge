import requests
from pathlib import Path


def upload_image(host: str, file_path: Path, subdir: str, image_name: str|None):
    if image_name is None:
        image_name = file_path.name
        
    with open(file_path, 'rb') as f:
        file_data = f.read()
    
    resp = requests.post(
        f'{host}/upload/image',
        files = {'image': (image_name, file_data)},
        data = {'subfolder': subdir, 'overwrite': '1'},
    )

    if resp.status_code != 200:
        raise RuntimeError(f'oh no, server said nono {resp.status_code}')