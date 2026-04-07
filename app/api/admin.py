from fastapi import APIRouter
from app.schemas.stats import StatsResponse
from app.utils.dependencies import DbSession

router = APIRouter()


@router.get("/dashboard", response_model=StatsResponse)
def dashboard(db: DbSession):
    return "test"
