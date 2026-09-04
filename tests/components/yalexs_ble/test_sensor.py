"""Test the Yale Access Bluetooth sensors."""

from unittest.mock import Mock

import pytest
from yalexs_ble import DoorStatus, LockStatus

from homeassistant.components.yalexs_ble.const import (
    CONF_ACTIVITY_COUNT,
    CONF_BATTERY_REPORTING,
    OPTION_OFF,
    OPTION_ON,
)
from homeassistant.const import STATE_UNKNOWN, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import mock_entry, mock_push_lock, mock_push_lock_class, setup_entry

BATTERY = "sensor.front_door_battery"
BATTERY_VOLTAGE = "sensor.front_door_battery_voltage"
SIGNAL_STRENGTH = "sensor.front_door_signal_strength"
UNREAD_EVENTS = "sensor.front_door_unread_activity_records"

ACTIVITY_COUNT_LIBRARY = frozenset({"activity_count"})
CONFIGURE = frozenset({"configure"})


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
@pytest.mark.parametrize(
    ("options", "battery_sensors"),
    [
        pytest.param({}, True, id="unconfigured"),
        pytest.param({CONF_BATTERY_REPORTING: OPTION_ON}, True, id="on"),
        pytest.param({CONF_BATTERY_REPORTING: OPTION_OFF}, False, id="off"),
    ],
)
async def test_battery_sensors_follow_the_option(
    hass: HomeAssistant, options: dict[str, str], battery_sensors: bool
) -> None:
    """Test the battery sensors are created unless the option is off."""
    entry = mock_entry(options)

    await setup_entry(hass, entry, mock_push_lock_class(mock_push_lock()))

    assert (hass.states.get(BATTERY) is not None) is battery_sensors
    assert (hass.states.get(BATTERY_VOLTAGE) is not None) is battery_sensors
    assert hass.states.get(SIGNAL_STRENGTH) is not None


# No enabling fixture here: the option is the opt-in, so the sensor is enabled.
@pytest.mark.parametrize(
    ("options", "accepted", "created"),
    [
        pytest.param({}, ACTIVITY_COUNT_LIBRARY, False, id="unconfigured"),
        pytest.param(
            {CONF_ACTIVITY_COUNT: OPTION_OFF},
            ACTIVITY_COUNT_LIBRARY,
            False,
            id="off",
        ),
        pytest.param(
            {CONF_ACTIVITY_COUNT: OPTION_ON},
            ACTIVITY_COUNT_LIBRARY,
            True,
            id="on and accepted",
        ),
        pytest.param(
            {CONF_ACTIVITY_COUNT: OPTION_ON},
            frozenset(),
            False,
            id="on and ignored",
        ),
    ],
)
async def test_unread_events_sensor_follows_the_option(
    hass: HomeAssistant,
    options: dict[str, str],
    accepted: frozenset[str],
    created: bool,
) -> None:
    """Test the unread activity records sensor is created when asked for."""
    entry = mock_entry(options)
    push_lock = mock_push_lock(accepted=accepted)

    await setup_entry(hass, entry, mock_push_lock_class(push_lock, has=CONFIGURE))

    assert (hass.states.get(UNREAD_EVENTS) is not None) is created


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_unread_events_sensor_reads_the_count(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Test the sensor carries the count the library publishes."""
    entry = mock_entry({CONF_ACTIVITY_COUNT: OPTION_ON})
    push_lock = mock_push_lock(accepted=ACTIVITY_COUNT_LIBRARY)
    push_lock.lock_state = Mock(
        lock=LockStatus.UNLOCKED,
        door=DoorStatus.CLOSED,
        battery=None,
        auth=None,
        unread_event_count=242,
    )

    await setup_entry(hass, entry, mock_push_lock_class(push_lock, has=CONFIGURE))

    state = hass.states.get(UNREAD_EVENTS)
    assert state is not None
    assert state.state == "242"
    registry_entry = entity_registry.async_get(UNREAD_EVENTS)
    assert registry_entry is not None
    assert registry_entry.entity_category is EntityCategory.DIAGNOSTIC


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_unread_events_sensor_on_a_library_without_the_field(
    hass: HomeAssistant,
) -> None:
    """Test the sensor reads nothing when the library omits the count."""
    entry = mock_entry({CONF_ACTIVITY_COUNT: OPTION_ON})
    push_lock = mock_push_lock(accepted=ACTIVITY_COUNT_LIBRARY)
    push_lock.lock_state = Mock(
        spec=["lock", "door", "battery", "auth"],
        lock=LockStatus.UNLOCKED,
        door=DoorStatus.CLOSED,
        battery=None,
        auth=None,
    )

    await setup_entry(hass, entry, mock_push_lock_class(push_lock, has=CONFIGURE))

    state = hass.states.get(UNREAD_EVENTS)
    assert state is not None
    assert state.state == STATE_UNKNOWN
