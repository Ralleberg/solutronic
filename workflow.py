import socket
import requests

def find_solutronic_devices(timeout=2):
    """Scan local network for devices with 'solutronic' in the response."""
    devices = []
    ip_base = "192.168.68."
    
    for i in range(1, 255):  # Scanner hele subnettet
        ip = f"{ip_base}{i}"
        try:
            response = requests.get(f"http://{ip}", timeout=timeout)
            if "solutronic" in response.text.lower():
                devices.append(ip)
        except (requests.ConnectionError, requests.Timeout):
            continue
    
    return devices
