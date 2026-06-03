import asyncio
import logging
import ssl

import aiohttp

from clusterspider.core.module_base import BaseModule, ModuleResult, TargetType

logger = logging.getLogger(__name__)


class HttpTitleModule(BaseModule):
    @property
    def name(self) -> str:
        return "http_title"

    @property
    def description(self) -> str:
        return "Fetch HTTP/HTTPS page title and basic headers"

    @property
    def supported_targets(self) -> list[TargetType]:
        return [TargetType.DOMAIN, TargetType.IP]

    @property
    def timeout(self) -> float:
        return 20.0

    async def execute(self, target: str, target_type: TargetType) -> ModuleResult:
        results = {}
        entities = []
        scheme_errors = {}

        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        connector = aiohttp.TCPConnector(ssl=ssl_ctx)

        async with aiohttp.ClientSession(connector=connector) as session:
            for scheme in ["https", "http"]:
                url = f"{scheme}://{target}"
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10),
                                           allow_redirects=True) as resp:
                        body = await resp.text(errors="replace")
                        title = self._extract_title(body)
                        headers = {k: v for k, v in resp.headers.items()
                                   if k.lower() in ("server", "x-powered-by", "content-type")}
                        results[scheme] = {
                            "status": resp.status,
                            "title": title,
                            "headers": headers,
                            "final_url": str(resp.url),
                        }
                        if resp.headers.get("server"):
                            entities.append({
                                "type": "technology",
                                "value": resp.headers["server"],
                                "source": f"http_{scheme}",
                            })
                except asyncio.TimeoutError:
                    err = f"{scheme.upper()} connection timed out"
                    logger.warning(f"[http_title] {err} for {target}")
                    scheme_errors[scheme] = err
                except aiohttp.ClientConnectorError as e:
                    err = f"{scheme.upper()} connection failed: {e}"
                    logger.warning(f"[http_title] {err} for {target}")
                    scheme_errors[scheme] = err
                except Exception as e:
                    err = f"{scheme.upper()} error: {e}"
                    logger.warning(f"[http_title] {err} for {target}")
                    scheme_errors[scheme] = err

        has_success = any("status" in v for v in results.values())

        if not has_success:
            error_msg = "; ".join(f"{k}: {v}" for k, v in scheme_errors.items())
            logger.error(f"[http_title] All schemes failed for {target}: {error_msg}")
            return ModuleResult(
                module_name=self.name,
                target=target,
                target_type=target_type.value,
                success=False,
                data={"scheme_errors": scheme_errors},
                error=f"All HTTP(S) connections failed: {error_msg}",
            )

        if scheme_errors:
            results["partial_errors"] = scheme_errors

        return ModuleResult(
            module_name=self.name,
            target=target,
            target_type=target_type.value,
            success=True,
            data=results,
            entities=entities,
        )

    @staticmethod
    def _extract_title(html: str) -> str | None:
        lower = html.lower()
        start = lower.find("<title")
        if start == -1:
            return None
        start = lower.find(">", start)
        if start == -1:
            return None
        end = lower.find("</title>", start)
        if end == -1:
            return None
        return html[start + 1:end].strip()
