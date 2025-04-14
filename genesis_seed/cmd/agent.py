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

from genesis_seed.common import clients
from genesis_seed.common import utils
from genesis_seed.common import constants as c
from genesis_seed.services.agent import SeedOSAgentService


def main():
    log = logging.getLogger(__name__)

    # Load configuration from the Kernel command line
    cfg = utils.cfg_from_cmdline()

    if c.GC_CMDLINE_KEY_BASE_URL not in cfg:
        ValueError(
            f"Missing {c.GC_CMDLINE_KEY_BASE_URL} parameter in kernel command line"
        )

    log.warning("GC endpoint: %s", cfg[c.GC_CMDLINE_KEY_BASE_URL])
    api = clients.OrchAPI(cfg[c.GC_CMDLINE_KEY_BASE_URL])

    service = SeedOSAgentService(orch_api=api, iter_min_period=3)

    service.start()

    log.info("Bye!!!")


if __name__ == "__main__":
    main()
