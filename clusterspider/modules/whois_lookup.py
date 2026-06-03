import asyncio
import logging

import whois as python_whois

from clusterspider.core.module_base import BaseModule, ModuleResult, TargetType

logger = logging.getLogger(__name__)


class WhoisModule(BaseModule):
    @property
    def name(self) -> str:
        return "whois"

    @property
    def description(self) -> str:
        return "Query Whois registration information"

    @property
    def supported_targets(self) -> list[TargetType]:
        return [TargetType.DOMAIN]

    @property
    def timeout(self) -> float:
        return 30.0

    async def execute(self, target: str, target_type: TargetType) -> ModuleResult:
        loop = asyncio.get_event_loop()

        try:
            w = await loop.run_in_executor(None, python_whois.whois, target)
        except Exception as e:
            err = f"Whois query failed: {e}"
            logger.error(f"[whois] {err} for {target}")
            return ModuleResult(
                module_name=self.name,
                target=target,
                target_type=target_type.value,
                success=False,
                error=err,
            )

        if not w or not w.domain_name:
            err = f"No whois data returned for '{target}'"
            logger.warning(f"[whois] {err}")
            return ModuleResult(
                module_name=self.name,
                target=target,
                target_type=target_type.value,
                success=False,
                error=err,
            )

        data = {}
        entities = []

        raw = {}
        for key in ["domain_name", "registrar", "creation_date", "expiration_date",
                    "updated_date", "name_servers", "status", "emails", "org",
                    "country", "state", "city"]:
            val = getattr(w, key, None)
            if val is not None:
                if isinstance(val, list):
                    raw[key] = [str(v) for v in val]
                else:
                    raw[key] = str(val)
        data = raw

        if w.name_servers:
            ns_list = w.name_servers if isinstance(w.name_servers, list) else [w.name_servers]
            for ns in ns_list:
                entities.append({"type": "nameserver", "value": ns.lower(), "source": "whois"})

        if w.emails:
            email_list = w.emails if isinstance(w.emails, list) else [w.emails]
            for email in email_list:
                entities.append({"type": "email", "value": email, "source": "whois"})

        return ModuleResult(
            module_name=self.name,
            target=target,
            target_type=target_type.value,
            success=True,
            data=data,
            entities=entities,
        )
