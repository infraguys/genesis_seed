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
import configparser
import uuid as sys_uuid

from genesis_seed.dm import models
from genesis_seed.services import basic
from genesis_seed.common import clients
from genesis_seed.common import utils
from genesis_seed.common import system
from genesis_seed.common import http
from genesis_seed.common import exceptions as exp
from genesis_seed.common import constants as c


LOG = logging.getLogger(__name__)
DEFAULT_BLOCK_DEVICE = "/dev/vda"


class SeedOSAgentService(basic.BasicService):
    FINISH_FLAG_PATH = "/seed_os_finished"

    def __init__(
        self,
        orch_api: clients.OrchAPI,
        iter_min_period=3,
        iter_pause=0.1,
    ):
        super().__init__(iter_min_period, iter_pause)
        self._system_uuid = system.system_uuid()
        self._orch_api = orch_api

    def _is_rebooting(self) -> bool:
        return os.path.exists(self.FINISH_FLAG_PATH)

    def _reboot(self):
        subprocess.run("/bin/sh -c '(sleep 1 && reboot -f)&'", shell=True)
        with open(self.FINISH_FLAG_PATH, "w") as f:
            f.write("")

    def _register_agent(self, dp_payload: models.Payload):
        agent = models.CoreAgent.from_system_uuid()
        try:
            agent: models.CoreAgent = self._orch_api.agents.create(agent)
            LOG.info("Agent registered: %s", agent)
        except http.HttpConflictError:
            # Agent already registered
            pass

        self._orch_api.agents.register_payload(agent.uuid, dp_payload)
        LOG.info("Payload registered: %s", dp_payload)

    def _set_status(
        self,
        machine: models.Machine,
        node: models.Node | None = None,
    ) -> None:
        machine_update = {
            "status": machine.status,
            "description": machine.description,
        }
        node_update = {}

        if node is not None:
            node_update = {
                "status": node.status,
                "description": node.description,
            }

        self._orch_api.machines.update(machine.uuid, **machine_update)

        if node_update:
            self._orch_api.nodes.update(node.uuid, **node_update)

    def _set_error_status(
        self,
        machine: models.Machine,
        node: models.Node | None = None,
        description: str = "",
    ) -> None:
        if (
            machine.status != c.MachineStatus.ERROR.value
            or node.status != c.NodeStatus.ERROR.value
        ):
            node.description = machine.description = description
            node.status = c.NodeStatus.ERROR.value
            machine.status = c.MachineStatus.ERROR.value
            self._set_status(machine, node)

    def _set_in_progress_status(
        self,
        machine: models.Machine,
        node: models.Node | None = None,
        description: str = "",
    ) -> None:
        if (
            machine.status != c.MachineStatus.IN_PROGRESS.value
            or node.status != c.NodeStatus.IN_PROGRESS.value
            or machine.description != description
        ):
            node.description = machine.description = description
            node.status = c.NodeStatus.IN_PROGRESS.value
            machine.status = c.MachineStatus.IN_PROGRESS.value
            self._set_status(machine, node)

    def _actualize_machine(
        self, cp_payload: models.Payload, dp_payload: models.Payload
    ) -> None:
        update = {}
        cp_machine = cp_payload.machine
        dp_machine = dp_payload.machine

        # Actualize cores
        if cp_machine.cores != dp_machine.cores:
            update["cores"] = dp_machine.cores

        # Actualize ram
        if cp_machine.ram != dp_machine.ram:
            update["ram"] = dp_machine.ram

        if update:
            self._orch_api.machines.update(dp_machine.uuid, **update)

        # Actualize interfaces
        if cp_payload.interfaces != dp_payload.interfaces:
            machine_client = self._orch_api.machines(cp_machine.uuid)
            # Create interfaces
            for iface in set(dp_payload.interfaces) - set(
                cp_payload.interfaces
            ):
                machine_client.interfaces.create(iface)

            # Delete interfaces
            for iface in set(cp_payload.interfaces) - set(
                dp_payload.interfaces
            ):
                machine_client.interfaces.delete(iface.uuid)

            # Update interfaces
            for iface in set(cp_payload.interfaces) & set(
                dp_payload.interfaces
            ):
                machine_client.interfaces.update(iface.uuid, iface)

    def _configure_core_agent(self) -> None:
        cfg_path = utils.real_path(c.CORE_AGENT_CFG_PATH)

        # Mount FS

        if not os.path.exists(cfg_path):
            LOG.debug(
                "Image without core agent, skip agent configuration part."
            )
            # TODO(a.kremenetsky): Unmount FS
            return

        # Configure core agent, set orch correct orch endpoint
        config = configparser.ConfigParser()
        config.read(cfg_path)
        config["core_agent"]["orch_endpoint"] = self._orch_api.orch_endpoint

        # Dump configuration to the disk
        with open(cfg_path) as f:
            config.write(f)
        LOG.info(
            "The core agent has been configured to %s endpoint",
            self._orch_api.orch_endpoint,
        )

        # Unmount FS

    def _place_node(
        self, cp_payload: models.Payload, dp_payload: models.Payload
    ) -> None:
        node = cp_payload.node
        machine = cp_payload.machine

        if not node.image.startswith("http"):
            raise ValueError(f"Image is not a URL: {node.image}")

        # Detect an acceptable block device
        # TODO(akremenetsky): Need to consider an image size,
        # take the smallest at the moment
        for block_device in system.get_disks():
            break
        else:
            self._set_error_status(
                machine, node, "No acceptable block device found"
            )
            raise exp.NoAcceptableBlockDevice()

        # Start flashing
        # TODO(akremenetsky): Save dp_payload.machine.status to DP payload.
        # We need it to reduce write operation on CP in case if something goes
        # wrong and the cycle is repeating again and again.
        progress = 0
        LOG.warning("Flashing progress: 0%")
        self._set_in_progress_status(
            machine, node, "Image flashing in progress"
        )

        def handler(total: int, written: int, chunk: bytes):
            nonlocal progress

            current_progress = int((written / total) * 100)
            if current_progress > progress:
                progress = current_progress
                LOG.warning("Flashing progress: %d%%", progress)

        http.stream_to_file(
            source_url=node.image,
            destination_path=block_device["path"],
            chunk_handler=handler,
        )
        LOG.warning("Flashing progress: 100%")

        utils.flush_disk(block_device["path"])

        # FIXME(a.kremenetsky): For cases if there is the core agent in the
        # image we need to set a correct orch endpoint for it. This
        # functionality may dropped in the future when private DNS feature
        # will be added to Genesis.
        self._configure_core_agent()

        # TODO(a.kremenetsky): The ACTIVE status should be set by the
        # core agent.
        # Finish the flashing process, make machine and nodes as active
        self._orch_api.machines.update(
            machine.uuid,
            boot="hd0",
            status=c.MachineStatus.ACTIVE.value,
            image=node.image,
            description="",
        )
        self._orch_api.nodes.update(
            node.uuid, status=c.NodeStatus.ACTIVE.value, description=""
        )

        self._reboot()

    def _clear_machine(
        self, cp_payload: models.Payload, dp_payload: models.Payload
    ) -> None:
        dp_machine = dp_payload.machine
        dp_machine.status = c.MachineStatus.IDLE.value
        dp_machine.description = ""
        dp_machine.boot = c.BootAlternative.network.value

        self._orch_api.machines.update(
            dp_machine.uuid,
            boot=c.BootAlternative.network.value,
            status=c.MachineStatus.IDLE.value,
            image=None,
            description="",
        )

        # TODO(akremenetsky): Clear block devices

    def _actualize_image(
        self, cp_payload: models.Payload, dp_payload: models.Payload
    ) -> None:
        # TODO(akremenetsky): Will be implemented later
        pass

    def _actualize_node(
        self, cp_payload: models.Payload, dp_payload: models.Payload
    ) -> None:
        cp_node = cp_payload.node
        dp_node = dp_payload.node

        # New node
        if dp_node is None and cp_node is not None:
            return self._place_node(cp_payload, dp_payload)

        # Actualize image
        if (
            cp_node is not None
            and dp_node is not None
            and cp_node.image != dp_node.image
        ):
            return self._actualize_image(cp_payload, dp_payload)

        # The node was removed from the machine.
        # Clear the machine.
        if cp_node is None:
            return self._clear_machine(cp_payload, dp_payload)

    def _actualize_agent(
        self, cp_payload: models.Payload, dp_payload: models.Payload
    ) -> None:
        # Everything has been updated, save the updated_at time stamp
        dp_payload.payload_updated_at = cp_payload.payload_updated_at

    def _iteration(self):
        LOG.warning("Iteration %s", self._iteration_number)
        if self._is_rebooting():
            return

        dp_payload = models.CoreAgent.collect_payload()

        # Check if the agent is registered
        try:
            cp_payload = self._orch_api.agents.get_target_payload(
                self._system_uuid, dp_payload
            )
            LOG.debug("Target payload: %s", cp_payload)
        except http.HttpNotFoundError:
            # Auto discovery mechanism
            self._register_agent(dp_payload)
            return

        # Nothing to do, payload is the same
        if cp_payload == dp_payload:
            return

        LOG.debug("Payload actualization is required")

        self._actualize_machine(cp_payload, dp_payload)
        self._actualize_node(cp_payload, dp_payload)
        self._actualize_agent(cp_payload, dp_payload)

        # Save the payload after actualization
        models.CoreAgent.save_payload(dp_payload)
