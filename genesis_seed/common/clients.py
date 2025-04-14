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


class CollectionBaseModelClient(http.HttpClient):
    ACTIONS_KEY = "actions"
    INVOKE_KEY = "invoke"

    __collection_url__: str = None
    __model__: tp.Type[models.SimpleViewMixin] = None
    __resource_client__: tp.Type["ResourceBaseModelClient"] = None

    def __init__(self, base_url: str, timeout: int = 20):
        super().__init__(timeout)
        self._base_url = base_url

    def __call__(
        self, resource_uuid: sys_uuid.UUID
    ) -> "ResourceBaseModelClient":
        if self.__resource_client__ is None:
            raise ValueError("Resource client is not defined")
        return self.__resource_client__(self, resource_uuid)

    def _collection_url(self):
        if not self._base_url.endswith(
            "/"
        ) and not self.__collection_url__.startswith("/"):
            return self._base_url + "/" + self.__collection_url__
        return self._base_url + self.__collection_url__

    def resource_url(self, uuid: sys_uuid.UUID):
        return urljoin(self._collection_url(), str(uuid))

    def get(self, uuid: sys_uuid.UUID) -> models.SimpleViewMixin:
        url = self.resource_url(uuid)
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
        url = self.resource_url(uuid)
        resp = super().put(url, data=params)
        return self.__model__.restore_from_simple_view(**resp.json())

    def delete(self, uuid: sys_uuid.UUID) -> None:
        url = self.resource_url(uuid)
        super().delete(url)

    def do_action(
        self, name: str, uuid: sys_uuid.UUID, invoke: bool = False, **kwargs
    ) -> tp.Dict[str, tp.Any] | None:
        url = self.resource_url(uuid) + "/"
        action_url = urljoin(urljoin(url, self.ACTIONS_KEY) + "/", name)

        if invoke:
            action_url = urljoin(action_url + "/", self.INVOKE_KEY)
            resp = super().post(action_url, data=kwargs)
        else:
            resp = super().get(action_url, data=kwargs)

        # Try to convert response to json
        resp.raise_for_status()
        try:
            return resp.json()
        except http.HttpError:
            return None


class ResourceBaseModelClient(http.HttpClient):
    ACTIONS_KEY = "actions"
    INVOKE_KEY = "invoke"

    __model__: tp.Type[models.SimpleViewMixin] = None

    def __init__(
        self,
        collection: CollectionBaseModelClient,
        resource_uuid: sys_uuid.UUID,
        timeout: int = 20,
    ):
        super().__init__(timeout)
        self._collection = collection
        self._resource_uuid = resource_uuid

    def resource_url(self):
        return self._collection.resource_url(self._resource_uuid)

    def get(self) -> models.SimpleViewMixin:
        url = self.resource_url()
        resp = super().get(url)
        return self.__model__.restore_from_simple_view(**resp.json())

    def update(self, **params: tp.Dict[str, tp.Any]) -> models.SimpleViewMixin:
        url = self.resource_url()
        resp = super().put(url, data=params)
        return self.__model__.restore_from_simple_view(**resp.json())

    def delete(self) -> None:
        url = self.resource_url()
        super().delete(url)

    def do_action(
        self, name: str, invoke: bool = False, **kwargs
    ) -> tp.Dict[str, tp.Any] | None:
        url = self.resource_url() + "/"
        action_url = urljoin(urljoin(url, self.ACTIONS_KEY) + "/", name)

        if invoke:
            action_url = urljoin(action_url + "/", self.INVOKE_KEY)
            resp = super().post(action_url, data=kwargs)
        else:
            resp = super().get(action_url, data=kwargs)

        # Try to convert response to json
        resp.raise_for_status()
        try:
            return resp.json()
        except http.HttpError:
            return None


class InterfacesClient(CollectionBaseModelClient):
    __collection_url__ = "/interfaces/"
    __model__ = models.Interface


class MachineClient(ResourceBaseModelClient):
    __model__ = models.Machine

    @property
    def interfaces(self):
        return InterfacesClient(base_url=self.resource_url())


class MachinesClient(CollectionBaseModelClient):
    __collection_url__ = "/v1/machines/"
    __model__ = models.Machine
    __resource_client__ = MachineClient


class NodesClient(CollectionBaseModelClient):
    __collection_url__ = "/v1/nodes/"
    __model__ = models.Node


class CoreAgentsClient(CollectionBaseModelClient):
    __collection_url__ = "/v1/core_agents/"
    __model__ = models.CoreAgent

    def get_target_payload(
        self, uuid: sys_uuid.UUID, dp_payload: models.Payload
    ) -> models.Payload:
        payload_data = self.do_action(
            "get_payload",
            uuid,
            payload_hash=dp_payload.payload_hash,
            payload_updated_at=dp_payload.payload_updated_at,
        )
        return models.Payload.restore_from_simple_view(**payload_data)

    def register_payload(
        self, uuid: sys_uuid.UUID, dp_payload: models.Payload
    ) -> None:
        dp_payload.update_payload_hash()
        state = dp_payload.dump_to_simple_view()
        self.do_action("register_payload", uuid, invoke=True, **state)


class OrchAPI:
    def __init__(self, base_url: str):
        self._machines_client = MachinesClient(base_url)
        self._nodes_client = NodesClient(base_url)
        self._agents_client = CoreAgentsClient(base_url)

    @property
    def machines(self):
        return self._machines_client

    @property
    def nodes(self):
        return self._nodes_client

    @property
    def agents(self):
        return self._agents_client
