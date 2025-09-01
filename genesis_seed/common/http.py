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
import logging
import urllib.request
import urllib.parse
import typing as tp
import zlib

from genesis_seed.common import exceptions
from genesis_seed.common import constants as c

LOG = logging.getLogger(__name__)

HttpMethodType = tp.Literal["GET", "POST", "PUT", "DELETE"]
JSON_CONTENT_TYPE = "application/json"


class HttpError(exceptions.GSException):
    message = "Http Error: %(http_err)s"


class DownloadMismatchError(exceptions.GSException):
    message = "Downloaded mismatch. Expected: %(expected)s, got: %(got)s"


class DownloadDecompressError(exceptions.GSException):
    message = (
        "EOF not found while decompressing, broken original archive "
        "or download error."
    )


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


class BaseChunkHandler:
    def __init__(self, content_length: int) -> None:
        self.in_bytes = 0
        self.out_bytes = 0

        self.content_length = content_length

    def handle_chunk(self, chunk: bytes, out_file: tp.BinaryIO) -> int:
        return 0

    def is_clean(self):
        if not self.content_length == self.in_bytes:
            raise DownloadMismatchError(
                expected=self.content_length, got=self.written
            )


class PlainChunkHandler(BaseChunkHandler):
    def handle_chunk(self, chunk: bytes, out_file: tp.BinaryIO) -> int:
        out_file.write(chunk)
        written = len(chunk)
        self.in_bytes += written
        self.out_bytes += written
        return written


class GZChunkHandler(BaseChunkHandler):
    def __init__(self, content_length: int, chunk_size: int):
        self.chunk_size = chunk_size
        # Set appropriate wbits to support gzip
        self.d = zlib.decompressobj(wbits=15 + 32)
        super().__init__(content_length=content_length)

    def handle_chunk(self, chunk: bytes, out_file: tp.BinaryIO) -> int:
        self.in_bytes += len(chunk)
        tail = chunk
        written = 0
        while True:
            # there may be many zeroes, so decompress in chunks
            raw_chunk = self.d.decompress(tail, max_length=self.chunk_size)
            if not raw_chunk:
                break
            tail = self.d.unconsumed_tail
            out_file.write(raw_chunk)
            written += len(raw_chunk)

        self.out_bytes += written
        return written

    def is_clean(self):
        if not self.d.eof:
            raise DownloadDecompressError()
        super().is_clean()


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
    read = written = 0

    req = urllib.request.Request(source_url)
    # It's absurd to compress already compressed file
    if not source_url.endswith(".gz"):
        req.add_header("Accept-Encoding", "gzip")
    with urllib.request.urlopen(req) as response:
        content_length = int(response.headers.get("Content-Length", 0))
        is_gzipped = response.headers.get(
            "Content-Encoding"
        ) == "gzip" or source_url.endswith(".gz")

        if is_gzipped:
            LOG.warning(
                "Got gzipped stream/file, progress will be innacurate..."
            )
            chunker = GZChunkHandler(content_length, chunk_size=chunk_size)
        else:
            chunker = PlainChunkHandler(content_length)

        with open(destination_path, "wb") as file:
            while True:
                chunk = response.read(chunk_size)
                read += len(chunk)
                written += chunker.handle_chunk(chunk, file)

                if not chunk:
                    break

                if chunk_handler is not None:
                    chunk_handler(content_length, read, written, chunk)

    chunker.is_clean()
