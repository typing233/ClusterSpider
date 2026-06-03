import asyncio
import logging
import ssl
from datetime import datetime

from clusterspider.core.module_base import BaseModule, ModuleResult, TargetType
from clusterspider.core.rate_limiter import rate_limiters

logger = logging.getLogger(__name__)

COMMON_PORTS = [
    21, 22, 23, 25, 53, 80, 110, 111, 135, 139, 143, 443, 445, 465, 587,
    993, 995, 1433, 1521, 2049, 3306, 3389, 5432, 5900, 6379, 8080, 8443,
    8888, 9090, 9200, 27017,
]

SERVICE_NAMES = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS",
    80: "HTTP", 110: "POP3", 111: "RPC", 135: "MSRPC", 139: "NetBIOS",
    143: "IMAP", 443: "HTTPS", 445: "SMB", 465: "SMTPS", 587: "Submission",
    993: "IMAPS", 995: "POP3S", 1433: "MSSQL", 1521: "Oracle",
    2049: "NFS", 3306: "MySQL", 3389: "RDP", 5432: "PostgreSQL",
    5900: "VNC", 6379: "Redis", 8080: "HTTP-Proxy", 8443: "HTTPS-Alt",
    8888: "HTTP-Alt", 9090: "Web-Admin", 9200: "Elasticsearch", 27017: "MongoDB",
}


class PortScanModule(BaseModule):
    @property
    def name(self) -> str:
        return "port_scan"

    @property
    def description(self) -> str:
        return "Async TCP port scan with banner grabbing on common service ports"

    @property
    def supported_targets(self) -> list[TargetType]:
        return [TargetType.DOMAIN, TargetType.IP]

    @property
    def timeout(self) -> float:
        return 90.0

    async def execute(self, target: str, target_type: TargetType) -> ModuleResult:
        await rate_limiters.acquire("port_scan")

        open_ports: list[dict] = []
        scan_start = datetime.utcnow()

        # Scan in batches to avoid overwhelming the target
        batch_size = 10
        for i in range(0, len(COMMON_PORTS), batch_size):
            batch = COMMON_PORTS[i:i + batch_size]
            tasks = [self._probe_port(target, port) for port in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for port, result in zip(batch, results):
                if isinstance(result, Exception):
                    continue
                if result:
                    open_ports.append(result)

        scan_duration = (datetime.utcnow() - scan_start).total_seconds()

        entities = []
        for port_info in open_ports:
            entities.append({
                "type": "port",
                "value": f"{target}:{port_info['port']}",
                "port": port_info["port"],
                "protocol": "tcp",
                "service": port_info.get("service", "unknown"),
                "banner": port_info.get("banner", ""),
                "source": "port_scan",
            })

        return ModuleResult(
            module_name=self.name,
            target=target,
            target_type=target_type.value,
            success=True,
            data={
                "open_ports": open_ports,
                "ports_scanned": len(COMMON_PORTS),
                "open_count": len(open_ports),
                "scan_duration_s": round(scan_duration, 2),
            },
            entities=entities,
        )

    async def _probe_port(self, host: str, port: int) -> dict | None:
        try:
            fut = asyncio.open_connection(host, port)
            reader, writer = await asyncio.wait_for(fut, timeout=3.0)
        except (asyncio.TimeoutError, OSError, ConnectionRefusedError):
            return None

        service = SERVICE_NAMES.get(port, "unknown")
        banner = ""

        try:
            # Try to grab a banner (read up to 1024 bytes with short timeout)
            data = await asyncio.wait_for(reader.read(1024), timeout=2.0)
            banner = data.decode("utf-8", errors="replace").strip()[:256]

            # Infer service from banner if not in known list
            if service == "unknown" and banner:
                service = self._infer_service(banner)
        except (asyncio.TimeoutError, OSError):
            pass

        # For TLS ports, try to get TLS info
        if port in (443, 465, 993, 995, 8443) and not banner:
            banner = await self._get_tls_info(host, port)

        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

        return {
            "port": port,
            "service": service,
            "banner": banner,
            "state": "open",
        }

    async def _get_tls_info(self, host: str, port: int) -> str:
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            fut = asyncio.open_connection(host, port, ssl=ctx)
            reader, writer = await asyncio.wait_for(fut, timeout=3.0)
            ssl_obj = writer.get_extra_info("ssl_object")
            if ssl_obj:
                cipher = ssl_obj.cipher()
                version = ssl_obj.version()
                info = f"{version} {cipher[0]}" if cipher else version or ""
                writer.close()
                await writer.wait_closed()
                return info
        except Exception:
            pass
        return ""

    @staticmethod
    def _infer_service(banner: str) -> str:
        lower = banner.lower()
        if "ssh" in lower:
            return "SSH"
        if "ftp" in lower:
            return "FTP"
        if "smtp" in lower:
            return "SMTP"
        if "http" in lower:
            return "HTTP"
        if "mysql" in lower:
            return "MySQL"
        if "postgresql" in lower or "postgres" in lower:
            return "PostgreSQL"
        if "redis" in lower:
            return "Redis"
        if "mongodb" in lower or "mongo" in lower:
            return "MongoDB"
        if "imap" in lower:
            return "IMAP"
        if "pop" in lower:
            return "POP3"
        return "unknown"
