"""合燃华润燃气数据协调器."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import HFCRGasAPI, HFCRGasAPIError, HFCRGasAuthError
from .const import DAILY_UPDATE_HOUR, DAILY_UPDATE_MINUTE, DOMAIN

_LOGGER = logging.getLogger(__name__)


class HFCRGasCoordinator(DataUpdateCoordinator[dict]):
    """合燃华润燃气数据更新协调器."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: HFCRGasAPI,
        entry: ConfigEntry,
    ) -> None:
        """初始化协调器."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{api.huhao}",
            # 不使用固定间隔，改用定时触发
            update_interval=None,
        )
        self.api = api
        self.config_entry = entry
        self._next_update: datetime | None = None
        self._schedule_next_update()

    def _schedule_next_update(self) -> None:
        """计算下次更新时间."""
        now = dt_util.now()
        today_target = now.replace(
            hour=DAILY_UPDATE_HOUR, minute=DAILY_UPDATE_MINUTE,
            second=0, microsecond=0,
        )
        if now >= today_target:
            self._next_update = today_target + timedelta(days=1)
        else:
            self._next_update = today_target

    async def async_setup_daily_refresh(self) -> None:
        """注册每日定时刷新."""
        # 每天到点触发
        unsub = async_track_time_change(
            self.hass,
            self._handle_time_change,
            hour=DAILY_UPDATE_HOUR,
            minute=DAILY_UPDATE_MINUTE,
            second=0,
        )
        self.config_entry.async_on_unload(unsub)
        # 启动时立即刷新一次
        await self.async_request_refresh()

    @callback
    def _handle_time_change(self, now: datetime) -> None:
        """定时触发刷新."""
        _LOGGER.info("定时刷新触发: %s", now)
        self.hass.async_create_task(self.async_request_refresh())

    async def _async_update_data(self) -> dict:
        """从 API 获取最新数据."""
        try:
            # 确保凭证有效
            if not self.api.encrypted_yhh or not self.api.resource_identifier:
                _LOGGER.info("凭证缺失，执行绑定")
                await self.api.bind()

            data = await self.api.get_all_data()

            # 更新下次更新时间
            self._schedule_next_update()

            # 将下次更新时间加入返回数据
            data["next_update_time"] = self._next_update

            # 更新配置中的认证信息
            self._update_entry_data()

            return data

        except HFCRGasAuthError as err:
            _LOGGER.warning("认证失败，尝试重新绑定: %s", err)
            try:
                await self.api.bind()
                data = await self.api.get_all_data()
                self._schedule_next_update()
                data["next_update_time"] = self._next_update
                self._update_entry_data()
                return data
            except HFCRGasAPIError as retry_err:
                raise UpdateFailed(f"重新绑定后仍然失败: {retry_err}") from retry_err

        except HFCRGasAPIError as err:
            raise UpdateFailed(f"获取数据失败: {err}") from err

        except Exception as err:
            raise UpdateFailed(f"未知错误: {err}") from err

    def _update_entry_data(self) -> None:
        """如果认证信息有变化，更新配置."""
        entry = self.config_entry
        if not entry:
            return

        new_data = dict(entry.data)
        updated = False
        for key in [
            "encrypted_yhh",
            "resource_identifier",
            "rqb_gh",
            "rqb_id",
            "user_name",
            "address",
            "meter_type",
            "is_wlw",
        ]:
            val = getattr(self.api, key, None)
            if val is not None and val != new_data.get(key):
                new_data[key] = val
                updated = True
        if updated:
            self.hass.config_entries.async_update_entry(entry, data=new_data)
