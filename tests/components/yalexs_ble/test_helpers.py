"""Test the Yale Access Bluetooth helpers for other integrations."""

import pytest

from homeassistant.components.yalexs_ble.helpers import async_get_push_lock
from homeassistant.core import HomeAssistant

from . import (
    YALE_ACCESS_LOCK_DISCOVERY_INFO,
    mock_entry,
    mock_push_lock,
    mock_push_lock_class,
    setup_entry,
)

ADDRESS = YALE_ACCESS_LOCK_DISCOVERY_INFO.address


@pytest.mark.parametrize(
    "address",
    [
        pytest.param(ADDRESS, id="as stored"),
        pytest.param(ADDRESS.lower(), id="lowercase"),
    ],
)
async def test_get_push_lock_returns_the_lock_of_the_loaded_entry(
    hass: HomeAssistant, address: str
) -> None:
    """Test the lookup returns the PushLock of the loaded entry at the address."""
    push_lock = mock_push_lock()
    await setup_entry(hass, mock_entry(), mock_push_lock_class(push_lock))

    assert async_get_push_lock(hass, address) is push_lock


async def test_get_push_lock_returns_none_for_an_unknown_address(
    hass: HomeAssistant,
) -> None:
    """Test the lookup returns None for an address no entry has."""
    await setup_entry(hass, mock_entry(), mock_push_lock_class(mock_push_lock()))

    assert async_get_push_lock(hass, "11:22:33:44:55:66") is None


async def test_get_push_lock_returns_none_for_an_unloaded_entry(
    hass: HomeAssistant,
) -> None:
    """Test the lookup returns None once the entry at the address is unloaded."""
    entry = mock_entry()
    await setup_entry(hass, entry, mock_push_lock_class(mock_push_lock()))

    await hass.config_entries.async_unload(entry.entry_id)

    assert async_get_push_lock(hass, ADDRESS) is None
