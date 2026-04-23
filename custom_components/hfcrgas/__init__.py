"""合燃华润燃气 Home Assistant 集成."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .api import HFCRGasAPI
from .const import DOMAIN
from .coordinator import HFCRGasCoordinator

PLATFORMS = [Platform.SENSOR]

type HFCRGasConfigEntry = ConfigEntry[HFCRGasCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """设置配置条目."""
    api = HFCRGasAPI(
        huhao=entry.data["huhao"],
        phone=entry.data["phone"],
    )
    # 恢复之前的认证信息
    if "encrypted_yhh" in entry.data:
        api.encrypted_yhh = entry.data["encrypted_yhh"]
    if "resource_identifier" in entry.data:
        api.resource_identifier = entry.data["resource_identifier"]
    if "rqb_gh" in entry.data:
        api.rqb_gh = entry.data["rqb_gh"]
    if "rqb_id" in entry.data:
        api.rqb_id = entry.data["rqb_id"]
    if "user_name" in entry.data:
        api.user_name = entry.data["user_name"]
    if "address" in entry.data:
        api.address = entry.data["address"]
    if "meter_type" in entry.data:
        api.meter_type = entry.data["meter_type"]
    if "is_wlw" in entry.data:
        api.is_wlw = entry.data["is_wlw"]

    coordinator = HFCRGasCoordinator(hass, api, entry)
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # 注册每日定时刷新（首次刷新在内部执行）
    await coordinator.async_setup_daily_refresh()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载配置条目."""
    coordinator = entry.runtime_data
    await coordinator.api.close()

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
