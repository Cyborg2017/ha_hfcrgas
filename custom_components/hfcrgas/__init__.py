"""合燃华润燃气 Home Assistant 集成."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, CoreState, EVENT_HOMEASSISTANT_STARTED
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.helpers.event import async_call_later

from .api import HFCRGasAPI
from .const import DOMAIN
from .coordinator import HFCRGasCoordinator

PLATFORMS = [Platform.SENSOR]

type HFCRGasConfigEntry = ConfigEntry[HFCRGasCoordinator]

_LOGGER = logging.getLogger(__name__)

# 前端卡片配置
URL_BASE = "/hfcrgas-local"
MANIFEST_PATH = Path(__file__).parent / "manifest.json"
try:
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        INTEGRATION_VERSION = json.load(f).get("version", "0.0.0")
except Exception:
    INTEGRATION_VERSION = "0.0.0"

CARD_FILENAME = "hfcrgas-card.js"

# 确保只注册一次
_STATIC_REGISTERED = False


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """组件初始化时注册前端卡片资源."""
    await _register_static_and_js(hass)

    # HA 启动后追加 Lovelace storage 注册（持久化，防刷新丢失）
    async def _register_lovelace_storage(_event=None) -> None:
        await _register_lovelace_resource(hass)

    if hass.state == CoreState.running:
        await _register_lovelace_storage()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _register_lovelace_storage)

    return True


async def _register_static_and_js(hass: HomeAssistant) -> None:
    """立即注册静态路径和 add_extra_js_url（首次加载必需）."""
    global _STATIC_REGISTERED
    if _STATIC_REGISTERED:
        return
    _STATIC_REGISTERED = True

    # 注册静态文件路径
    try:
        await hass.http.async_register_static_paths([
            StaticPathConfig(URL_BASE, str(Path(__file__).parent / "www"), False)
        ])
    except RuntimeError:
        _LOGGER.debug("静态路径已注册: %s", URL_BASE)

    # 立即注册 add_extra_js_url（确保首次加载就能用）
    add_extra_js_url(hass, f"{URL_BASE}/{CARD_FILENAME}")
    _LOGGER.debug("注册前端卡片: %s/%s", URL_BASE, CARD_FILENAME)


async def _register_lovelace_resource(hass: HomeAssistant) -> None:
    """通过 Lovelace storage API 持久化注册资源（防刷新丢失）."""
    lovelace = hass.data.get("lovelace")
    if not lovelace or not hasattr(lovelace, "resources") or lovelace.resources is None:
        return

    url = f"{URL_BASE}/{CARD_FILENAME}?v={INTEGRATION_VERSION}"
    url_base_no_version = f"{URL_BASE}/{CARD_FILENAME}"

    async def _check_and_register(_now=None) -> None:
        try:
            if not lovelace.resources.loaded:
                _LOGGER.debug("Lovelace 资源未加载，3秒后重试")
                async_call_later(hass, 3, _check_and_register)
                return

            existing = [r for r in lovelace.resources.async_items() if r["url"].startswith(URL_BASE)]

            for resource in existing:
                resource_path = resource["url"].split("?")[0]
                if resource_path == url_base_no_version:
                    if resource["url"] != url:
                        _LOGGER.info("更新卡片资源版本: %s -> %s", resource["url"], url)
                        await lovelace.resources.async_update_item(
                            resource["id"],
                            {"res_type": "module", "url": url},
                        )
                    return

            _LOGGER.info("持久化注册前端卡片: %s", url)
            await lovelace.resources.async_create_item(
                {"res_type": "module", "url": url}
            )
        except Exception as ex:
            _LOGGER.debug("Lovelace 资源注册失败: %s", ex)

    await _check_and_register()


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
