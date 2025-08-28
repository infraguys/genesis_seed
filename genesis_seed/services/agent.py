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
import logging
import subprocess

from genesis_seed.services import basic
from genesis_seed.common import clients
from genesis_seed.common import utils
from genesis_seed.dm import models
from genesis_seed.common import http


LOG = logging.getLogger(__name__)
DEFAULT_BLOCK_DEVICE = "/dev/vda"


class SeedOSAgentService(basic.BasicService):
    FINISH_FLAG_PATH = "/seed_os_finished"

    def __init__(
        self,
        user_api: clients.UserAPI,
        iter_min_period=3,
        iter_pause=0.1,
    ):
        super().__init__(iter_min_period, iter_pause)
        self._system_uuid = utils.system_uuid()
        self._user_api = user_api

    def _is_ready(self) -> bool:
        return os.path.exists(self.FINISH_FLAG_PATH)

    def _mark_ready(self):
        with open(self.FINISH_FLAG_PATH, "w") as f:
            f.write("")

    def _iteration(self):
        LOG.warning("Iteration %s", self._iteration_number)
        if self._is_ready():
            return

        machines = self._user_api.machines.filter(
            firmware_uuid=str(self._system_uuid)
        )

        # The auto discovery feature is not yet implemented
        # It will be added in the future
        if not machines:
            LOG.warning("No machines found")
            return

        machine: models.Machine = machines[0]

        # Free machine
        if not machine.node:
            if machine.status != "IDLE":
                self._user_api.machines.update(
                    machine.uuid,
                    status="IDLE",
                )
            return

        node: models.Node = self._user_api.nodes.get(machine.node)

        if not node.image.startswith("http"):
            raise ValueError(f"Image is not a URL: {node.image}")

        progress = 0
        LOG.warning("Flashing progress: 0%")
        self._user_api.machines.update(machine.uuid, status="IN_PROGRESS")
        self._user_api.nodes.update(node.uuid, status="IN_PROGRESS")

        def handler(total: int, read: int, written: int, chunk: bytes):
            nonlocal progress
            if total == 0:
                LOG.warning(
                    "Flashing progress: %d MiB written", written / 1024**2
                )
                return
            current_progress = int((read / total) * 100)
            if current_progress > progress:
                progress = current_progress
                LOG.warning(
                    "Flashing progress: %d%%, %d MiB written",
                    progress,
                    written / 1024**2,
                )

        http.stream_to_file(
            source_url=node.image,
            destination_path=DEFAULT_BLOCK_DEVICE,
            chunk_handler=handler,
        )
        LOG.warning("Flashing progress: 100%")

        utils.flush_disk(DEFAULT_BLOCK_DEVICE)

        self._user_api.machines.update(
            machine.uuid,
            boot="hd0",
            status="ACTIVE",
            image=node.image,
        )
        self._user_api.nodes.update(node.uuid, status="ACTIVE")

        self._mark_ready()
        subprocess.run("/bin/sh -c '(sleep 1 && reboot -f)&'", shell=True)
