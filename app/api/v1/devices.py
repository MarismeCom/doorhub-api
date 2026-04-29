from fastapi import APIRouter, HTTPException

from app.deps import DBSessionDep
from app.schemas import ApiResponse, DeviceCreate, DeviceResponse, DeviceUpdate
from app.services.device import DeviceService

router = APIRouter(prefix="/api/v1/devices", tags=["设备管理"])
device_svc = DeviceService()


def serialize_device(device):
    payload = DeviceResponse.model_validate(device).model_dump()
    payload["status"] = "active" if device.is_active else "inactive"
    return payload


@router.get("", response_model=ApiResponse)
async def get_devices(db: DBSessionDep):
    try:
        devices = await device_svc.list_active(db)
        return ApiResponse(
            data={
                "total": len(devices),
                "devices": [serialize_device(device) for device in devices],
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 5000, "message": str(e)})


@router.post("", response_model=ApiResponse)
async def create_device(data: DeviceCreate, db: DBSessionDep):
    try:
        device = await device_svc.create_device(db, data)
        return ApiResponse(message="设备创建成功", data={"device": serialize_device(device)})
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": 2002, "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 5000, "message": str(e)})


@router.put("/{device_id}", response_model=ApiResponse)
async def update_device(device_id: int, data: DeviceUpdate, db: DBSessionDep):
    try:
        device = await device_svc.update_device(db, device_id, data)
        return ApiResponse(message="设备更新成功", data={"device": serialize_device(device)})
    except ValueError as e:
        status_code = 404 if str(e) == "设备不存在" else 400
        error_code = 2001 if status_code == 404 else 2002
        raise HTTPException(status_code=status_code, detail={"code": error_code, "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 5000, "message": str(e)})


@router.delete("/{device_id}", response_model=ApiResponse)
async def delete_device(device_id: int, db: DBSessionDep):
    try:
        await device_svc.delete_device(db, device_id)
        return ApiResponse(message="设备删除成功")
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"code": 2001, "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 5000, "message": str(e)})


@router.get("/{ip}/status", response_model=ApiResponse)
async def get_device_status(ip: str, db: DBSessionDep):
    try:
        info = await device_svc.get_status(db, ip)
        return ApiResponse(data={"status": "ok", "device": info})
    except Exception as e:
        return ApiResponse(code=1001, message="设备连接失败", data={"status": "unreachable", "error": str(e)})
