import logging

import aiohttp

from clusterspider.core.module_base import BaseModule, ModuleResult, TargetType
from clusterspider.core.rate_limiter import rate_limiters
from clusterspider.config import settings

logger = logging.getLogger(__name__)

IPINFO_URL = "https://ipinfo.io/{ip}/json"
FALLBACK_URL = "http://ip-api.com/json/{ip}"


class IpGeolocationModule(BaseModule):
    @property
    def name(self) -> str:
        return "ip_geolocation"

    @property
    def description(self) -> str:
        return "Query IP geolocation and ASN information"

    @property
    def supported_targets(self) -> list[TargetType]:
        return [TargetType.IP]

    @property
    def timeout(self) -> float:
        return 20.0

    async def execute(self, target: str, target_type: TargetType) -> ModuleResult:
        await rate_limiters.acquire("ipinfo")

        try:
            if settings.ipinfo_token:
                data = await self._query_ipinfo(target)
            else:
                data = await self._query_fallback(target)
        except aiohttp.ClientError as e:
            return ModuleResult(
                module_name=self.name,
                target=target,
                target_type=target_type.value,
                success=False,
                error=f"HTTP error: {e}",
            )

        if not data:
            return ModuleResult(
                module_name=self.name,
                target=target,
                target_type=target_type.value,
                success=False,
                error="No geolocation data returned",
            )

        entities = []
        org_name = data.get("org", "")
        asn = data.get("asn", "")

        if org_name:
            entities.append({
                "type": "organization",
                "value": org_name,
                "asn": asn,
                "source": "ip_geolocation",
            })

        return ModuleResult(
            module_name=self.name,
            target=target,
            target_type=target_type.value,
            success=True,
            data=data,
            entities=entities,
        )

    async def _query_ipinfo(self, ip: str) -> dict:
        url = IPINFO_URL.format(ip=ip)
        headers = {"Authorization": f"Bearer {settings.ipinfo_token}"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return {}
                data = await resp.json()
                org_raw = data.get("org", "")
                parts = org_raw.split(" ", 1)
                asn = parts[0] if parts else ""
                org_name = parts[1] if len(parts) > 1 else org_raw

                loc = data.get("loc", "")
                lat, lon = (loc.split(",") + ["", ""])[:2]

                return {
                    "ip": ip,
                    "country": data.get("country", ""),
                    "region": data.get("region", ""),
                    "city": data.get("city", ""),
                    "lat": float(lat) if lat else None,
                    "lon": float(lon) if lon else None,
                    "org": org_name,
                    "asn": asn,
                    "hostname": data.get("hostname", ""),
                }

    async def _query_fallback(self, ip: str) -> dict:
        url = FALLBACK_URL.format(ip=ip)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return {}
                data = await resp.json()
                if data.get("status") != "success":
                    return {}
                return {
                    "ip": ip,
                    "country": data.get("countryCode", ""),
                    "region": data.get("regionName", ""),
                    "city": data.get("city", ""),
                    "lat": data.get("lat"),
                    "lon": data.get("lon"),
                    "org": data.get("org", ""),
                    "asn": data.get("as", "").split(" ")[0],
                    "isp": data.get("isp", ""),
                }
