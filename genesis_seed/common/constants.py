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
import enum
import uuid as sys_uuid


GLOBAL_SERVICE_NAME = "genesis_seed"
SERVICE_PROJECT_ID = sys_uuid.UUID("00000000-0000-0000-0000-000000000000")

WORK_DIR = "/var/lib/genesis"
NODE_UUID_PATH = os.path.join(WORK_DIR, "node-id")

CHUNK_SIZE = 16 << 20  # 16Mb

KERNEL_CMDLINE_PATH = "/proc/cmdline"
GC_CMDLINE_DEF_PREFIX = "gc_"
GC_CMDLINE_KEY_ORCH_API = f"{GC_CMDLINE_DEF_PREFIX}orch_api"
GC_CMDLINE_KEY_STATUS_API = f"{GC_CMDLINE_DEF_PREFIX}status_api"

AGENT_CAPABILITIES = ("guest_machine",)
AGENT_FACTS = ()
AGENT_PAYLOAD_PATH = "/payload.json"


class MachineStatus(str, enum.Enum):
    NEW = "NEW"
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    STARTED = "STARTED"
    ACTIVE = "ACTIVE"
    IDLE = "IDLE"
    ERROR = "ERROR"
    FLASHED = "FLASHED"
