"""Test the Yale Access Bluetooth locks."""

from unittest.mock import MagicMock, patch, sentinel

import pytest
from yalexs_ble import DoorStatus, LockState, LockStatus

from homeassistant.components.lock import (
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
from homeassistant.components.yalexs_ble.lock import _UNLATCHED, _UNLATCHING
from homeassistant.const import ATTR_ENTITY_ID, ATTR_SUPPORTED_FEATURES
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceNotSupported
from homeassistant.helpers import entity_registry as er

from . import (
    YALE_ACCESS_LOCK_DISCOVERY_INFO,
    mock_entry,
    mock_push_lock,
    mock_push_lock_class,
    setup_entry,
)

LOCK = "lock.front_door"
SECURE_MODE_LOCK = "lock.front_door_secure_mode"
SECURE_MODE_UNIQUE_ID = f"{YALE_ACCESS_LOCK_DISCOVERY_INFO.address}_secure_mode"

UNLATCH_LIBRARY = frozenset({"configure", "unlatch"})


def _deliver(push_lock: MagicMock, status: LockStatus) -> None:
    """Deliver a lock status to every callback the entities registered."""
    state = LockState(
        lock=status,
        door=DoorStatus.CLOSED,
        battery=None,
        auth=None,
        auto_lock=None,
        auto_lock_prev=None,
    )
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
        auto_lock=None,
        auto_lock_prev=None,
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
