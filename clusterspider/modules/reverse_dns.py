import asyncio
import logging

import dns.resolver
import dns.reversename

from clusterspider.core.module_base import BaseModule, ModuleResult, TargetType

logger = logging.getLogger(__name__)


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
            except dns.resolver.NXDOMAIN:
                err = f"Domain '{target}' does not exist (NXDOMAIN), cannot resolve IPs"
                logger.error(f"[reverse_dns] {err}")
                return ModuleResult(
                    module_name=self.name,
                    target=target,
                    target_type=target_type.value,
                    success=False,
                    error=err,
                )
            except dns.resolver.Timeout:
                err = f"DNS resolution timed out for '{target}'"
                logger.error(f"[reverse_dns] {err}")
                return ModuleResult(
                    module_name=self.name,
                    target=target,
                    target_type=target_type.value,
                    success=False,
                    error=err,
                )
            except Exception as e:
                err = f"Failed to resolve A records for '{target}': {e}"
                logger.error(f"[reverse_dns] {err}")
                return ModuleResult(
                    module_name=self.name,
                    target=target,
                    target_type=target_type.value,
                    success=False,
                    error=err,
                )

        if not ips:
            err = f"No IP addresses found for '{target}'"
            logger.warning(f"[reverse_dns] {err}")
            return ModuleResult(
                module_name=self.name,
                target=target,
                target_type=target_type.value,
                success=False,
                error=err,
            )

        lookup_errors = []
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
            except dns.resolver.NXDOMAIN:
                results.append({"ip": ip, "ptr_records": [], "error": "no PTR record"})
                lookup_errors.append(f"{ip}: no PTR record")
            except dns.resolver.Timeout:
                results.append({"ip": ip, "ptr_records": [], "error": "timeout"})
                lookup_errors.append(f"{ip}: timeout")
            except Exception as e:
                results.append({"ip": ip, "ptr_records": [], "error": str(e)})
                lookup_errors.append(f"{ip}: {e}")

        all_failed = all(not r.get("ptr_records") for r in results)
        if all_failed and lookup_errors:
            error_msg = f"All reverse lookups failed: {'; '.join(lookup_errors)}"
            logger.warning(f"[reverse_dns] {error_msg}")
            return ModuleResult(
                module_name=self.name,
                target=target,
                target_type=target_type.value,
                success=False,
                data={"reverse_lookups": results},
                error=error_msg,
            )

        return ModuleResult(
            module_name=self.name,
            target=target,
            target_type=target_type.value,
            success=True,
            data={"reverse_lookups": results},
            entities=entities,
        )
