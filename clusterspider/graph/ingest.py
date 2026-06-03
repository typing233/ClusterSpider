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

RELATIONSHIP_MAP = {
    ("domain", "ip"): RelationType.RESOLVES_TO,
    ("domain", "subdomain"): RelationType.HAS_SUBDOMAIN,
    ("domain", "nameserver"): RelationType.NAMESERVER,
    ("domain", "email"): RelationType.REGISTERED_BY,
    ("ip", "domain"): RelationType.REVERSE_DNS,
    ("certificate", "domain"): RelationType.ISSUED_TO,
    ("email", "leak"): RelationType.APPEARS_IN,
    ("email", "username"): RelationType.HAS_USERNAME,
    ("ip", "organization"): RelationType.BELONGS_TO_ASN,
    ("domain", "organization"): RelationType.BELONGS_TO_ORG,
}


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

            rel_type = self._resolve_relationship(result.target_type, entity_type_str)
            if rel_type:
                from_label = target_label
                from_key = self._node_key(target_label, target_value)
                to_key = self._node_key(entity_label, entity_value, entity)

                await self.repo.merge_relationship(
                    from_label=from_label,
                    from_key=from_key,
                    to_label=entity_label,
                    to_key=to_key,
                    rel_type=rel_type,
                    properties={"source": result.module_name, "discovered_at": datetime.utcnow().isoformat()},
                    user_id=user_id,
                )

        logger.info(f"Ingested {len(result.entities)} entities from {result.module_name}")

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

    def _resolve_relationship(self, target_type: str, entity_type: str) -> RelationType | None:
        key = (target_type, entity_type)
        return RELATIONSHIP_MAP.get(key)

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
        elif label == EntityType.ORGANIZATION:
            props["name"] = value
            if "asn" in entity:
                props["asn"] = entity["asn"]
        elif label == EntityType.LEAK_RECORD:
            props["breach_name"] = value
            if "breach_date" in entity:
                props["breach_date"] = entity["breach_date"]
            if "data_classes" in entity:
                props["data_classes"] = entity["data_classes"]

        return props

    def _node_key(self, label: EntityType, value: str, entity: dict | None = None) -> dict:
        if label == EntityType.CERTIFICATE:
            fp = entity.get("fingerprint", value) if entity else value
            return {"fingerprint": fp}
        elif label == EntityType.ORGANIZATION:
            return {"name": value.lower()}
        elif label == EntityType.LEAK_RECORD:
            return {"breach_name": value.lower()}
        elif label == EntityType.USERNAME:
            platform = entity.get("platform", "unknown") if entity else "unknown"
            return {"value": value.lower(), "platform": platform}
        return {"value": value.lower()}
