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
import dataclasses
import os
import uuid as sys_uuid


@dataclasses.dataclass
class BlockDevice:
    path: str
    size: int
    uuid: sys_uuid.UUID | None = None
    partitions: list["BlockDevice"] = dataclasses.field(default_factory=list)

    @classmethod
    def from_sysfs_block_path(
        cls, path: str, sector_size: int = 512
    ) -> "BlockDevice":
        with open(os.path.join(path, "size"), "r") as f:
            sectors = int(f.read().strip())
        size = (sectors * sector_size) // (1024**3)
        device_path = "/dev/" + os.path.basename(path)
        return cls(path=device_path, size=size)
