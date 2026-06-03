import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime

from jinja2 import Template

from .celery_app import celery_app
from clusterspider.config import settings
from clusterspider.graph.driver import get_driver, close_driver
from clusterspider.graph.repository import GraphRepository
from clusterspider.graph.models import EntityType

logger = logging.getLogger(__name__)

REPORT_HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>ClusterSpider OSINT Report - {{ title }}</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 40px; color: #1a1a2e; background: #fff; line-height: 1.6; }
        h1 { color: #0f3460; border-bottom: 3px solid #0f3460; padding-bottom: 12px; margin-bottom: 5px; }
        h2 { color: #16213e; margin-top: 35px; border-left: 4px solid #0f3460; padding-left: 12px; }
        h3 { color: #1a1a2e; margin-top: 20px; }
        .meta { color: #555; font-size: 14px; margin-bottom: 30px; }
        .executive-summary { background: #f0f4ff; border: 1px solid #c7d2fe; border-radius: 8px; padding: 20px; margin: 20px 0; }
        .executive-summary h3 { margin-top: 0; color: #3730a3; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 20px 0; }
        .stat-card { background: #f8f9fa; border-radius: 8px; padding: 16px; border-left: 4px solid #0f3460; }
        .stat-value { font-size: 28px; font-weight: bold; color: #0f3460; }
        .stat-label { font-size: 11px; color: #666; text-transform: uppercase; letter-spacing: 0.5px; }
        .findings { background: #fff7ed; border: 1px solid #fed7aa; border-radius: 8px; padding: 20px; margin: 20px 0; }
        .findings h3 { margin-top: 0; color: #9a3412; }
        .findings ul { margin: 0; padding-left: 20px; }
        .findings li { margin-bottom: 8px; }
        .severity-high { color: #dc2626; font-weight: 600; }
        .severity-medium { color: #d97706; font-weight: 600; }
        .severity-low { color: #059669; }
        table { width: 100%; border-collapse: collapse; margin: 15px 0; font-size: 13px; }
        th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #e5e7eb; }
        th { background: #f1f3f5; font-weight: 600; color: #374151; }
        tr:hover { background: #f9fafb; }
        .tag { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; margin: 1px 2px; }
        .tag-domain { background: #dbeafe; color: #1e40af; }
        .tag-ip { background: #dcfce7; color: #166534; }
        .tag-email { background: #fef3c7; color: #92400e; }
        .tag-leak { background: #fee2e2; color: #991b1b; }
        .tag-cert { background: #fce7f3; color: #9d174d; }
        .tag-org { background: #e0e7ff; color: #3730a3; }
        .graph-snapshot { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin: 20px 0; }
        .graph-snapshot h3 { margin-top: 0; }
        .graph-legend { display: flex; flex-wrap: wrap; gap: 12px; margin: 10px 0; }
        .graph-legend-item { display: flex; align-items: center; gap: 4px; font-size: 12px; }
        .legend-dot { width: 10px; height: 10px; border-radius: 50%; }
        .relationship-list { columns: 2; column-gap: 20px; font-size: 12px; }
        .relationship-list li { margin-bottom: 4px; }
        .section-empty { color: #9ca3af; font-style: italic; padding: 10px 0; }
        .footer { margin-top: 50px; padding-top: 20px; border-top: 2px solid #e5e7eb; color: #6b7280; font-size: 12px; display: flex; justify-content: space-between; }
        @media print {
            body { padding: 20px; }
            .no-print { display: none; }
        }
    </style>
</head>
<body>
    <h1>ClusterSpider OSINT Intelligence Report</h1>
    <div class="meta">
        <strong>Target:</strong> {{ title }} &nbsp;|&nbsp;
        <strong>Type:</strong> {{ target_type }} &nbsp;|&nbsp;
        <strong>Generated:</strong> {{ generated_at }} &nbsp;|&nbsp;
        <strong>Depth:</strong> {{ depth }}-hop analysis
    </div>

    <!-- Executive Summary -->
    <div class="executive-summary">
        <h3>Executive Summary</h3>
        <p>
            Analysis of <strong>{{ title }}</strong> identified
            <strong>{{ total_nodes }}</strong> related entities across
            <strong>{{ total_relationships }}</strong> relationships.
            {% if leak_count > 0 %}
            <span class="severity-high">{{ leak_count }} breach exposure(s) detected.</span>
            {% endif %}
            {% if cert_count > 0 %}
            {{ cert_count }} SSL certificate(s) mapped.
            {% endif %}
            {{ subdomain_count }} subdomain(s) and {{ ip_count }} IP address(es) discovered.
        </p>
    </div>

    <!-- Statistics -->
    <h2>Statistics Summary</h2>
    <div class="stats">
        <div class="stat-card">
            <div class="stat-value">{{ total_nodes }}</div>
            <div class="stat-label">Total Entities</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{{ subdomain_count }}</div>
            <div class="stat-label">Subdomains</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{{ ip_count }}</div>
            <div class="stat-label">IP Addresses</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{{ email_count }}</div>
            <div class="stat-label">Email Addresses</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{{ leak_count }}</div>
            <div class="stat-label">Breach Records</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{{ cert_count }}</div>
            <div class="stat-label">Certificates</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{{ org_count }}</div>
            <div class="stat-label">Organizations</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{{ port_count }}</div>
            <div class="stat-label">Open Ports</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{{ total_relationships }}</div>
            <div class="stat-label">Relationships</div>
        </div>
    </div>

    <!-- Key Findings -->
    <h2>Key Findings</h2>
    <div class="findings">
        <h3>Risk Assessment</h3>
        <ul>
        {% if leak_count > 0 %}
            <li class="severity-high">CRITICAL: {{ leak_count }} data breach(es) detected involving this target's associated accounts. Immediate credential rotation recommended.</li>
        {% endif %}
        {% if exposed_emails|length > 0 %}
            <li class="severity-medium">WARNING: {{ exposed_emails|length }} email address(es) discovered in public sources (code repositories, certificates, WHOIS).</li>
        {% endif %}
        {% if subdomain_count > 20 %}
            <li class="severity-medium">ATTENTION: Large attack surface with {{ subdomain_count }} subdomains. Review for abandoned/forgotten services.</li>
        {% elif subdomain_count > 0 %}
            <li class="severity-low">{{ subdomain_count }} subdomain(s) identified. Standard enumeration coverage.</li>
        {% endif %}
        {% if cert_expired_count > 0 %}
            <li class="severity-medium">WARNING: {{ cert_expired_count }} expired or soon-to-expire certificate(s) detected.</li>
        {% endif %}
        {% if ip_count > 0 %}
            <li class="severity-low">{{ ip_count }} unique IP address(es) mapped across {{ org_count }} organization(s)/ASN(s).</li>
        {% endif %}
        {% if port_count > 0 %}
            <li class="severity-medium">ATTENTION: {{ port_count }} open port(s) detected. Review exposed services for unnecessary attack surface.</li>
        {% endif %}
        {% if findings|length == 0 and leak_count == 0 %}
            <li class="severity-low">No critical findings. Standard internet presence observed.</li>
        {% endif %}
        </ul>
    </div>

    <!-- Leaked Account List -->
    {% if leaks %}
    <h2>Data Breach Exposure</h2>
    <p>The following breaches include data associated with this target:</p>
    <table>
        <tr><th>Breach Name</th><th>Date</th><th>Exposed Data Types</th><th>Records</th></tr>
        {% for leak in leaks %}
        <tr>
            <td><strong>{{ leak.breach_name or leak.get('value', 'Unknown') }}</strong></td>
            <td>{{ leak.get('breach_date', 'N/A') }}</td>
            <td>
                {% if leak.get('data_classes') %}
                    {% for dc in leak.data_classes[:8] %}<span class="tag tag-leak">{{ dc }}</span>{% endfor %}
                    {% if leak.data_classes|length > 8 %}+{{ leak.data_classes|length - 8 }} more{% endif %}
                {% else %}N/A{% endif %}
            </td>
            <td>{{ leak.get('pwn_count', 'N/A') }}</td>
        </tr>
        {% endfor %}
    </table>
    {% endif %}

    <!-- Subdomain Enumeration -->
    {% if subdomains %}
    <h2>Subdomain Enumeration Results</h2>
    <p>{{ subdomains|length }} subdomain(s) discovered via DNS brute-force and certificate transparency logs:</p>
    <table>
        <tr><th>#</th><th>Subdomain</th><th>Discovery Source</th></tr>
        {% for d in subdomains[:100] %}
        <tr>
            <td>{{ loop.index }}</td>
            <td><code>{{ d.value }}</code></td>
            <td>{{ d.get('data_source', 'multiple') }}</td>
        </tr>
        {% endfor %}
    </table>
    {% if subdomains|length > 100 %}
    <p class="section-empty">... and {{ subdomains|length - 100 }} more subdomains (truncated)</p>
    {% endif %}
    {% endif %}

    <!-- IP Addresses & Services -->
    {% if ips %}
    <h2>IP Addresses & Infrastructure</h2>
    <table>
        <tr><th>IP Address</th><th>Version</th><th>Country</th><th>City</th><th>Organization / ASN</th></tr>
        {% for ip in ips %}
        <tr>
            <td><code>{{ ip.value }}</code></td>
            <td>{{ ip.get('version', 'v4') }}</td>
            <td>{{ ip.get('geo_country', '-') }}</td>
            <td>{{ ip.get('geo_city', '-') }}</td>
            <td>{{ ip.get('org_name', '-') }} {% if ip.get('asn') %}({{ ip.asn }}){% endif %}</td>
        </tr>
        {% endfor %}
    </table>
    {% endif %}

    <!-- Certificates -->
    {% if certs %}
    <h2>SSL/TLS Certificates</h2>
    <table>
        <tr><th>Fingerprint</th><th>Issuer</th><th>Valid From</th><th>Valid To</th><th>Status</th></tr>
        {% for cert in certs[:30] %}
        <tr>
            <td><code>{{ cert.get('fingerprint', '-')[:16] }}...</code></td>
            <td>{{ cert.get('issuer', '-') }}</td>
            <td>{{ cert.get('not_before', '-') }}</td>
            <td>{{ cert.get('not_after', '-') }}</td>
            <td>
                {% if cert.get('_expired') %}<span class="severity-high">Expired</span>
                {% else %}<span class="severity-low">Valid</span>{% endif %}
            </td>
        </tr>
        {% endfor %}
    </table>
    {% endif %}

    <!-- Email Addresses -->
    {% if emails %}
    <h2>Discovered Email Addresses</h2>
    <table>
        <tr><th>Email</th><th>Breach Exposure</th></tr>
        {% for email in emails %}
        <tr>
            <td><code>{{ email.value }}</code></td>
            <td>{% if email.get('leak_count', 0) > 0 %}<span class="severity-high">{{ email.leak_count }} breach(es)</span>{% else %}<span class="severity-low">None detected</span>{% endif %}</td>
        </tr>
        {% endfor %}
    </table>
    {% endif %}

    <!-- Open Ports & Services -->
    {% if host_ports %}
    <h2>Open Ports & Services</h2>
    <p>{{ port_count }} open port(s) discovered via TCP port scanning across {{ host_ports|length }} host(s):</p>
    {% for host, host_port_list in host_ports.items() %}
    <h3><code>{{ host }}</code> ({{ host_port_list|length }} port(s))</h3>
    <table>
        <tr><th>Port</th><th>Protocol</th><th>Service</th><th>Banner / Details</th><th>Source</th></tr>
        {% for p in host_port_list|sort(attribute='port') %}
        <tr>
            <td><strong>{{ p.get('port', '-') }}</strong></td>
            <td>{{ p.get('protocol', 'tcp') }}</td>
            <td>
                {% if p.get('service', 'unknown') in ['SSH', 'RDP', 'VNC', 'Telnet', 'MSSQL', 'MySQL', 'PostgreSQL', 'Redis', 'MongoDB'] %}
                    <span class="severity-medium">{{ p.get('service', 'unknown') }}</span>
                {% else %}
                    {{ p.get('service', 'unknown') }}
                {% endif %}
            </td>
            <td><code>{{ p.get('banner', '-')[:80] }}</code></td>
            <td>{{ p.get('data_source', 'port_scan') }}</td>
        </tr>
        {% endfor %}
    </table>
    {% endfor %}
    {% endif %}

    <!-- Organizations -->
    {% if orgs %}
    <h2>Associated Organizations / ASNs</h2>
    <table>
        <tr><th>Organization</th><th>ASN</th><th>Description</th></tr>
        {% for org in orgs %}
        <tr>
            <td>{{ org.get('name', '-') }}</td>
            <td>{{ org.get('asn', '-') }}</td>
            <td>{{ org.get('description', '-') }}</td>
        </tr>
        {% endfor %}
    </table>
    {% endif %}

    <!-- Relationship Graph Snapshot -->
    <h2>Relationship Graph Snapshot</h2>
    <div class="graph-snapshot">
        <h3>Entity Relationship Overview</h3>
        <div class="graph-legend">
            <div class="graph-legend-item"><div class="legend-dot" style="background:#06b6d4"></div> Domain</div>
            <div class="graph-legend-item"><div class="legend-dot" style="background:#22c55e"></div> IP</div>
            <div class="graph-legend-item"><div class="legend-dot" style="background:#f59e0b"></div> Email</div>
            <div class="graph-legend-item"><div class="legend-dot" style="background:#a855f7"></div> Username</div>
            <div class="graph-legend-item"><div class="legend-dot" style="background:#ec4899"></div> Certificate</div>
            <div class="graph-legend-item"><div class="legend-dot" style="background:#3b82f6"></div> Organization</div>
            <div class="graph-legend-item"><div class="legend-dot" style="background:#ef4444"></div> LeakRecord</div>
            <div class="graph-legend-item"><div class="legend-dot" style="background:#64748b"></div> Port</div>
        </div>
        <p><strong>Node count by type:</strong></p>
        <ul class="relationship-list">
        {% for label, count in node_counts.items() %}
            <li><span class="tag tag-domain">{{ label }}</span> {{ count }}</li>
        {% endfor %}
        </ul>
        <p><strong>Relationship count by type:</strong></p>
        <ul class="relationship-list">
        {% for rel_type, count in rel_counts.items() %}
            <li>{{ rel_type }}: {{ count }}</li>
        {% endfor %}
        </ul>
        <p style="font-size:12px; color:#6b7280; margin-top:10px;">
            Graph contains {{ total_nodes }} nodes and {{ total_relationships }} edges within {{ depth }}-hop radius of target.
            Use the interactive Graph Explorer in the web dashboard for full visualization.
        </p>
    </div>

    <div class="footer">
        <span>Generated by ClusterSpider OSINT Platform v0.2.0</span>
        <span>{{ generated_at }}</span>
    </div>
</body>
</html>
"""


@celery_app.task(bind=True, name="clusterspider.workers.report_tasks.generate_report")
def generate_report(self, user_id: str, target: str, target_type: str, format: str = "html"):
    return asyncio.run(_generate_report_async(user_id, target, target_type, format))


async def _generate_report_async(user_id: str, target: str, target_type: str, format: str):
    driver = await get_driver()
    repo = GraphRepository(driver)

    label = EntityType.DOMAIN if target_type == "domain" else EntityType.IP
    depth = 3

    # Get full neighbor subgraph
    neighbors = await repo.get_neighbors(label, target.lower(), user_id, depth=depth)
    all_nodes = neighbors.get("nodes", [])
    all_edges = neighbors.get("edges", [])

    # Also get user-level stats
    stats = await repo.get_stats(user_id)

    await close_driver()

    # Classify nodes
    leaks = [n for n in all_nodes if n.get("_label") == "LeakRecord"]
    domains = [n for n in all_nodes if n.get("_label") == "Domain"]
    ips = [n for n in all_nodes if n.get("_label") == "IP"]
    emails = [n for n in all_nodes if n.get("_label") == "Email"]
    certs = [n for n in all_nodes if n.get("_label") == "Certificate"]
    orgs = [n for n in all_nodes if n.get("_label") == "Organization"]
    usernames = [n for n in all_nodes if n.get("_label") == "Username"]
    ports = [n for n in all_nodes if n.get("_label") == "Port"]

    # Determine subdomains (domains that aren't the target itself)
    subdomains = [d for d in domains if d.get("value", "") != target.lower()]

    # Check cert expiration
    cert_expired_count = 0
    now_str = datetime.utcnow().strftime("%Y-%m-%d")
    for cert in certs:
        not_after = cert.get("not_after", "")
        if not_after and not_after < now_str:
            cert["_expired"] = True
            cert_expired_count += 1

    # Enrich emails with leak count
    email_in_leaks = set()
    for edge in all_edges:
        if edge.get("type") == "APPEARS_IN":
            email_in_leaks.add(edge.get("source"))
    for email in emails:
        email["leak_count"] = 1 if email.get("_id") in email_in_leaks else 0

    # Enrich IPs with org info
    ip_to_org = {}
    for edge in all_edges:
        if edge.get("type") == "BELONGS_TO_ASN":
            ip_to_org[edge.get("source")] = edge.get("target")
    org_map = {o.get("_id"): o for o in orgs}
    for ip in ips:
        org_id = ip_to_org.get(ip.get("_id"))
        if org_id and org_id in org_map:
            ip["org_name"] = org_map[org_id].get("name", "")
            ip["asn"] = org_map[org_id].get("asn", "")

    # Enrich ports: map HAS_PORT edges to connect ports back to their host
    port_to_host: dict[str, str] = {}
    for edge in all_edges:
        if edge.get("type") == "HAS_PORT":
            port_to_host[edge.get("target")] = edge.get("source")

    # Build ports list with host info
    port_map = {p.get("_id"): p for p in ports}
    # Group ports by host IP/domain
    host_ports: dict[str, list[dict]] = {}
    for port in ports:
        host_id = port_to_host.get(port.get("_id", ""))
        # Find the host node's value
        host_value = "unknown"
        for n in all_nodes:
            if n.get("_id") == host_id:
                host_value = n.get("value", "unknown")
                break
        host_ports.setdefault(host_value, []).append(port)

    # Node and relationship counts for graph snapshot
    node_counts: dict[str, int] = {}
    for n in all_nodes:
        lbl = n.get("_label", "Unknown")
        node_counts[lbl] = node_counts.get(lbl, 0) + 1

    rel_counts: dict[str, int] = {}
    for e in all_edges:
        rt = e.get("type", "UNKNOWN")
        rel_counts[rt] = rel_counts.get(rt, 0) + 1

    total_relationships = sum(rel_counts.values())
    exposed_emails = [e for e in emails if e.get("leak_count", 0) > 0]

    template = Template(REPORT_HTML_TEMPLATE)
    html_content = template.render(
        title=target,
        target_type=target_type,
        generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        depth=depth,
        total_nodes=len(all_nodes),
        total_relationships=total_relationships,
        subdomain_count=len(subdomains),
        ip_count=len(ips),
        email_count=len(emails),
        leak_count=len(leaks),
        cert_count=len(certs),
        org_count=len(orgs),
        port_count=len(ports),
        cert_expired_count=cert_expired_count,
        leaks=leaks,
        subdomains=subdomains,
        ips=ips,
        emails=emails,
        certs=certs,
        orgs=orgs,
        ports=ports,
        host_ports=host_ports,
        exposed_emails=exposed_emails,
        findings=[],
        node_counts=node_counts,
        rel_counts=rel_counts,
    )

    reports_dir = os.path.join(tempfile.gettempdir(), "clusterspider_reports")
    os.makedirs(reports_dir, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    if format == "pdf":
        try:
            from weasyprint import HTML
            pdf_path = os.path.join(reports_dir, f"report_{target}_{timestamp}.pdf")
            HTML(string=html_content).write_pdf(pdf_path)
            return {"format": "pdf", "path": pdf_path, "target": target}
        except ImportError:
            logger.warning("WeasyPrint not installed, falling back to HTML")
            format = "html"

    html_path = os.path.join(reports_dir, f"report_{target}_{timestamp}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return {"format": "html", "path": html_path, "target": target}
