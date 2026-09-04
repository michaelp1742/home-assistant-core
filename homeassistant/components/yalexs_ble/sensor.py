"""Support for yalexs ble sensors."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import override

from yalexs_ble import ConnectionInfo, LockInfo, LockState

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricPotential,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import YALEXSBLEConfigEntry
from .entity import YALEXSBLEEntity
from .models import LockOptions, YaleXSBLEData


@dataclass(frozen=True, kw_only=True)
class YaleXSBLESensorEntityDescription(SensorEntityDescription):
    """Describes Yale Access Bluetooth sensor entity."""

    value_fn: Callable[[LockState, LockInfo, ConnectionInfo], int | float | None]
    exists_fn: Callable[[LockOptions], bool] = lambda options: True


SENSORS: tuple[YaleXSBLESensorEntityDescription, ...] = (
    YaleXSBLESensorEntityDescription(
        key="",  # No key for the original RSSI sensor unique id
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        has_entity_name=True,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_registry_enabled_default=False,
        value_fn=lambda state, info, connection: connection.rssi,
    ),
    YaleXSBLESensorEntityDescription(
        key="battery_level",
        device_class=SensorDeviceClass.BATTERY,
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        has_entity_name=True,
        native_unit_of_measurement=PERCENTAGE,
        exists_fn=lambda options: options.battery_reporting,
        value_fn=lambda state, info, connection: (
            state.battery.percentage if state.battery else None
        ),
    ),
    YaleXSBLESensorEntityDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        has_entity_name=True,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        entity_registry_enabled_default=False,
        exists_fn=lambda options: options.battery_reporting,
        value_fn=lambda state, info, connection: (
            state.battery.voltage if state.battery else None
        ),
    ),
    YaleXSBLESensorEntityDescription(
        key="unread_events",
        translation_key="unread_events",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        has_entity_name=True,
        exists_fn=lambda options: options.activity_count,
        # None until the first reading, and always None on a library that does
        # not publish the field.
        value_fn=lambda state, info, connection: getattr(
            state, "unread_event_count", None
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: YALEXSBLEConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up YALE XS Bluetooth sensors."""
    data = entry.runtime_data
    async_add_entities(
        YaleXSBLESensor(description, data)
        for description in SENSORS
        if description.exists_fn(data.options)
    )


class YaleXSBLESensor(YALEXSBLEEntity, SensorEntity):
    """Yale XS Bluetooth sensor."""

    entity_description: YaleXSBLESensorEntityDescription

    def __init__(
        self,
        description: YaleXSBLESensorEntityDescription,
        data: YaleXSBLEData,
    ) -> None:
        """Initialize the sensor."""
        self.entity_description = description
        super().__init__(data)
        self._attr_unique_id = f"{data.lock.address}{description.key}"

    @callback
    @override
    def _async_update_state(
        self, new_state: LockState, lock_info: LockInfo, connection_info: ConnectionInfo
    ) -> None:
        """Update the state."""
        self._attr_native_value = self.entity_description.value_fn(
            new_state, lock_info, connection_info
        )
        super()._async_update_state(new_state, lock_info, connection_info)
