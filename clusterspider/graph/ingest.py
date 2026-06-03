import logging
from datetime import datetime

from neo4j import AsyncDriver

from clusterspider.core.module_base import ModuleResult
from .models import EntityType, RelationType, GraphEdge
from .repository import GraphRepository

logger = logging.getLogger(__name__)

ENTITY_TYPE_MAP = {
    "domain": EntityType.DOMAIN,
    "subdomain": EntityType.DOMAIN,
    "ip": EntityType.IP,
    "ipv6": EntityType.IP,
    "email": EntityType.EMAIL,
    "nameserver": EntityType.DOMAIN,
    "technology": EntityType.ORGANIZATION,
    "username": EntityType.USERNAME,
    "certificate": EntityType.CERTIFICATE,
    "organization": EntityType.ORGANIZATION,
    "leak": EntityType.LEAK_RECORD,
}

RELATIONSHIP_RULES: list[dict] = [
    # DNS: domain resolves to IP
    {"from_target": "domain", "entity_type": "ip", "rel": RelationType.RESOLVES_TO, "direction": "target->entity"},
    {"from_target": "domain", "entity_type": "ipv6", "rel": RelationType.RESOLVES_TO, "direction": "target->entity"},
    # DNS: domain has subdomain
    {"from_target": "domain", "entity_type": "subdomain", "rel": RelationType.HAS_SUBDOMAIN, "direction": "target->entity"},
    # DNS: domain nameserver
    {"from_target": "domain", "entity_type": "nameserver", "rel": RelationType.NAMESERVER, "direction": "target->entity"},
    # DNS MX: domain has mail exchange
    {"from_target": "domain", "entity_type": "domain", "rel": RelationType.MAIL_EXCHANGE, "direction": "target->entity", "source_filter": "dns_mx"},
    # WHOIS: domain registered by email
    {"from_target": "domain", "entity_type": "email", "rel": RelationType.REGISTERED_BY, "direction": "target->entity"},
    # Reverse DNS: IP -> domain
    {"from_target": "ip", "entity_type": "domain", "rel": RelationType.REVERSE_DNS, "direction": "target->entity"},
    # Certificate transparency: certificate ISSUED_TO domain (cert -> domain)
    {"from_target": "domain", "entity_type": "certificate", "rel": RelationType.ISSUED_TO, "direction": "entity->target"},
    # Certificate transparency: discovered subdomain via cert
    {"from_target": "domain", "entity_type": "subdomain", "rel": RelationType.HAS_SUBDOMAIN, "direction": "target->entity", "module_filter": "cert_transparency"},
    # IP geolocation: IP belongs to ASN/org
    {"from_target": "ip", "entity_type": "organization", "rel": RelationType.BELONGS_TO_ASN, "direction": "target->entity"},
    # Leak check: email appears in breach
    {"from_target": "email", "entity_type": "leak", "rel": RelationType.APPEARS_IN, "direction": "target->entity"},
    # Leak check: domain-level scan discovers leaks (domain -> leak as domain exposure)
    {"from_target": "domain", "entity_type": "leak", "rel": RelationType.APPEARS_IN, "direction": "target->entity"},
    # GitHub search: entities found in repos
    {"from_target": "domain", "entity_type": "email", "rel": RelationType.FOUND_IN_REPO, "direction": "target->entity", "module_filter": "github_search"},
    {"from_target": "domain", "entity_type": "domain", "rel": RelationType.FOUND_IN_REPO, "direction": "target->entity", "module_filter": "github_search"},
    {"from_target": "email", "entity_type": "domain", "rel": RelationType.FOUND_IN_REPO, "direction": "target->entity", "module_filter": "github_search"},
    # Social profiles: email has username
    {"from_target": "username", "entity_type": "username", "rel": RelationType.HAS_USERNAME, "direction": "target->entity"},
    # Domain belongs to org (from whois)
    {"from_target": "domain", "entity_type": "organization", "rel": RelationType.BELONGS_TO_ORG, "direction": "target->entity"},
]


