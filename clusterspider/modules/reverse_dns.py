import asyncio
import socket
import dns.resolver
import dns.reversename

from clusterspider.core.module_base import BaseModule, ModuleResult, TargetType


class ReverseDnsModule(BaseModule):
    @property
    def name(self) -> str:
        return "reverse_dns"

    @property
    def description(self) -> str:
        return "Perform reverse DNS lookup on IP addresses"

    @property
    def supported_targets(self) -> list[TargetType]:
        return [TargetType.IP, TargetType.DOMAIN]

    async def execute(self, target: str, target_type: TargetType) -> ModuleResult:
        loop = asyncio.get_event_loop()
        results = []
        entities = []

        ips = []
        if target_type == TargetType.IP:
            ips = [target]
        else:
            try:
                resolver = dns.resolver.Resolver()
                answers = await loop.run_in_executor(
                    None, lambda: resolver.resolve(target, "A")
                )
                ips = [rdata.to_text() for rdata in answers]
            except Exception:
                pass

        for ip in ips:
            try:
                rev_name = dns.reversename.from_address(ip)
                answer = await loop.run_in_executor(
                    None, lambda rn=rev_name: dns.resolver.resolve(rn, "PTR")
                )
                ptrs = [rdata.to_text().rstrip(".") for rdata in answer]
                results.append({"ip": ip, "ptr_records": ptrs})
                for ptr in ptrs:
                    entities.append({"type": "domain", "value": ptr, "source": "reverse_dns"})
            except Exception:
                results.append({"ip": ip, "ptr_records": []})

        return ModuleResult(
            module_name=self.name,
            target=target,
            target_type=target_type.value,
            success=True,
            data={"reverse_lookups": results},
            entities=entities,
        )
