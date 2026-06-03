import logging

import aiohttp

from clusterspider.core.module_base import BaseModule, ModuleResult, TargetType
from clusterspider.core.rate_limiter import rate_limiters
from clusterspider.config import settings

logger = logging.getLogger(__name__)

HIBP_API_URL = "https://haveibeenpwned.com/api/v3"


class LeakCheckModule(BaseModule):
    @property
    def name(self) -> str:
        return "leak_check"

    @property
    def description(self) -> str:
        return "Check email addresses against breach databases (HIBP-compatible API)"

    @property
    def supported_targets(self) -> list[TargetType]:
        return [TargetType.EMAIL, TargetType.DOMAIN]

    @property
    def timeout(self) -> float:
        return 30.0

    async def execute(self, target: str, target_type: TargetType) -> ModuleResult:
        if not settings.hibp_api_key:
            return ModuleResult(
                module_name=self.name,
                target=target,
                target_type=target_type.value,
                success=False,
                error="HIBP API key not configured",
            )

        await rate_limiters.acquire("hibp")

        try:
            if target_type == TargetType.EMAIL:
                breaches = await self._check_email(target)
            else:
                breaches = await self._check_domain(target)
        except aiohttp.ClientError as e:
            return ModuleResult(
                module_name=self.name,
                target=target,
                target_type=target_type.value,
                success=False,
                error=f"API error: {e}",
            )

        entities = []
        for breach in breaches:
            entities.append({
                "type": "leak",
                "value": breach.get("Name", ""),
                "breach_name": breach.get("Name", ""),
                "breach_date": breach.get("BreachDate", ""),
                "data_classes": breach.get("DataClasses", []),
                "source": "hibp",
            })

        return ModuleResult(
            module_name=self.name,
            target=target,
            target_type=target_type.value,
            success=True,
            data={"breach_count": len(breaches), "breaches": breaches},
            entities=entities,
        )

    async def _check_email(self, email: str) -> list[dict]:
        url = f"{HIBP_API_URL}/breachedaccount/{email}"
        return await self._api_request(url, params={"truncateResponse": "false"})

    async def _check_domain(self, domain: str) -> list[dict]:
        url = f"{HIBP_API_URL}/breaches"
        breaches = await self._api_request(url)
        return [b for b in breaches if domain.lower() in b.get("Domain", "").lower()]

    async def _api_request(self, url: str, params: dict | None = None) -> list[dict]:
        headers = {
            "hibp-api-key": settings.hibp_api_key,
            "user-agent": "ClusterSpider-OSINT",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=headers, params=params,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status == 404:
                    return []
                if resp.status == 429:
                    logger.warning("HIBP rate limit hit, backing off")
                    return []
                if resp.status != 200:
                    logger.warning(f"HIBP API returned {resp.status}")
                    return []
                return await resp.json()
