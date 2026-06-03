import logging

from neo4j import AsyncDriver

logger = logging.getLogger(__name__)

CONSTRAINTS = [
    "CREATE CONSTRAINT domain_unique IF NOT EXISTS FOR (d:Domain) REQUIRE (d.value, d.user_id) IS UNIQUE",
    "CREATE CONSTRAINT ip_unique IF NOT EXISTS FOR (i:IP) REQUIRE (i.value, i.user_id) IS UNIQUE",
    "CREATE CONSTRAINT email_unique IF NOT EXISTS FOR (e:Email) REQUIRE (e.value, e.user_id) IS UNIQUE",
    "CREATE CONSTRAINT username_unique IF NOT EXISTS FOR (u:Username) REQUIRE (u.value, u.platform, u.user_id) IS UNIQUE",
    "CREATE CONSTRAINT cert_unique IF NOT EXISTS FOR (c:Certificate) REQUIRE (c.fingerprint, c.user_id) IS UNIQUE",
    "CREATE CONSTRAINT org_unique IF NOT EXISTS FOR (o:Organization) REQUIRE (o.name, o.user_id) IS UNIQUE",
    "CREATE CONSTRAINT leak_unique IF NOT EXISTS FOR (l:LeakRecord) REQUIRE (l.breach_name, l.user_id) IS UNIQUE",
]

INDEXES = [
    "CREATE INDEX domain_value_idx IF NOT EXISTS FOR (d:Domain) ON (d.value)",
    "CREATE INDEX ip_value_idx IF NOT EXISTS FOR (i:IP) ON (i.value)",
    "CREATE INDEX email_value_idx IF NOT EXISTS FOR (e:Email) ON (e.value)",
    "CREATE INDEX username_value_idx IF NOT EXISTS FOR (u:Username) ON (u.value)",
    "CREATE INDEX cert_fp_idx IF NOT EXISTS FOR (c:Certificate) ON (c.fingerprint)",
    "CREATE INDEX org_name_idx IF NOT EXISTS FOR (o:Organization) ON (o.name)",
    "CREATE INDEX leak_name_idx IF NOT EXISTS FOR (l:LeakRecord) ON (l.breach_name)",
]

FULLTEXT_INDEX = """
CREATE FULLTEXT INDEX entity_fulltext IF NOT EXISTS
FOR (d:Domain|i:IP|e:Email|u:Username|o:Organization)
ON EACH [d.value, i.value, e.value, u.value, o.name]
"""


async def init_schema(driver: AsyncDriver):
    async with driver.session() as session:
        for constraint in CONSTRAINTS:
            try:
                await session.run(constraint)
            except Exception as e:
                logger.debug(f"Constraint may already exist: {e}")

        for index in INDEXES:
            try:
                await session.run(index)
            except Exception as e:
                logger.debug(f"Index may already exist: {e}")

        try:
            await session.run(FULLTEXT_INDEX)
        except Exception as e:
            logger.debug(f"Fulltext index may already exist: {e}")

    logger.info("Neo4j schema initialized")
