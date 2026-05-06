import calendar
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.holiday_cache_manager import holiday_cache_manager
from app.deps import DBSessionDep
from app.repositories.holiday_calendar import HolidayCalendarRepository
from app.schemas import (
    ApiResponse,
    AttendanceDailyResponse,
    AttendanceRecalculateRequest,
    AttendanceRuleSettingsUpdate,
    HolidayCacheRefreshRequest,
    HolidayCacheScheduleUpdate,
)
from app.services.attendance_record import AttendanceRecordService
from app.services.workday import AilccCachedWorkdayProvider, build_workday_provider

router = APIRouter(prefix="/api/v1/attendance-records", tags=["考勤记录"])
attendance_record_svc = AttendanceRecordService()
holiday_calendar_repo = HolidayCalendarRepository()


@router.get("", response_model=ApiResponse)
async def get_attendance_records(
    db: DBSessionDep,
    year_month: str,
    keyword: str = None,
    status: int = Query(default=None, ge=1, le=7),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    try:
        await attendance_record_svc.ensure_monthly_records(db, year_month, keyword=keyword)
        records, total = await attendance_record_svc.list_daily_records(
            db, year_month, keyword, status, page, page_size, ensure=False
        )
        summary = await attendance_record_svc.get_monthly_summary(db, year_month, keyword, ensure=False)
        return ApiResponse(
            data={
                "total": total,
                "page": page,
                "page_size": page_size,
                "summary": summary.model_dump(),
                "records": [AttendanceDailyResponse.model_validate(item) for item in records],
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": 2002, "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 5000, "message": str(e)})


@router.post("/recalculate", response_model=ApiResponse)
async def recalculate_attendance_records(data: AttendanceRecalculateRequest, db: DBSessionDep):
    try:
        await attendance_record_svc.ensure_monthly_records(db, data.year_month, user_id=data.user_id, force=True)
        summary = await attendance_record_svc.get_monthly_summary(db, data.year_month, data.user_id, ensure=False)
        return ApiResponse(message="考勤记录已重算", data={"summary": summary.model_dump()})
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": 2002, "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 5000, "message": str(e)})


@router.get("/rule-settings", response_model=ApiResponse)
async def get_attendance_rule_settings(db: DBSessionDep):
    try:
        settings = await attendance_record_svc.get_rule_settings(db)
        return ApiResponse(data=settings)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 5000, "message": str(e)})


@router.put("/rule-settings", response_model=ApiResponse)
async def update_attendance_rule_settings(data: AttendanceRuleSettingsUpdate, db: DBSessionDep):
    try:
        settings = await attendance_record_svc.update_rule_settings(db, data.plan_start, data.plan_end)
        return ApiResponse(message="考勤规则已保存", data=settings)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": 2002, "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 5000, "message": str(e)})


@router.get("/export/monthly")
async def export_monthly_attendance(
    db: DBSessionDep,
    year_month: str,
    keyword: str = None,
    status: int = Query(default=None, ge=1, le=7),
):
    try:
        content = await attendance_record_svc.export_monthly_csv(db, year_month, keyword, status)
        filename = f"attendance_{year_month.replace('-', '')}.csv"
        return StreamingResponse(
            iter([content]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": 2002, "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 5000, "message": str(e)})


@router.get("/holiday-cache/status", response_model=ApiResponse)
async def get_holiday_cache_status():
    return ApiResponse(data=holiday_cache_manager.get_status())


@router.get("/holiday-cache/settings", response_model=ApiResponse)
async def get_holiday_cache_settings():
    return ApiResponse(data=holiday_cache_manager.get_settings())


@router.put("/holiday-cache/settings", response_model=ApiResponse)
async def update_holiday_cache_settings(data: HolidayCacheScheduleUpdate):
    try:
        hour, minute = [int(part) for part in data.time.split(":", 1)]
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail={"code": 2002, "message": "时间格式必须为 HH:mm"})

    if data.frequency not in {"daily", "weekly"}:
        raise HTTPException(status_code=400, detail={"code": 2002, "message": "frequency 必须为 daily 或 weekly"})
    if not (1 <= data.weekday <= 7):
        raise HTTPException(status_code=400, detail={"code": 2002, "message": "weekday 必须为 1-7"})

    settings = holiday_cache_manager.update_settings(
        enabled=data.enabled,
        frequency=data.frequency,
        time_value=data.time,
        weekday=data.weekday,
    )
    return ApiResponse(message="节假日缓存刷新配置已更新", data=settings)


@router.post("/holiday-cache/refresh", response_model=ApiResponse)
async def refresh_holiday_cache(data: HolidayCacheRefreshRequest):
    try:
        result = holiday_cache_manager.start_manual_refresh(data.year)
        return ApiResponse(message="节假日缓存刷新任务已启动", data=result)
    except RuntimeError as e:
        status_code = 409 if "正在执行" in str(e) else 500
        raise HTTPException(status_code=status_code, detail={"code": 5002, "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 5000, "message": str(e)})


@router.get("/holiday-cache/calendar", response_model=ApiResponse)
async def get_holiday_cache_calendar(db: DBSessionDep, year_month: str):
    try:
        year, month = [int(part) for part in year_month.split("-", 1)]
        calendar.monthrange(year, month)
    except ValueError:
        raise HTTPException(status_code=400, detail={"code": 2002, "message": "year_month 必须为 YYYY-MM"})

    provider = build_workday_provider()
    if isinstance(provider, AilccCachedWorkdayProvider):
        try:
            await provider.ensure_year_cached(db, year)
        except Exception:
            # Calendar view can still render fallback dates without blocking the page.
            pass

    rows = await holiday_calendar_repo.list_by_year_month(db, year, month)
    items = [
        {
            "date": row.holiday_date.isoformat(),
            "year": row.year,
            "type": row.type,
            "is_holiday": row.is_holiday,
            "name": row.name,
            "source": row.source,
            "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
        }
        for row in rows
    ]
    return ApiResponse(data={"year_month": year_month, "days": items})
