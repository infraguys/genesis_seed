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

import functools
import json
import logging
import os
import typing as tp
import uuid as sys_uuid

from exordos_seed.common import constants as c
from exordos_seed.common import exceptions as base_exc
from exordos_seed.common.http import base as http
from exordos_seed.common.http import clients
from exordos_seed.dm import models

LOG = logging.getLogger(__name__)


class AgentAlreadyExists(base_exc.GSException):
    message = "Agent already exists: %(uuid)s"


class AgentNotFound(base_exc.GSException):
    message = "Agent not found: %(uuid)s"


class ResourceAlreadyExists(base_exc.GSException):
    message = "Resource already exists: %(uuid)s"


class ResourceNotFound(base_exc.GSException):
    message = "Resource not found: %(uuid)s"


class BootAPI:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url
        self._agents_client = clients.UniversalAgentsClient(base_url)
        self._encryption_keys_client = clients.NodeEncryptionKeyClient(base_url)

    @property
    def agents(self):
        return self._agents_client

    @property
    def encryption_keys(self):
        return self._encryption_keys_client

    @functools.lru_cache
    def resources(self, kind: str) -> clients.ResourcesClient:
        return clients.ResourcesClient(self._base_url, kind)


class CoreClient:
    def __init__(
        self,
        boot_endpoint: str,
    ) -> None:
        self._boot_endpoint = boot_endpoint
        self._boot_api = BootAPI(boot_endpoint)

    def agents_create(
        self, agent: models.UniversalAgent, **kwargs: tp.Any
    ) -> models.UniversalAgent:
        """Create an instance of Universal agent."""
        try:
            agent = self._boot_api.agents.create(agent)
            LOG.info("Agent registered: %s", agent.uuid)
        except http.HttpConflictError:
            raise AgentAlreadyExists(uuid=agent.uuid)

        return agent

    def agents_update(
        self, agent: models.UniversalAgent, **kwargs: tp.Any
    ) -> models.UniversalAgent:
        """Update an instance of Universal agent."""
        try:
            data = {
                "capabilities": agent.capabilities,
                "facts": agent.facts,
                "name": agent.name,
            }

            agent = self._boot_api.agents.update(agent.uuid, **data)
            LOG.info("Agent updated: %s", agent.uuid)
        except http.HttpNotFoundError:
            raise AgentNotFound(uuid=agent.uuid)

        return agent

    def agents_get_payload(
        self,
        uuid: sys_uuid.UUID,
        payload: models.Payload | None,
        **kwargs: tp.Any,
    ) -> models.Payload:
        """Get payload for of the Universal agent."""
        if payload is None:
            payload = models.Payload.empty()

        try:
            payload = self._boot_api.agents.get_payload(uuid, payload)
        except http.HttpNotFoundError:
            raise AgentNotFound(uuid=uuid)

        return payload

    def resources_create(
        self, resource: models.Resource, **kwargs: tp.Any
    ) -> models.Resource:
        """Create a resource."""
        try:
            resource = self._boot_api.resources(resource.kind).create(resource)
            LOG.info("Resource created: %s", resource.uuid)
        except http.HttpConflictError:
            raise ResourceAlreadyExists(uuid=resource.uuid)

        return resource

    def resources_get(
        self, kind: str, uuid: sys_uuid.UUID, **kwargs: tp.Any
    ) -> models.Resource:
        """Get the resource."""
        try:
            resource = self._boot_api.resources(kind).get(uuid)
        except http.HttpNotFoundError:
            raise ResourceNotFound(uuid=uuid)

        return resource

    def resources_update(
        self, kind: str, uuid: sys_uuid.UUID, **kwargs: tp.Any
    ) -> models.Resource:
        """Update the resource."""

        try:
            if "uuid" in kwargs:
                if str(uuid) != kwargs["uuid"]:
                    raise ValueError("UUID in kwargs does not match the uuid")
                # The positional `uuid` is a UUID object and validated.
                # Remove from kwargs to avoid conflicts when calling update.
                del kwargs["uuid"]
            resource = self._boot_api.resources(kind).update(uuid, **kwargs)
        except http.HttpNotFoundError:
            raise ResourceNotFound(uuid=uuid)

        return resource

    def resources_delete(self, resource: models.Resource, **kwargs: tp.Any) -> None:
        """Delete the resource."""
        try:
            self._boot_api.resources(resource.kind).delete(resource.uuid)
        except http.HttpNotFoundError:
            raise ResourceNotFound(uuid=resource.uuid)

    def private_keys_refresh(
        self,
        uuid: sys_uuid.UUID,
    ) -> str:
        """Refresh the private key."""
        try:
            key = self._boot_api.encryption_keys.refresh_secret(uuid)
        except http.HttpNotFoundError:
            raise AgentNotFound(uuid=uuid)

        return key


