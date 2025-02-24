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
# Use half the number of cores
NPROC=$(shell echo "$(shell nproc)/2 + 1" | bc)

# There is an issue with building busybox on Ubuntu 24.04:
# https://github.com/gramineproject/gramine/tree/master/CI-Examples/busybox#note-on-ubuntu-2404-and-centos-stream-9
# Therefore we use binaries from busybox 1.35.0
BUSYBOX_VERSION="1.35.0"
BUSYBOX_URL="https://www.busybox.net/downloads/binaries/${BUSYBOX_VERSION}-x86_64-linux-musl/busybox"
RAMDISK_DIR="initrd"
RAMDISK_NAME="initrd.img"

# Take Python 3.10 since we don't need the newest features
# in the Seed OS but it takes significant less space.
PYTHON_VERSION="3.10.9"
PYTHON_URL="https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tar.xz"
PYTHON_DIR="$(shell pwd)/Python-${PYTHON_VERSION}"
PYTHON_TARBALL="Python-${PYTHON_VERSION}.tar.xz"
PYTHON_OUTPUT_DIR="${PYTHON_DIR}/output"

# Default target
all: kernel initrd

clean: clean_kernel clean_busybox clean_python clean_initrd

# Kernel part

kernel: download_kernel build_kernel
	cp linux-${KERNEL_VERSION}/arch/x86/boot/bzImage vmlinuz

download_kernel:
ifeq (,$(wildcard "${KERNEL_TARBALL}"))
	rm -f ${KERNEL_TARBALL}
endif
ifeq (,$(wildcard ${KERNEL_DIR}))
	rm -fr ${KERNEL_DIR}
endif
	wget ${KERNEL_URL}
	tar -xf linux-${KERNEL_VERSION}.tar.xz

build_kernel:
	cp kernel/kernel.cfg linux-${KERNEL_VERSION}/.config
	make -j${NPROC} -C linux-${KERNEL_VERSION}

clean_kernel:
	rm -fr ${KERNEL_DIR}
	rm -f ${KERNEL_TARBALL}
	rm -f vmlinuz

# Busybox part

busybox: download_busybox build_busybox

download_busybox: clean_busybox
	wget ${BUSYBOX_URL}

build_busybox:
	chmod +x busybox

clean_busybox:
	rm -f ./busybox

# Python part

python: download_python build_python

download_python: clean_python
	wget ${PYTHON_URL}
	tar -xf ${PYTHON_TARBALL}

build_python:
	rm -fr ${PYTHON_OUTPUT_DIR}
	mkdir ${PYTHON_OUTPUT_DIR}
# Building with static libraries and no shared libraries
# Alternative configure paramters are:
# --disable-shared LDFLAGS="-static" CFLAGS="-static" CPPFLAGS="-static" 
# but resulting binaries take slightly more space.
	cd ${PYTHON_DIR} && \
		./configure \
			LDFLAGS="-static -static-libgcc" \
			CPPFLAGS="-fPIC -static" \
			--disable-shared \
			--prefix=${PYTHON_OUTPUT_DIR} && \
		cp ../python/Setup ${PYTHON_DIR}/Modules/Setup && \
		make install -j${NPROC} ; \
		cd ..

clean_python:
	rm -fr ${PYTHON_DIR}
	rm -f ${PYTHON_TARBALL}

# Initramfs part

initrd: busybox python
	mkdir ${RAMDISK_DIR}
	cd ${RAMDISK_DIR} && \
		mkdir dev etc proc sys tmp lib mnt var bin
	cp init ${RAMDISK_DIR}/init
	chmod +x ${RAMDISK_DIR}/init
	./busybox --install ${RAMDISK_DIR}/bin
	cp -r ${PYTHON_OUTPUT_DIR}/lib/* ${RAMDISK_DIR}/lib/
	cp ${PYTHON_OUTPUT_DIR}/bin/python3 ${RAMDISK_DIR}/bin/
	cd ${RAMDISK_DIR} && \
		find . | cpio -H newc -o | gzip -9 >../${RAMDISK_NAME}

clean_initrd:
	rm -fr ${RAMDISK_DIR}
	rm -f ${RAMDISK_NAME}

.PHONY: kernel clean build_kernel clean_kernel download_kernel \
	    busybox download_busybox build_busybox clean_busybox \
	    python download_python build_python clean_python \
	    clean_initrd initrd all
