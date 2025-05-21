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
import hashlib
import datetime
import ipaddress
import dataclasses
import types
import typing as tp
import uuid as sys_uuid
from genesis_seed.common import system
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

        for field in dataclasses.fields(cls):
            match field.type:
                case datetime.datetime():
                    kwargs[field.name] = datetime.datetime.strptime(
                        kwargs[field.name],
                        c.DEFAULT_DATETIME_FORMAT,
                    )
                case sys_uuid.UUID():
                    kwargs[field.name] = sys_uuid.UUID(kwargs[field.name])
                case ipaddress.IPv4Address():
                    kwargs[field.name] = ipaddress.IPv4Address(
                        kwargs[field.name]
                    )
                case types.UnionType():
                    for class_ in tp.get_args(field.type):
                        if (
                            issubclass(class_, SimpleViewMixin)
                            and field.name in kwargs
                            and kwargs[field.name]
                        ):
                            kwargs[field.name] = (
                                class_.restore_from_simple_view(
                                    **kwargs[field.name]
                                )
                            )
                            break
                case SimpleViewMixin():
                    kwargs[field.name] = field.type.restore_from_simple_view(
                        **kwargs[field.name]
                    )

        return cls(**kwargs)

    def dump_to_simple_view(self) -> tp.Dict[str, tp.Any]:
        view = dataclasses.asdict(self)

        for k, v in view.copy().items():
            match v:
                case SimpleViewMixin():
                    view[k] = v.dump_to_simple_view()
                case datetime.datetime():
                    view[k] = v.strftime(c.DEFAULT_DATETIME_FORMAT)
                case ipaddress.IPv4Address():
                    view[k] = str(v)
                case sys_uuid.UUID():
                    view[k] = str(v)

        return view


@dataclasses.dataclass
class Interface(SimpleViewMixin):
    name: str
    mac: str
    ipv4: ipaddress.IPv4Address
    mask: ipaddress.IPv4Address
    mtu: int

    def __post_init__(self):
        if isinstance(self.ipv4, str):
            self.ipv4 = ipaddress.IPv4Address(self.ipv4)

        if isinstance(self.mask, str):
            self.mask = ipaddress.IPv4Address(self.mask)

    def __eq__(self, other: "Interface") -> bool:
        return self.__hash__() == other.__hash__()

    def __hash__(self) -> int:
        return hash((self.name, self.mac, self.ipv4, self.mask, self.mtu))

    @classmethod
    def from_system(cls) -> tp.List["Interface"]:
        ifaces = []
        for iface in system.get_ifaces():
            # TODO(akremenetsky): Support multiple IPv4 addresses for an interface
            ipv4 = next(iter(iface["ipv4_addresses"]), None)
            mask = next(iter(iface["masks"]), None)
            ifaces.append(
                cls(
                    name=iface["name"],
                    mac=iface["mac"],
                    ipv4=ipv4,
                    mask=mask,
                    mtu=iface["mtu"],
                )
            )

        return ifaces


@dataclasses.dataclass
class Machine(SimpleViewMixin):
    uuid: sys_uuid.UUID
    cores: int
    ram: int
    status: str
    machine_type: str
    boot: str
    pool: sys_uuid.UUID | None = None
    project_id: sys_uuid.UUID = c.SERVICE_PROJECT_ID
    node: sys_uuid.UUID | None = None
    firmware_uuid: sys_uuid.UUID | None = None
    name: str = ""
    description: str = ""
    image: str | None = None

    def __post_init__(self):
        if isinstance(self.uuid, str):
            self.uuid = sys_uuid.UUID(self.uuid)

        if isinstance(self.project_id, str):
            self.project_id = sys_uuid.UUID(self.project_id)

        if isinstance(self.pool, str):
            self.pool = sys_uuid.UUID(self.pool)

        if isinstance(self.node, str):
            self.node = sys_uuid.UUID(self.node)

        if isinstance(self.firmware_uuid, str):
            self.firmware_uuid = sys_uuid.UUID(self.firmware_uuid)

    @classmethod
    def from_system(cls):
        uuid = system.system_uuid()
        cores = system.get_cores()
        ram = system.get_memory()

        return cls(
            uuid=uuid,
            firmware_uuid=uuid,
            cores=cores,
            ram=ram,
            status=c.MachineStatus.IDLE.value,
            boot=c.BootAlternative.network.value,
            # TODO(akremenetsky): Determine machine type
            machine_type=c.MachineType.HW.value,
        )


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

    def __post_init__(self):
        if isinstance(self.uuid, str):
            self.uuid = sys_uuid.UUID(self.uuid)

        if isinstance(self.project_id, str):
            self.project_id = sys_uuid.UUID(self.project_id)


