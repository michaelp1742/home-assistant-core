"""Test the Yale Access Bluetooth binary sensors."""

import pytest
from yalexs_ble import DoorStatus

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from . import mock_entry, mock_push_lock, mock_push_lock_class, setup_entry

DOOR_SENSOR = "binary_sensor.front_door_door"


@pytest.mark.parametrize(
    ("door", "expected"),
    [
        pytest.param(DoorStatus.CLOSED, STATE_OFF, id="closed"),
        pytest.param(DoorStatus.OPENED, STATE_ON, id="opened"),
    ],
)
async def test_door_sensor_follows_the_library_answer(
    hass: HomeAssistant, door: DoorStatus, expected: str
) -> None:
    """Test the door sensor follows the library's own door sense answer."""
    entry = mock_entry()
    push_lock = mock_push_lock(door=door, door_sense=True)

    await setup_entry(hass, entry, mock_push_lock_class(push_lock))

    state = hass.states.get(DOOR_SENSOR)
    assert state is not None
    assert state.state == expected


async def test_no_door_sensor_when_the_library_says_the_lock_has_none(
    hass: HomeAssistant,
) -> None:
    """Test the door entity is absent when the library answers no."""
    entry = mock_entry()

    await setup_entry(
        hass, entry, mock_push_lock_class(mock_push_lock(door_sense=False))
    )

    assert hass.states.get(DOOR_SENSOR) is None


@pytest.mark.parametrize(
    ("model", "created"),
    [
        pytest.param("M1XXX012LU", True, id="model with a door sensor"),
        pytest.param("ASL-02", False, id="model without one"),
    ],
)
async def test_door_sensor_uses_the_model_heuristic_on_an_older_library(
    hass: HomeAssistant, model: str, created: bool
) -> None:
    """Test a library without the property falls back to the lock info."""
    entry = mock_entry()
    push_lock = mock_push_lock(model=model, door_sense=None)

    await setup_entry(hass, entry, mock_push_lock_class(push_lock))

    assert (hass.states.get(DOOR_SENSOR) is not None) is created


@pytest.mark.parametrize(
    "door",
    [
        pytest.param(DoorStatus.UNKNOWN, id="init"),
        pytest.param(DoorStatus.UNKNOWN_04, id="unknown_04"),
    ],
)
async def test_door_sensor_is_unknown_while_the_lock_has_no_door_reading(
    hass: HomeAssistant, door: DoorStatus
) -> None:
    """Test a status that carries no reading leaves the door sensor unknown."""
    entry = mock_entry()
    push_lock = mock_push_lock(door=door)

    await setup_entry(hass, entry, mock_push_lock_class(push_lock))

    state = hass.states.get(DOOR_SENSOR)
    assert state is not None
    assert state.state == STATE_UNKNOWN
