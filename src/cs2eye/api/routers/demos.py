import uuid

import httpx
from fastapi import APIRouter, UploadFile, File, HTTPException
from starlette import status

from cs2eye.api.schemas.demos import DemoListResponse, DemoUploadResponse, HltvDemoResolveResponse, \
    HltvDemoResolveResponse, HltvDemoResolveRequest
from cs2eye.core.config import settings
from cs2eye.integrations.hltv.demo_resolver import resolve_hltv_demo_url

router = APIRouter(prefix="/demos", tags=["demos"])

@router.get("", response_model=DemoListResponse)
async def list_demos() -> DemoListResponse:

    return DemoListResponse()

@router.post("/upload", response_model=DemoUploadResponse)
async def upload_demo_manual(file: UploadFile = File(...)) -> DemoUploadResponse:
    if not file.filename or not file.filename.endswith(".dem"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .dem file is allowed",)

    return DemoUploadResponse(
        id = str(uuid.uuid4()),
        filename = file.filename,
        status="accepted",
    )

@router.post("/hltv/resolve", response_model=HltvDemoResolveResponse)
async def resolve_hltv_demo(
    payload: HltvDemoResolveRequest,
) -> HltvDemoResolveResponse:
    try:
        resolved_demo = await resolve_hltv_demo_url(payload.match_url)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except httpx.HTTPStatusError as error:
        raise HTTPException(
            status_code=400,
            detail=f"Could not load HLTV match page: HTTP {error.response.status_code}",
        ) from error
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=400,
            detail=f"Could not load HLTV match page: {error}",
        ) from error

    return HltvDemoResolveResponse(**resolved_demo)

