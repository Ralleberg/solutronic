import os
import requests
import yaml
from zeroconf import Zeroconf, ServiceBrowser, ServiceInfo

DEFAULT_HOST = "192.168.68.199"
DOMAIN = "solutronic"
CONFIG_PATH = "/config/configuration.yaml"  # Tilpas sti til Home Assistant

class SolutronicDiscovery:
    """Class to handle Solutronic device discovery."""

    def __init__(self):
        self.zeroconf = Zeroconf()
        self.solutronic_ip = None

    def discover_device(self):
        """Discover Solutronic devices on the network using mDNS."""
        print("Scanning for Solutronic devices on the network...")
        browser = ServiceBrowser(self.zeroconf, "_http._tcp.local.", self)
        input("Press Enter to stop scanning...")  # Giver tid til scanning
        self.zeroconf.close()

    def add_service(self, zeroconf, type, name):
        """Handle service discovery."""
        info = zeroconf.get_service_info(type, name)
        if info and "solutronic" in name.lower():
            self.solutronic_ip = info.parsed_addresses()[0]
            print(f"Found Solutronic device: {self.solutronic_ip}")

    def get_device_ip(self):
        """Return the discovered Solutronic device IP."""
        return self.solutronic_ip or DEFAULT_HOST


def fetch_test_data(host):
    """Fetch data from the Solutronic device to validate connection."""
    url = f"http://{host}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        print(f"Successfully connected to Solutronic device at {host}")
        return True
    except requests.RequestException as e:
        print(f"Failed to connect to Solutronic device: {e}")
        return False


def update_configuration_yaml(host):
    """Add Solutronic configuration to configuration.yaml."""
    if not os.path.exists(CONFIG_PATH):
        print(f"Error: configuration.yaml not found at {CONFIG_PATH}")
        return False

    with open(CONFIG_PATH, "r") as file:
        try:
            config = yaml.safe_load(file) or {}
        except yaml.YAMLError as e:
            print(f"Error reading YAML file: {e}")
            return False

    # Check if sensor configuration exists
    sensors = config.get("sensor", [])
    if not isinstance(sensors, list):
        sensors = [sensors]

    # Add Solutronic configuration
    solutronic_config = {"platform": DOMAIN, "host": host}
    if solutronic_config not in sensors:
        sensors.append(solutronic_config)
        config["sensor"] = sensors

        # Write updated configuration back
        with open(CONFIG_PATH, "w") as file:
            yaml.safe_dump(config, file)
        print(f"Updated configuration.yaml with Solutronic integration.")
        return True
    else:
        print("Solutronic integration already exists in configuration.yaml.")
        return False


def main():
    """Main workflow to set up Solutronic integration."""
    print("Welcome to the Solutronic integration setup for Home Assistant!")
    discovery = SolutronicDiscovery()

    # Step 1: Discover device on network
    discovery.discover_device()
    host = discovery.get_device_ip()

    # Step 2: Validate connection
    if not fetch_test_data(host):
        print("Falling back to default IP address...")
        host = DEFAULT_HOST
        if not fetch_test_data(host):
            print("Could not connect to any Solutronic device. Exiting.")
            return

    # Step 3: Update configuration.yaml
    if update_configuration_yaml(host):
        print("Setup completed! Please restart Home Assistant to activate the integration.")
    else:
        print("Setup failed. Please check your configuration.yaml manually.")


if __name__ == "__main__":
    main()