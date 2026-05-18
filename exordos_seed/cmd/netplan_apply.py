#!/usr/bin/env python3

#    Copyright 2025 Genesis Corporation
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

import json
import logging
import os
import re
import subprocess
import sys
import typing as tp

from exordos_seed.common import constants as c

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)


def run_cmd(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run shell command and return result."""
    LOG.debug("Running: %s", " ".join(cmd))
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _parse_ip_link_show(output: str) -> list[dict[str, str]]:
    """Parse text output of 'ip link show' into interface list.

    Busybox ip doesn't support -json, so we parse text format:
    2: eth0: <BROADCAST,MULTICAST> mtu 1500 ...
        link/ether 52:54:00:f5:c5:a7 brd ...
    """
    interfaces = []
    current = None

    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue

        # Match interface header line: "2: eth0: <BROADCAST...>"
        m = re.match(r"^\d+:\s+(\S+):\s+<", line)
        if m:
            if current:
                interfaces.append(current)
            current = {"ifname": m.group(1), "address": ""}
            continue

        # Match link/ether line: "link/ether 52:54:00:f5:c5:a7 brd..."
        if current and "link/ether" in line:
            m = re.search(r"link/ether\s+([0-9a-fA-F:]{17})", line)
            if m:
                current["address"] = m.group(1)

    if current:
        interfaces.append(current)

    return interfaces


def interface_exists(iface: str) -> bool:
    """Check if network interface exists."""
    try:
        result = run_cmd(["ip", "link", "show", iface], check=False)
        return result.returncode == 0
    except Exception:
        return False


def find_interface_by_mac(macaddress: str) -> str | None:
    """Find interface name by MAC address.

    Returns interface name or None if not found.
    MAC address comparison is case-insensitive.
    """
    target_mac = macaddress.lower()
    try:
        result = run_cmd(["ip", "link", "show"], check=False)
        if result.returncode != 0:
            return None
        interfaces = _parse_ip_link_show(result.stdout)
        LOG.debug("Found interfaces: %s", interfaces)
        for iface in interfaces:
            addr = iface.get("address", "").lower()
            if addr == target_mac:
                return iface.get("ifname")
    except Exception as e:
        LOG.error("Error finding interface by MAC: %s", e)
    return None


def set_interface_up(iface: str) -> bool:
    """Bring interface up."""
    try:
        run_cmd(["ip", "link", "set", iface, "up"])
        LOG.info("Interface %s brought up", iface)
        return True
    except subprocess.CalledProcessError as e:
        LOG.error("Failed to bring up %s: %s", iface, e.stderr)
        return False


def flush_interface_addresses(iface: str) -> None:
    """Remove all IP addresses from interface."""
    try:
        run_cmd(["ip", "addr", "flush", "dev", iface])
        LOG.info("Flushed addresses on %s", iface)
    except subprocess.CalledProcessError as e:
        LOG.warning("Failed to flush addresses on %s: %s", iface, e.stderr)


def add_address(iface: str, address: str) -> bool:
    """Add IP address to interface."""
    try:
        run_cmd(["ip", "addr", "add", address, "dev", iface])
        LOG.info("Added address %s to %s", address, iface)
        return True
    except subprocess.CalledProcessError as e:
        LOG.error("Failed to add address %s to %s: %s", address, iface, e.stderr)
        return False


def set_default_gateway(gateway: str, iface: str | None = None) -> bool:
    """Set default gateway."""
    cmd = ["ip", "route", "add", "default", "via", gateway]
    if iface:
        cmd.extend(["dev", iface])
    try:
        # Try to add, ignore if already exists
        result = run_cmd(cmd, check=False)
        if result.returncode == 0:
            LOG.info("Added default gateway via %s", gateway)
        return True
    except subprocess.CalledProcessError as e:
        LOG.error("Failed to add gateway %s: %s", gateway, e.stderr)
        return False


def add_route(
    destination: str, gateway: str | None = None, iface: str | None = None
) -> bool:
    """Add static route."""
    cmd = ["ip", "route", "add", destination]
    if gateway:
        cmd.extend(["via", gateway])
    if iface:
        cmd.extend(["dev", iface])
    try:
        result = run_cmd(cmd, check=False)
        if result.returncode == 0:
            LOG.info("Added route to %s", destination)
        return True
    except subprocess.CalledProcessError:
        return False


def configure_dns(
    nameservers: list[str], search_domains: list[str] | None = None
) -> None:
    """Configure DNS servers in /etc/resolv.conf."""
    try:
        with open("/etc/resolv.conf", "w") as f:
            if search_domains:
                for domain in search_domains:
                    f.write(f"search {domain}\n")
            for ns in nameservers:
                f.write(f"nameserver {ns}\n")
        LOG.info("Configured DNS servers: %s", nameservers)
    except IOError as e:
        LOG.error("Failed to configure DNS: %s", e)


def apply_ethernet_config(iface_name: str, config: dict[str, tp.Any]) -> bool:
    """Apply ethernet interface configuration.

    iface_name is the logical name from netplan config (e.g., 'if-eth0').
    If 'match' directive is present, resolve to physical interface by MAC.
    """
    # Check if match directive is present
    match_config = config.get("match", {})
    target_mac = match_config.get("macaddress")

    if target_mac:
        # Resolve interface by MAC address
        resolved_iface = find_interface_by_mac(target_mac)
        if not resolved_iface:
            LOG.error("No interface found with MAC %s for %s", target_mac, iface_name)
            return False
        LOG.info("Resolved %s -> %s (MAC: %s)", iface_name, resolved_iface, target_mac)
        iface = resolved_iface
    else:
        # Use interface name directly
        iface = iface_name

    if not interface_exists(iface):
        LOG.warning("Interface %s does not exist, skipping", iface)
        return False

    # Bring interface up first
    set_interface_up(iface)

    # Check if DHCP is enabled
    dhcp4 = config.get("dhcp4", False)
    dhcp6 = config.get("dhcp6", False)

    if dhcp4 or dhcp6:
        # TODO(akremenetsky): Initiate a DHCP client
        # For DHCP, just ensure interface is up
        # udhcpc or dhclient should be started separately if needed
        LOG.info("DHCP enabled on %s, interface is up", iface)
        return True

    # Flush existing addresses for static config
    flush_interface_addresses(iface)

    # Apply static addresses
    addresses = config.get("addresses", [])
    if isinstance(addresses, str):
        addresses = [addresses]

    for addr in addresses:
        add_address(iface, addr)

    # Apply routes
    routes = config.get("routes", [])
    for route in routes:
        to_addr = route.get("to")
        via = route.get("via")
        if to_addr:
            add_route(to_addr, via, iface)

    # Set gateway if specified (legacy format)
    gateway4 = config.get("gateway4")
    if gateway4:
        set_default_gateway(gateway4, iface)

    gateway6 = config.get("gateway6")
    if gateway6:
        set_default_gateway(gateway6, iface)

    # Configure DNS nameservers for this interface
    nameservers = config.get("nameservers", {})
    if nameservers:
        addresses = nameservers.get("addresses", [])
        search = nameservers.get("search", [])
        if addresses:
            configure_dns(addresses, search)

    return True


def load_netplan_json(filepath: str) -> dict[str, tp.Any]:
    """Load netplan configuration from JSON file."""
    with open(filepath, "r") as f:
        return json.load(f)


def apply_netplan_config(config: dict[str, tp.Any]) -> bool:
    """Apply netplan configuration."""
    network = config.get("network", {})

    if not network:
        LOG.warning("No network configuration found")
        return False

    version = network.get("version", 2)
    LOG.info("Applying netplan config version %s", version)

    # Process ethernet interfaces only (bridges, bonds, vlans not supported)
    ethernets = network.get("ethernets", {})
    for iface, iface_config in ethernets.items():
        LOG.info("Configuring ethernet interface: %s", iface)
        apply_ethernet_config(iface, iface_config)

    # Configure global DNS if present
    nameservers = network.get("nameservers", {})
    if nameservers:
        addresses = nameservers.get("addresses", [])
        search = nameservers.get("search", [])
        if addresses:
            configure_dns(addresses, search)

    return True


def apply_netplan_from_disk(netplan_dir: str = c.AUTONOMOUS_NETPLAN_DIR) -> bool:
    """Apply all netplan JSON configurations from disk."""
    if not os.path.isdir(netplan_dir):
        LOG.error("Netplan directory not found: %s", netplan_dir)
        return False

    success = False
    for filename in sorted(os.listdir(netplan_dir)):
        if filename.endswith(".json"):
            filepath = os.path.join(netplan_dir, filename)
            LOG.info("Loading netplan config from %s", filepath)
            config = load_netplan_json(filepath)
            if config:
                if apply_netplan_config(config):
                    success = True

    return success


def main() -> int:
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    LOG.info("Applying netplan configuration from disk")

    if apply_netplan_from_disk():
        LOG.info("Netplan configuration applied successfully")
        return 0
    else:
        LOG.error("Failed to apply netplan configuration")
        return 1


if __name__ == "__main__":
    sys.exit(main())
