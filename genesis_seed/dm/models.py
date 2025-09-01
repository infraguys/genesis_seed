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
import dataclasses
import uuid as sys_uuid

from genesis_seed.common import constants as c


class SimpleViewMixin:
    @classmethod
    def restore_from_simple_view(cls, **kwargs) -> "SimpleViewMixin":
        future_fields = set(kwargs.keys()) - set(
            (f.name for f in dataclasses.fields(cls))
        )

        # Ignore future fields
        for f in future_fields:
            kwargs.pop(f)

        return cls(**kwargs)

    def dump_to_simple_view(self) -> tp.Dict[str, tp.Any]:
        view = dataclasses.asdict(self)

        for k, v in view.copy().items():
            if isinstance(v, sys_uuid.UUID):
                view[k] = str(v)

        return view


@dataclasses.dataclass
class Machine(SimpleViewMixin):
    uuid: sys_uuid.UUID
    cores: int
    ram: int
    status: str
    machine_type: str
    pool: sys_uuid.UUID
    boot: str
    project_id: sys_uuid.UUID = c.SERVICE_PROJECT_ID
    node: sys_uuid.UUID | None = None
    firmware_uuid: sys_uuid.UUID | None = None
    name: str = ""
    description: str = ""
    image: str | None = None


@dataclasses.dataclass
class Node(SimpleViewMixin):
    uuid: sys_uuid.UUID
    cores: int
    ram: int
    status: str
    image: str
    node_type: str
    project_id: sys_uuid.UUID = c.SERVICE_PROJECT_ID
    name: str = ""
    description: str = ""
