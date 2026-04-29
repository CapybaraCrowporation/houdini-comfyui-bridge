import requests  # type:ignore


class Requester:
    def __init__(self, host: str, *, api_key: str|None = None):
        host = host.rstrip('/ ')
        self.__host = host
        self.__api_key = api_key
        self.__extra_headers = {}
        if api_key:
            self.__extra_headers['X-API-Key'] = api_key
        # cloud.comfy.org uses /api/ prefix and different polling endpoints
        self._is_cloud = 'cloud.comfy.org' in host

    @property
    def is_cloud(self) -> bool:
        return self._is_cloud

    def _url(self, path: str) -> str:
        # host may already contain /api (e.g. https://cloud.comfy.org/api) — no extra prefix needed
        return f'{self.__host}/{path}'

    def prompt(self, graph_json_data: dict):
        data = {'prompt': graph_json_data}
        if self.__api_key and not self._is_cloud:
            # local ComfyUI reads api_key from extra_data; cloud uses X-API-Key header only
            data['extra_data'] = {'api_key_comfy_org': self.__api_key}
        return self.post('prompt', json=data)

    # Generic functions

    def post(self, path: str, *, json=None, data=None, files=None, headers=None):
        return requests.post(
            self._url(path),
            json=json,
            data=data,
            files=files,
            headers={**self.__extra_headers, **(headers or {})},
        )

    def get(self, path: str, *, params=None, headers=None):
        return requests.get(
            self._url(path),
            params=params,
            headers={**self.__extra_headers, **(headers or {})},
        )

    def delete(self, path: str, *, json=None, headers=None):
        return requests.delete(
            self._url(path),
            json=json,
            headers={**self.__extra_headers, **(headers or {})},
        )
