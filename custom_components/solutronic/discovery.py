import aiohttp
import asyncio
import ifaddr
import ipaddress

async def discover_solutronic():
    """Scan local network for Solutronic inverters."""
    network = _get_local_subnet()
    if not network:
        return []

    async with aiohttp.ClientSession() as session:
        tasks = [
            _check_ip(session, str(host))
            for host in network.hosts()
        ]
        results = await asyncio.gather(*tasks)
        return [ip for ip in results if ip]


async def _check_ip(session, ip):
    url = f"http://{ip}:8888/solutronic/"
    try:
        async with session.get(url, timeout=1) as r:
            if r.status == 200:
                return ip
    except:
        return None


def _get_local_subnet():
    """Auto-detect the subnet HA is running on."""
    adapters = ifaddr.get_adapters()
    for adapter in adapters:
        for ip in adapter.ips:
            if isinstance(ip.ip, str) and "." in ip.ip:
                try:
                    return ipaddress.ip_network(f"{ip.ip}/{ip.network_prefix}", strict=False)
                except:
                    pass
    return None