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
import subprocess
import typing as tp
import uuid as sys_uuid
import logging

from genesis_seed.common import constants as c
from genesis_seed.dm import hw_models

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)

SYS_BLOCK_PATH = "/sys/block"


class SupportedFSNotFound(Exception):
    pass


def node_uuid(path: str = c.NODE_UUID_PATH) -> sys_uuid.UUID:
    with open(path, "r") as f:
        return sys_uuid.UUID(f.read().strip())


def system_uuid() -> sys_uuid.UUID:
    """Return system uuid"""
    with open("/sys/class/dmi/id/product_uuid") as f:
        return sys_uuid.UUID(f.read().strip())


def flush_disk(device: str) -> None:
    _FLUSH_CMD = """fdisk "{device}" <<EOF
w
EOF
"""
    cmd = _FLUSH_CMD.format(device=device)
    subprocess.run(cmd, shell=True)


def cfg_from_cmdline(
    prefix: str | None = c.GC_CMDLINE_DEF_PREFIX,
) -> tp.Dict[str, str | bool]:
    """
    Parse the kernel command line options and return them as a configuration
    dictionary.

    Parameters
    ----------
    prefix : str | None
        Filter the options by prefix. If `None`, all options are returned.

    Returns
    -------
    cfg : Dict[str, str | bool]
        The configuration dictionary. Boolean values are for options that
        do not have an equals sign, i.e. they are treated as boolean.
    """
    with open(c.KERNEL_CMDLINE_PATH, "r") as f:
        options = f.read().strip().split(" ")

    # Filter by prefix
    if prefix:
        options = [opt for opt in options if opt.startswith(prefix)]

    cfg = {}
    for opt in options:
        # Treat as boolean if no equals
        if "=" not in opt:
            cfg[opt] = True
            continue

        key, value = opt.split("=", 1)
        cfg[key] = value

    return cfg


def block_devices(skip_virtual: bool = True) -> list[hw_models.BlockDevice]:
    devices = []
    if not os.path.isdir(SYS_BLOCK_PATH):
        return devices

    # Detect block devices
    for bd in os.listdir(SYS_BLOCK_PATH):
        bd_path = os.path.join(SYS_BLOCK_PATH, bd)
        try:
            realpath = os.path.realpath(bd_path)
        except OSError:
            continue

        if skip_virtual and "/devices/virtual/" in realpath:
            continue

        device = hw_models.BlockDevice.from_sysfs_block_path(bd_path)
        devices.append(device)

        # Detect partitions
        for partition in os.listdir(bd_path):
            partition_path = os.path.join(bd_path, partition)

            # Skip non-partitions
            if not os.path.exists(os.path.join(partition_path, "partition")):
                continue

            partition_device = hw_models.BlockDevice.from_sysfs_block_path(
                partition_path
            )

            device.partitions.append(partition_device)

    return devices


def mount_root_partition(
    devices: list[hw_models.BlockDevice],
    mount_point: str = "/mnt",
    indicators: tuple[str, ...] = ("var", "dev", "boot"),
) -> None:
    if not devices:
        raise FileNotFoundError("No devices found")

    os.makedirs(mount_point, exist_ok=True)

    # Check if something is already mounted at mount_point
    result = subprocess.run(
        ["mountpoint", "-q", mount_point],
        capture_output=True,
    )
    if result.returncode == 0:
        LOG.warning("Something is already mounted at %s", mount_point)
        return

    count = 0
    for device in devices:
        for partition in device.partitions:
            count += 1
            # It's fine if nothing is mounted at mount_point
            unmount_root_partition(mount_point)

            try:
                subprocess.check_call(
                    ["mount", partition.path, mount_point],
                )
            except subprocess.CalledProcessError:
                # Just skip it, try the next partition
                continue

            # Check if it is the root partition
            if any(
                not os.path.exists(os.path.join(mount_point, indicator))
                for indicator in indicators
            ):
                continue

            LOG.warning(
                "Root partition %s mounted at %s in %s tries",
                partition.path,
                mount_point,
                count,
            )
            return

    raise SupportedFSNotFound(f"The root partition was not found on {count} partitions")


def unmount_root_partition(mount_point: str = "/mnt") -> None:
    result = subprocess.run(["mountpoint", "-q", mount_point])
    if result.returncode != 0:
        LOG.warning("Nothing is mounted at %s", mount_point)
        return

    subprocess.check_call(["umount", mount_point])
