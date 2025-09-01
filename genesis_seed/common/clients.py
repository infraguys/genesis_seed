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
import typing as tp
import uuid as sys_uuid
from urllib.parse import urljoin

from genesis_seed.common import http
from genesis_seed.dm import models


class BaseModelClient(http.HttpClient):
    __collection_url__: str = None
    __model__: tp.Type[models.SimpleViewMixin] = None

    def __init__(self, base_url: str, timeout: int = 20):
        super().__init__(timeout)
        self._base_url = base_url

    def _collection_url(self):
        if not self._base_url.endswith(
            "/"
        ) and not self.__collection_url__.startswith("/"):
            return self._base_url + "/" + self.__collection_url__
        return self._base_url + self.__collection_url__

    def _resource_url(self, uuid: sys_uuid.UUID):
        return urljoin(self._collection_url(), str(uuid))

    def get(self, uuid: sys_uuid.UUID) -> models.SimpleViewMixin:
        url = self._resource_url(uuid)
        resp = super().get(url)
        return self.__model__.restore_from_simple_view(**resp.json())

    def filter(
        self, **filters: tp.Dict[str, tp.Any]
    ) -> models.SimpleViewMixin:
        resp = super().get(self._collection_url(), params=filters)
        return [
            self.__model__.restore_from_simple_view(**o) for o in resp.json()
        ]

    def create(self, object: models.SimpleViewMixin) -> models.SimpleViewMixin:
        data = object.dump_to_simple_view()
        resp = super().post(self._collection_url(), data)
        return self.__model__.restore_from_simple_view(**resp.json())

    def update(
        self, uuid: sys_uuid.UUID, **params: tp.Dict[str, tp.Any]
    ) -> models.SimpleViewMixin:
        url = self._resource_url(uuid)
        resp = super().put(url, data=params)
        return self.__model__.restore_from_simple_view(**resp.json())

    def delete(self, uuid: sys_uuid.UUID) -> None:
        url = self._resource_url(uuid)
        super().delete(url)


class MachinesClient(BaseModelClient):
    __collection_url__ = "/v1/machines/"
    __model__ = models.Machine


class NodesClient(BaseModelClient):
    __collection_url__ = "/v1/nodes/"
    __model__ = models.Node


class UserAPI:
    def __init__(self, base_url: str):
        self._machine_client = MachinesClient(base_url)
        self._node_client = NodesClient(base_url)

    @property
    def machines(self):
        return self._machine_client

    @property
    def nodes(self):
        return self._node_client
