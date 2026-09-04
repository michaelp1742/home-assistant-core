"""Test the Yale Access Bluetooth init."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from yalexs_ble import AuthError, ValidatedLockConfig

from homeassistant.components.yalexs_ble import _library_options, _resolve_options
from homeassistant.components.yalexs_ble.config_cache import async_add_validated_config
from homeassistant.components.yalexs_ble.const import (
    CONF_ACTIVITY_COUNT,
    CONF_ALWAYS_CONNECTED,
    CONF_AUTO_LOCK,
    CONF_BATTERY_REPORTING,
    CONF_DOOR_SENSE,
    CONF_KEY,
    CONF_SECURE_MODE,
    CONF_UNLATCH,
    OPTION_DEFAULT,
    OPTION_OFF,
    OPTION_ON,
)
from homeassistant.components.yalexs_ble.models import LibraryReport, LockOptions
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import CoreState, HomeAssistant

from . import (
    YALE_ACCESS_LOCK_DISCOVERY_INFO,
    mock_entry,
    mock_push_lock,
    mock_push_lock_class,
    setup_entry,
)

ROTATED_KEY = "0d4e5f8621c6a139eaffbedcb846b60f"


async def test_setup_retries_when_not_advertising_at_startup(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test setup is retried with a diagnostic reason when not advertising at startup."""
    entry = mock_entry()
    hass.set_state(CoreState.starting)

    with patch(
        "homeassistant.components.yalexs_ble.bluetooth."
        "async_address_reachability_diagnostics",
        return_value="mock reachability reason",
    ):
        await setup_entry(hass, entry, mock_push_lock_class(mock_push_lock()))

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert (
        f"{YALE_ACCESS_LOCK_DISCOVERY_INFO.name} "
        f"({YALE_ACCESS_LOCK_DISCOVERY_INFO.address}) is not advertising yet: "
        "mock reachability reason" in caplog.text
    )