@dataclasses.dataclass
class Payload(SimpleViewMixin):
    machine: Machine | None = None
    node: Node | None = None
    interfaces: tp.List[Interface] = dataclasses.field(default_factory=list)

    # This field is used for CP payloads
    payload_hash: str = ""
    payload_updated_at: str = dataclasses.field(
        default_factory=lambda: datetime.datetime(
            1970, 1, 1, 0, 1, tzinfo=datetime.timezone.utc
        ).strftime(c.DEFAULT_DATETIME_FORMAT)
    )

    @classmethod
    def restore_from_simple_view(cls, **kwargs) -> "Payload":
        payload = super().restore_from_simple_view(**kwargs)
        interfaces = kwargs.pop("interfaces", [])
        interfaces = [
            Interface.restore_from_simple_view(**i) for i in interfaces
        ]
        payload.interfaces = interfaces
        return payload

    def __eq__(self, other: "Payload") -> bool:
        return self.__hash__() == other.__hash__()

    def __hash__(self) -> int:
        if self.payload_hash:
            return hash(self.payload_hash)

        return hash(self._calculate_payload_hash())

    def dump_to_simple_view(self):
        view = super().dump_to_simple_view()

        if self.machine is not None:
            view["machine"] = self.machine.dump_to_simple_view()

        if self.node is not None:
            view["node"] = self.node.dump_to_simple_view()

        view["interfaces"] = [i.dump_to_simple_view() for i in self.interfaces]

        return view

    def _calculate_payload_hash(self) -> str:
        """Calculate payload hash using dedicated fields."""
        m = hashlib.sha256()
        data = {}

        # Base payload object
        if self.machine is not None:
            data = {
                "machine": {
                    "image": self.machine.image,
                    "node": str(self.node),
                }
            }

        if self.node is not None:
            data["node"] = {
                "cores": self.node.cores,
                "ram": self.node.ram,
                "node_type": self.node.node_type,
                "image": self.node.image,
            }

        if self.interfaces:
            data["interfaces"] = [
                {
                    "mac": iface.mac,
                    "ipv4": str(iface.ipv4),
                    "mask": str(iface.mask),
                }
                for iface in self.interfaces
            ]

        m.update(
            json.dumps(data, separators=(",", ":"), sort_keys=True).encode(
                "utf-8"
            )
        )
        return m.hexdigest()

    def update_payload_hash(self):
        self.payload_hash = self._calculate_payload_hash()

    @classmethod
    def from_file(cls, path: str) -> "Payload":
        with open(path, "r") as f:
            data = json.load(f)

        machine = data["machine"]
        node = data.get("node")
        return cls(
            machine=Machine.restore_from_simple_view(**machine),
            node=(
                None if node is None else Node.restore_from_simple_view(**node)
            ),
        )


@dataclasses.dataclass
class CoreAgent(SimpleViewMixin):
    PAYLOAD_PATH = "/seed-agent-payload.json"

    uuid: sys_uuid.UUID
    # payload_updated_at: str
    name: str = ""
    description: str = ""

    @classmethod
    def from_system_uuid(cls):
        uuid = system.system_uuid()
        return cls(
            uuid=uuid,
            name=f"Core Agent {str(uuid)[:8]}",
        )

    @classmethod
    def empty_payload(cls) -> Payload:
        interfaces = Interface.from_system()
        return Payload(
            machine=Machine.from_system(), node=None, interfaces=interfaces
        )

    @classmethod
    def collect_payload(cls) -> Payload:
        """Collect payload from the data plane."""
        # TODO(akremenetsky): The simplest implementation is to keep some
        # values into a file. This should be reworked in the future.
        # The values should be collected from the data plane.
        if not os.path.exists(cls.PAYLOAD_PATH):
            empty = cls.empty_payload()
            with open(cls.PAYLOAD_PATH, "w") as f:
                json.dump(empty.dump_to_simple_view(), f, indent=2)
            empty.update_payload_hash()
            return empty

        with open(cls.PAYLOAD_PATH) as f:
            payload_data = json.load(f)
            payload: Payload = Payload.restore_from_simple_view(**payload_data)

        interfaces = Interface.from_system()
        payload.interfaces = interfaces

        payload.update_payload_hash()
        return payload

    @classmethod
    def save_payload(cls, payload: Payload) -> None:
        """Collect payload from the data plane."""
        # TODO(akremenetsky): The simplest implementation is to keep some
        # values into a file. This should be reworked in the future.
        # The values should be collected from the data plane.
        with open(cls.PAYLOAD_PATH, "w") as f:
            payload_data = payload.dump_to_simple_view()
            json.dump(payload_data, f, indent=2)
