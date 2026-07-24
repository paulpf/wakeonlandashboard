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


def _arping(network: str) -> list[dict]:
    """Run arp-scan or nmap ARP ping and parse results."""
    hosts: list[dict] = []

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
                    hosts.append({"ip": ip, "mac": mac, "hostname": "", "vendor": vendor})
                except ValueError:
                    pass
        if hosts:
            return hosts
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass

    # fallback: read /proc/net/arp
    try:
        with open("/proc/net/arp") as f:
            lines = f.readlines()[1:]  # skip header
        for line in lines:
            parts = line.split()
            if len(parts) >= 4:
                ip = parts[0]
                mac = parts[3].upper().replace("-", ":")
                if mac not in ("00:00:00:00:00:00", ""):
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
        result = subprocess.run(
            ["ping", "-c", "1", "-W", str(int(timeout * 1000)), ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout + 1,
        )
        return result.returncode == 0
    except Exception:
        return False


def scan_network(network: str = "192.168.1.0/24") -> list[dict]:
    """ARP scan the network and return list of discovered hosts."""
    hosts = _arping(network)

    if not hosts:
        # ultra-fallback: ping sweep
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
            hosts.append({"ip": ip, "mac": "", "hostname": "", "vendor": ""})

    # resolve hostnames in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as ex:
        futs = {ex.submit(_resolve_hostname, h["ip"]): i for i, h in enumerate(hosts)}
        for fut in concurrent.futures.as_completed(futs):
            hosts[futs[fut]]["hostname"] = fut.result()

    return hosts


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
