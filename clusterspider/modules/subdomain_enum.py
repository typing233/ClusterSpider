import asyncio
import dns.resolver

from clusterspider.core.module_base import BaseModule, ModuleResult, TargetType


COMMON_SUBDOMAINS = [
    "www", "mail", "ftp", "blog", "dev", "api", "admin", "test",
    "staging", "app", "m", "mobile", "cdn", "static", "img",
    "ns1", "ns2", "dns", "vpn", "remote", "portal", "shop",
    "store", "web", "cloud", "git", "docs", "wiki", "forum",
    "support", "help", "status", "monitor", "login", "sso",
]


class SubdomainEnumModule(BaseModule):
    @property
    def name(self) -> str:
        return "subdomain_enum"

    @property
    def description(self) -> str:
        return "Enumerate subdomains using common wordlist"

    @property
    def supported_targets(self) -> list[TargetType]:
        return [TargetType.DOMAIN]

    @property
    def timeout(self) -> float:
        return 60.0

    async def execute(self, target: str, target_type: TargetType) -> ModuleResult:
        found = []
        entities = []
        resolver = dns.resolver.Resolver()
        resolver.timeout = 3
        resolver.lifetime = 3

        loop = asyncio.get_event_loop()

        async def check_subdomain(prefix: str):
            fqdn = f"{prefix}.{target}"
            try:
                answers = await loop.run_in_executor(
                    None, lambda: resolver.resolve(fqdn, "A")
                )
                ips = [rdata.to_text() for rdata in answers]
                found.append({"subdomain": fqdn, "ips": ips})
                entities.append({"type": "subdomain", "value": fqdn, "source": "wordlist"})
                for ip in ips:
                    entities.append({"type": "ip", "value": ip, "source": f"subdomain:{fqdn}"})
            except Exception:
                pass

        tasks = [check_subdomain(prefix) for prefix in COMMON_SUBDOMAINS]
        await asyncio.gather(*tasks)

        found.sort(key=lambda x: x["subdomain"])

        return ModuleResult(
            module_name=self.name,
            target=target,
            target_type=target_type.value,
            success=True,
            data={"subdomains_found": len(found), "subdomains": found},
            entities=entities,
        )
