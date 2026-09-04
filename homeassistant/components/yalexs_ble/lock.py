"""Support for Yale Access Bluetooth locks."""

from typing import Any, override

from yalexs_ble import ConnectionInfo, LockInfo, LockState, LockStatus

from homeassistant.components.lock import (
    DOMAIN as LOCK_DOMAIN,
    LockEntity,
    LockEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import YALEXSBLEConfigEntry
from .const import DOMAIN
from .entity import YALEXSBLEEntity
from .models import YaleXSBLEData

# The unlatch statuses arrived with the library release that added
# PushLock.unlatch(). On an older library both resolve to None, which no
# reported status is, so the branches that compare against them are inert.
_UNLATCHING = getattr(LockStatus, "UNLATCHING", None)
_UNLATCHED = getattr(LockStatus, "UNLATCHED", None)


def _secure_mode_unique_id(address: str) -> str:
    """Return the secure mode lock's unique id for a lock address."""
    return f"{address}_secure_mode"


@callback
def _async_enable_secure_mode_lock(
    hass: HomeAssistant, entry: YALEXSBLEConfigEntry
) -> None:
    """Clear an integration disable on the secure mode lock's registry entry."""
    # The registry takes the enabled default only at first registration, so an
    # existing row the integration disabled is enabled here when the choice is
    # on. A row the user disabled is theirs, and so is one the entry's
    # preference against new entities disabled. Clearing the disable also makes
    # Home Assistant reload the entry once more thirty seconds later, though
    # the entity is added in this setup.
    if entry.pref_disable_new_entities:
        return
    entity_registry = er.async_get(hass)
    entity_id = entity_registry.async_get_entity_id(
        LOCK_DOMAIN, DOMAIN, _secure_mode_unique_id(entry.runtime_data.lock.address)
    )
    if entity_id is None:
        return
    existing = entity_registry.async_get(entity_id)
    if existing and existing.disabled_by is er.RegistryEntryDisabler.INTEGRATION:
        entity_registry.async_update_entity(entity_id, disabled_by=None)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: YALEXSBLEConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up locks."""
    data = entry.runtime_data
    entities: list[YaleXSBLEBaseLock] = [YaleXSBLELock(data)]
    if data.options.secure_mode:
        if data.options.secure_mode_enabled:
            _async_enable_secure_mode_lock(hass, entry)
        entities.append(YaleXSBLESecureModeLock(data))
    async_add_entities(entities)


class YaleXSBLEBaseLock(YALEXSBLEEntity, LockEntity):
    """A yale xs ble lock."""

    _secure_mode: bool = False

    @callback
    @override
    def _async_update_state(
        self, new_state: LockState, lock_info: LockInfo, connection_info: ConnectionInfo
    ) -> None:
        """Update the state."""
        self._attr_is_locked = False
        self._attr_is_locking = False
        self._attr_is_unlocking = False
        self._attr_is_jammed = False
        self._attr_is_open = False
        self._attr_is_opening = False
        lock_state = new_state.lock
        if lock_state is LockStatus.LOCKED:
            self._attr_is_locked = not self._secure_mode
        elif lock_state is LockStatus.LOCKING:
            self._attr_is_locking = True
        elif lock_state is LockStatus.UNLOCKING:
            self._attr_is_unlocking = True
        elif lock_state is LockStatus.SECUREMODE:
            self._attr_is_locked = True
        elif lock_state in (
            LockStatus.UNKNOWN_01,
            LockStatus.UNKNOWN_06,
            LockStatus.JAMMED,
        ):
            self._attr_is_jammed = True
        elif lock_state is _UNLATCHING:
            self._attr_is_opening = True
        elif lock_state is _UNLATCHED:
            self._attr_is_open = True
        elif lock_state is LockStatus.UNKNOWN:
            self._attr_is_locked = None
        super()._async_update_state(new_state, lock_info, connection_info)

    @override
    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the lock."""
        await self._device.unlock()


class YaleXSBLELock(YaleXSBLEBaseLock, LockEntity):
    """A yale xs ble lock not in secure mode."""

    _attr_name = None

    def __init__(self, data: YaleXSBLEData) -> None:
        """Initialize the entity."""
        super().__init__(data)
        if data.options.unlatch:
            self._attr_supported_features = LockEntityFeature.OPEN

    @override
    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the lock."""
        await self._device.lock()

    @override
    async def async_open(self, **kwargs: Any) -> None:
        """Unlatch the lock."""
        # The method arrives with the library release that carries the unlatch
        # key, and the open feature is offered only where that key was
        # accepted, so it is read with a default rather than named.
        unlatch: Any = getattr(self._device, "unlatch", None)
        await unlatch()


class YaleXSBLESecureModeLock(YaleXSBLEBaseLock):
    """A yale xs ble lock in secure mode."""

    _attr_translation_key = "secure_mode"
    _secure_mode = True

    def __init__(self, data: YaleXSBLEData) -> None:
        """Initialize the entity."""
        super().__init__(data)
        self._attr_unique_id = _secure_mode_unique_id(self._device.address)
        self._attr_entity_registry_enabled_default = data.options.secure_mode_enabled

    @callback
    @override
    def _async_update_state(
        self, new_state: LockState, lock_info: LockInfo, connection_info: ConnectionInfo
    ) -> None:
        """Update the state.

        The unlatch statuses describe the latch, which this entity does not
        model, so it goes on reporting whether the lock is in secure mode.
        """
        super()._async_update_state(new_state, lock_info, connection_info)
        self._attr_is_opening = False
        self._attr_is_open = False

    @override
    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the lock."""
        await self._device.securemode()
