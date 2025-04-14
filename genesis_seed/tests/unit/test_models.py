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

import ipaddress
import uuid as sys_uuid

import pytest

from genesis_seed.dm import models


@pytest.fixture
def machine_data():
    return {
        "uuid": "123e4567-e89b-12d3-a456-426614174000",
        "cores": 4,
        "ram": 8192,
        "status": "IDLE",
        "machine_type": "VM",
        "boot": "network",
        "pool": None,
        "project_id": "00000000-0000-0000-0000-000000000000",
        "node": None,
        "firmware_uuid": None,
        "name": "test_machine",
        "description": "Test Machine Description",
        "image": None,
    }


@pytest.fixture
def node_data():
    return {
        "uuid": "123e4567-e89b-12d3-a456-426614174001",
        "cores": 2,
        "ram": 4096,
        "status": "ACTIVE",
        "image": "http://example.com/image.iso",
        "node_type": "VM",
        "project_id": "00000000-0000-0000-0000-000000000000",
        "name": "test_node",
        "description": "Test Node Description",
    }


@pytest.fixture
def interface_data():
    return {
        "name": "eth0",
        "mac": "00:1A:2B:3C:4D:5E",
        "ipv4": "192.168.1.1",
        "mask": "255.255.255.0",
        "mtu": 1500,
    }


@pytest.fixture
def payload_data(machine_data, node_data):
    return {
        "machine": models.Machine(**machine_data).dump_to_simple_view(),
        "node": models.Node(**node_data).dump_to_simple_view(),
        "payload_hash": "",
        "payload_updated_at": "1970-01-01T00:01:00+00:00",
    }


@pytest.fixture
def payload_data_with_interfaces():
    return {
        "payload_updated_at": "2025-04-29T14:57:38.749489+00:00",
        "machine": {
            "uuid": "f9eac394-e52c-4e21-9858-afa56d585184",
            "created_at": "2025-04-29 14:57:38.749482",
            "updated_at": "2025-04-29 14:57:38.749489",
            "project_id": "00000000-0000-0000-0000-000000000000",
            "name": "",
            "description": "",
            "cores": 2,
            "ram": 1977,
            "status": "IDLE",
            "machine_type": "HW",
            "node": None,
            "pool": "2bd17956-600b-4beb-8ddd-9fc4856262e6",
            "boot": "network",
            "firmware_uuid": "f9eac394-e52c-4e21-9858-afa56d585184",
            "builder": None,
            "build_status": "READY",
            "image": None,
        },
        "interfaces": [
            {
                "uuid": "9dc201f3-8c28-445d-824c-4ccd53e6c6d9",
                "name": "eth0",
                "description": "",
                "created_at": "2025-04-29 14:57:38.751049",
                "updated_at": "2025-04-29 14:57:38.751052",
                "machine": "f9eac394-e52c-4e21-9858-afa56d585184",
                "mac": "52:54:00:56:4a:19",
                "ipv4": "10.20.1.12",
                "mask": "255.255.252.0",
                "mtu": 1500,
            }
        ],
        "payload_hash": "1af5ec2ac7b0b3f39fca9afde5976a0c",
    }


class TestMachine:
    def test_machine_creation(self, machine_data):
        machine = models.Machine(**machine_data)
        assert str(machine.uuid) == machine_data["uuid"]
        assert machine.cores == machine_data["cores"]
        # Add more assertions for each field


class TestPayload:
    def test_payload_creation(self, payload_data):
        payload = models.Payload.restore_from_simple_view(**payload_data)
        assert str(payload.machine.uuid) == payload_data["machine"]["uuid"]
        assert str(payload.node.uuid) == payload_data["node"]["uuid"]

    def test_payload_hash_calculation(self, payload_data):
        payload = models.Payload.restore_from_simple_view(**payload_data)
        calculated_hash = payload._calculate_payload_hash()
        assert isinstance(calculated_hash, str)

    def test_payload_equality(self, payload_data):
        payload1 = models.Payload.restore_from_simple_view(**payload_data)
        payload2 = models.Payload.restore_from_simple_view(**payload_data)
        assert payload1 == payload2

    def test_payload_with_interfaces(self, payload_data_with_interfaces):
        payload1 = models.Payload.restore_from_simple_view(
            **payload_data_with_interfaces
        )
        payload2 = models.Payload.restore_from_simple_view(
            **payload_data_with_interfaces
        )

        assert payload1 == payload2
        assert payload1.interfaces == payload2.interfaces
        assert isinstance(payload1.machine, models.Machine)
        assert isinstance(payload1.interfaces[0], models.Interface)


class TestSimpleViewMixin:
    def test_dump_to_simple_view(self, machine_data):
        machine = models.Machine(**machine_data)
        view = machine.dump_to_simple_view()

        assert view["uuid"] == str(machine_data["uuid"])
        assert view["name"] == machine_data["name"]

    def test_restore_from_simple_view(self, machine_data):
        machine = models.Machine.restore_from_simple_view(**machine_data)
        assert isinstance(machine, models.Machine)
        assert str(machine.uuid) == machine_data["uuid"]
        assert machine.name == machine_data["name"]

    def test_dump_and_restore(self, machine_data):
        machine = models.Machine(**machine_data)
        view = machine.dump_to_simple_view()
        machine = models.Machine.restore_from_simple_view(**view)
        assert isinstance(machine, models.Machine)
        assert str(machine.uuid) == machine_data["uuid"]
        assert machine.name == machine_data["name"]

    def test_dump_restore_payload(self, payload_data):
        payload = models.Payload.restore_from_simple_view(**payload_data)

        assert isinstance(payload.machine, models.Machine)
        assert isinstance(payload.node, models.Node)

        view = payload.dump_to_simple_view()

        assert isinstance(view["machine"], dict)
        assert isinstance(view["node"], dict)

        assert isinstance(view["machine"]["uuid"], str)
        assert isinstance(view["node"]["uuid"], str)

        payload = models.Payload.restore_from_simple_view(**view)

        assert isinstance(payload.machine, models.Machine)
        assert isinstance(payload.node, models.Node)

        assert isinstance(payload.machine.uuid, sys_uuid.UUID)
        assert isinstance(payload.node.uuid, sys_uuid.UUID)


class TestInterface:
    def test_interface_post_init(self, interface_data):
        interface = models.Interface(**interface_data)
        isinstance(interface.ipv4, ipaddress.IPv4Address)
        isinstance(interface.mask, ipaddress.IPv4Address)

    # Test the dump_to_simple_view method
    def test_interface_dump_to_simple_view(self, interface_data):
        interface = models.Interface(**interface_data)
        view = interface.dump_to_simple_view()

        # Check if the view correctly represents the data
        assert view["name"] == interface_data["name"]
        assert view["mac"] == interface_data["mac"]
        assert view["mtu"] == interface_data["mtu"]
        assert view["ipv4"] == interface_data["ipv4"]
        assert view["mask"] == interface_data["mask"]
