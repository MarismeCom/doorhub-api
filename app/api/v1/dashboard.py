from fastapi import APIRouter, HTTPException

from app.deps import CurrentUserDep, DBSessionDep
from app.schemas import ApiResponse
from app.services.dashboard import DashboardService

router = APIRouter(prefix="/api/v1/dashboard", tags=["工作台"])
dashboard_svc = DashboardService()


@router.get("/summary", response_model=ApiResponse)
async def get_dashboard_summary(db: DBSessionDep, current_user: CurrentUserDep):
    try:
        return ApiResponse(data=await dashboard_svc.get_summary(db))
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 5000, "message": str(e)})
