import logging

import aiohttp

from clusterspider.core.module_base import BaseModule, ModuleResult, TargetType
from clusterspider.core.rate_limiter import rate_limiters

logger = logging.getLogger(__name__)

CRTSH_URL = "https://crt.sh/"


class CertTransparencyModule(BaseModule):
    @property
    def name(self) -> str:
        return "cert_transparency"

    @property
    def description(self) -> str:
        return "Query Certificate Transparency logs via crt.sh for subdomain discovery"

    @property
    def supported_targets(self) -> list[TargetType]:
        return [TargetType.DOMAIN]

    @property
    def timeout(self) -> float:
        return 60.0

    async def execute(self, target: str, target_type: TargetType) -> ModuleResult:
        await rate_limiters.acquire("crtsh")

        entities = []
        certs = []

        try:
            params = {"q": f"%.{target}", "output": "json"}
            async with aiohttp.ClientSession() as session:
                async with session.get(CRTSH_URL, params=params, timeout=aiohttp.ClientTimeout(total=45)) as resp:
                    if resp.status != 200:
                        return ModuleResult(
                            module_name=self.name,
                            target=target,
                            target_type=target_type.value,
                            success=False,
                            error=f"crt.sh returned HTTP {resp.status}",
                        )
                    data = await resp.json(content_type=None)

        except aiohttp.ClientError as e:
            return ModuleResult(
                module_name=self.name,
                target=target,
                target_type=target_type.value,
                success=False,
                error=f"HTTP error: {e}",
            )

        seen_domains: set[str] = set()
        seen_certs: set[str] = set()

        for entry in data or []:
            name_value = entry.get("name_value", "")
            cert_id = str(entry.get("id", ""))

            # Parse all domains covered by this cert entry
            entry_domains: list[str] = []
            for domain in name_value.split("\n"):
                domain = domain.strip().lower().lstrip("*.")
                if domain and domain.endswith(target) or domain == target:
                    entry_domains.append(domain)
                    if domain != target and domain not in seen_domains:
                        seen_domains.add(domain)
                        entities.append({
                            "type": "subdomain",
                            "value": domain,
                            "source": "crt.sh",
                        })

            if cert_id and cert_id not in seen_certs:
                seen_certs.add(cert_id)
                fingerprint = entry.get("serial_number", cert_id)

                certs.append({
                    "id": cert_id,
                    "issuer": entry.get("issuer_name", ""),
                    "not_before": entry.get("not_before", ""),
                    "not_after": entry.get("not_after", ""),
                    "common_name": entry.get("common_name", ""),
                    "san_domains": entry_domains,
                })

                # Emit cert entity with san_domains list so ingest can create
                # ISSUED_TO edges to each covered domain
                entities.append({
                    "type": "certificate",
                    "value": fingerprint,
                    "fingerprint": fingerprint,
                    "issuer": entry.get("issuer_name", ""),
                    "not_before": entry.get("not_before", ""),
                    "not_after": entry.get("not_after", ""),
                    "san_domains": entry_domains,
                    "san_count": len(entry_domains),
                    "source": "crt.sh",
                })

        return ModuleResult(
            module_name=self.name,
            target=target,
            target_type=target_type.value,
            success=True,
            data={
                "total_certs": len(seen_certs),
                "unique_subdomains": len(seen_domains),
                "certificates": certs[:50],
            },
            entities=entities,
        )
