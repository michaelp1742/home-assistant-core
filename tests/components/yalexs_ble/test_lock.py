"""Test the Yale Access Bluetooth locks."""

import asyncio
from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock, Mock, patch, sentinel

from freezegun.api import FrozenDateTimeFactory
import pytest
from yalexs_ble import DoorStatus, LockState, LockStatus

from homeassistant.components.lock import (
    ATTR_CHANGED_BY,
    DATA_COMPONENT as LOCK_DATA_COMPONENT,
    DOMAIN as LOCK_DOMAIN,
    SERVICE_OPEN,
    LockEntityFeature,
)
from homeassistant.components.yalexs_ble.const import (
    CONF_SECURE_MODE,
    CONF_UNLATCH,
    DOMAIN,
    OPTION_DEFAULT,
    OPTION_OFF,
    OPTION_ON,
)
from homeassistant.components.yalexs_ble.helpers import (
    LockStatusChange,
    async_register_attributor,
)
from homeassistant.components.yalexs_ble.lock import _UNLATCHED, _UNLATCHING
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    EVENT_STATE_CHANGED,
    SERVICE_LOCK,
    SERVICE_UNLOCK,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    Context,
    Event,
    EventStateChangedData,
    HomeAssistant,
    ServiceResponse,
    State,
    callback,
)
from homeassistant.exceptions import ServiceNotSupported
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event

from . import (
    YALE_ACCESS_LOCK_DISCOVERY_INFO,
    mock_entry,
    mock_push_lock,
    mock_push_lock_class,
    setup_entry,
)

from tests.common import async_capture_events

LOCK = "lock.front_door"
SECURE_MODE_LOCK = "lock.front_door_secure_mode"
DOOR_SENSOR = "binary_sensor.front_door_door"
BATTERY = "sensor.front_door_battery"
SECURE_MODE_UNIQUE_ID = f"{YALE_ACCESS_LOCK_DISCOVERY_INFO.address}_secure_mode"

UNLATCH_LIBRARY = frozenset({"configure", "unlatch"})


def _deliver(
    push_lock: MagicMock,
    status: LockStatus,
    *,
    door: DoorStatus = DoorStatus.CLOSED,
    battery: Mock | None = None,
    auth: Mock | None = None,
) -> None:
    """Deliver a lock state to every callback registered on the push lock."""
    state = LockState(lock=status, door=door, battery=battery, auth=auth)
    for call in push_lock.register_callback.call_args_list:
        call.args[0](state, push_lock.lock_info, push_lock.connection_info)


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
@pytest.mark.parametrize(
    ("options", "secure_mode_lock"),
    [
        pytest.param({}, True, id="unconfigured"),
        pytest.param({CONF_SECURE_MODE: OPTION_ON}, True, id="on"),
        pytest.param({CONF_SECURE_MODE: OPTION_OFF}, False, id="off"),
    ],
)
async def test_secure_mode_lock_follows_the_option(
    hass: HomeAssistant, options: dict[str, str], secure_mode_lock: bool
) -> None:
    """Test the secure mode lock is created unless the option is off."""
    entry = mock_entry(options)

    await setup_entry(hass, entry, mock_push_lock_class(mock_push_lock()))

    assert hass.states.get(LOCK) is not None
    assert (hass.states.get(SECURE_MODE_LOCK) is not None) is secure_mode_lock