async def test_setup_configures_the_lock_before_start(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test the stored choices reach configure() before the lock is started."""
    caplog.set_level(logging.DEBUG, logger="homeassistant.components.yalexs_ble")
    entry = mock_entry(
        {
            CONF_ALWAYS_CONNECTED: True,
            CONF_SECURE_MODE: OPTION_ON,
            CONF_DOOR_SENSE: OPTION_OFF,
            CONF_BATTERY_REPORTING: OPTION_DEFAULT,
        }
    )
    push_lock = mock_push_lock(
        accepted=frozenset({"always_connected", "door_sense"}),
        ignored=frozenset({"secure_mode"}),
    )
    push_lock_class = mock_push_lock_class(push_lock, has=frozenset({"configure"}))

    await setup_entry(hass, entry, push_lock_class)

    # always_connected reaches this library through configure(), so the
    # constructor is called with no keyword.
    assert push_lock_class.mock_calls[0].kwargs == {}
    calls = [call[0] for call in push_lock.method_calls]
    assert calls.index("configure") < calls.index("start")
    # The library default choice sends nothing, so battery_reporting is absent.
    assert push_lock.configure.mock_calls[0].args[0] == {
        "always_connected": True,
        "secure_mode": True,
        "door_sense": False,
    }
    assert entry.runtime_data.options == LockOptions(
        unlatch=False,
        secure_mode=True,
        secure_mode_enabled=True,
        battery_reporting=True,
        activity_count=False,
        auto_lock=False,
        unlatch_hold_time=False,
    )
    assert entry.runtime_data.configure_report == LibraryReport(
        accepted=frozenset({"always_connected", "door_sense"}),
        ignored=frozenset({"secure_mode"}),
    )
    assert (
        "passing options to the library: always_connected, door_sense, secure_mode; "
        "accepted always_connected, door_sense; ignored secure_mode" in caplog.text
    )
    # The library took the always connected key, so nothing is warned about.
    assert not [
        record for record in caplog.records if record.levelno == logging.WARNING
    ]


async def test_setup_uses_the_always_connected_keyword_on_an_older_library(
    hass: HomeAssistant,
) -> None:
    """Test a library without configure() takes always_connected as a keyword."""
    entry = mock_entry({CONF_ALWAYS_CONNECTED: True, CONF_SECURE_MODE: OPTION_OFF})
    push_lock = mock_push_lock()
    push_lock_class = mock_push_lock_class(push_lock)

    await setup_entry(hass, entry, push_lock_class)

    assert push_lock_class.mock_calls[0].kwargs == {"always_connected": True}
    assert entry.runtime_data.configure_report is None
    assert entry.runtime_data.options.secure_mode is False


@pytest.mark.parametrize(
    ("option", "passed", "accepted", "ignored", "resolved"),
    [
        pytest.param(
            CONF_UNLATCH,
            {"unlatch": True, "parameters": True},
            frozenset({"unlatch"}),
            frozenset(),
            True,
            id="unlatch-accepted",
        ),
        pytest.param(
            CONF_UNLATCH,
            {"unlatch": True, "parameters": True},
            frozenset(),
            frozenset({"unlatch"}),
            False,
            id="unlatch-ignored",
        ),
        pytest.param(
            CONF_ACTIVITY_COUNT,
            {"activity_count": True},
            frozenset({"activity_count"}),
            frozenset(),
            True,
            id="activity count-accepted",
        ),
        pytest.param(
            CONF_ACTIVITY_COUNT,
            {"activity_count": True},
            frozenset(),
            frozenset({"activity_count"}),
            False,
            id="activity count-ignored",
        ),
    ],
)
async def test_a_library_carried_feature_needs_the_key_accepted(
    hass: HomeAssistant,
    option: str,
    passed: dict[str, bool],
    accepted: frozenset[str],
    ignored: frozenset[str],
    resolved: bool,
) -> None:
    """Test a feature the library carries follows the report, not the choice."""
    entry = mock_entry({option: OPTION_ON})
    push_lock = mock_push_lock(accepted=accepted, ignored=ignored)

    await setup_entry(
        hass, entry, mock_push_lock_class(push_lock, has=frozenset({"configure"}))
    )

    assert push_lock.configure.mock_calls[0].args[0] == passed
    assert getattr(entry.runtime_data.options, option) is resolved


async def test_key_rotation_restart_keeps_the_configured_instance(
    hass: HomeAssistant,
) -> None:
    """Test the restart after a key rotation reuses the configured lock."""
    entry = mock_entry({CONF_ALWAYS_CONNECTED: True})
    async_add_validated_config(
        hass,
        YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
        ValidatedLockConfig(
            "Front Door",
            YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
            "M1XXX012LU",
            ROTATED_KEY,
            67,
        ),
    )
    push_lock = mock_push_lock(accepted=frozenset({"always_connected"}))
    push_lock.wait_for_first_update = AsyncMock(
        side_effect=[AuthError("key rotated"), None]
    )
    push_lock_class = mock_push_lock_class(push_lock, has=frozenset({"configure"}))

    await setup_entry(hass, entry, push_lock_class)

    assert push_lock_class.call_count == 1
    assert push_lock.configure.call_count == 1
    push_lock.set_lock_key.assert_called_once_with(ROTATED_KEY, 67)
    assert push_lock.start.call_count == 2
    assert entry.data[CONF_KEY] == ROTATED_KEY
    assert entry.runtime_data.configure_report is not None


async def test_setup_passes_nothing_when_no_option_is_stored(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test an install that never opened the options page sends no key."""
    caplog.set_level(logging.DEBUG, logger="homeassistant.components.yalexs_ble")
    entry = mock_entry()
    push_lock = mock_push_lock()

    await setup_entry(
        hass, entry, mock_push_lock_class(push_lock, has=frozenset({"configure"}))
    )

    assert push_lock.configure.mock_calls[0].args[0] == {}
    assert entry.runtime_data.options == LockOptions(
        unlatch=False,
        secure_mode=True,
        secure_mode_enabled=False,
        battery_reporting=True,
        activity_count=False,
        auto_lock=False,
        unlatch_hold_time=False,
    )
    assert (
        "passing options to the library: none; accepted none; ignored none"
        in caplog.text
    )


def test_helpers_delete_the_attributes_an_older_library_lacks() -> None:
    """Test the class mock answers hasattr as the library version it stands for."""
    push_lock: MagicMock = mock_push_lock(door_sense=None)
    assert hasattr(push_lock, "door_sense") is False

    lock_without_unlatch = mock_push_lock()
    push_lock_class = mock_push_lock_class(
        lock_without_unlatch, has=frozenset({"configure"})
    )
    assert hasattr(push_lock_class, "configure") is True
    assert hasattr(push_lock_class, "supported_options") is False
    assert hasattr(push_lock_class, "unlatch") is False
    assert hasattr(lock_without_unlatch, "unlatch") is False


@pytest.mark.parametrize(
    ("stored", "warnings_expected"),
    [pytest.param(True, 1, id="on"), pytest.param(False, 0, id="off")],
)
async def test_setup_warns_only_when_the_library_refuses_a_true_always_connected(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    stored: bool,
    warnings_expected: int,
) -> None:
    """Test a refused always connected choice of on is warned and one of off is not."""
    entry = mock_entry({CONF_ALWAYS_CONNECTED: stored})
    push_lock = mock_push_lock(ignored=frozenset({"always_connected"}))

    await setup_entry(
        hass, entry, mock_push_lock_class(push_lock, has=frozenset({"configure"}))
    )

    warnings = [
        record for record in caplog.records if record.levelno == logging.WARNING
    ]
    assert len(warnings) == warnings_expected
    assert all(
        "did not take the always connected option" in warning.getMessage()
        for warning in warnings
    )


async def test_setup_reports_the_choices_an_older_library_cannot_take(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test the stored choices a library without the channel drops are named."""
    caplog.set_level(logging.DEBUG, logger="homeassistant.components.yalexs_ble")
    entry = mock_entry({CONF_UNLATCH: OPTION_ON, CONF_ACTIVITY_COUNT: OPTION_ON})

    await setup_entry(hass, entry, mock_push_lock_class(mock_push_lock()))

    assert (
        "the library has no options channel, so the stored feature choices are not "
        "passed to it: activity_count, unlatch" in caplog.text
    )


def test_library_options_passes_parameters_when_auto_lock_is_on() -> None:
    """Test an auto-lock choice of on passes the parameters key."""
    assert _library_options({CONF_AUTO_LOCK: OPTION_ON}) == {"parameters": True}


def test_library_options_passes_parameters_when_unlatch_is_on() -> None:
    """Test an unlatch choice of on passes the parameters key with its own."""
    assert _library_options({CONF_UNLATCH: OPTION_ON}) == {
        "unlatch": True,
        "parameters": True,
    }


@pytest.mark.parametrize(
    "stored",
    [
        pytest.param({}, id="nothing stored"),
        pytest.param({CONF_AUTO_LOCK: OPTION_OFF}, id="auto lock off"),
        pytest.param({CONF_AUTO_LOCK: OPTION_DEFAULT}, id="auto lock default"),
        pytest.param({CONF_UNLATCH: OPTION_OFF}, id="unlatch off"),
    ],
)
def test_library_options_passes_no_parameters_key_otherwise(
    stored: dict[str, str],
) -> None:
    """Test no parameters key is passed when neither choice is on."""
    assert "parameters" not in _library_options(stored)


@pytest.mark.parametrize(
    ("stored", "accepted", "resolved"),
    [
        pytest.param(
            {CONF_AUTO_LOCK: OPTION_ON},
            frozenset({"parameters"}),
            True,
            id="on and accepted",
        ),
        pytest.param(
            {CONF_AUTO_LOCK: OPTION_ON}, frozenset(), False, id="on and ignored"
        ),
        pytest.param(
            {CONF_AUTO_LOCK: OPTION_OFF}, frozenset({"parameters"}), False, id="off"
        ),
        pytest.param({}, frozenset({"parameters"}), False, id="unconfigured"),
    ],
)
def test_resolve_options_auto_lock_needs_the_choice_and_parameters_accepted(
    stored: dict[str, str], accepted: frozenset[str], resolved: bool
) -> None:
    """Test auto_lock resolves true only with the choice on and the key accepted."""
    assert _resolve_options(stored, accepted).auto_lock is resolved


@pytest.mark.parametrize(
    ("stored", "accepted", "resolved"),
    [
        pytest.param(
            {CONF_UNLATCH: OPTION_ON},
            frozenset({"unlatch", "parameters"}),
            True,
            id="both accepted",
        ),
        pytest.param(
            {CONF_UNLATCH: OPTION_ON},
            frozenset({"parameters"}),
            False,
            id="unlatch ignored",
        ),
        pytest.param(
            {CONF_UNLATCH: OPTION_ON},
            frozenset({"unlatch"}),
            False,
            id="parameters ignored",
        ),
        pytest.param(
            {CONF_UNLATCH: OPTION_OFF},
            frozenset({"unlatch", "parameters"}),
            False,
            id="unlatch off",
        ),
    ],
)
def test_resolve_options_hold_time_needs_unlatch_and_parameters_accepted(
    stored: dict[str, str], accepted: frozenset[str], resolved: bool
) -> None:
    """Test unlatch_hold_time needs unlatch resolved and the parameters key accepted."""
    assert _resolve_options(stored, accepted).unlatch_hold_time is resolved
