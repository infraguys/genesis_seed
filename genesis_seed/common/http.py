#    Copyright 2025 Genesis Corporation.
#
#    All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
from __future__ import annotations

import json
import urllib.request
import urllib.parse
import typing as tp

from genesis_seed.common import exceptions
from genesis_seed.common import constants as c

HttpMethodType = tp.Literal["GET", "POST", "PUT", "DELETE"]
JSON_CONTENT_TYPE = "application/json"


class HttpError(exceptions.GSException):
    message = "Http Error: %(http_err)s"


class DownloadMismatchError(exceptions.GSException):
    message = "Downloaded mismatch. Expected: %(expected)s, got: %(got)s"


class HttpResp:
    def __init__(self, resp_code: int, text: bytes, content_type: str) -> None:
        self.text = text
        self.content_type = content_type
        self.resp_code = resp_code

    def json(self) -> tp.Dict[str, tp.Any] | None:
        if self.content_type == JSON_CONTENT_TYPE:
            return json.loads(self.text.decode("utf-8"))

        raise HttpError(http_err="Invalid content type")


class HttpClient:
    def __init__(self, timeout: int = 20):
        self._timeout = timeout

    def _request(
        self,
        method: HttpMethodType,
        url: str,
        data: tp.Any | None = None,
        headers: tp.Dict[str, tp.Any] | None = None,
    ) -> HttpResp:
        if headers is None:
            headers = {}

        if data is not None:
            if isinstance(data, dict) or isinstance(data, list):
                data = json.dumps(data).encode("utf-8")
                headers["Content-Type"] = JSON_CONTENT_TYPE

        req = urllib.request.Request(
            url, data=data, headers=headers, method=method
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as response:
            return HttpResp(
                resp_code=response.status,
                text=response.read(),
                content_type=response.getheader("Content-Type"),
            )

    def get(
        self,
        url: str,
        params: tp.Optional[tp.Dict[str, tp.Any]] = None,
        headers: tp.Dict[str, tp.Any] | None = None,
    ) -> HttpResp:
        if params:
            url += "?" + urllib.parse.urlencode(params)
        return self._request("GET", url, headers=headers)

    def post(
        self,
        url: str,
        data: str | tp.Dict[str, tp.Any],
        headers: tp.Dict[str, tp.Any] | None = None,
    ) -> HttpResp:
        return self._request("POST", url, data=data, headers=headers)

    def put(
        self,
        url: str,
        data: str | tp.Dict[str, tp.Any],
        headers: tp.Dict[str, tp.Any] | None = None,
    ) -> HttpResp:
        return self._request("PUT", url, data=data, headers=headers)

    def delete(
        self, url: str, headers: tp.Dict[str, tp.Any] | None = None
    ) -> HttpResp:
        return self._request("DELETE", url, headers=headers)


def stream_to_file(
    source_url: str,
    destination_path: str,
    chunk_size: int = c.CHUNK_SIZE,
    chunk_handler: tp.Callable | None = None,
) -> None:
    """
    Downloads a file from a source URL and streams it to a destination path.

    The caller can pass a chunk handler that will be called for each chunk of
    data as it is received. The handler is passed the total content length of
    the file, the amount of data written to disk, and the actual chunk of data.

    :param source_url: URL to download from
    :param destination_path: Path to write the file to
    :param chunk_size: Size of chunks to read from the URL in bytes
    :param chunk_handler: Optional callable to call for each chunk of data
    :raises DownloadMismatchError: If the total amount of data written to disk
        does not match the content length in the HTTP response headers
    """
    written = 0

    with urllib.request.urlopen(source_url) as response:
        content_length = int(response.headers["Content-Length"])

        with open(destination_path, "wb") as file:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break

                file.write(chunk)
                written += len(chunk)

                if chunk_handler is not None:
                    chunk_handler(content_length, written, chunk)

    if content_length != written:
        raise DownloadMismatchError(expected=content_length, got=written)
