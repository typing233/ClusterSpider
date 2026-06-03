import logging
import re

import aiohttp

from clusterspider.core.module_base import BaseModule, ModuleResult, TargetType
from clusterspider.core.rate_limiter import rate_limiters
from clusterspider.config import settings

logger = logging.getLogger(__name__)

GITHUB_API_URL = "https://api.github.com/search/code"


class GithubSearchModule(BaseModule):
    @property
    def name(self) -> str:
        return "github_search"

    @property
    def description(self) -> str:
        return "Search GitHub code repositories for references to target (domains, emails, secrets)"

    @property
    def supported_targets(self) -> list[TargetType]:
        return [TargetType.DOMAIN, TargetType.EMAIL]

    @property
    def timeout(self) -> float:
        return 30.0

    async def execute(self, target: str, target_type: TargetType) -> ModuleResult:
        if not settings.github_token:
            return ModuleResult(
                module_name=self.name,
                target=target,
                target_type=target_type.value,
                success=False,
                error="GitHub token not configured",
            )

        await rate_limiters.acquire("github")

        try:
            results = await self._search(target)
        except aiohttp.ClientError as e:
            return ModuleResult(
                module_name=self.name,
                target=target,
                target_type=target_type.value,
                success=False,
                error=f"GitHub API error: {e}",
            )

        entities = []
        findings = []

        for item in results:
            repo_url = item.get("repository", {}).get("html_url", "")
            file_path = item.get("path", "")
            repo_name = item.get("repository", {}).get("full_name", "")

            findings.append({
                "repository": repo_name,
                "file": file_path,
                "url": item.get("html_url", ""),
            })

            emails = self._extract_emails(item.get("text_matches", []))
            for email in emails:
                entities.append({
                    "type": "email",
                    "value": email,
                    "source": f"github:{repo_name}",
                })

            domains = self._extract_domains(item.get("text_matches", []), target)
            for domain in domains:
                entities.append({
                    "type": "domain",
                    "value": domain,
                    "source": f"github:{repo_name}",
                })

        return ModuleResult(
            module_name=self.name,
            target=target,
            target_type=target_type.value,
            success=True,
            data={
                "total_results": len(findings),
                "findings": findings[:30],
            },
            entities=entities,
        )

    async def _search(self, query: str) -> list[dict]:
        headers = {
            "Authorization": f"token {settings.github_token}",
            "Accept": "application/vnd.github.text-match+json",
        }
        params = {"q": query, "per_page": 30}

        async with aiohttp.ClientSession() as session:
            async with session.get(
                GITHUB_API_URL, headers=headers, params=params,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status == 403:
                    logger.warning("GitHub rate limit exceeded")
                    return []
                if resp.status != 200:
                    logger.warning(f"GitHub API returned {resp.status}")
                    return []
                data = await resp.json()
                return data.get("items", [])

    def _extract_emails(self, text_matches: list[dict]) -> list[str]:
        emails: set[str] = set()
        email_re = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
        for match in text_matches:
            fragment = match.get("fragment", "")
            found = email_re.findall(fragment)
            emails.update(e.lower() for e in found)
        return list(emails)

    def _extract_domains(self, text_matches: list[dict], base_domain: str) -> list[str]:
        domains: set[str] = set()
        domain_re = re.compile(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*\." + re.escape(base_domain))
        for match in text_matches:
            fragment = match.get("fragment", "")
            found = domain_re.findall(fragment)
            domains.update(d.lower() for d in found if d.lower() != base_domain)
        return list(domains)
