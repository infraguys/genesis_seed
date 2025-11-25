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
import logging
import uuid as sys_uuid

from genesis_seed.services import basic
from genesis_seed.common import utils
from genesis_seed.dm import models
from genesis_seed.common.orch import core
from genesis_seed.common import constants as c
from genesis_seed.drivers import guest


LOG = logging.getLogger(__name__)
PAYLOAD_UPDATE_RATE = 60


class SeedOSAgentService(basic.BasicService):
    FINISH_FLAG_PATH = "/seed_os_finished"

    def __init__(
        self,
        core_client: core.CoreClient,
        agent_uuid: sys_uuid.UUID | None = None,
        payload_path: str | None = c.AGENT_PAYLOAD_PATH,
        iter_min_period=3,
        iter_pause=0.1,
    ):
        super().__init__(iter_min_period, iter_pause)
        self._system_uuid = utils.system_uuid()
        self._api = core_client
        self._agent_uuid = agent_uuid or utils.system_uuid()
        self._payload_path = payload_path

        # NOTE(akremenetsky): Someday we will have a dynamic driver
        # registration but for now directly call specific drivers.
        self._caps_drivers = [guest.GuestCapDriver()]

    def _register_agent(self) -> None:
        agent = models.UniversalAgent.from_system_uuid(
            c.AGENT_CAPABILITIES, c.AGENT_FACTS, self._agent_uuid
        )
        try:
            self._api.agents_create(agent)
            LOG.info("Agent registered: %s", agent.uuid)
        except core.AgentAlreadyExists:
            LOG.warning("Agent already registered: %s", agent.uuid)

            # Update the agent capabilities and facts if they were changed
            self._api.agents_update(agent)

    def _cap_driver_iteration(
        self,
        driver: guest.GuestCapDriver,
        payload: models.Payload,
    ) -> None:
        driver.run(self._api, payload)

    def _setup(self):
        # Call registry at start to update capabilities and facts
        self._register_agent()

    def _iteration(self):
        # Last successfully saved payload. Use it to compare with CP payload.
        # Explicitly load the payload every PAYLOAD_UPDATE_RATE iterations
        if (
            self._payload_path
            and self._iteration_number % PAYLOAD_UPDATE_RATE != 0
        ):
            last_payload = models.Payload.load(self._payload_path)
        else:
            last_payload = None

        # Get the payload from the control plane
        try:
            payload = self._api.agents_get_payload(
                self._agent_uuid, last_payload
            )
        except core.AgentNotFound:
            # Auto discovery mechanism
            self._register_agent()
            return

        for driver in self._caps_drivers:
            self._cap_driver_iteration(driver, payload)
