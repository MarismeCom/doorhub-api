import asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.repositories.user import UserRepository
from app.schemas import DeviceUserSyncPreviewItem, UserCreate, UserUpdate
from app.core.zk_client import ZKClient, ZKOperationError


class DuplicateUserFieldError(ValueError):
    def __init__(self, duplicate_fields: list[dict]):
        self.duplicate_fields = duplicate_fields
        joined = "，".join([f"{item['label']}“{item['value']}”" for item in duplicate_fields])
        super().__init__(f"{joined} 已存在")


class UserService:
    SYNCABLE_FIELDS = ("uid", "name", "privilege", "password", "group_id", "user_id", "card")

    def __init__(self):
        self.repository = UserRepository()

    async def get_users(
        self,
        db: AsyncSession,
        device_ip: str = None,
        sync: bool = False,
        keyword: str = None,
        page: int = 1,
        page_size: int = 20,
        sort_field: str | None = None,
        sort_order: str = "desc",
    ) -> tuple[list[User], int]:
        users, total = await self.repository.list_active(
            db,
            page=page,
            page_size=page_size,
            keyword=keyword,
            sort_field=sort_field,
            sort_order=sort_order,
        )
        changed = False
        for user in users:
            changed = self._apply_synced_card_state(user) or changed
        if changed:
            await db.commit()
        return users, total

    async def suggest_next_user_id(self, db: AsyncSession) -> str:
        user_ids = await self.repository.list_all_user_ids(db)
        used_numeric_ids = {int(item) for item in user_ids if str(item).isdigit()}

        candidate = 1
        while True:
            if candidate not in used_numeric_ids:
                return str(candidate)
            candidate += 1

    async def create_user(self, db: AsyncSession, data: UserCreate, device_ip: str = None) -> User:
        await self._ensure_unique_fields(db, name=data.name, user_id=data.user_id, card=data.card or 0)

        uid = await self.repository.get_max_uid(db) + 1
        user = User(
            uid=uid,
            name=data.name,
            privilege=data.privilege,
            password=data.password or "",
            group_id=data.group_id or "",
            user_id=data.user_id,
            card=data.card or 0,
            status="active",
            sync_status="pending",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    async def update_user(self, db: AsyncSession, user_id: str, data: UserUpdate) -> User:
        user = await self.repository.get_active_by_user_id(db, user_id)
        if not user:
            raise ValueError(f"用户 {user_id} 不存在")

        await self._ensure_unique_fields(
            db,
            name=data.name,
            user_id=user.user_id,
            card=data.card or 0,
            exclude_user_id=user.user_id,
        )

        user.name = data.name
        user.privilege = data.privilege
        user.password = data.password or ""
        user.group_id = data.group_id or ""
        user.card = data.card or 0
        user.sync_status = "pending"
        user.sync_error = None

        await db.commit()
        await db.refresh(user)
        return user

    async def delete_user(self, db: AsyncSession, user_id: str, device_ip: str = None) -> bool:
        user = await self.repository.get_active_by_user_id(db, user_id)
        if not user:
            raise ValueError(f"用户 {user_id} 不存在")
        user.status = "disabled"
        user.sync_status = "pending_disable"
        user.sync_error = None
        await db.commit()
        return True

    async def sync_user_to_device(self, db: AsyncSession, device_ip: str, user_id: str) -> dict:
        user = await self.repository.get_by_user_id(db, user_id)
        if not user:
            return {"status": "error", "message": "用户不存在"}

        try:
            client = ZKClient(device_ip)
            if user.sync_status == "pending":
                await asyncio.to_thread(
                    client.save_user,
                    user.uid,
                    user.name,
                    user.privilege,
                    user.password or "",
                    user.group_id or "",
                    user.user_id,
                    user.card or 0,
                )
                verification = await asyncio.to_thread(self._verify_user_synced_on_device, client, user)
                if verification["status"] != "success":
                    user.sync_status = "failed"
                    user.sync_error = verification["message"]
                    await db.commit()
                    return verification

                user.sync_status = "synced"
                user.sync_error = None
                await db.commit()
                return {"status": "success", "message": "同步成功，设备回读校验通过"}
            if user.sync_status == "pending_disable":
                await asyncio.to_thread(
                    client.save_user,
                    user.uid,
                    user.name,
                    user.privilege,
                    "",
                    user.group_id or "",
                    user.user_id,
                    0,
                )
                verification = await asyncio.to_thread(self._verify_user_disabled_on_device, client, user)
                if verification["status"] != "success":
                    user.sync_status = "failed"
                    user.sync_error = verification["message"]
                    await db.commit()
                    return verification

                user.password = ""
                user.card = 0
                user.sync_status = "synced_disabled"
                user.sync_error = None
                await db.commit()
                return {"status": "success", "message": "离职同步成功，设备回读校验通过"}
            if user.sync_status == "pending_delete":
                await asyncio.to_thread(client.delete_user, user.uid)
                user.sync_status = "synced_deleted"
                user.sync_error = None
                await db.commit()
                return {"status": "success", "message": "删除同步成功"}
            if user.sync_status == "synced":
                return {"status": "skipped", "message": "用户已同步"}
            if user.sync_status == "synced_disabled":
                return {"status": "skipped", "message": "用户已停用同步"}
            return {"status": "error", "message": f"未知状态: {user.sync_status}"}
        except ZKOperationError as e:
            user.sync_status = "failed"
            user.sync_error = str(e)
            await db.commit()
            return {"status": "error", "message": f"同步失败: {e}"}
        except Exception as e:
            user.sync_status = "failed"
            user.sync_error = str(e)
            await db.commit()
            return {"status": "error", "message": f"同步异常: {e}"}

    async def sync_pending_users(self, db: AsyncSession, device_ip: str) -> dict:
        pending_users = await self.repository.list_pending(db)
        success_count = 0
        failed_count = 0
        errors = []
        for user in pending_users:
            result = await self.sync_user_to_device(db, device_ip, user.user_id)
            if result["status"] == "success":
                success_count += 1
            else:
                failed_count += 1
                errors.append(f"{user.user_id}: {result['message']}")
        return {"total": len(pending_users), "success": success_count, "failed": failed_count, "errors": errors}

    async def get_sync_status(self, db: AsyncSession, user_id: str = None) -> dict:
        if user_id:
            user = await self.repository.get_by_user_id(db, user_id)
            if not user:
                return {"status": "error", "message": "用户不存在"}
            return {"user_id": user.user_id, "sync_status": user.sync_status, "sync_error": user.sync_error}

        pending_users = await self.repository.list_failed_or_pending(db)
        return {
            "pending_count": len(pending_users),
            "users": [
                {"user_id": u.user_id, "name": u.name, "sync_status": u.sync_status, "sync_error": u.sync_error}
                for u in pending_users
            ],
        }

    async def sync_users_from_device(self, db: AsyncSession, device_ip: str, mode: str = "preview") -> dict:
        client = ZKClient(device_ip)
        device_users = await asyncio.to_thread(client.get_users)
        local_users = await self.repository.list_active_all(db)
        local_by_user_id = {user.user_id: user for user in local_users}
        local_by_uid = {user.uid: user for user in local_users}

        missing_in_local = []
        different_in_local = []
        uid_conflicts = []
        matched_count = 0
        inserted_count = 0
        updated_count = 0
        skipped_count = 0

        for raw_user in device_users:
            device_user = self._normalize_device_user(raw_user)
            local_user = local_by_user_id.get(device_user["user_id"])
            if local_user is None:
                uid_owner = local_by_uid.get(device_user["uid"])
                if uid_owner and uid_owner.user_id != device_user["user_id"]:
                    uid_conflicts.append(
                        DeviceUserSyncPreviewItem(
                            **device_user,
                            action="uid_conflict",
                            local_snapshot=self._serialize_local_user(uid_owner),
                        )
                    )
                    skipped_count += 1
                    continue

                item = DeviceUserSyncPreviewItem(**device_user, action="missing_in_local")
                missing_in_local.append(item)
                if mode in {"write_missing", "overwrite_local"}:
                    user = User(
                        uid=device_user["uid"],
                        name=device_user["name"],
                        privilege=device_user["privilege"],
                        password=device_user["password"],
                        group_id=device_user["group_id"],
                        user_id=device_user["user_id"],
                        card=device_user["card"],
                        status="active",
                        sync_status="synced",
                        sync_error=None,
                        deleted_at=None,
                    )
                    self._apply_synced_card_state(user, mark_synced=True)
                    db.add(user)
                    inserted_count += 1
                    local_by_uid[user.uid] = user
                    local_by_user_id[user.user_id] = user
                continue

            if not self._diff_local_and_device(local_user, device_user):
                matched_count += 1
                continue

            different_in_local.append(
                DeviceUserSyncPreviewItem(
                    **device_user,
                    action="different_in_local",
                    local_snapshot=self._serialize_local_user(local_user),
                )
            )
            if mode == "overwrite_local":
                for field in self.SYNCABLE_FIELDS:
                    setattr(local_user, field, device_user[field])
                local_user.deleted_at = None
                local_user.sync_error = None
                self._apply_synced_card_state(local_user, mark_synced=True)
                updated_count += 1
            else:
                skipped_count += 1

        if mode in {"write_missing", "overwrite_local"}:
            await db.commit()

        return {
            "device_ip": device_ip,
            "mode": mode,
            "device_total": len(device_users),
            "local_total": len(local_users),
            "matched_count": matched_count,
            "missing_in_local_count": len(missing_in_local),
            "different_in_local_count": len(different_in_local),
            "uid_conflict_count": len(uid_conflicts),
            "inserted_count": inserted_count,
            "updated_count": updated_count,
            "skipped_count": skipped_count,
            "supported_actions": ["preview", "write_missing", "overwrite_local"],
            "missing_in_local": [item.model_dump() for item in missing_in_local],
            "different_in_local": [item.model_dump() for item in different_in_local],
            "uid_conflicts": [item.model_dump() for item in uid_conflicts],
        }

    def _normalize_device_user(self, device_user) -> dict:
        return {
            "uid": int(getattr(device_user, "uid", 0) or 0),
            "user_id": str(getattr(device_user, "user_id", "") or ""),
            "name": str(getattr(device_user, "name", "") or ""),
            "privilege": int(getattr(device_user, "privilege", 0) or 0),
            "password": str(getattr(device_user, "password", "") or ""),
            "group_id": str(getattr(device_user, "group_id", "") or ""),
            "card": int(getattr(device_user, "card", 0) or 0),
        }

    def _verify_user_synced_on_device(self, client: ZKClient, user: User) -> dict:
        device_users = client.get_users()
        target = next((item for item in device_users if str(getattr(item, "user_id", "") or "") == user.user_id), None)
        if target is None:
            return {"status": "error", "message": f"同步后校验失败: 设备中未找到用户 {user.user_id}"}

        device_snapshot = self._normalize_device_user(target)
        expected = {
            "uid": int(user.uid),
            "user_id": user.user_id,
            "name": user.name,
            "privilege": int(user.privilege or 0),
            "password": user.password or "",
            "group_id": user.group_id or "",
            "card": int(user.card or 0),
        }
        mismatches = [
            field
            for field, expected_value in expected.items()
            if device_snapshot[field] != expected_value
        ]
        if mismatches:
            return {
                "status": "error",
                "message": f"同步后校验失败: 设备中的 {user.user_id} 字段不一致 ({', '.join(mismatches)})",
                "mismatches": mismatches,
            }

        return {"status": "success", "message": "设备回读校验通过"}

    def _verify_user_disabled_on_device(self, client: ZKClient, user: User) -> dict:
        device_users = client.get_users()
        target = next((item for item in device_users if str(getattr(item, "user_id", "") or "") == user.user_id), None)
        if target is None:
            return {"status": "error", "message": f"停用后校验失败: 设备中未找到用户 {user.user_id}"}

        device_snapshot = self._normalize_device_user(target)
        mismatches = []
        if device_snapshot["password"] != "":
            mismatches.append("password")
        if device_snapshot["card"] != 0:
            mismatches.append("card")

        if mismatches:
            return {
                "status": "error",
                "message": f"停用后校验失败: 设备中的 {user.user_id} 字段未清空 ({', '.join(mismatches)})",
                "mismatches": mismatches,
            }

        return {"status": "success", "message": "设备停用回读校验通过"}

    def _serialize_local_user(self, user: User) -> dict:
        self._apply_synced_card_state(user)
        return {
            "uid": user.uid,
            "user_id": user.user_id,
            "name": user.name,
            "privilege": user.privilege,
            "password": user.password or "",
            "card": user.card or 0,
            "group_id": user.group_id or "",
            "status": user.status or "active",
            "sync_status": user.sync_status,
        }

    def _apply_synced_card_state(self, user: User, mark_synced: bool = False) -> bool:
        changed = False
        card_value = int(user.card or 0)

        if card_value == 0:
            if (user.password or "") != "":
                user.password = ""
                changed = True
            if user.status != "disabled":
                user.status = "disabled"
                changed = True
            if mark_synced and user.sync_status != "synced_disabled":
                user.sync_status = "synced_disabled"
                changed = True
            elif user.sync_status == "synced":
                user.sync_status = "synced_disabled"
                changed = True
        else:
            if user.status == "disabled":
                user.status = "active"
                changed = True
            if mark_synced and user.sync_status != "synced":
                user.sync_status = "synced"
                changed = True
            elif user.sync_status == "synced_disabled":
                user.sync_status = "synced"
                changed = True

        return changed

    async def _ensure_unique_fields(
        self,
        db: AsyncSession,
        *,
        name: str,
        user_id: str,
        card: int,
        exclude_user_id: str | None = None,
    ) -> None:
        duplicate_fields = []

        existing_user_id = await self.repository.get_active_by_user_id(db, user_id)
        if existing_user_id and existing_user_id.user_id != exclude_user_id:
            duplicate_fields.append({"field": "user_id", "label": "用户ID", "value": user_id})

        existing_name = await self.repository.get_by_name(db, name)
        if existing_name and existing_name.user_id != exclude_user_id:
            duplicate_fields.append({"field": "name", "label": "姓名", "value": name})

        if card:
            existing_card = await self.repository.get_by_card(db, card)
            if existing_card and existing_card.user_id != exclude_user_id:
                duplicate_fields.append({"field": "card", "label": "卡号", "value": str(card)})

        if duplicate_fields:
            raise DuplicateUserFieldError(duplicate_fields)

    def _diff_local_and_device(self, local_user: User, device_user: dict) -> dict:
        diff = {}
        for field in self.SYNCABLE_FIELDS:
            local_value = getattr(local_user, field) or (0 if field == "card" else "")
            device_value = device_user[field]
            if local_value != device_value:
                diff[field] = {"local": local_value, "device": device_value}
        return diff
