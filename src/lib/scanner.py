import subprocess
import socket
import ipaddress
import threading
import concurrent.futures
from typing import Optional

# vendor prefix lookup (shortened OUI table — expand as needed or use manuf package)
_OUI: dict[str, str] = {}

try:
    # optional: if scapy is available use its manuf database
    from scapy.data import ETHER_TYPES  # noqa — just a reachability check
    from scapy.all import conf as _scapy_conf
    _SCAPY = True
except Exception:
    _SCAPY = False


def _is_valid_unicast(ip: str) -> bool:
    """Check if IP is a valid unicast address (not broadcast, multicast, or reserved)."""
    try:
        addr = ipaddress.ip_address(ip)
        # Exclude multicast (224.0.0.0 - 239.255.255.255)
        if addr.is_multicast:
            return False
        # Exclude broadcast (255.255.255.255)
        if ip == "255.255.255.255":
            return False
        # Exclude network address (x.x.x.0) and subnet broadcast (x.x.x.255)
        octets = ip.split(".")
        if len(octets) == 4:
            last_octet = octets[3]
            if last_octet in ("0", "255"):
                return False
        return True
    except ValueError:
        return False


def _arping(network: str) -> list[dict]:
    """Run arp-scan, arp -a, or read /proc/net/arp to get MAC addresses."""
    hosts: list[dict] = []
    import sys

    # try arp-scan first (Linux / LXC)
    try:
        out = subprocess.check_output(
            ["arp-scan", "--localnet", "--quiet", "--ignoredups"],
            stderr=subprocess.DEVNULL,
            timeout=30,
        ).decode(errors="replace")
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                ip = parts[0].strip()
                mac = parts[1].strip().upper()
                vendor = parts[2].strip() if len(parts) > 2 else ""
                try:
                    ipaddress.ip_address(ip)
                    if _is_valid_unicast(ip):  # Filter out broadcast/multicast
                        hosts.append({"ip": ip, "mac": mac, "hostname": "", "vendor": vendor})
                except ValueError:
                    pass
        if hosts:
            return hosts
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass

    # Windows: try arp -a
    if sys.platform == "win32":
        try:
            out = subprocess.check_output(["arp", "-a"], stderr=subprocess.DEVNULL).decode(errors="replace")
            for line in out.splitlines():
                parts = line.split()
                # Windows arp format: IP  MAC  Type
                if len(parts) >= 2:
                    try:
                        ip = parts[0].strip()
                        ipaddress.ip_address(ip)
                        mac = parts[1].strip().upper().replace("-", ":")
                        if mac not in ("00:00:00:00:00:00", "") and len(mac) == 17 and _is_valid_unicast(ip):  # valid MAC and unicast
                            hosts.append({"ip": ip, "mac": mac, "hostname": "", "vendor": ""})
                    except (ValueError, IndexError):
                        pass
            if hosts:
                return hosts
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass

    # fallback: read /proc/net/arp (Linux)
    try:
        with open("/proc/net/arp") as f:
            lines = f.readlines()[1:]  # skip header
        for line in lines:
            parts = line.split()
            if len(parts) >= 4:
                ip = parts[0]
                mac = parts[3].upper().replace("-", ":")
                if mac not in ("00:00:00:00:00:00", "") and _is_valid_unicast(ip):
                    hosts.append({"ip": ip, "mac": mac, "hostname": "", "vendor": ""})
        if hosts:
            return hosts
    except (FileNotFoundError, PermissionError):
        pass

    return hosts


def _resolve_hostname(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ""


def _ping(ip: str, timeout: float = 0.5) -> bool:
    try:
        import sys
        if sys.platform == "win32":
            # Windows: ping -n 1 -w <milliseconds>
            result = subprocess.run(
                ["ping", "-n", "1", "-w", str(int(timeout * 1000)), ip],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout + 1,
            )
        else:
            # Linux/Mac: ping -c 1 -W <milliseconds>
            result = subprocess.run(
                ["ping", "-c", "1", "-W", str(int(timeout * 1000)), ip],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout + 1,
            )
        return result.returncode == 0
    except Exception:
        return False


def _scan_single(network: str) -> list[dict]:
    """Scan a single CIDR network and return discovered hosts (no hostname resolution)."""
    hosts = _arping(network)

    if not hosts:
        try:
            net = ipaddress.ip_network(network, strict=False)
            ips = [str(h) for h in net.hosts()]
        except ValueError:
            ips = []

        alive: list[str] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=64) as ex:
            futs = {ex.submit(_ping, ip): ip for ip in ips}
            for fut in concurrent.futures.as_completed(futs):
                if fut.result():
                    alive.append(futs[fut])

        for ip in sorted(alive, key=lambda x: ipaddress.ip_address(x)):
            if _is_valid_unicast(ip):  # Filter out broadcast/multicast
                hosts.append({"ip": ip, "mac": "", "hostname": "", "vendor": ""})

    return hosts


def scan_network(network = "192.168.1.0/24") -> list[dict]:
    """Scan one or multiple networks (str or list of CIDR strings).

    Returns deduplicated list of hosts with resolved hostnames.
    """
    networks = [network] if isinstance(network, str) else list(network)

    seen_ips: set[str] = set()
    merged: list[dict] = []

    for net in networks:
        net = net.strip()
        if not net:
            continue
        for host in _scan_single(net):
            if host["ip"] not in seen_ips:
                seen_ips.add(host["ip"])
                merged.append(host)

    # resolve hostnames in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as ex:
        futs = {ex.submit(_resolve_hostname, h["ip"]): i for i, h in enumerate(merged)}
        for fut in concurrent.futures.as_completed(futs):
            merged[futs[fut]]["hostname"] = fut.result()

    return merged


KNOWN_PORTS = [22, 80, 443, 3389, 5900, 8006, 8080, 8443, 9090]


def check_port(ip: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False


def check_device_online(ip: str, port: int = None, timeout: float = 1.5) -> bool:
    if not ip:
        return False
    if port:
        return check_port(ip, port, timeout)
    return _ping(ip, timeout)


def scan_ports_for_ip(ip: str, ports: list[int] = None, timeout: float = 0.8) -> list[int]:
    """Return list of open ports for a single IP."""
    if not ip:
        return []
    targets = ports if ports is not None else KNOWN_PORTS
    open_ports: list[int] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(targets)) as ex:
        futs = {ex.submit(check_port, ip, p, timeout): p for p in targets}
        for fut in concurrent.futures.as_completed(futs):
            if fut.result():
                open_ports.append(futs[fut])
    return sorted(open_ports)


def scan_ports_bulk(ips: list[str], ports: list[int] = None,
                    timeout: float = 0.8) -> dict[str, list[int]]:
    """Scan ports for multiple IPs in parallel. Returns {ip: [open_port, ...]}."""
    results: dict[str, list[int]] = {}
    if not ips:
        return results
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as ex:
        futs = {ex.submit(scan_ports_for_ip, ip, ports, timeout): ip for ip in ips}
        for fut in concurrent.futures.as_completed(futs):
            ip = futs[fut]
            results[ip] = fut.result()
    return results
