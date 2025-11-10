
import subprocess
import re
from enum import Enum
# ----------- Detect the single connected client -----------
def get_single_client_ip():
    """Return the IP of the single client connected to wlan0."""
    # Get MAC addresses using iw
    try:
        iw_output = subprocess.check_output(["iw", "dev", "wlan0", "station", "dump"], text=True)
        macs = re.findall(r"Station ([0-9a-f:]{17})", iw_output)
        if not macs:
            return None
        mac = macs[0]  # pick the first (and only) client
    except subprocess.CalledProcessError:
        return None

    # Map MAC to IP using arp
    try:
        arp_output = subprocess.check_output(["arp", "-n"], text=True)
        ip_map = {}
        for line in arp_output.splitlines():
            parts = line.split()
            if len(parts) >= 3:
                ip_addr, _, mac_addr = parts[0], parts[1], parts[2]
                ip_map[mac_addr.lower()] = ip_addr
        return ip_map.get(mac.lower())
    except subprocess.CalledProcessError:
        return None
    

class States(Enum):
    Default = 0,
    SettingUpHW = 1,
    ConnectingHost = 2,
    ConnectingBroker = 3,
    Idelling =4,
    Preparing = 5,
    Running = 6,
    Finishing = 7,

