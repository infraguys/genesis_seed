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
import ipaddress
import subprocess
import typing as tp
import uuid as sys_uuid

from genesis_seed.common import constants as c


def system_uuid() -> sys_uuid.UUID:
    """Return system uuid"""
    with open("/sys/class/dmi/id/product_uuid") as f:
        return sys_uuid.UUID(f.read().strip())


def get_cores(cpuinfo_path: str = "/proc/cpuinfo") -> int:
    with open(cpuinfo_path) as f:
        return sum(1 for line in f if line.startswith("processor"))


def get_memory(meminfo_path: str = "/proc/meminfo") -> int:
    with open(meminfo_path) as f:
        for line in f:
            if line.startswith("MemTotal"):
                # Extract the number and convert it from kB to MB
                mem_kb = int(line.split()[1])
                return mem_kb >> 10

    raise RuntimeError(f"Unable to find MemTotal in {meminfo_path}")


def get_disks(
    min_size: int = c.MINIMAL_BLOCK_DEVICE_SIZE_GB,
) -> tp.Generator[dict, None, None]:
    """Return list of disks"""
    block_devices_path = "/sys/block/"
    virtual_block_devices_path = "/sys/devices/virtual/block/"

    # Include only physical block devices
    block_devices = set(os.listdir(block_devices_path)) - set(
        os.listdir(virtual_block_devices_path)
    )

    # Return devices in sorted order
    for bd_name in sorted(block_devices):
        path = os.path.join(block_devices_path, bd_name)

        with open(os.path.join(path, "size")) as f:
            size_in_sectors = int(f.read().strip())

        with open(os.path.join(path, "queue", "logical_block_size")) as f:
            sector_size = int(f.read().strip())

        size_gb = (size_in_sectors * sector_size) >> 30
        if size_gb < min_size:
            continue

        yield {
            "path": os.path.join("/dev", bd_name),
            "size": size_gb,
        }


def get_ifaces(skip_virtual: bool = True) -> tp.List[tp.Dict[str, tp.Any]]:
    """Return interfaces information."""
    ifaces = os.listdir("/sys/class/net")
    virtual_ifaces = set(os.listdir("/sys/devices/virtual/net"))
    result = []

    for iface in ifaces:
        if skip_virtual and iface in virtual_ifaces:
            continue

        # Get the MAC address of the interface
        with open(f"/sys/class/net/{iface}/address") as f:
            mac_address = f.read().strip()

        # Get the maximum transmission unit (MTU) of the interface
        with open(f"/sys/class/net/{iface}/mtu") as f:
            mtu = f.read().strip()

        # Get interface IPv4 address and mask
        ipv4_address = mask = None
        try:
            output = (
                subprocess.check_output(f"ip -4 addr show {iface}", shell=True)
                .decode("utf-8")
                .splitlines()[1]
            )
            value = output.strip().split()[1]
            ipv4, _ = value.split("/")
            ipv4_address = ipaddress.IPv4Address(ipv4)
            mask = ipaddress.IPv4Network(value, strict=False).netmask
        except Exception:
            # Unable to detect IPv4 address
            pass

        iface_spec = dict(
            name=iface,
            mac=mac_address,
            mtu=int(mtu),
            ipv4_addresses=(ipv4_address,) if ipv4_address is not None else (),
            masks=(mask,) if mask is not None else (),
        )
        result.append(iface_spec)

    return result
