import logging
from datetime import datetime
from typing import Any

from neo4j import AsyncDriver

from clusterspider.config import settings
from .models import EntityType, RelationType

logger = logging.getLogger(__name__)


class GraphRepository:
    def __init__(self, driver: AsyncDriver):
        self.driver = driver

    # ─── BATCH WRITE OPERATIONS (for large-scale ingest) ───

    async def merge_nodes_batch(
        self, label: EntityType, nodes: list[dict[str, Any]], user_id: str
    ):
        """Batch merge multiple nodes in a single transaction using UNWIND."""
        if not nodes:
            return

        merge_key = self._get_merge_key(label)
        now = datetime.utcnow().isoformat()

        for node in nodes:
            node["user_id"] = user_id
            node["last_updated"] = now

        match_clause = ", ".join(f"{k}: item.{k}" for k in merge_key)
        query = (
            f"UNWIND $nodes AS item "
            f"MERGE (n:{label.value} {{{match_clause}, user_id: item.user_id}}) "
            f"ON CREATE SET n += item, n.first_seen = datetime() "
            f"ON MATCH SET n += item"
        )

        async with self.driver.session() as session:
            await session.run(query, {"nodes": nodes})

    async def merge_relationships_batch(
        self,
        from_label: EntityType,
        to_label: EntityType,
        rel_type: RelationType,
        edges: list[dict],
        user_id: str,
    ):
        """Batch merge relationships. Each edge dict has 'from_key', 'to_key', 'properties'."""
        if not edges:
            return

        now = datetime.utcnow().isoformat()
        from_key_field = self._get_value_field(from_label)
        to_key_field = self._get_value_field(to_label)

        query = (
            f"UNWIND $edges AS edge "
            f"MATCH (a:{from_label.value} {{{from_key_field}: edge.from_val, user_id: $user_id}}) "
            f"MATCH (b:{to_label.value} {{{to_key_field}: edge.to_val, user_id: $user_id}}) "
            f"MERGE (a)-[r:{rel_type.value}]->(b) "
            f"SET r += edge.props, r.last_seen = $now"
        )

        prepared = []
        for e in edges:
            prepared.append({
                "from_val": list(e["from_key"].values())[0],
                "to_val": list(e["to_key"].values())[0],
                "props": e.get("properties", {}),
            })

        async with self.driver.session() as session:
            await session.run(query, {"edges": prepared, "user_id": user_id, "now": now})

    # ─── SINGLE WRITE OPERATIONS ───

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

    # ─── READ OPERATIONS (optimized) ───

    async def get_node(self, label: EntityType, value: str, user_id: str) -> dict | None:
        key_field = self._get_value_field(label)
        query = (
            f"MATCH (n:{label.value} {{{key_field}: $value, user_id: $user_id}}) "
            f"RETURN n, labels(n)[0] as lbl, elementId(n) as eid"
        )
        async with self.driver.session() as session:
            result = await session.run(query, {"value": value, "user_id": user_id})
            record = await result.single()
            if record:
                node = dict(record["n"])
                node["_label"] = record["lbl"]
                node["_id"] = record["eid"]
                return node
            return None

    async def get_neighbors(
        self,
        label: EntityType,
        value: str,
        user_id: str,
        depth: int = 2,
        rel_types: list[str] | None = None,
        limit: int = 500,
    ) -> dict:
        """Optimized neighbor query with pagination and proper variable-length path traversal."""
        depth = min(depth, settings.max_graph_depth)
        key_field = self._get_value_field(label)

        rel_filter = ""
        if rel_types:
            rel_filter = ":" + "|".join(rel_types)

        # Use a single efficient query that collects nodes and relationships from all paths
        query = (
            f"MATCH (start:{label.value} {{{key_field}: $value, user_id: $user_id}}) "
            f"WITH start "
            f"MATCH path = (start)-[r{rel_filter}*1..{depth}]-(neighbor) "
            f"WHERE neighbor.user_id = $user_id "
            f"WITH start, nodes(path) AS pathNodes, relationships(path) AS pathRels "
            f"LIMIT $path_limit "
            f"UNWIND pathNodes AS n "
            f"WITH collect(DISTINCT n) AS allNodes, collect(pathRels) AS allPathRels "
            f"UNWIND allPathRels AS rels "
            f"UNWIND rels AS r "
            f"WITH allNodes, collect(DISTINCT r) AS allRels "
            f"RETURN allNodes, allRels"
        )

        async with self.driver.session() as session:
            try:
                result = await session.run(
                    query, {"value": value, "user_id": user_id, "path_limit": limit}
                )
                record = await result.single()
            except Exception as e:
                logger.warning(f"Neighbor query failed, trying simple approach: {e}")
                return await self._get_neighbors_simple(label, value, user_id, depth, rel_types, limit, session)

            if not record:
                return {"nodes": [], "edges": []}

            nodes = []
            for node in record["allNodes"]:
                n = dict(node)
                n["_label"] = list(node.labels)[0] if node.labels else "Unknown"
                n["_id"] = node.element_id
                nodes.append(n)

            edges = []
            for rel in record["allRels"]:
                edges.append({
                    "source": rel.start_node.element_id,
                    "target": rel.end_node.element_id,
                    "type": rel.type,
                    "properties": dict(rel),
                })

            return {"nodes": nodes, "edges": edges}

    async def _get_neighbors_simple(self, label, value, user_id, depth, rel_types, limit, session):
        """Fallback for when the optimized query hits issues (e.g., no APOC)."""
        key_field = self._get_value_field(label)
        rel_filter = ""
        if rel_types:
            rel_filter = ":" + "|".join(rel_types)

        # Iteratively expand level by level for better control
        all_nodes = {}
        all_edges = []

        # Get start node
        start_q = f"MATCH (n:{label.value} {{{key_field}: $value, user_id: $user_id}}) RETURN n, elementId(n) as eid, labels(n)[0] as lbl"
        res = await session.run(start_q, {"value": value, "user_id": user_id})
        rec = await res.single()
        if not rec:
            return {"nodes": [], "edges": []}

        start_node = dict(rec["n"])
        start_node["_id"] = rec["eid"]
        start_node["_label"] = rec["lbl"]
        all_nodes[rec["eid"]] = start_node

        frontier = {rec["eid"]}

        for _ in range(depth):
            if not frontier:
                break
            expand_q = (
                f"MATCH (a)-[r{rel_filter}]-(b) "
                f"WHERE elementId(a) IN $frontier AND b.user_id = $user_id "
                f"RETURN DISTINCT b, elementId(b) as eid, labels(b)[0] as lbl, "
                f"r, elementId(a) as src_id, type(r) as rtype, "
                f"startNode(r) = a as is_outgoing "
                f"LIMIT $limit"
            )
            res = await session.run(expand_q, {"frontier": list(frontier), "user_id": user_id, "limit": limit})
            records = await res.data()

            next_frontier = set()
            for r in records:
                node_id = r["eid"]
                if node_id not in all_nodes:
                    n = dict(r["b"])
                    n["_id"] = node_id
                    n["_label"] = r["lbl"]
                    all_nodes[node_id] = n
                    next_frontier.add(node_id)

                rel = r["r"]
                all_edges.append({
                    "source": rel.start_node.element_id,
                    "target": rel.end_node.element_id,
                    "type": rel.type,
                    "properties": dict(rel),
                })

            frontier = next_frontier

        return {"nodes": list(all_nodes.values()), "edges": all_edges}

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

    async def search_nodes(
        self, query_text: str, user_id: str, limit: int = 20, node_type: str | None = None
    ) -> list[dict]:
        """Full-text search with optional node type filter."""
        if node_type:
            # Direct indexed lookup when type is known
            label = self._resolve_label(node_type)
            if label:
                key_field = self._get_value_field(label)
                query = (
                    f"MATCH (n:{label.value}) "
                    f"WHERE n.user_id = $user_id AND n.{key_field} CONTAINS $query_text "
                    f"RETURN n, labels(n)[0] as lbl, elementId(n) as eid "
                    f"LIMIT $limit"
                )
                async with self.driver.session() as session:
                    result = await session.run(
                        query, {"query_text": query_text.lower(), "user_id": user_id, "limit": limit}
                    )
                    records = await result.data()
                    return [
                        {**dict(r["n"]), "_label": r["lbl"], "_id": r["eid"]}
                        for r in records
                    ]

        # Full-text index search
        query = (
            "CALL db.index.fulltext.queryNodes('entity_fulltext', $query_text) "
            "YIELD node, score "
            "WHERE node.user_id = $user_id "
            "RETURN node, score, labels(node)[0] as lbl, elementId(node) as eid "
            "ORDER BY score DESC LIMIT $limit"
        )
        async with self.driver.session() as session:
            try:
                result = await session.run(
                    query, {"query_text": query_text, "user_id": user_id, "limit": limit}
                )
                records = await result.data()
                return [
                    {**dict(r["node"]), "_label": r["lbl"], "_id": r["eid"], "_score": r["score"]}
                    for r in records
                ]
            except Exception:
                # Fallback: if fulltext index not yet created, do CONTAINS across labels
                return await self._search_fallback(query_text, user_id, limit)

    async def _search_fallback(self, query_text: str, user_id: str, limit: int) -> list[dict]:
        query = (
            "MATCH (n) WHERE n.user_id = $user_id AND "
            "(n.value CONTAINS $q OR n.name CONTAINS $q OR n.breach_name CONTAINS $q OR n.fingerprint CONTAINS $q) "
            "RETURN n, labels(n)[0] as lbl, elementId(n) as eid LIMIT $limit"
        )
        async with self.driver.session() as session:
            result = await session.run(query, {"q": query_text.lower(), "user_id": user_id, "limit": limit})
            records = await result.data()
            return [
                {**dict(r["n"]), "_label": r["lbl"], "_id": r["eid"]}
                for r in records
            ]

    async def get_stats(self, user_id: str) -> dict:
        """Efficient stats using count store (index-backed)."""
        labels = ["Domain", "IP", "Email", "Username", "Certificate", "Organization", "LeakRecord"]
        stats = {}

        async with self.driver.session() as session:
            # Count nodes per label in a single query
            for lbl in labels:
                result = await session.run(
                    f"MATCH (n:{lbl} {{user_id: $user_id}}) RETURN count(n) as c",
                    {"user_id": user_id},
                )
                rec = await result.single()
                if rec and rec["c"] > 0:
                    stats[lbl] = rec["c"]

            # Count relationships
            rel_result = await session.run(
                "MATCH (a {user_id: $user_id})-[r]->(b) "
                "RETURN type(r) as type, count(r) as count",
                {"user_id": user_id},
            )
            rel_records = await rel_result.data()
            stats["_relationships"] = {r["type"]: r["count"] for r in rel_records}

        return stats

    async def get_node_degree(self, node_id: str, user_id: str) -> dict:
        """Get in/out degree for a node (useful for identifying high-connectivity hubs)."""
        query = (
            "MATCH (n) WHERE elementId(n) = $node_id AND n.user_id = $user_id "
            "OPTIONAL MATCH (n)-[out]->() "
            "OPTIONAL MATCH (n)<-[inc]-() "
            "RETURN count(DISTINCT out) as out_degree, count(DISTINCT inc) as in_degree"
        )
        async with self.driver.session() as session:
            result = await session.run(query, {"node_id": node_id, "user_id": user_id})
            record = await result.single()
            if record:
                return {"in_degree": record["in_degree"], "out_degree": record["out_degree"]}
            return {"in_degree": 0, "out_degree": 0}

    async def get_high_degree_nodes(self, user_id: str, min_degree: int = 5, limit: int = 20) -> list[dict]:
        """Find hub nodes with high connectivity — useful for identifying critical infrastructure."""
        query = (
            "MATCH (n {user_id: $user_id})-[r]-() "
            "WITH n, count(r) as degree "
            "WHERE degree >= $min_degree "
            "RETURN n, degree, labels(n)[0] as lbl, elementId(n) as eid "
            "ORDER BY degree DESC LIMIT $limit"
        )
        async with self.driver.session() as session:
            result = await session.run(
                query, {"user_id": user_id, "min_degree": min_degree, "limit": limit}
            )
            records = await result.data()
            return [
                {**dict(r["n"]), "_label": r["lbl"], "_id": r["eid"], "_degree": r["degree"]}
                for r in records
            ]

    async def delete_user_data(self, user_id: str):
        """Delete all nodes and relationships for a user (GDPR / account deletion)."""
        query = (
            "MATCH (n {user_id: $user_id}) "
            "DETACH DELETE n"
        )
        async with self.driver.session() as session:
            await session.run(query, {"user_id": user_id})

    # ─── HELPERS ───

    def _resolve_label(self, type_str: str) -> EntityType | None:
        mapping = {
            "domain": EntityType.DOMAIN,
            "ip": EntityType.IP,
            "email": EntityType.EMAIL,
            "username": EntityType.USERNAME,
            "certificate": EntityType.CERTIFICATE,
            "organization": EntityType.ORGANIZATION,
            "leak": EntityType.LEAK_RECORD,
            "leakrecord": EntityType.LEAK_RECORD,
        }
        return mapping.get(type_str.lower())

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
