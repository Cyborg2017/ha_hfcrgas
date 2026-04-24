"""合燃华润燃气传感器平台."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HFCRGasCoordinator

import logging

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class HFCRGasSensorEntityDescription(SensorEntityDescription):
    """合肥燃气传感器描述."""

    value_fn: Callable[[dict], Any]


SENSOR_DESCRIPTIONS: list[HFCRGasSensorEntityDescription] = [
    HFCRGasSensorEntityDescription(
        key="meter_reading",
        translation_key="meter_reading",
        device_class=SensorDeviceClass.GAS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        icon="mdi:counter",
        value_fn=lambda data: data.get("meter_reading"),
    ),
    HFCRGasSensorEntityDescription(
        key="yesterday_gas_usage",
        translation_key="yesterday_gas_usage",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        icon="mdi:fire",
        value_fn=lambda data: data.get("yesterday_usage"),
    ),
    HFCRGasSensorEntityDescription(
        key="monthly_gas_usage",
        translation_key="monthly_gas_usage",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        icon="mdi:chart-bar",
        value_fn=lambda data: data.get("monthly_usage"),
    ),
    HFCRGasSensorEntityDescription(
        key="yearly_gas_usage",
        translation_key="yearly_gas_usage",
        device_class=SensorDeviceClass.GAS,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        icon="mdi:gas-cylinder",
        value_fn=lambda data: data.get("yearly_usage"),
    ),
    HFCRGasSensorEntityDescription(
        key="latest_bill_usage",
        translation_key="latest_bill_usage",
        device_class=SensorDeviceClass.GAS,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        icon="mdi:chart-bar",
        value_fn=lambda data: data.get("current_period_usage"),
    ),
    HFCRGasSensorEntityDescription(
        key="last_bill_amount",
        translation_key="last_bill_amount",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="CNY",
        icon="mdi:currency-cny",
        value_fn=lambda data: data.get("last_bill_amount"),
    ),
    HFCRGasSensorEntityDescription(
        key="last_bill_date",
        translation_key="last_bill_date",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:calendar",
        value_fn=lambda data: data.get("last_bill_date"),
    ),
    HFCRGasSensorEntityDescription(
        key="balance",
        translation_key="balance",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="CNY",
        icon="mdi:wallet",
        value_fn=lambda data: data.get("balance"),
    ),
    HFCRGasSensorEntityDescription(
        key="last_payment_amount",
        translation_key="last_payment_amount",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="CNY",
        icon="mdi:cash",
        value_fn=lambda data: data.get("last_payment_amount"),
    ),
    HFCRGasSensorEntityDescription(
        key="next_update_time",
        translation_key="next_update_time",
        icon="mdi:clock-outline",
        value_fn=lambda data: (
            data.get("next_update_time").strftime("%Y-%m-%d %H:%M")
            if data.get("next_update_time") else None
        ),
    ),
    HFCRGasSensorEntityDescription(
        key="daily_gas_usage_30d",
        translation_key="daily_gas_usage_30d",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        icon="mdi:chart-bar",
        value_fn=lambda data: data.get("total_30d"),
    ),
]


class HFCRGasSensorEntity(CoordinatorEntity[HFCRGasCoordinator], SensorEntity):
    """合燃华润燃气传感器实体."""

    _attr_has_entity_name = True

    entity_description: HFCRGasSensorEntityDescription

    def __init__(
        self,
        coordinator: HFCRGasCoordinator,
        description: HFCRGasSensorEntityDescription,
        huhao: str,
    ) -> None:
        """初始化传感器."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"hfcrgas_{huhao}_{description.key}"

        # 设备名称：地址
        address = coordinator.api.address or "未知地址"
        # 型号：用户名 - 户号
        user_name = coordinator.api.user_name or ""
        model = f"{user_name} - {huhao}" if user_name else huhao

        # 从 manifest.json 读取版本号
        import json
        from pathlib import Path
        manifest_path = Path(__file__).parent / "manifest.json"
        try:
            sw_version = json.loads(manifest_path.read_text(encoding="utf-8")).get("version", "unknown")
        except Exception:
            sw_version = "unknown"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, huhao)},
            "name": address,
            "manufacturer": "合肥华润燃气",
            "model": model,
            "sw_version": sw_version,
        }

        # 手动设置 entity ID，避免中文地址转拼音导致 ID 过长
        self.entity_id = f"sensor.hfcrgas_{huhao}_{description.key}"
        self.huhao = huhao

    @property
    def native_value(self) -> float | date | datetime | str | None:
        """返回传感器值."""
        if self.coordinator.data is None:
            return None
        value = self.entity_description.value_fn(self.coordinator.data)
        if value is not None:
            # 对时间戳类型特殊处理
            if self.entity_description.device_class == SensorDeviceClass.TIMESTAMP:
                if isinstance(value, datetime):
                    return value
                if isinstance(value, str):
                    try:
                        return datetime.fromisoformat(value)
                    except ValueError:
                        return None
                return None
            # 对日期类型特殊处理 - HA 要求返回 date 对象
            if self.entity_description.device_class == SensorDeviceClass.DATE:
                if isinstance(value, date):
                    return value
                if isinstance(value, str) and len(value) >= 10:
                    try:
                        return datetime.strptime(value[:10], "%Y-%m-%d").date()
                    except ValueError:
                        return None
                return None
            try:
                return float(value) if not isinstance(value, str) else value
            except (ValueError, TypeError):
                return value
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """返回额外属性."""
        attrs: dict[str, Any] = {}
        data = self.coordinator.data
        if data is None:
            return attrs

        if self.entity_description.key == "meter_reading":
            attrs["户号"] = data.get("huhao")
            attrs["用户名"] = data.get("user_name")
            attrs["地址"] = data.get("address")
            attrs["表类型"] = data.get("meter_type")
            attrs["表号"] = data.get("rqb_gh")
            attrs["是否物联网表"] = "是" if data.get("is_wlw") else "否"

        elif self.entity_description.key == "yesterday_gas_usage":
            daily_data = data.get("daily_data", {})
            if daily_data and isinstance(daily_data, dict):
                yql = daily_data.get("YQL", [])
                ri_qi = daily_data.get("riQi", [])
                if yql and ri_qi:
                    recent_days = min(7, len(yql))
                    for i in range(1, recent_days + 1):
                        idx = len(yql) - i
                        if idx >= 0:
                            date_str = ri_qi[idx][:10] if idx < len(ri_qi) else ""
                            try:
                                usage = float(yql[idx])
                            except (ValueError, IndexError):
                                usage = 0.0
                            attrs[date_str] = usage

        elif self.entity_description.key == "last_bill_amount":
            attrs["账单月份"] = data.get("last_bill_ym")
            attrs["账单日期"] = data.get("last_bill_date")
            bill_data = data.get("bill_data", {})
            if bill_data and isinstance(bill_data, dict):
                bills = bill_data.get("list", [])
                for bill in bills[:6]:
                    ym = bill.get("billYm", "")
                    amt = bill.get("totalAmt", "0")
                    usage = bill.get("bcyql", "0")
                    attrs[f"账单_{ym}"] = f"金额:{amt}元 用量:{usage}m³"

        elif self.entity_description.key == "monthly_gas_usage":
            attrs["统计方式"] = "按月累计（从日用量数据计算）"

        elif self.entity_description.key == "latest_bill_usage":
            attrs["账单月份"] = data.get("last_bill_ym")
            attrs["账单日期"] = data.get("last_bill_date")

        elif self.entity_description.key == "last_payment_amount":
            attrs["缴费日期"] = data.get("last_payment_date")

        elif self.entity_description.key == "daily_gas_usage_30d":
            daily_30d = data.get("daily_30d", [])
            if daily_30d:
                attrs["daylist"] = daily_30d
                attrs["30天总用气量"] = data.get("total_30d", 0)
                attrs["30天日均用气量"] = data.get("avg_30d", 0)
                attrs["用户名"] = data.get("user_name")
                attrs["地址"] = data.get("address")
                attrs["户号"] = data.get("huhao")
                attrs["余额"] = data.get("balance")
                attrs["本月用气量"] = data.get("monthly_usage")
                attrs["昨日用气量"] = data.get("yesterday_usage")
                attrs["表读数"] = data.get("meter_reading")
                attrs["最近出账日期"] = data.get("last_bill_date")
                attrs["最近出账用气量"] = data.get("current_period_usage")
                attrs["最近出账金额"] = data.get("last_bill_amount")
                attrs["年度出账用气量"] = data.get("yearly_usage")

        return attrs


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置传感器实体."""
    coordinator: HFCRGasCoordinator = entry.runtime_data

    # 首次获取数据，容忍失败（服务器504等不应阻止集成加载）
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:  # noqa: BLE001
        _LOGGER.warning("首次数据刷新失败，集成仍将加载")

    huhao = entry.data["huhao"]

    entities = [
        HFCRGasSensorEntity(coordinator, description, huhao)
        for description in SENSOR_DESCRIPTIONS
    ]

    async_add_entities(entities)
