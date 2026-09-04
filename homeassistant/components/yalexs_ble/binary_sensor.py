"""Support for yalexs ble binary sensors."""

from typing import override

from yalexs_ble import ConnectionInfo, DoorStatus, LockInfo, LockState, PushLock

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import YALEXSBLEConfigEntry
from .entity import YALEXSBLEEntity


def _door_sense(lock: PushLock) -> bool:
    """Return whether the library treats the lock as having a door sensor.

    PushLock.door_sense carries the door sense option and the model heuristic
    together, so the door entity and the door status requests follow one
    answer. A library without the property has the heuristic alone.
    """
    if hasattr(lock, "door_sense"):
        return bool(lock.door_sense)
    return bool(lock.lock_info and lock.lock_info.door_sense)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: YALEXSBLEConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up YALE XS binary sensors."""
    data = entry.runtime_data
    if _door_sense(data.lock):
        async_add_entities([YaleXSBLEDoorSensor(data)])


class YaleXSBLEDoorSensor(YALEXSBLEEntity, BinarySensorEntity):
    """Yale XS BLE binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.DOOR

    @callback
    @override
    def _async_update_state(
        self, new_state: LockState, lock_info: LockInfo, connection_info: ConnectionInfo
    ) -> None:
        """Update the state."""
        # The lock's Init state and its unknown 0x04 status carry no door reading,
        # so neither renders as a closed door.
        if new_state.door in (DoorStatus.UNKNOWN, DoorStatus.UNKNOWN_04):
            self._attr_is_on = None
        else:
            self._attr_is_on = new_state.door is DoorStatus.OPENED
        super()._async_update_state(new_state, lock_info, connection_info)
