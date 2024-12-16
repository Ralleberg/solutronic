import socket
import ipaddress
import requests


def get_local_subnet():
    """Find the local subnet based on the host's IP address."""
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        # Assume a subnet mask of 255.255.255.0 (CIDR /24)
        ip_network = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
        return ip_network
    except Exception as e:
        print(f"Failed to determine local subnet: {e}")
        return None


def find_solutronic_devices(timeout=2):
    """Scan the local subnet for Solutronic devices."""
    devices = []

    # Get the local subnet
    subnet = get_local_subnet()
    if not subnet:
        print("Could not determine local subnet.")
        return devices

    # Scan each IP in the subnet
    for ip in subnet.hosts():
        try:
            response = requests.get(f"http://{ip}", timeout=timeout)
            if "solutronic" in response.text.lower():
                devices.append(str(ip))
        except (requests.ConnectionError, requests.Timeout):
            continue

    return devices
