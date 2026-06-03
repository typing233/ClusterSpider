import logging

import aiohttp

from clusterspider.core.module_base import BaseModule, ModuleResult, TargetType
from clusterspider.core.rate_limiter import rate_limiters

logger = logging.getLogger(__name__)

PLATFORMS = {
    "github": "https://github.com/{username}",
    "twitter": "https://x.com/{username}",
    "instagram": "https://www.instagram.com/{username}/",
    "reddit": "https://www.reddit.com/user/{username}",
    "linkedin": "https://www.linkedin.com/in/{username}",
    "keybase": "https://keybase.io/{username}",
    "hackernews": "https://news.ycombinator.com/user?id={username}",
    "gitlab": "https://gitlab.com/{username}",
    "medium": "https://medium.com/@{username}",
    "dev.to": "https://dev.to/{username}",
}


class SocialProfilesModule(BaseModule):
    @property
    def name(self) -> str:
        return "social_profiles"

    @property
    def description(self) -> str:
        return "Check username existence across social platforms"

    @property
    def supported_targets(self) -> list[TargetType]:
        return [TargetType.USERNAME]

    @property
    def timeout(self) -> float:
        return 45.0

    async def execute(self, target: str, target_type: TargetType) -> ModuleResult:
        found_profiles = []
        entities = []

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10),
            headers={"User-Agent": "Mozilla/5.0 (compatible; ClusterSpider/0.2)"},
        ) as session:
            for platform, url_template in PLATFORMS.items():
                await rate_limiters.acquire("social")
                url = url_template.format(username=target)

                try:
                    async with session.head(url, allow_redirects=True) as resp:
                        if resp.status == 200:
                            found_profiles.append({
                                "platform": platform,
                                "url": url,
                                "status": "found",
                            })
                            entities.append({
                                "type": "username",
                                "value": target,
                                "platform": platform,
                                "profile_url": url,
                                "source": "social_profiles",
                            })
                        elif resp.status == 404:
                            continue
                        else:
                            logger.debug(f"{platform}: got status {resp.status} for {target}")
                except aiohttp.ClientError:
                    logger.debug(f"{platform}: connection error for {target}")
                    continue

        return ModuleResult(
            module_name=self.name,
            target=target,
            target_type=target_type.value,
            success=True,
            data={
                "platforms_checked": len(PLATFORMS),
                "profiles_found": len(found_profiles),
                "profiles": found_profiles,
            },
            entities=entities,
        )
