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

from genesis_seed.common.http import base
from genesis_seed.dm import models


class BaseModelClient(base.HttpClient):
    ACTIONS_KEY = "actions"
    INVOKE_KEY = "invoke"

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
        self, **filters: dict[str, tp.Any]
    ) -> list[models.SimpleViewMixin]:
        resp = super().get(self._collection_url(), params=filters)
        return [
            self.__model__.restore_from_simple_view(**o) for o in resp.json()
        ]

    def create(self, object: models.SimpleViewMixin) -> models.SimpleViewMixin:
        data = object.dump_to_simple_view()
        resp = super().post(self._collection_url(), data)
        return self.__model__.restore_from_simple_view(**resp.json())

    def update(
        self, uuid: sys_uuid.UUID, **params: dict[str, tp.Any]
    ) -> models.SimpleViewMixin:
        url = self._resource_url(uuid)
        resp = super().put(url, data=params)
        return self.__model__.restore_from_simple_view(**resp.json())

    def delete(self, uuid: sys_uuid.UUID) -> None:
        url = self._resource_url(uuid)
        super().delete(url)

    def do_action(
        self,
        name: str,
        uuid: sys_uuid.UUID,
        invoke: bool = False,
        **kwargs,
    ) -> dict[str, tp.Any] | None:
        url = self._resource_url(uuid) + "/"
        action_url = urljoin(urljoin(url, self.ACTIONS_KEY) + "/", name)

        if invoke:
            action_url = urljoin(action_url + "/", self.INVOKE_KEY)
            resp = self._request("POST", action_url, data=kwargs)
        else:
            resp = self._request("GET", action_url, params=kwargs)

        resp.raise_for_status()

        # Try to convert response to json
        try:
            return resp.json()
        except base.HttpError:
            return None


class UniversalAgentsClient(BaseModelClient):
    __collection_url__ = "/v1/agents/"
    __model__ = models.UniversalAgent

    def get_payload(
        self, uuid: sys_uuid.UUID, last_payload: models.Payload
    ) -> models.Payload:
        payload_data = self.do_action(
            "get_payload",
            uuid,
            hash=last_payload.hash,
            version=last_payload.version,
        )
        cp_payload = models.Payload.restore_from_simple_view(**payload_data)

        # Choose the target payload. If the payloads are equal, the CP returns
        # light payload without capabilities so use the last payload
        # in this case.
        return last_payload if last_payload == cp_payload else cp_payload


class NodeEncryptionKeyClient(BaseModelClient):
    __collection_url__ = "/v1/nodes/"
    __model__ = models.NodeEncryptionKey

    def refresh_secret(self, uuid: sys_uuid.UUID) -> str:
        data = self.do_action(
            "refresh_secret",
            uuid,
            invoke=True,
        )
        return data["key"]


class ResourcesClient(BaseModelClient):
    API_VERSION = "v1"

    __model__ = models.Resource

    def __init__(
        self,
        base_url: str,
        kind: str,
    ) -> None:
        base_url = base_url.rstrip("/")
        self._collecton_path = f"/{self.API_VERSION}/kind/{kind}/resources/"
        super().__init__(base_url)
        self._kind = kind

    def _collection_url(self) -> str:
        return self._base_url + self._collecton_path

    def _set_kind_ref(self, resource: models.Resource | dict) -> None:
        """Set the resource kind as a reference.

        The `kind` field in the response is a reference since the kind is
        a collection now. It's not convenient to use it as the reference
        so set it to a reference before creating the resource in Status API.
        """
        ref = f"/{self.API_VERSION}/kind/{self._kind}"

        try:
            resource.kind = ref
        except AttributeError:
            if "kind" in resource:
                resource["kind"] = ref

    def _drop_kind_ref(self, resource: models.Resource | dict) -> None:
        """Drop the kind reference and set it as a string.

        The `kind` field in the response is a reference since the kind is
        a collection now. It's not convenient to use it as the reference
        so drop the reference and set the kind as a string before using it.
        """
        try:
            resource.kind = self._kind
        except AttributeError:
            if "kind" in resource:
                resource["kind"] = self._kind

    def get(self, uuid: sys_uuid.UUID) -> models.Resource:
        resource = super().get(uuid)
        self._drop_kind_ref(resource)
        return resource

    def filter(self, **filters: dict[str, tp.Any]) -> list[models.Resource]:
        resources = super().filter(**filters)
        for r in resources:
            self._drop_kind_ref(r)
        return resources

    def create(self, object: models.Resource) -> models.Resource:
        self._set_kind_ref(object)
        resource = super().create(object)
        self._drop_kind_ref(resource)
        return resource

    def update(
        self, uuid: sys_uuid.UUID, **params: dict[str, tp.Any]
    ) -> models.Resource:
        self._set_kind_ref(params)
        resource = super().update(uuid, **params)
        self._drop_kind_ref(resource)
        return resource
