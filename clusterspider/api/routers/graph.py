from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from clusterspider.auth.models import User
from clusterspider.api.dependencies import get_current_user, get_graph_repo
from clusterspider.graph.models import EntityType
from clusterspider.graph.repository import GraphRepository

router = APIRouter()


ENTITY_TYPE_MAP = {
    "domain": EntityType.DOMAIN,
    "ip": EntityType.IP,
    "email": EntityType.EMAIL,
    "username": EntityType.USERNAME,
    "certificate": EntityType.CERTIFICATE,
    "organization": EntityType.ORGANIZATION,
    "leak": EntityType.LEAK_RECORD,
}


@router.get("/nodes/{entity_type}/{value}")
async def get_node(
    entity_type: str,
    value: str,
    user: User = Depends(get_current_user),
    repo: GraphRepository = Depends(get_graph_repo),
):
    label = ENTITY_TYPE_MAP.get(entity_type)
    if not label:
        raise HTTPException(status_code=400, detail=f"Unknown entity type: {entity_type}")

    node = await repo.get_node(label, value.lower(), user.id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    return node


@router.get("/neighbors")
async def get_neighbors(
    entity_type: str = Query(...),
    value: str = Query(...),
    depth: int = Query(default=2, ge=1, le=5),
    rel_types: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    repo: GraphRepository = Depends(get_graph_repo),
):
    label = ENTITY_TYPE_MAP.get(entity_type)
    if not label:
        raise HTTPException(status_code=400, detail=f"Unknown entity type: {entity_type}")

    rel_list = rel_types.split(",") if rel_types else None

    result = await repo.get_neighbors(label, value.lower(), user.id, depth=depth, rel_types=rel_list)
    return result


@router.get("/path")
async def shortest_path(
    from_type: str = Query(...),
    from_value: str = Query(...),
    to_type: str = Query(...),
    to_value: str = Query(...),
    user: User = Depends(get_current_user),
    repo: GraphRepository = Depends(get_graph_repo),
):
    from_label = ENTITY_TYPE_MAP.get(from_type)
    to_label = ENTITY_TYPE_MAP.get(to_type)

    if not from_label or not to_label:
        raise HTTPException(status_code=400, detail="Unknown entity type")

    result = await repo.shortest_path(
        from_label, from_value.lower(),
        to_label, to_value.lower(),
        user.id,
    )
    return result


@router.get("/search")
async def search_nodes(
    q: str = Query(..., min_length=2),
    limit: int = Query(default=20, ge=1, le=100),
    node_type: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    repo: GraphRepository = Depends(get_graph_repo),
):
    results = await repo.search_nodes(q, user.id, limit=limit, node_type=node_type)
    return {"results": results, "total": len(results)}


@router.get("/stats")
async def graph_stats(
    user: User = Depends(get_current_user),
    repo: GraphRepository = Depends(get_graph_repo),
):
    stats = await repo.get_stats(user.id)
    return stats


@router.get("/hubs")
async def get_hub_nodes(
    min_degree: int = Query(default=5, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    repo: GraphRepository = Depends(get_graph_repo),
):
    results = await repo.get_high_degree_nodes(user.id, min_degree=min_degree, limit=limit)
    return {"hubs": results, "total": len(results)}


@router.delete("/data")
async def delete_user_data(
    user: User = Depends(get_current_user),
    repo: GraphRepository = Depends(get_graph_repo),
):
    await repo.delete_user_data(user.id)
    return {"detail": "All graph data deleted"}