async def test_secure_mode_lock_is_enabled_when_the_choice_is_on(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Test the choice on registers the secure mode lock enabled."""
    entry = mock_entry({CONF_SECURE_MODE: OPTION_ON})

    await setup_entry(hass, entry, mock_push_lock_class(mock_push_lock()))

    registry_entry = entity_registry.async_get(SECURE_MODE_LOCK)
    assert registry_entry is not None
    assert registry_entry.disabled_by is None
    assert hass.states.get(SECURE_MODE_LOCK) is not None


@pytest.mark.parametrize(
    ("disabled_by", "disable_new_entities", "expected", "has_state"),
    [
        pytest.param(
            er.RegistryEntryDisabler.INTEGRATION, False, None, True, id="integration"
        ),
        pytest.param(
            er.RegistryEntryDisabler.USER,
            False,
            er.RegistryEntryDisabler.USER,
            False,
            id="user",
        ),
        pytest.param(
            er.RegistryEntryDisabler.INTEGRATION,
            True,
            er.RegistryEntryDisabler.INTEGRATION,
            False,
            id="preference",
        ),
    ],
)
async def test_secure_mode_lock_enable_clears_only_the_integration_disable(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    disabled_by: er.RegistryEntryDisabler,
    disable_new_entities: bool,
    expected: er.RegistryEntryDisabler | None,
    has_state: bool,
) -> None:
    """Test setup clears its own disable on the row and leaves any other alone."""
    entry = mock_entry({CONF_SECURE_MODE: OPTION_ON})
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, pref_disable_new_entities=disable_new_entities
    )
    entity_registry.async_get_or_create(
        LOCK_DOMAIN,
        DOMAIN,
        SECURE_MODE_UNIQUE_ID,
        config_entry=entry,
        suggested_object_id="front_door_secure_mode",
        disabled_by=disabled_by,
    )

    await setup_entry(hass, entry, mock_push_lock_class(mock_push_lock()))

    registry_entry = entity_registry.async_get(SECURE_MODE_LOCK)
    assert registry_entry is not None
    assert registry_entry.disabled_by is expected
    assert (hass.states.get(SECURE_MODE_LOCK) is not None) is has_state


@pytest.mark.parametrize(
    "options",
    [
        pytest.param({}, id="unconfigured"),
        pytest.param({CONF_SECURE_MODE: OPTION_DEFAULT}, id="default"),
    ],
)
async def test_secure_mode_lock_stays_disabled_when_not_set(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, options: dict[str, str]
) -> None:
    """Test the secure mode lock is registered disabled without the choice."""
    entry = mock_entry(options)

    await setup_entry(hass, entry, mock_push_lock_class(mock_push_lock()))

    registry_entry = entity_registry.async_get(SECURE_MODE_LOCK)
    assert registry_entry is not None
    assert registry_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION


@pytest.mark.parametrize(
    "options",
    [
        pytest.param({}, id="unconfigured"),
        pytest.param({CONF_SECURE_MODE: OPTION_DEFAULT}, id="default"),
    ],
)
async def test_an_integration_disable_survives_a_choice_that_is_not_on(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, options: dict[str, str]
) -> None:
    """Test a choice that is not on leaves an existing integration disable alone."""
    entry = mock_entry(options)
    entry.add_to_hass(hass)
    entity_registry.async_get_or_create(
        LOCK_DOMAIN,
        DOMAIN,
        SECURE_MODE_UNIQUE_ID,
        config_entry=entry,
        suggested_object_id="front_door_secure_mode",
        disabled_by=er.RegistryEntryDisabler.INTEGRATION,
    )

    await setup_entry(hass, entry, mock_push_lock_class(mock_push_lock()))

    registry_entry = entity_registry.async_get(SECURE_MODE_LOCK)
    assert registry_entry is not None
    assert registry_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get(SECURE_MODE_LOCK) is None


async def test_secure_mode_lock_keeps_an_enabled_row_when_returned_to_not_set(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Test a row enabled while the choice was on stays enabled after not set."""
    entry = mock_entry({})
    entry.add_to_hass(hass)
    entity_registry.async_get_or_create(
        LOCK_DOMAIN,
        DOMAIN,
        SECURE_MODE_UNIQUE_ID,
        config_entry=entry,
        suggested_object_id="front_door_secure_mode",
        disabled_by=None,
    )

    await setup_entry(hass, entry, mock_push_lock_class(mock_push_lock()))

    registry_entry = entity_registry.async_get(SECURE_MODE_LOCK)
    assert registry_entry is not None
    assert registry_entry.disabled_by is None
    assert hass.states.get(SECURE_MODE_LOCK) is not None


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
@pytest.mark.parametrize(
    ("options", "accepted", "features"),
    [
        pytest.param(
            {CONF_UNLATCH: OPTION_ON},
            frozenset({"unlatch"}),
            LockEntityFeature.OPEN,
            id="on and accepted",
        ),
        pytest.param(
            {CONF_UNLATCH: OPTION_ON},
            frozenset(),
            LockEntityFeature(0),
            id="on and ignored",
        ),
        pytest.param(
            {}, frozenset({"unlatch"}), LockEntityFeature(0), id="unconfigured"
        ),
    ],
)
async def test_open_feature_follows_the_unlatch_option(
    hass: HomeAssistant,
    options: dict[str, str],
    accepted: frozenset[str],
    features: LockEntityFeature,
) -> None:
    """Test the open feature needs the choice and the library's acceptance."""
    entry = mock_entry(options)
    push_lock = mock_push_lock(accepted=accepted)

    await setup_entry(hass, entry, mock_push_lock_class(push_lock, has=UNLATCH_LIBRARY))

    state = hass.states.get(LOCK)
    assert state is not None
    assert state.attributes[ATTR_SUPPORTED_FEATURES] is features
    secure_mode_state = hass.states.get(SECURE_MODE_LOCK)
    assert secure_mode_state is not None
    assert secure_mode_state.attributes[ATTR_SUPPORTED_FEATURES] is LockEntityFeature(0)


async def test_open_unlatches_the_lock(hass: HomeAssistant) -> None:
    """Test the open action asks the lock to pull the latch back."""
    entry = mock_entry({CONF_UNLATCH: OPTION_ON})
    push_lock = mock_push_lock(accepted=frozenset({"unlatch"}))

    await setup_entry(hass, entry, mock_push_lock_class(push_lock, has=UNLATCH_LIBRARY))
    await hass.services.async_call(
        LOCK_DOMAIN, SERVICE_OPEN, {ATTR_ENTITY_ID: LOCK}, blocking=True
    )

    push_lock.unlatch.assert_awaited_once()


async def test_open_is_refused_without_the_option(hass: HomeAssistant) -> None:
    """Test the open action is not offered when the option is not on."""
    entry = mock_entry()
    push_lock = mock_push_lock()

    await setup_entry(hass, entry, mock_push_lock_class(push_lock, has=UNLATCH_LIBRARY))

    with pytest.raises(ServiceNotSupported):
        await hass.services.async_call(
            LOCK_DOMAIN, SERVICE_OPEN, {ATTR_ENTITY_ID: LOCK}, blocking=True
        )
    push_lock.unlatch.assert_not_awaited()


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        pytest.param(sentinel.UNLATCHING, "opening", id="unlatching"),
        pytest.param(sentinel.UNLATCHED, "open", id="unlatched"),
        pytest.param(LockStatus.UNLOCKED, "unlocked", id="unlocked"),
        pytest.param(LockStatus.JAMMED, "jammed", id="jammed"),
    ],
)
async def test_unlatch_statuses_map_to_opening_and_open(
    hass: HomeAssistant, status: object, expected: str
) -> None:
    """Test the two unlatch statuses reach the open and opening states."""
    entry = mock_entry()
    push_lock = mock_push_lock()
    push_lock.lock_state = LockState(
        lock=status,
        door=DoorStatus.CLOSED,
        battery=None,
        auth=None,
    )

    with (
        patch(
            "homeassistant.components.yalexs_ble.lock._UNLATCHING", sentinel.UNLATCHING
        ),
        patch(
            "homeassistant.components.yalexs_ble.lock._UNLATCHED", sentinel.UNLATCHED
        ),
    ):
        await setup_entry(hass, entry, mock_push_lock_class(push_lock))

    state = hass.states.get(LOCK)
    assert state is not None
    assert state.state == expected


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        pytest.param(LockStatus.LOCKED, "locked", id="locked"),
        pytest.param(LockStatus.UNLOCKED, "unlocked", id="unlocked"),
        pytest.param(LockStatus.LOCKING, "locking", id="locking"),
        pytest.param(LockStatus.JAMMED, "jammed", id="jammed"),
    ],
)
async def test_statuses_map_as_before_on_a_library_without_unlatch(
    hass: HomeAssistant, status: LockStatus, expected: str
) -> None:
    """Test the unlatch branches are inert when the statuses do not exist."""
    entry = mock_entry()
    push_lock = mock_push_lock(lock=status)

    with (
        patch("homeassistant.components.yalexs_ble.lock._UNLATCHING", None),
        patch("homeassistant.components.yalexs_ble.lock._UNLATCHED", None),
    ):
        await setup_entry(hass, entry, mock_push_lock_class(push_lock))

    state = hass.states.get(LOCK)
    assert state is not None
    assert state.state == expected


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_the_secure_mode_lock_does_not_follow_the_latch(
    hass: HomeAssistant,
) -> None:
    """Test the secure mode entity reports the lock, not the latch."""
    entry = mock_entry()
    push_lock = mock_push_lock()

    with (
        patch(
            "homeassistant.components.yalexs_ble.lock._UNLATCHING", sentinel.UNLATCHING
        ),
        patch(
            "homeassistant.components.yalexs_ble.lock._UNLATCHED", sentinel.UNLATCHED
        ),
    ):
        await setup_entry(hass, entry, mock_push_lock_class(push_lock))
        _deliver(push_lock, sentinel.UNLATCHED)
        await hass.async_block_till_done()

    assert hass.states.get(LOCK).state == "open"
    assert hass.states.get(SECURE_MODE_LOCK).state == "unlocked"