class GraphIngestor:
    def __init__(self, driver: AsyncDriver):
        self.repo = GraphRepository(driver)

    async def ingest_result(self, result: ModuleResult, user_id: str):
        if not result.success or not result.entities:
            return

        target_label = self._infer_target_label(result.target_type)
        target_value = result.target.lower().strip()

        await self.repo.merge_node(
            label=target_label,
            properties={"value": target_value},
            user_id=user_id,
        )

        for entity in result.entities:
            entity_type_str = entity.get("type", "")
            entity_value = entity.get("value", "").strip()
            if not entity_value:
                continue

            entity_label = ENTITY_TYPE_MAP.get(entity_type_str)
            if not entity_label:
                logger.warning(f"Unknown entity type: {entity_type_str}")
                continue

            node_props = self._build_node_props(entity_label, entity)
            await self.repo.merge_node(
                label=entity_label,
                properties=node_props,
                user_id=user_id,
            )

            # Find all matching relationship rules and create edges
            edges_created = await self._create_edges_for_entity(
                target_label=target_label,
                target_value=target_value,
                entity_label=entity_label,
                entity=entity,
                entity_type_str=entity_type_str,
                module_name=result.module_name,
                user_id=user_id,
            )

            if not edges_created:
                logger.debug(
                    f"No relationship rule matched: target_type={result.target_type}, "
                    f"entity_type={entity_type_str}, module={result.module_name}"
                )

        logger.info(f"Ingested {len(result.entities)} entities from {result.module_name} for user {user_id}")

    async def _create_edges_for_entity(
        self,
        target_label: EntityType,
        target_value: str,
        entity_label: EntityType,
        entity: dict,
        entity_type_str: str,
        module_name: str,
        user_id: str,
    ) -> bool:
        target_type_str = self._label_to_target_type(target_label)
        entity_value = entity.get("value", "").strip().lower()
        created = False

        for rule in RELATIONSHIP_RULES:
            if rule["from_target"] != target_type_str:
                continue
            if rule["entity_type"] != entity_type_str:
                continue
            if "module_filter" in rule and rule["module_filter"] != module_name:
                continue
            if "source_filter" in rule:
                entity_source = entity.get("source", "")
                if rule["source_filter"] != entity_source:
                    continue

            target_key = self._node_key(target_label, target_value)
            entity_key = self._node_key(entity_label, entity_value, entity)

            rel_props = {
                "source": module_name,
                "discovered_at": datetime.utcnow().isoformat(),
            }
            if entity.get("source"):
                rel_props["data_source"] = entity["source"]

            if rule["direction"] == "target->entity":
                await self.repo.merge_relationship(
                    from_label=target_label,
                    from_key=target_key,
                    to_label=entity_label,
                    to_key=entity_key,
                    rel_type=rule["rel"],
                    properties=rel_props,
                    user_id=user_id,
                )
            else:
                # entity->target (e.g., Certificate ISSUED_TO Domain)
                await self.repo.merge_relationship(
                    from_label=entity_label,
                    from_key=entity_key,
                    to_label=target_label,
                    to_key=target_key,
                    rel_type=rule["rel"],
                    properties=rel_props,
                    user_id=user_id,
                )
            created = True

        return created

    async def ingest_edge(self, edge: GraphEdge, user_id: str):
        await self.repo.merge_relationship(
            from_label=edge.from_label,
            from_key=edge.from_key,
            to_label=edge.to_label,
            to_key=edge.to_key,
            rel_type=edge.rel_type,
            properties=edge.properties,
            user_id=user_id,
        )

    def _infer_target_label(self, target_type: str) -> EntityType:
        mapping = {
            "domain": EntityType.DOMAIN,
            "ip": EntityType.IP,
            "email": EntityType.EMAIL,
            "username": EntityType.USERNAME,
        }
        return mapping.get(target_type, EntityType.DOMAIN)

    def _label_to_target_type(self, label: EntityType) -> str:
        mapping = {
            EntityType.DOMAIN: "domain",
            EntityType.IP: "ip",
            EntityType.EMAIL: "email",
            EntityType.USERNAME: "username",
            EntityType.CERTIFICATE: "certificate",
            EntityType.ORGANIZATION: "organization",
            EntityType.LEAK_RECORD: "leak",
        }
        return mapping.get(label, "domain")

    def _build_node_props(self, label: EntityType, entity: dict) -> dict:
        value = entity.get("value", "").strip().lower()
        props: dict = {}

        if label == EntityType.DOMAIN:
            props["value"] = value
        elif label == EntityType.IP:
            props["value"] = value
            props["version"] = "v6" if ":" in value else "v4"
        elif label == EntityType.EMAIL:
            props["value"] = value
        elif label == EntityType.USERNAME:
            props["value"] = value
            props["platform"] = entity.get("platform", "unknown")
            if "profile_url" in entity:
                props["profile_url"] = entity["profile_url"]
        elif label == EntityType.CERTIFICATE:
            props["fingerprint"] = entity.get("fingerprint", value)
            for field in ("serial", "issuer", "not_before", "not_after"):
                if field in entity:
                    props[field] = entity[field]
            if "san_count" in entity:
                props["san_count"] = entity["san_count"]
        elif label == EntityType.ORGANIZATION:
            props["name"] = value
            if "asn" in entity:
                props["asn"] = entity["asn"]
            if "description" in entity:
                props["description"] = entity["description"]
        elif label == EntityType.LEAK_RECORD:
            props["breach_name"] = value
            if "breach_date" in entity:
                props["breach_date"] = entity["breach_date"]
            if "data_classes" in entity:
                props["data_classes"] = entity["data_classes"]
            if "pwn_count" in entity:
                props["pwn_count"] = entity["pwn_count"]

        return props

    def _node_key(self, label: EntityType, value: str, entity: dict | None = None) -> dict:
        if label == EntityType.CERTIFICATE:
            fp = entity.get("fingerprint", value) if entity else value
            return {"fingerprint": fp.lower()}
        elif label == EntityType.ORGANIZATION:
            name = entity.get("value", value) if entity else value
            return {"name": name.lower()}
        elif label == EntityType.LEAK_RECORD:
            bn = entity.get("breach_name", value) if entity else value
            return {"breach_name": bn.lower()}
        elif label == EntityType.USERNAME:
            platform = entity.get("platform", "unknown") if entity else "unknown"
            return {"value": value.lower(), "platform": platform}
        return {"value": value.lower()}
