from fastapi import APIRouter

from cs2eye.api.schemas.demos import DemoMapOption, DemoMapsResponse
from cs2eye.services.demo_map_result_service import STANDARD_MAPS

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/maps", response_model=DemoMapsResponse)
async def list_maps() -> DemoMapsResponse:
    return DemoMapsResponse(items=[
        DemoMapOption(code=code, title=code.title(), demo_names=[f"de_{code}"])
        for code in STANDARD_MAPS
    ])
