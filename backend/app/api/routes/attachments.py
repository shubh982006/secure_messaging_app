from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile

from app.api.deps import CurrentUser
from app.schemas.message import UploadedAttachment
from app.services import attachment_service

router = APIRouter(prefix="/attachments", tags=["attachments"])


@router.post("", response_model=UploadedAttachment, status_code=201)
async def upload_attachment(
    _: CurrentUser,
    file: Annotated[UploadFile, File()],
    # The browser already knows an image's pixel size; sending it avoids adding
    # an image-processing dependency just to read two integers.
    width: Annotated[int | None, Form()] = None,
    height: Annotated[int | None, Form()] = None,
) -> UploadedAttachment:
    """Upload one file and get back the metadata to attach to a message.

    Two steps on purpose: the file is uploaded first, then referenced by URL in
    ``message.send``. That keeps the hot message path pure JSON over the socket.
    """
    stored = await attachment_service.store_upload(file)
    return UploadedAttachment(
        **stored,
        width=width if width and 0 < width < 20000 else None,
        height=height if height and 0 < height < 20000 else None,
    )