class AutonomousCoreClient:
    """Core client for autonomous mode without orchestrator.

    This client reads configuration from local files instead of making
    HTTP requests to the orchestrator. It's used when the system runs
    in autonomous mode (autonomous=1 in kernel cmdline).

    Expected data structure in work_dir (default /autonomous/):
    - update.json
      Contains: {"target_image": "...", "original_image": "..."}
    - private_key (optional)
      Contains encryption key for the agent
    """

    def __init__(
        self,
        work_dir: str = c.AUTONOMOUS_WORK_DIR,
    ) -> None:
        self._work_dir = work_dir
        self._update_json_path = os.path.join(work_dir, "update.json")
        self._private_key_path = os.path.join(work_dir, "private_key")

    def _load_update_data(self) -> dict:
        """Load update data from JSON file on mounted disk."""
        try:
            with open(self._update_json_path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            LOG.warning("Update data not found at %s", self._update_json_path)
            return {}
        except json.JSONDecodeError as e:
            LOG.error("Failed to parse update.json: %s", e)
            return {}

    def agents_create(
        self, agent: models.UniversalAgent, **kwargs: tp.Any
    ) -> models.UniversalAgent:
        """Create an instance of Universal agent (no-op in autonomous mode)."""
        LOG.info("Agent registration skipped in autonomous mode: %s", agent.uuid)
        return agent

    def agents_update(
        self, agent: models.UniversalAgent, **kwargs: tp.Any
    ) -> models.UniversalAgent:
        """Update an instance of Universal agent (no-op in autonomous mode)."""
        LOG.info("Agent update skipped in autonomous mode: %s", agent.uuid)
        return agent

    def agents_get_payload(
        self,
        uuid: sys_uuid.UUID,
        payload: models.Payload | None,
        **kwargs: tp.Any,
    ) -> models.Payload:
        """Get payload from local update.json file."""
        update_data = self._load_update_data()

        if not update_data:
            LOG.warning("No update data available, returning empty payload")
            return models.Payload.empty()

        target_image = update_data.get("target_image", "")

        # Build guest machine resource from update data
        guest_machine = models.GuestMachine(
            uuid=uuid,
            image=target_image,
            boot="network",
            status=c.MachineStatus.NEW.value,
        )

        # Build capabilities payload
        capabilities = {
            "guest_machine": {
                "resources": [
                    {
                        "uuid": str(uuid),
                        "kind": "guest_machine",
                        "status": c.MachineStatus.NEW.value,
                        "value": guest_machine.dump_to_simple_view(),
                    }
                ]
            }
        }

        return models.Payload(
            hash="",
            version=1,
            capabilities=capabilities,
            facts={},
        )

    def resources_create(
        self, resource: models.Resource, **kwargs: tp.Any
    ) -> models.Resource:
        """Create a resource (no-op in autonomous mode)."""
        LOG.info("Resource creation logged in autonomous mode: %s", resource.uuid)
        return resource

    def resources_get(
        self, kind: str, uuid: sys_uuid.UUID, **kwargs: tp.Any
    ) -> models.Resource:
        """Get the resource (returns empty resource in autonomous mode)."""
        LOG.warning("Resource get not supported in autonomous mode: %s", uuid)
        raise ResourceNotFound(uuid=uuid)

    def resources_update(
        self, kind: str, uuid: sys_uuid.UUID, **kwargs: tp.Any
    ) -> models.Resource:
        """Update the resource (no-op in autonomous mode)."""
        LOG.info("Resource update logged in autonomous mode: %s (%s)", uuid, kind)
        # Return a minimal resource
        return models.Resource(
            uuid=uuid,
            kind=kind,
            value=kwargs.get("value", {}),
            status=kwargs.get("status", "ACTIVE"),
        )

    def resources_delete(self, resource: models.Resource, **kwargs: tp.Any) -> None:
        """Delete the resource (no-op in autonomous mode)."""
        LOG.info("Resource deletion logged in autonomous mode: %s", resource.uuid)

    def private_keys_refresh(
        self,
        uuid: sys_uuid.UUID,
    ) -> str:
        """Get private key from local file or return empty."""
        try:
            with open(self._private_key_path, "r") as f:
                key = f.read().strip()
                LOG.info("Private key loaded from %s", self._private_key_path)
                return key
        except FileNotFoundError:
            LOG.warning(
                "No private key found at %s, returning empty key",
                self._private_key_path,
            )
            return ""
