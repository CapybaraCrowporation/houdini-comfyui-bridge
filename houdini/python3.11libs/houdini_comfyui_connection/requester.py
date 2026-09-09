import requests  # type:ignore


class Requester:
    def __init__(self, host: str, *, api_key: str|None = None):
        host = host.rstrip('/ ')
        self.__host = host
        self.__api_key = api_key
        self.__extra_headers = {
            'X-API-Key': api_key,
        }

    def prompt(self, graph_json_data: dict):
        data = {
            'prompt': graph_json_data,
        }
        if self.__api_key:
            data['extra_data'] = {'api_key_comfy_org': self.__api_key}

        return self.post('prompt', json=data)

    # Generic functions

    def post(self, path: str, *, json=None, data=None, files=None, headers=None):
        return requests.post(
            f'{self.__host}/{path}',
            json=json,
            data=data,
            files=files,
            headers={**self.__extra_headers, **(headers or {})},
        )

    def get(self, path: str, *, params=None, headers=None):
        return requests.get(
            f'{self.__host}/{path}',
            params=params,
            headers={**self.__extra_headers, **(headers or {})},
        )

    def delete(self, path: str, *, json=None, headers=None):
        return requests.delete(
            f'{self.__host}/{path}',
            json=json,
            headers={**self.__extra_headers, **(headers or {})},
        )
