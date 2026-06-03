import asyncio
import logging

import dns.resolver
import dns.rdatatype

from clusterspider.core.module_base import BaseModule, ModuleResult, TargetType

logger = logging.getLogger(__name__)

RECORD_TYPES = ["A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA"]


class DnsRecordsModule(BaseModule):
    @property
    def name(self) -> str:
        return "dns_records"

    @property
    def description(self) -> str:
        return "Query DNS records (A, AAAA, MX, NS, TXT, CNAME, SOA)"

    @property
    def supported_targets(self) -> list[TargetType]:
        return [TargetType.DOMAIN]

    async def execute(self, target: str, target_type: TargetType) -> ModuleResult:
        records = {}
        entities = []
        errors = []
        resolver = dns.resolver.Resolver()
        resolver.timeout = 10
        resolver.lifetime = 10

        loop = asyncio.get_event_loop()

        for rtype in RECORD_TYPES:
            try:
                answers = await loop.run_in_executor(
                    None, lambda rt=rtype: resolver.resolve(target, rt)
                )
                record_list = [rdata.to_text() for rdata in answers]
                records[rtype] = record_list

                if rtype == "A":
                    for ip in record_list:
                        entities.append({"type": "ip", "value": ip, "source": "dns_a"})
                elif rtype == "AAAA":
                    for ip in record_list:
                        entities.append({"type": "ipv6", "value": ip, "source": "dns_aaaa"})
                elif rtype == "MX":
                    for mx in record_list:
                        host = mx.split()[-1].rstrip(".")
                        entities.append({"type": "domain", "value": host, "source": "dns_mx"})
                elif rtype == "NS":
                    for ns in record_list:
                        entities.append({"type": "nameserver", "value": ns.rstrip("."), "source": "dns_ns"})

            except dns.resolver.NXDOMAIN:
                err = f"Domain '{target}' does not exist (NXDOMAIN)"
                logger.warning(f"[dns_records] {err}")
                return ModuleResult(
                    module_name=self.name,
                    target=target,
                    target_type=target_type.value,
                    success=False,
                    data={"records": {}},
                    error=err,
                )
            except dns.resolver.NoNameservers as e:
                err = f"No nameservers available for '{target}': {e}"
                logger.warning(f"[dns_records] {err}")
                errors.append(f"{rtype}: {err}")
            except dns.resolver.NoAnswer:
                continue
            except dns.resolver.Timeout:
                err = f"DNS query timeout for {rtype} record"
                logger.warning(f"[dns_records] {err}")
                errors.append(f"{rtype}: timeout")
            except Exception as e:
                err = f"Unexpected error querying {rtype}: {e}"
                logger.warning(f"[dns_records] {err}")
                errors.append(f"{rtype}: {e}")

        if not records:
            error_msg = "No DNS records resolved"
            if errors:
                error_msg += f"; errors: {'; '.join(errors)}"
            logger.error(f"[dns_records] Failed for {target}: {error_msg}")
            return ModuleResult(
                module_name=self.name,
                target=target,
                target_type=target_type.value,
                success=False,
                data={"records": {}},
                error=error_msg,
            )

        return ModuleResult(
            module_name=self.name,
            target=target,
            target_type=target_type.value,
            success=True,
            data={"records": records, "partial_errors": errors if errors else None},
            entities=entities,
        )