@pytest.mark.parametrize(
    ("latch_status", "resting_status", "expected"),
    [
        pytest.param(
            sentinel.UNLATCHED, LockStatus.LOCKED, "locked", id="locked after"
        ),
        pytest.param(
            sentinel.UNLATCHING, LockStatus.UNLOCKED, "unlocked", id="unlocked after"
        ),
    ],
)
async def test_the_open_states_clear_when_the_lock_settles(
    hass: HomeAssistant,
    latch_status: object,
    resting_status: LockStatus,
    expected: str,
) -> None:
    """Test the resting status replaces the open and opening states."""
    entry = mock_entry()
    push_lock = mock_push_lock()

    with (
        patch(
            "homeassistant.components.yalexs_ble.lock._UNLATCHING", sentinel.UNLATCHING
        ),
        patch(
            "homeassistant.components.yalexs_ble.lock._UNLATCHED", sentinel.UNLATCHED
        ),
    ):
        await setup_entry(hass, entry, mock_push_lock_class(push_lock))
        _deliver(push_lock, latch_status)
        await hass.async_block_till_done()
        assert hass.states.get(LOCK).state in ("open", "opening")

        _deliver(push_lock, resting_status)
        await hass.async_block_till_done()

    assert hass.states.get(LOCK).state == expected


