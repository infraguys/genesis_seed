# Copyright 2025 Genesis Corporation
#
# All Rights Reserved.
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

KERNEL_VERSION="6.13.4"
KERNEL_URL="https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-${KERNEL_VERSION}.tar.xz"
KERNEL_DIR="linux-${KERNEL_VERSION}"
KERNEL_TARBALL="linux-${KERNEL_VERSION}.tar.xz"

# Default target
all: kernel

kernel: download_kernel build_kernel

clean: clean_kernel

download_kernel:
ifeq (,$(wildcard "${KERNEL_TARBALL}"))
	rm -f ${KERNEL_TARBALL}
endif
ifeq (,$(wildcard ${KERNEL_DIR}))
	rm -fr ${KERNEL_DIR}
endif
	wget ${KERNEL_URL}
	tar -xf linux-${KERNEL_VERSION}.tar.xz

# Build Linux Kernel
build_kernel:
	cp kernel/kernel.cfg linux-${KERNEL_VERSION}/.config
	make -j8 -C linux-${KERNEL_VERSION}

clean_kernel:
	rm -fr ${KERNEL_DIR}
	rm -f ${KERNEL_TARBALL}


.PHONY: kernel clean build_kernel clean_kernel download_kernel all