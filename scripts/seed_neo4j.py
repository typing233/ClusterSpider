"""Seed Neo4j with sample data for development/testing."""
import asyncio
from clusterspider.graph.driver import get_driver, close_driver
from clusterspider.graph.schema import init_schema
from clusterspider.graph.repository import GraphRepository
from clusterspider.graph.models import EntityType, RelationType

SAMPLE_USER = "dev-user-001"


async def main():
    driver = await get_driver()
    await init_schema(driver)
    repo = GraphRepository(driver)

    # Sample entities
    await repo.merge_node(EntityType.DOMAIN, {"value": "example.com"}, SAMPLE_USER)
    await repo.merge_node(EntityType.DOMAIN, {"value": "mail.example.com"}, SAMPLE_USER)
    await repo.merge_node(EntityType.IP, {"value": "93.184.216.34", "version": "v4", "geo_country": "US"}, SAMPLE_USER)
    await repo.merge_node(EntityType.EMAIL, {"value": "admin@example.com"}, SAMPLE_USER)
    await repo.merge_node(EntityType.ORGANIZATION, {"name": "Example Inc", "asn": "AS15133"}, SAMPLE_USER)

    # Sample relationships
    await repo.merge_relationship(
        EntityType.DOMAIN, {"value": "example.com"},
        EntityType.IP, {"value": "93.184.216.34"},
        RelationType.RESOLVES_TO, user_id=SAMPLE_USER,
    )
    await repo.merge_relationship(
        EntityType.DOMAIN, {"value": "example.com"},
        EntityType.DOMAIN, {"value": "mail.example.com"},
        RelationType.HAS_SUBDOMAIN, user_id=SAMPLE_USER,
    )
    await repo.merge_relationship(
        EntityType.DOMAIN, {"value": "example.com"},
        EntityType.EMAIL, {"value": "admin@example.com"},
        RelationType.REGISTERED_BY, user_id=SAMPLE_USER,
    )
    await repo.merge_relationship(
        EntityType.IP, {"value": "93.184.216.34"},
        EntityType.ORGANIZATION, {"name": "Example Inc"},
        RelationType.BELONGS_TO_ASN, user_id=SAMPLE_USER,
    )

    print("Sample data seeded successfully.")
    await close_driver()


if __name__ == "__main__":
    asyncio.run(main())