@pytest.mark.skipif(
    not hasattr(LockStatus, "UNLATCHING"),
    reason=(
        "the installed library has no unlatch statuses, so nothing here holds the "
        "names until the requirement moves"
    ),
)
def test_the_unlatch_statuses_name_the_library_members() -> None:
    """Test the module constants read the library's own status members."""
    assert _UNLATCHING is LockStatus.UNLATCHING
    assert _UNLATCHED is LockStatus.UNLATCHED


class _Attributor:
    """Keep each change it is told about, with the lock entity's state at that moment."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize with the instance whose states it reads."""
        self.hass = hass
        self.changes: list[LockStatusChange] = []
        self.states: list[State | None] = []

    @callback
    def async_lock_status_changed(self, change: LockStatusChange) -> None:
        """Keep the change and the state written for it."""
        self.changes.append(change)
        self.states.append(self.hass.states.get(change.entity_id))


async def _setup_attributed_lock(
    hass: HomeAssistant,
    *attributors: _Attributor,
    options: dict[str, str] | None = None,
    has: frozenset[str] = frozenset(),
    **lock: Any,
) -> MagicMock:
    """Set up the lock entities and register the attributors for the lock."""
    push_lock = mock_push_lock(**lock)
    await setup_entry(
        hass, mock_entry(options), mock_push_lock_class(push_lock, has=has)
    )
    for attributor in attributors:
        async_register_attributor(hass, push_lock.address, attributor)
    return push_lock


async def _call_lock(hass: HomeAssistant, context: Context) -> None:
    """Call the lock action on the lock entity under context."""
    await hass.services.async_call(
        LOCK_DOMAIN,
        SERVICE_LOCK,
        {ATTR_ENTITY_ID: LOCK},
        blocking=True,
        context=context,
    )


def _lock_states(events: list[Event[EventStateChangedData]]) -> list[State | None]:
    """Return the new state of each captured state_changed event for the lock entity."""
    return [
        event.data["new_state"] for event in events if event.data["entity_id"] == LOCK
    ]


async def test_a_change_is_written_at_once_with_no_attributor(
    hass: HomeAssistant,
) -> None:
    """Test a change of the lock status is written at once with no attributor."""
    push_lock = await _setup_attributed_lock(hass, lock=LockStatus.LOCKED)

    _deliver(push_lock, LockStatus.UNLOCKED)

    state = hass.states.get(LOCK)
    assert state.state == "unlocked"
    assert state.attributes.get(ATTR_CHANGED_BY) is None


