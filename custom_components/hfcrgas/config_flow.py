"""合肥燃气配置流程."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .api import HFCRGasAPI, HFCRGasAPIError, HFCRGasAuthError, validate_input
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class HFCRGasConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """合燃华润燃气配置流程."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """处理用户输入."""
        errors: dict[str, str] = {}

        if user_input is not None:
            huhao = user_input["huhao"]
            phone = user_input["phone"]

            # 检查是否已配置
            await self.async_set_unique_id(huhao)
            self._abort_if_unique_id_configured()

            try:
                api = await validate_input(huhao, phone)
            except HFCRGasAuthError:
                errors["base"] = "bind_failed"
            except HFCRGasAPIError as err:
                msg = str(err).lower()
                if "户号" in msg or "10" in msg:
                    errors["base"] = "invalid_huhao"
                elif "手机" in msg:
                    errors["base"] = "invalid_phone"
                else:
                    errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("未知异常")
                errors["base"] = "unknown"
            else:
                # 保存认证信息到配置中
                data = {
                    "huhao": huhao,
                    "phone": phone,
                    "open_id": api.open_id,
                    "encrypted_yhh": api.encrypted_yhh or "",
                    "resource_identifier": api.resource_identifier or "",
                    "rqb_gh": api.rqb_gh or "",
                    "rqb_id": api.rqb_id or "",
                    "user_name": api.user_name or "",
                    "address": api.address or "",
                    "meter_type": api.meter_type or "",
                    "is_wlw": api.is_wlw,
                }

                await api.close()

                return self.async_create_entry(
                    title="合燃华润燃气",
                    data=data,
                )

        data_schema = vol.Schema(
            {
                vol.Required("huhao"): str,
                vol.Required("phone"): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )
