import socket
import struct


def send_magic_packet(mac: str, broadcast: str = "255.255.255.255", port: int = 9) -> None:
    """Send a Wake-on-LAN magic packet for the given MAC address."""
    mac = mac.upper().replace(":", "").replace("-", "").replace(".", "")
    if len(mac) != 12:
        raise ValueError(f"Invalid MAC address: {mac}")

    # Build magic packet: 6x 0xFF + 16x MAC
    raw = bytes.fromhex("FF" * 6 + mac * 16)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.connect_ex((broadcast, port))
        sock.send(raw)
