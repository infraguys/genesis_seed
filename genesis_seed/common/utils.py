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
import typing as tp
import uuid as sys_uuid
import subprocess

from genesis_seed.common import constants as c


def node_uuid(path: str = c.NODE_UUID_PATH) -> sys_uuid.UUID:
    with open(path, "r") as f:
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


def real_path(path: str, mount: str = c.MNT_PATH) -> str:
    return os.path.join(mount, path)
