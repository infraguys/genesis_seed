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
import os
import json
import typing as tp
import dataclasses
import uuid as sys_uuid

from genesis_seed.common import utils


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

    def dump_to_simple_view(self) -> dict[str, tp.Any]:
        view = dataclasses.asdict(self)

        for k, v in view.copy().items():
            if isinstance(v, sys_uuid.UUID):
                view[k] = str(v)

        return view


@dataclasses.dataclass
class UniversalAgent(SimpleViewMixin):
    """Universal Agent model.

    Unified agent that implements common logic of abstract resource and
    fact management.

    The models has helpful tools to APIs, resource, payload and other models.
    """

    uuid: sys_uuid.UUID
    name: str
    capabilities: dict[str, tp.Any]
    facts: dict[str, tp.Any]
    node: sys_uuid.UUID
    status: str
    description: str = ""

    def __post_init__(self):
        self.uuid = sys_uuid.UUID(str(self.uuid))
        self.node = sys_uuid.UUID(str(self.node))

    @classmethod
    def from_system_uuid(
        cls,
        capabilities: tp.Iterable[str],
        facts: tp.Iterable[str],
        agent_uuid: sys_uuid.UUID | None = None,
        agent_name: str | None = None,
    ):
        system_uuid = utils.system_uuid()
        uuid = agent_uuid or system_uuid
        capabilities = {"capabilities": list(capabilities)}
        facts = {"facts": list(facts)}
        return cls(
            uuid=uuid,
            name=agent_name or f"Universal Agent {str(uuid)[:8]}",
            status="ACTIVE",
            capabilities=capabilities,
            facts=facts,
            # Actually it's won't be true for some cases. For instance,
            # baremetal nodes added by hands. We dont' have such cases
            # so keep it simple so far.
            node=system_uuid,
        )


@dataclasses.dataclass
class Payload(SimpleViewMixin):
    """This model is used to represent the payload of the agent.

    The models is used as for control plane and data plane.
    The control plane payload is received from Orch API and it
    has be applied to the data plane, excepting `facts`.
    A data plane payload is a collected payload from the data.
    If CP and DP payloads are different from target values of
    resources that means we need to update something on the data plane.
    If CP and DP payloads are different from facts point of view,
    it means we need to update something in the Status API to save
    new facts.

    capabilities - a set of managed resources, for example, configuration,
        secrets and so on. An orchestrator sets which resources should be
        presented on the data plane. CP resources from the capabilities
        contains only managed fields. When these resources are gathered
        from the data plane they may have some additional fields,
        for instance, created time, updated time and so on. Only the
        managed fields are orchestrated.

    facts - opposite to the capabilities. These resources are gathered from
        the data plane independently from the orchestrator. In other words,
        they are not managed by the orchestrator. A simple example of facts
        are network interfaces.

    hash - a hash of the payload. The formula is described below:
        hash(
            hash(cap_resource0.hash),
            hash(cap_resource1.hash),
            ...
            hash(fact_resource0.full_hash),
            hash(fact_resource1.full_hash),
            ...
        )

    """

    hash: str = ""
    version: int = 0
    capabilities: dict[str, tp.Any] = dataclasses.field(default_factory=dict)
    facts: dict[str, tp.Any] = dataclasses.field(default_factory=dict)

    def save(self, payload_path: str) -> None:
        """Save the payload from the data plane."""
        # FIXME(akremenetsky): We cannot calculate the hash
        # so we keep it as is.

        # Create missing directories
        payload_dir = os.path.dirname(payload_path)
        if not os.path.exists(payload_dir):
            os.makedirs(payload_dir)

        payload_data = self.dump_to_simple_view()

        tmp_file = f"{payload_path}.tmp"
        with open(tmp_file, "w") as f:
            json.dump(payload_data, f, indent=2)
        os.replace(tmp_file, payload_path)

    @classmethod
    def empty(cls):
        return cls()

    @classmethod
    def load(cls, payload_path: str) -> "Payload":
        """Load the saved payload from the file."""
        if not os.path.exists(payload_path):
            return cls.empty()

        # Load base from the payload file
        with open(payload_path) as f:
            payload_data = json.load(f)
            payload: Payload = Payload.restore_from_simple_view(**payload_data)

        return payload


@dataclasses.dataclass
class Resource(SimpleViewMixin):
    """This model is represent an abstract resource for the Universal Agent.

    This model is mostly used as an actual resource, for instance, gathered
    from the data plane. In this case the `value` dict contains a real object
    from the data plane in dict format.

    kind - resource kind, for instance, "config", "secret", ...
    value - resource value in dict format.
    hash - hash value only for the target fields.
    full_hash - hash value for the whole value (all fields).
    status - resource status, for instance, "ACTIVE", "NEW", ...

    Some explanation for the `hash` and `full_hash`. Let's assume we have
    the following target node resource:
    {
        "uuid": "a1b2c3d4-e5f6-7890-a1b2-c3d4e5f67890",
        "name": "vm",
        "project_id": "12345678-c625-4fee-81d5-f691897b8142",
        "root_disk_size": 15,
        "cores": 1,
        "ram": 1024,
        "image": "http://10.20.0.1:8080/genesis-base.raw"
    }
    All these fields are considered as target fields and they are used
    to calculate `hash`.

    After node creation we have the the follwing:
    {
        "uuid": "a1b2c3d4-e5f6-7890-a1b2-c3d4e5f67890",
        "name": "vm",
        "project_id": "12345678-c625-4fee-81d5-f691897b8142",
        "root_disk_size": 15,
        "cores": 1,
        "ram": 1024,
        "image": "http://10.20.0.1:8080/genesis-base.raw",

        // Not target fields below
        "created_at": "2022-01-01T00:00:00+00:00",
        "updated_at": "2022-01-01T00:00:00+00:00",
        "default_network": {}
    }

    For hash calculation only the target fields are used as discussed
    above. `full_hash` is calculated for all fields.
    """

    uuid: sys_uuid.UUID
    kind: str
    value: dict[str, tp.Any]
    hash: str = ""
    full_hash: str = ""
    status: str = "ACTIVE"
    res_uuid: sys_uuid.UUID | None = None
    node: sys_uuid.UUID | None = None

    def __post_init__(self):
        self.uuid = sys_uuid.UUID(str(self.uuid))
        self.res_uuid = sys_uuid.uuid5(self.uuid, self.kind)
        self.node = utils.system_uuid()


@dataclasses.dataclass
class GuestMachine(SimpleViewMixin):
    uuid: sys_uuid.UUID
    image: str
    boot: str = "network"
    status: str = "NEW"
    block_devices: dict[str, tp.Any] = dataclasses.field(default_factory=dict)
    net_devices: dict[str, tp.Any] = dataclasses.field(default_factory=dict)
    pci_devices: dict[str, tp.Any] = dataclasses.field(default_factory=dict)

    def __post_init__(self):
        self.uuid = sys_uuid.UUID(str(self.uuid))


@dataclasses.dataclass
class NodeEncryptionKey(SimpleViewMixin):
    """API encryption key model."""

    uuid: sys_uuid.UUID
    private_key: str