async def test_an_attributor_sets_changed_by_on_the_written_change(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Test the attributor is told after the write and sets changed_by on the change under its context."""
    attributor = _Attributor(hass)
    push_lock = await _setup_attributed_lock(hass, attributor, lock=LockStatus.LOCKED)

    _deliver(push_lock, LockStatus.UNLOCKED)

    written = hass.states.get(LOCK)
    assert written.state == "unlocked"
    assert written.attributes.get(ATTR_CHANGED_BY) is None
    assert attributor.states == [written]
    (change,) = attributor.changes
    assert change.entity_id == LOCK
    assert change.address == push_lock.address
    assert change.new_state.lock is LockStatus.UNLOCKED
    assert change.commanded is False
    assert change.latest
    freezer.tick(timedelta(seconds=1))
    context = Context()
    change.async_set_changed_by("Cleaner", context)
    state = hass.states.get(LOCK)
    assert state.state == "unlocked"
    assert state.attributes[ATTR_CHANGED_BY] == "Cleaner"
    assert state.context is context
    assert state.last_changed == written.last_changed
    assert state.last_updated == written.last_updated + timedelta(seconds=1)


async def test_the_first_set_on_a_change_wins(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Test the first set on a change writes, and a second set does nothing."""
    first = _Attributor(hass)
    second = _Attributor(hass)
    push_lock = await _setup_attributed_lock(
        hass, first, second, lock=LockStatus.LOCKED
    )
    _deliver(push_lock, LockStatus.UNLOCKED)
    (change,) = second.changes
    assert first.changes == [change]
    freezer.tick(timedelta(seconds=0.5))
    context = Context()
    change.async_set_changed_by("Cleaner", context)
    written = hass.states.get(LOCK)
    freezer.tick(timedelta(seconds=0.1))

    change.async_set_changed_by("Visitor", Context())

    state = hass.states.get(LOCK)
    assert state.attributes[ATTR_CHANGED_BY] == "Cleaner"
    assert state.context is context
    assert state.last_reported == written.last_reported


async def test_a_set_during_the_sets_own_write_does_nothing(
    hass: HomeAssistant,
) -> None:
    """Test a state listener's second set on a change during the first set's write writes nothing."""
    attributor = _Attributor(hass)
    push_lock = await _setup_attributed_lock(hass, attributor, lock=LockStatus.LOCKED)
    _deliver(push_lock, LockStatus.UNLOCKED)
    (change,) = attributor.changes
    sets: list[str | None] = []

    @callback
    def _set_again(event: Event[EventStateChangedData]) -> None:
        """Set changed_by on the change again while its first set is written."""
        sets.append(event.data["new_state"].attributes.get(ATTR_CHANGED_BY))
        change.async_set_changed_by("Visitor", Context())

    async_track_state_change_event(hass, LOCK, _set_again)

    change.async_set_changed_by("Cleaner", Context())

    assert sets == ["Cleaner"]
    assert hass.states.get(LOCK).attributes[ATTR_CHANGED_BY] == "Cleaner"


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
@pytest.mark.parametrize(
    (
        "options",
        "has",
        "accepted",
        "entity_id",
        "service",
        "method",
        "start",
        "external",
        "commanded",
        "expected",
    ),
    [
        pytest.param(
            {},
            frozenset(),
            frozenset(),
            LOCK,
            SERVICE_UNLOCK,
            "unlock",
            LockStatus.UNLOCKED,
            LockStatus.LOCKED,
            LockStatus.UNLOCKED,
            "unlocked",
            id="unlock",
        ),
        pytest.param(
            {},
            frozenset(),
            frozenset(),
            LOCK,
            SERVICE_LOCK,
            "lock",
            LockStatus.LOCKED,
            LockStatus.UNLOCKED,
            LockStatus.LOCKED,
            "locked",
            id="lock",
        ),
        pytest.param(
            {CONF_SECURE_MODE: OPTION_ON},
            frozenset(),
            frozenset(),
            SECURE_MODE_LOCK,
            SERVICE_LOCK,
            "securemode",
            LockStatus.UNLOCKED,
            LockStatus.LOCKED,
            LockStatus.SECUREMODE,
            "locked",
            id="secure mode lock",
        ),
        pytest.param(
            {CONF_UNLATCH: OPTION_ON},
            UNLATCH_LIBRARY,
            frozenset({"unlatch"}),
            LOCK,
            SERVICE_OPEN,
            "unlatch",
            LockStatus.LOCKED,
            LockStatus.UNLOCKED,
            sentinel.UNLATCHED,
            "open",
            id="open",
        ),
    ],
)
@patch("homeassistant.components.yalexs_ble.lock._UNLATCHED", sentinel.UNLATCHED)
async def test_a_change_during_a_command_is_commanded(
    hass: HomeAssistant,
    options: dict[str, str],
    has: frozenset[str],
    accepted: frozenset[str],
    entity_id: str,
    service: str,
    method: str,
    start: LockStatus,
    external: LockStatus,
    commanded: object,
    expected: str,
) -> None:
    """Test a change the library reports while a command is awaited is written at once and marked commanded."""
    attributor = _Attributor(hass)
    push_lock = await _setup_attributed_lock(
        hass, attributor, options=options, has=has, lock=start, accepted=accepted
    )
    _deliver(push_lock, external)
    changes = {change.entity_id: change for change in attributor.changes}
    changes[entity_id].async_set_changed_by("Cleaner", Context())
    assert hass.states.get(entity_id).attributes[ATTR_CHANGED_BY] == "Cleaner"
    attributor.changes.clear()
    getattr(push_lock, method).side_effect = lambda: _deliver(push_lock, commanded)
    call_context = Context()

    await hass.services.async_call(
        LOCK_DOMAIN,
        service,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
        context=call_context,
    )

    assert attributor.changes
    assert all(change.commanded for change in attributor.changes)
    state = hass.states.get(entity_id)
    assert state.state == expected
    assert state.attributes.get(ATTR_CHANGED_BY) is None
    assert state.context.id == call_context.id
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.runtime_data.lock_commands_in_flight == 0


async def test_a_change_while_a_second_command_is_awaited_is_commanded(
    hass: HomeAssistant,
) -> None:
    """Test a change reported after one of two awaited commands returns is still marked commanded."""
    attributor = _Attributor(hass)
    push_lock = await _setup_attributed_lock(hass, attributor, lock=LockStatus.LOCKED)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    entity = hass.data[LOCK_DATA_COMPONENT].get_entity(LOCK)
    unlock_answer = asyncio.Event()
    lock_answer = asyncio.Event()
    push_lock.unlock.side_effect = unlock_answer.wait
    push_lock.lock.side_effect = lock_answer.wait
    unlock = hass.async_create_task(entity.async_unlock())
    lock = hass.async_create_task(entity.async_lock())
    unlock_answer.set()
    await unlock

    _deliver(push_lock, LockStatus.UNLOCKED)
    lock_answer.set()
    await lock

    (change,) = attributor.changes
    assert change.commanded is True
    assert entry.runtime_data.lock_commands_in_flight == 0


async def test_a_failed_command_lowers_the_count(hass: HomeAssistant) -> None:
    """Test a command that raises leaves later changes not commanded."""
    attributor = _Attributor(hass)
    push_lock = await _setup_attributed_lock(hass, attributor, lock=LockStatus.LOCKED)
    push_lock.unlock.side_effect = RuntimeError("no answer")
    with pytest.raises(RuntimeError):
        await hass.services.async_call(
            LOCK_DOMAIN, SERVICE_UNLOCK, {ATTR_ENTITY_ID: LOCK}, blocking=True
        )

    _deliver(push_lock, LockStatus.UNLOCKED)

    (change,) = attributor.changes
    assert change.commanded is False
    assert hass.states.get(LOCK).state == "unlocked"


@pytest.mark.parametrize(
    ("update", "entity_id", "expected"),
    [
        pytest.param({"door": DoorStatus.OPENED}, DOOR_SENSOR, "on", id="door"),
        pytest.param(
            {"battery": Mock(voltage=5.9, percentage=80)}, BATTERY, "80", id="battery"
        ),
        pytest.param({"auth": Mock(successful=False)}, LOCK, "unavailable", id="auth"),
    ],
)
async def test_an_update_of_the_same_status_keeps_changed_by(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    update: dict[str, Any],
    entity_id: str,
    expected: str,
) -> None:
    """Test an update that keeps the lock status is written at once, keeps changed_by, and tells no attributor."""
    attributor = _Attributor(hass)
    push_lock = await _setup_attributed_lock(hass, attributor, lock=LockStatus.LOCKED)
    _deliver(push_lock, LockStatus.UNLOCKED)
    attributor.changes[0].async_set_changed_by("Cleaner", Context())
    set_at = hass.states.get(LOCK).last_reported
    freezer.tick(timedelta(seconds=1))

    _deliver(push_lock, LockStatus.UNLOCKED, **update)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == expected
    assert hass.states.get(LOCK).last_reported > set_at
    assert len(attributor.changes) == 1
    _deliver(push_lock, LockStatus.UNLOCKED)
    state = hass.states.get(LOCK)
    assert state.state == "unlocked"
    assert state.attributes[ATTR_CHANGED_BY] == "Cleaner"


async def test_a_change_of_the_lock_status_clears_changed_by(
    hass: HomeAssistant,
) -> None:
    """Test a change after a set is written at once with changed_by cleared and told as a new change."""
    attributor = _Attributor(hass)
    push_lock = await _setup_attributed_lock(hass, attributor, lock=LockStatus.LOCKED)
    _deliver(push_lock, LockStatus.UNLOCKED)
    attributor.changes[0].async_set_changed_by("Cleaner", Context())

    _deliver(push_lock, LockStatus.LOCKED)

    state = hass.states.get(LOCK)
    assert state.state == "locked"
    assert state.attributes.get(ATTR_CHANGED_BY) is None
    unlocked, locked = attributor.changes
    assert attributor.states[1] == state
    assert locked.new_state.lock is LockStatus.LOCKED
    assert locked.latest
    assert not unlocked.latest


async def test_a_set_on_an_earlier_change_does_nothing(hass: HomeAssistant) -> None:
    """Test a set on a change a later change of the lock status replaced writes nothing."""
    attributor = _Attributor(hass)
    push_lock = await _setup_attributed_lock(hass, attributor, lock=LockStatus.LOCKED)
    _deliver(push_lock, LockStatus.UNLOCKED)
    _deliver(push_lock, LockStatus.LOCKED)
    written = hass.states.get(LOCK)
    unlocked, _ = attributor.changes

    unlocked.async_set_changed_by("Cleaner", Context())

    state = hass.states.get(LOCK)
    assert state.state == "locked"
    assert state.attributes.get(ATTR_CHANGED_BY) is None
    assert state.last_reported == written.last_reported


async def test_changes_with_equal_fields_are_distinct(hass: HomeAssistant) -> None:
    """Test two changes of one entity to the same status are told apart by identity."""
    attributor = _Attributor(hass)
    push_lock = await _setup_attributed_lock(hass, attributor, lock=LockStatus.LOCKED)

    _deliver(push_lock, LockStatus.UNLOCKED)
    _deliver(push_lock, LockStatus.LOCKED)
    _deliver(push_lock, LockStatus.UNLOCKED)

    first, _, third = attributor.changes
    assert first.new_state == third.new_state
    assert first != third
    assert len({first, third}) == 2


async def test_a_set_on_the_earlier_change_during_the_write_does_nothing(
    hass: HomeAssistant,
) -> None:
    """Test a state listener's set on the earlier change during a later change's write writes nothing."""
    attributor = _Attributor(hass)
    push_lock = await _setup_attributed_lock(hass, attributor, lock=LockStatus.LOCKED)
    _deliver(push_lock, LockStatus.UNLOCKED)
    (unlocked,) = attributor.changes
    sets: list[str] = []

    @callback
    def _set_earlier(event: Event[EventStateChangedData]) -> None:
        """Set changed_by on the earlier change while the later change is written."""
        sets.append(event.data["new_state"].state)
        unlocked.async_set_changed_by("Cleaner", Context())

    async_track_state_change_event(hass, LOCK, _set_earlier)
    events = async_capture_events(hass, EVENT_STATE_CHANGED)

    _deliver(push_lock, LockStatus.LOCKED)

    assert sets == ["locked"]
    (locked,) = _lock_states(events)
    assert locked.state == "locked"
    assert locked.attributes.get(ATTR_CHANGED_BY) is None


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_each_lock_entity_tells_its_own_change(hass: HomeAssistant) -> None:
    """Test the two lock entities each tell the attributor with their own change, and each set writes its own entity."""
    attributor = _Attributor(hass)
    push_lock = await _setup_attributed_lock(
        hass, attributor, options={CONF_SECURE_MODE: OPTION_ON}
    )

    _deliver(push_lock, LockStatus.LOCKED)

    changes = {change.entity_id: change for change in attributor.changes}
    assert set(changes) == {LOCK, SECURE_MODE_LOCK}
    assert changes[LOCK] is not changes[SECURE_MODE_LOCK]
    assert changes[LOCK].new_state is changes[SECURE_MODE_LOCK].new_state
    changes[LOCK].async_set_changed_by("Cleaner", Context())
    changes[SECURE_MODE_LOCK].async_set_changed_by("Neighbour", Context())
    assert hass.states.get(LOCK).attributes[ATTR_CHANGED_BY] == "Cleaner"
    assert hass.states.get(SECURE_MODE_LOCK).attributes[ATTR_CHANGED_BY] == "Neighbour"


async def test_a_change_after_a_set_is_written_without_its_context(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Test a change after a set is written without the context the set gave."""
    attributor = _Attributor(hass)
    push_lock = await _setup_attributed_lock(hass, attributor, lock=LockStatus.LOCKED)
    _deliver(push_lock, LockStatus.UNLOCKED)
    context = Context()
    attributor.changes[0].async_set_changed_by("Cleaner", context)
    assert hass.states.get(LOCK).context is context
    freezer.tick(timedelta(seconds=3))

    _deliver(push_lock, LockStatus.LOCKING)

    state = hass.states.get(LOCK)
    assert state.state == "locking"
    assert state.context.id != context.id


async def test_a_set_during_a_command_keeps_the_service_calls_context(
    hass: HomeAssistant,
) -> None:
    """Test a set during a command writes under its context, and the command's change under the call's."""
    attributor = _Attributor(hass)
    push_lock = await _setup_attributed_lock(hass, attributor, lock=LockStatus.LOCKED)
    _deliver(push_lock, LockStatus.UNLOCKED)
    (unlocked,) = attributor.changes
    set_context = Context()

    def _lock() -> None:
        """Set changed_by on the earlier change, then report the command's change."""
        unlocked.async_set_changed_by("Cleaner", set_context)
        _deliver(push_lock, LockStatus.LOCKED)

    push_lock.lock.side_effect = _lock
    events = async_capture_events(hass, EVENT_STATE_CHANGED)
    call_context = Context()

    await _call_lock(hass, call_context)

    attributed, locked = _lock_states(events)
    assert attributed.state == "unlocked"
    assert attributed.attributes[ATTR_CHANGED_BY] == "Cleaner"
    assert attributed.context.id == set_context.id
    assert locked.state == "locked"
    assert locked.context.id == call_context.id


async def test_a_service_call_started_during_a_sets_write_keeps_its_context(
    hass: HomeAssistant,
) -> None:
    """Test a lock action a state listener starts during a set's write writes its change under the call's context."""
    attributor = _Attributor(hass)
    push_lock = await _setup_attributed_lock(hass, attributor, lock=LockStatus.LOCKED)
    _deliver(push_lock, LockStatus.UNLOCKED)
    (change,) = attributor.changes
    answer = asyncio.Event()

    async def _lock() -> None:
        """Report the command's change once the test answers."""
        await answer.wait()
        _deliver(push_lock, LockStatus.LOCKED)

    push_lock.lock.side_effect = _lock
    call_context = Context()
    calls: list[asyncio.Task[ServiceResponse]] = []
    removers: list[CALLBACK_TYPE] = []

    @callback
    def _call_lock_now(event: Event[EventStateChangedData]) -> None:
        """Start the lock action as an eager task, once."""
        removers[0]()
        calls.append(
            hass.async_create_task(
                hass.services.async_call(
                    LOCK_DOMAIN,
                    SERVICE_LOCK,
                    {ATTR_ENTITY_ID: LOCK},
                    blocking=True,
                    context=call_context,
                ),
                eager_start=True,
            )
        )

    removers.append(async_track_state_change_event(hass, LOCK, _call_lock_now))
    set_context = Context()

    change.async_set_changed_by("Cleaner", set_context)
    answer.set()
    await calls[0]

    assert hass.states.get(LOCK).state == "locked"
    assert hass.states.get(LOCK).context.id == call_context.id


async def test_a_set_while_the_lock_is_unavailable_shows_when_it_returns(
    hass: HomeAssistant,
) -> None:
    """Test a set while the lock is unavailable changes no state, and the next write of the status shows it."""
    attributor = _Attributor(hass)
    with patch(
        "homeassistant.components.bluetooth.async_track_unavailable"
    ) as track_unavailable:
        push_lock = await _setup_attributed_lock(
            hass, attributor, lock=LockStatus.LOCKED
        )
    _deliver(push_lock, LockStatus.UNLOCKED)
    for call in track_unavailable.call_args_list:
        call.args[1](YALE_ACCESS_LOCK_DISCOVERY_INFO)
    assert hass.states.get(LOCK).state == "unavailable"
    events = async_capture_events(hass, EVENT_STATE_CHANGED)

    attributor.changes[0].async_set_changed_by("Cleaner", Context())

    assert _lock_states(events) == []
    _deliver(push_lock, LockStatus.UNLOCKED)
    state = hass.states.get(LOCK)
    assert state.state == "unlocked"
    assert state.attributes[ATTR_CHANGED_BY] == "Cleaner"


async def test_a_set_after_the_entity_is_removed_writes_nothing(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Test a set on the latest change of a removed entity writes nothing and raises nothing."""
    attributor = _Attributor(hass)
    push_lock = await _setup_attributed_lock(hass, attributor, lock=LockStatus.LOCKED)
    _deliver(push_lock, LockStatus.UNLOCKED)
    (change,) = attributor.changes
    entity_registry.async_remove(LOCK)
    await hass.async_block_till_done()
    assert change.latest

    change.async_set_changed_by("Cleaner", Context())

    assert hass.states.get(LOCK) is None


async def test_an_attributor_that_removes_itself_skips_no_other(
    hass: HomeAssistant,
) -> None:
    """Test an attributor that removes its registration when told does not keep the next one from being told."""
    attributor = _Attributor(hass)
    push_lock = await _setup_attributed_lock(hass, lock=LockStatus.LOCKED)
    removing = _Attributor(hass)
    removers: list[CALLBACK_TYPE] = []

    class _RemovingAttributor:
        """Remove its own registration when told."""

        @callback
        def async_lock_status_changed(self, change: LockStatusChange) -> None:
            """Keep the change and remove the registration."""
            removing.async_lock_status_changed(change)
            removers[0]()

    removers.append(
        async_register_attributor(hass, push_lock.address, _RemovingAttributor())
    )
    async_register_attributor(hass, push_lock.address, attributor)

    _deliver(push_lock, LockStatus.UNLOCKED)
    _deliver(push_lock, LockStatus.LOCKED)

    assert len(removing.changes) == 1
    assert attributor.changes[0] is removing.changes[0]
    assert len(attributor.changes) == 2


async def test_an_attributor_registered_with_a_lowercase_address_is_told(
    hass: HomeAssistant,
) -> None:
    """Test registration matches the lock's address whatever its case."""
    attributor = _Attributor(hass)
    push_lock = await _setup_attributed_lock(hass, lock=LockStatus.LOCKED)
    async_register_attributor(hass, push_lock.address.lower(), attributor)

    _deliver(push_lock, LockStatus.UNLOCKED)

    (change,) = attributor.changes
    assert change.entity_id == LOCK


async def test_a_set_keeps_an_expired_service_call_context_expired(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Test a set after a service call's context is more than five seconds old leaves the next change under a new context."""
    attributor = _Attributor(hass)
    push_lock = await _setup_attributed_lock(hass, attributor, lock=LockStatus.UNLOCKED)
    push_lock.lock.side_effect = lambda: _deliver(push_lock, LockStatus.LOCKED)
    call_context = Context()
    await _call_lock(hass, call_context)
    assert hass.states.get(LOCK).context.id == call_context.id
    freezer.tick(timedelta(seconds=6))
    context = Context()
    attributor.changes[0].async_set_changed_by("Cleaner", context)
    assert hass.states.get(LOCK).context is context

    _deliver(push_lock, LockStatus.UNLOCKED)

    state = hass.states.get(LOCK)
    assert state.state == "unlocked"
    assert state.context.id not in {call_context.id, context.id}


async def test_a_command_started_during_the_write_does_not_mark_the_change(
    hass: HomeAssistant,
) -> None:
    """Test a command a state listener starts during the write leaves that change not commanded."""
    attributor = _Attributor(hass)
    push_lock = await _setup_attributed_lock(hass, attributor, lock=LockStatus.LOCKED)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    entity = hass.data[LOCK_DATA_COMPONENT].get_entity(LOCK)
    answer = asyncio.Event()
    push_lock.lock.side_effect = answer.wait
    tasks: list[asyncio.Task[None]] = []

    @callback
    def _lock(event: Event[EventStateChangedData]) -> None:
        """Start a lock command as an eager task."""
        tasks.append(hass.async_create_task(entity.async_lock(), eager_start=True))

    async_track_state_change_event(hass, LOCK, _lock)

    _deliver(push_lock, LockStatus.UNLOCKED)
    in_flight = entry.runtime_data.lock_commands_in_flight
    answer.set()
    await tasks[0]

    (change,) = attributor.changes
    assert change.commanded is False
    assert in_flight == 1
    assert entry.runtime_data.lock_commands_in_flight == 0
