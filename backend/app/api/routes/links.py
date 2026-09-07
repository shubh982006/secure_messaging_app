from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.services import link_service

router = APIRouter(prefix="/links", tags=["links"])


class LinkPreviewOut(BaseModel):
    url: str
    title: str | None = None
    description: str | None = None
    image: str | None = None
    site_name: str | None = None


@router.get("/preview", response_model=LinkPreviewOut)
async def preview(_: CurrentUser, url: str = Query(max_length=2048)) -> LinkPreviewOut:
    """Unfurl a link into an Open Graph card.

    Authenticated on purpose: an open URL-fetching endpoint is a gift to anyone
    probing your network. See link_service for the SSRF defences.
    """
    result = await link_service.get_preview(url)
    return LinkPreviewOut(
        url=result.url,
        title=result.title,
        description=result.description,
        image=result.image,
        site_name=result.site_name,
    )
