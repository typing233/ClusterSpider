import logging
from datetime import datetime
from typing import Any

from neo4j import AsyncDriver, AsyncSession

from clusterspider.config import settings
from .models import EntityType, RelationType

logger = logging.getLogger(__name__)


class GraphRepository:
    def __init__(self, driver: AsyncDriver):
        self.driver = driver

    async def merge_node(
        self, label: EntityType, properties: dict[str, Any], user_id: str
    ) -> dict:
        props = {**properties, "user_id": user_id, "last_updated": datetime.utcnow().isoformat()}
        merge_key = self._get_merge_key(label)

        match_props = {k: props[k] for k in merge_key if k in props}
        match_props["user_id"] = user_id

        set_props = {k: v for k, v in props.items() if k not in merge_key and v is not None}
        set_props["last_updated"] = datetime.utcnow().isoformat()

        query = (
            f"MERGE (n:{label.value} {{{self._props_to_match(merge_key)}, user_id: $user_id}}) "
            f"ON CREATE SET n.first_seen = datetime(), n += $set_props "
            f"ON MATCH SET n += $set_props "
            f"RETURN n"
        )

        params = {**match_props, "set_props": set_props}

        async with self.driver.session() as session:
            result = await session.run(query, params)
            record = await result.single()
            return dict(record["n"]) if record else {}

    async def merge_relationship(
        self,
        from_label: EntityType,
        from_key: dict[str, str],
        to_label: EntityType,
        to_key: dict[str, str],
        rel_type: RelationType,
        properties: dict[str, Any] | None = None,
        user_id: str = "",
    ):
        rel_props = properties or {}
        rel_props["last_seen"] = datetime.utcnow().isoformat()

        from_match = ", ".join(f"{k}: $from_{k}" for k in from_key)
        to_match = ", ".join(f"{k}: $to_{k}" for k in to_key)

        query = (
            f"MATCH (a:{from_label.value} {{{from_match}, user_id: $user_id}}) "
            f"MATCH (b:{to_label.value} {{{to_match}, user_id: $user_id}}) "
            f"MERGE (a)-[r:{rel_type.value}]->(b) "
            f"SET r += $rel_props "
            f"RETURN type(r)"
        )

        params = {"user_id": user_id, "rel_props": rel_props}
        for k, v in from_key.items():
            params[f"from_{k}"] = v
        for k, v in to_key.items():
            params[f"to_{k}"] = v

        async with self.driver.session() as session:
            await session.run(query, params)

    async def get_node(self, label: EntityType, value: str, user_id: str) -> dict | None:
        key_field = self._get_value_field(label)
        query = (
            f"MATCH (n:{label.value} {{{key_field}: $value, user_id: $user_id}}) "
            f"RETURN n"
        )
        async with self.driver.session() as session:
            result = await session.run(query, {"value": value, "user_id": user_id})
            record = await result.single()
            if record:
                node = dict(record["n"])
                node["_label"] = label.value
                return node
            return None

    async def get_neighbors(
        self,
        label: EntityType,
        value: str,
        user_id: str,
        depth: int = 2,
        rel_types: list[str] | None = None,
    ) -> dict:
        depth = min(depth, settings.max_graph_depth)
        key_field = self._get_value_field(label)

        rel_filter = ""
        if rel_types:
            rel_filter = ":" + "|".join(rel_types)

        query = (
            f"MATCH (start:{label.value} {{{key_field}: $value, user_id: $user_id}}) "
            f"CALL apoc.path.subgraphAll(start, {{maxLevel: $depth, "
            f"relationshipFilter: '{rel_filter}'}}) YIELD nodes, relationships "
            f"RETURN nodes, relationships"
        )

        fallback_query = (
            f"MATCH path = (start:{label.value} {{{key_field}: $value, user_id: $user_id}})"
            f"-[r{rel_filter}*1..{depth}]-(neighbor) "
            f"WHERE neighbor.user_id = $user_id "
            f"RETURN collect(DISTINCT neighbor) as nodes, collect(DISTINCT r) as relationships"
        )

        async with self.driver.session() as session:
            try:
                result = await session.run(query, {"value": value, "user_id": user_id, "depth": depth})
                record = await result.single()
            except Exception:
                result = await session.run(fallback_query, {"value": value, "user_id": user_id})
                record = await result.single()

            if not record:
                return {"nodes": [], "edges": []}

            nodes = []
            for node in record["nodes"]:
                n = dict(node)
                n["_label"] = list(node.labels)[0] if node.labels else "Unknown"
                n["_id"] = node.element_id
                nodes.append(n)

            edges = []
            rels = record["relationships"]
            if rels:
                for rel_list in rels:
                    if isinstance(rel_list, list):
                        for rel in rel_list:
                            edges.append({
                                "source": rel.start_node.element_id,
                                "target": rel.end_node.element_id,
                                "type": rel.type,
                                "properties": dict(rel),
                            })
                    else:
                        edges.append({
                            "source": rel_list.start_node.element_id,
                            "target": rel_list.end_node.element_id,
                            "type": rel_list.type,
                            "properties": dict(rel_list),
                        })

            return {"nodes": nodes, "edges": edges}

    async def shortest_path(
        self,
        from_label: EntityType,
        from_value: str,
        to_label: EntityType,
        to_value: str,
        user_id: str,
    ) -> dict:
        from_key = self._get_value_field(from_label)
        to_key = self._get_value_field(to_label)

        query = (
            f"MATCH (a:{from_label.value} {{{from_key}: $from_value, user_id: $user_id}}), "
            f"(b:{to_label.value} {{{to_key}: $to_value, user_id: $user_id}}), "
            f"path = shortestPath((a)-[*..{settings.max_graph_depth}]-(b)) "
            f"RETURN path"
        )

        async with self.driver.session() as session:
            result = await session.run(
                query, {"from_value": from_value, "to_value": to_value, "user_id": user_id}
            )
            record = await result.single()
            if not record:
                return {"nodes": [], "edges": [], "length": 0}

            path = record["path"]
            nodes = []
            for node in path.nodes:
                n = dict(node)
                n["_label"] = list(node.labels)[0] if node.labels else "Unknown"
                n["_id"] = node.element_id
                nodes.append(n)

            edges = []
            for rel in path.relationships:
                edges.append({
                    "source": rel.start_node.element_id,
                    "target": rel.end_node.element_id,
                    "type": rel.type,
                    "properties": dict(rel),
                })

            return {"nodes": nodes, "edges": edges, "length": len(path.relationships)}

    async def search_nodes(self, query_text: str, user_id: str, limit: int = 20) -> list[dict]:
        query = (
            "CALL db.index.fulltext.queryNodes('entity_fulltext', $query_text) "
            "YIELD node, score "
            "WHERE node.user_id = $user_id "
            "RETURN node, score ORDER BY score DESC LIMIT $limit"
        )
        async with self.driver.session() as session:
            result = await session.run(
                query, {"query_text": query_text, "user_id": user_id, "limit": limit}
            )
            records = await result.data()
            nodes = []
            for r in records:
                n = dict(r["node"])
                n["_label"] = list(r["node"].labels)[0] if r["node"].labels else "Unknown"
                n["_score"] = r["score"]
                nodes.append(n)
            return nodes

    async def get_stats(self, user_id: str) -> dict:
        query = (
            "MATCH (n) WHERE n.user_id = $user_id "
            "RETURN labels(n)[0] as label, count(n) as count"
        )
        async with self.driver.session() as session:
            result = await session.run(query, {"user_id": user_id})
            records = await result.data()
            stats = {r["label"]: r["count"] for r in records}

            rel_result = await session.run(
                "MATCH (a)-[r]->(b) WHERE a.user_id = $user_id "
                "RETURN type(r) as type, count(r) as count",
                {"user_id": user_id},
            )
            rel_records = await rel_result.data()
            stats["_relationships"] = {r["type"]: r["count"] for r in rel_records}
            return stats

    def _get_merge_key(self, label: EntityType) -> list[str]:
        keys = {
            EntityType.DOMAIN: ["value"],
            EntityType.IP: ["value"],
            EntityType.EMAIL: ["value"],
            EntityType.USERNAME: ["value", "platform"],
            EntityType.CERTIFICATE: ["fingerprint"],
            EntityType.ORGANIZATION: ["name"],
            EntityType.LEAK_RECORD: ["breach_name"],
        }
        return keys.get(label, ["value"])

    def _get_value_field(self, label: EntityType) -> str:
        fields = {
            EntityType.CERTIFICATE: "fingerprint",
            EntityType.ORGANIZATION: "name",
            EntityType.LEAK_RECORD: "breach_name",
        }
        return fields.get(label, "value")

    def _props_to_match(self, keys: list[str]) -> str:
        return ", ".join(f"{k}: ${k}" for k in keys)
