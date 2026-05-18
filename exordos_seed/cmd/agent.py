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

from exordos_seed.common import constants as c
from exordos_seed.common import utils
from exordos_seed.common.orch import core
from exordos_seed.services.agent import SeedOSAgentService


def _is_autonomous_mode(cfg: dict) -> bool:
    """Check if running in autonomous mode from kernel cmdline config."""
    # Check using the parsed config (with prefix filter)
    if c.AUTONOMOUS_CMDLINE_KEY in cfg:
        return True

    # Also check raw cmdline without prefix filter
    raw_cfg = utils.cfg_from_cmdline(prefix=None)
    autonomous_value = raw_cfg.get(c.AUTONOMOUS_CMDLINE_KEY, "")
    return autonomous_value == "1" or autonomous_value is True


def main():
    log = logging.getLogger(__name__)

    # Load configuration from the Kernel command line
    cfg = utils.cfg_from_cmdline()

    # Check for autonomous mode
    is_autonomous = _is_autonomous_mode(cfg)

    if is_autonomous:
        log.warning("Running in AUTONOMOUS mode")
        core_client = core.AutonomousCoreClient()
    else:
        # Standard mode requires boot API endpoint
        if c.GC_CMDLINE_KEY_BOOT_API not in cfg:
            raise ValueError(
                f"Missing {c.GC_CMDLINE_KEY_BOOT_API} parameter in kernel command line. "
                f"For autonomous mode, add 'autonomous=1' to kernel cmdline."
            )

        log.warning("GC Boot endpoint: %s", cfg[c.GC_CMDLINE_KEY_BOOT_API])
        core_client = core.CoreClient(
            boot_endpoint=cfg[c.GC_CMDLINE_KEY_BOOT_API],
        )

    service = SeedOSAgentService(core_client=core_client, iter_min_period=3)

    service.start()

    log.info("Bye!!!")


if __name__ == "__main__":
    main()
