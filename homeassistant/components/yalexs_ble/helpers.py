"""Helpers for integrations that work with a Yale Access Bluetooth lock."""

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from typing import Protocol

from yalexs_ble import LockState, PushLock

from homeassistant.const import CONF_ADDRESS
from homeassistant.core import CALLBACK_TYPE, Context, HomeAssistant, callback
from homeassistant.util.hass_dict import HassKey

from . import YALEXSBLEConfigEntry
from .const import DOMAIN


class Attributor(Protocol):
    """Learns the cause of the changes of the lock status that a lock entity writes."""

    @callback
    def async_lock_status_changed(self, change: LockStatusChange) -> None:
        """Take a change of the lock status that the lock entity has written."""


@dataclass(eq=False)
class LockStatusChange:
    """A change of the lock status that a lock entity has written."""

    entity_id: str
    address: str
    new_state: LockState
    commanded: bool
    _is_latest: Callable[[LockStatusChange], bool] = field(repr=False)
    _set_changed_by: Callable[[str, Context | None], None] = field(repr=False)
    _applied: bool = field(default=False, init=False, repr=False)

    @property
    def latest(self) -> bool:
        """Return True until the entity starts writing its next change of the lock status."""
        return self._is_latest(self)

    @callback
    def async_set_changed_by(self, changed_by: str, context: Context | None) -> None:
        """Set changed_by on the written state, under context for that one write.

        The first set the lock entity applies wins, and a set on a change that is
        no longer latest does nothing.
        """
        if not self._applied and self.latest:
            # Set before the call, so a set made during the write does nothing.
            self._applied = True
            self._set_changed_by(changed_by, context)


DATA_ATTRIBUTORS: HassKey[dict[str, list[Attributor]]] = HassKey(
    "yalexs_ble_attributors"
)


@callback
def async_register_attributor(
    hass: HomeAssistant, address: str, attributor: Attributor
) -> CALLBACK_TYPE:
    """Register an attributor for the lock at address and return its remover."""
    attributors = hass.data.setdefault(DATA_ATTRIBUTORS, {}).setdefault(
        address.upper(), []
    )
    attributors.append(attributor)
    return partial(attributors.remove, attributor)


@callback
def async_get_push_lock(hass: HomeAssistant, address: str) -> PushLock | None:
    """Return the PushLock of the loaded entry for the lock at address."""
    address = address.upper()
    entry: YALEXSBLEConfigEntry
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        if entry.data[CONF_ADDRESS] == address:
            return entry.runtime_data.lock
    return None
