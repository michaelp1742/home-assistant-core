"""The Yale Access Bluetooth integration."""

from collections.abc import Mapping
import logging
from typing import Any

from yalexs_ble import (
    AuthError,
    ConnectionInfo,
    LockInfo,
    LockState,
    PushLock,
    YaleXSBLEError,
    close_stale_connections_by_address,
    local_name_is_unique,
)

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothReachabilityIntent
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import CALLBACK_TYPE, CoreState, Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .config_cache import async_get_validated_config
from .const import (
    CONF_ACTIVITY_COUNT,
    CONF_ALWAYS_CONNECTED,
    CONF_AUTO_LOCK,
    CONF_BATTERY_REPORTING,
    CONF_KEY,
    CONF_LOCAL_NAME,
    CONF_SECURE_MODE,
    CONF_SLOT,
    CONF_UNLATCH,
    DEVICE_TIMEOUT,
    DOMAIN,
    FEATURE_OPTIONS,
    LIBRARY_KEYS,
    OPTION_ALWAYS_CONNECTED,
    OPTION_OFF,
    OPTION_ON,
    OPTION_PARAMETERS,
    OPTION_VALUES,
)
from .models import LibraryReport, LockOptions, YaleXSBLEData
from .util import async_find_existing_service_info, bluetooth_callback_matcher

type YALEXSBLEConfigEntry = ConfigEntry[YaleXSBLEData]

_LOGGER = logging.getLogger(__name__)


PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.LOCK,
    Platform.SENSOR,
]


def _library_options(stored: Mapping[str, Any]) -> dict[str, Any]:
    """Build the mapping handed to configure().

    Every stored choice goes down as a bool; a key the user never set, and a
    key the user set to the library default, are not passed at all, so the
    library's own answer holds for them.
    """
    options: dict[str, Any] = {}
    if CONF_ALWAYS_CONNECTED in stored:
        options[OPTION_ALWAYS_CONNECTED] = stored[CONF_ALWAYS_CONNECTED]
    for key, library_key in LIBRARY_KEYS.items():
        if (choice := stored.get(key)) in OPTION_VALUES:
            options[library_key] = OPTION_VALUES[choice]
    # A page that uses the ioctls can exist only if this key went down.
    if stored.get(CONF_AUTO_LOCK) == OPTION_ON or stored.get(CONF_UNLATCH) == OPTION_ON:
        options[OPTION_PARAMETERS] = True
    return options


def _resolve_options(
    stored: Mapping[str, Any], accepted: frozenset[str]
) -> LockOptions:
    """Resolve the stored choices to the values the platforms act on.

    A feature the integration carries alone follows the stored choice; a
    feature the library carries also needs the library to have accepted its
    key, so nothing is offered that the lock cannot be asked for.
    """
    unlatch = (
        stored.get(CONF_UNLATCH) == OPTION_ON and LIBRARY_KEYS[CONF_UNLATCH] in accepted
    )
    return LockOptions(
        unlatch=unlatch,
        secure_mode=stored.get(CONF_SECURE_MODE) != OPTION_OFF,
        secure_mode_enabled=stored.get(CONF_SECURE_MODE) == OPTION_ON,
        battery_reporting=stored.get(CONF_BATTERY_REPORTING) != OPTION_OFF,
        activity_count=stored.get(CONF_ACTIVITY_COUNT) == OPTION_ON
        and LIBRARY_KEYS[CONF_ACTIVITY_COUNT] in accepted,
        auto_lock=stored.get(CONF_AUTO_LOCK) == OPTION_ON
        and OPTION_PARAMETERS in accepted,
        unlatch_hold_time=unlatch and OPTION_PARAMETERS in accepted,
    )


async def async_setup_entry(hass: HomeAssistant, entry: YALEXSBLEConfigEntry) -> bool:
    """Set up Yale Access Bluetooth from a config entry."""
    local_name = entry.data[CONF_LOCAL_NAME]
    address = entry.data[CONF_ADDRESS]
    key = entry.data[CONF_KEY]
    slot = entry.data[CONF_SLOT]
    has_unique_local_name = local_name_is_unique(local_name)
    library_options = _library_options(entry.options)
    configure_report: LibraryReport | None = None
    if hasattr(PushLock, "configure"):
        push_lock = PushLock(local_name, address, None, key, slot)
        # The method arrives with the library release that carries the options
        # channel, so it is read with a default rather than named.
        configure: Any = getattr(push_lock, "configure", None)
        # configure() must run before start(): the options are read from the
        # first update cycle on.
        report = configure(library_options)
        configure_report = LibraryReport(
            accepted=frozenset(report.accepted), ignored=frozenset(report.ignored)
        )
        _LOGGER.debug(
            "%s: passing options to the library: %s; accepted %s; ignored %s",
            entry.title,
            ", ".join(sorted(library_options)) or "none",
            ", ".join(sorted(configure_report.accepted)) or "none",
            ", ".join(sorted(configure_report.ignored)) or "none",
        )
        # A refused True is a lost choice; a refused False is what the library
        # does on its own.
        if (
            library_options.get(OPTION_ALWAYS_CONNECTED)
            and OPTION_ALWAYS_CONNECTED not in configure_report.accepted
        ):
            _LOGGER.warning(
                "%s: the library did not take the always connected option, so the "
                "connection follows the library's own answer",
                entry.title,
            )
    else:
        # A library without the options channel takes always_connected as a
        # constructor keyword and nothing else.
        push_lock = PushLock(
            local_name,
            address,
            None,
            key,
            slot,
            always_connected=entry.options.get(CONF_ALWAYS_CONNECTED, False),
        )
        if dropped := sorted(
            option for option in FEATURE_OPTIONS if option in entry.options
        ):
            _LOGGER.debug(
                "%s: the library has no options channel, so the stored feature "
                "choices are not passed to it: %s",
                entry.title,
                ", ".join(dropped),
            )
    options = _resolve_options(
        entry.options, configure_report.accepted if configure_report else frozenset()
    )
    id_ = local_name if has_unique_local_name else address
    push_lock.set_name(f"{entry.title} ({id_})")

    # Ensure any lingering connections are closed since the device may not be
    # advertising when its connected to another client which will prevent us
    # from setting the device and setup will fail.
    await close_stale_connections_by_address(address)

    @callback
    def _async_update_ble(
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Update from a ble callback."""
        push_lock.update_advertisement(service_info.device, service_info.advertisement)

    shutdown_callback: CALLBACK_TYPE | None = await push_lock.start()

    @callback
    def _async_shutdown(event: Event | None = None) -> None:
        nonlocal shutdown_callback
        if shutdown_callback:
            shutdown_callback()
            shutdown_callback = None

    entry.async_on_unload(_async_shutdown)

    # We may already have the advertisement, so check for it.
    if service_info := async_find_existing_service_info(hass, local_name, address):
        push_lock.update_advertisement(service_info.device, service_info.advertisement)
    elif hass.state is CoreState.starting:
        # If we are starting and the advertisement is not found, do not delay
        # the setup. We will wait for the advertisement to be found and then
        # discovery will trigger setup retry.
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="device_not_advertising",
            translation_placeholders={
                "local_name": local_name,
                "address": address,
                "reason": bluetooth.async_address_reachability_diagnostics(
                    hass,
                    address.upper(),
                    BluetoothReachabilityIntent.CONNECTION,
                ),
            },
        )

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            _async_update_ble,
            bluetooth_callback_matcher(local_name, push_lock.address),
            bluetooth.BluetoothScanningMode.PASSIVE,
        )
    )

    try:
        await _async_wait_for_first_update(push_lock, local_name)
    except ConfigEntryAuthFailed:
        # If key has rotated, try to fetch it from the cache
        # and update
        if (validated_config := async_get_validated_config(hass, address)) and (
            validated_config.key != entry.data[CONF_KEY]
            or validated_config.slot != entry.data[CONF_SLOT]
        ):
            assert shutdown_callback is not None
            shutdown_callback()
            push_lock.set_lock_key(validated_config.key, validated_config.slot)
            shutdown_callback = await push_lock.start()
            await _async_wait_for_first_update(push_lock, local_name)
            # If we can use the cached key and slot, update the entry.
            hass.config_entries.async_update_entry(
                entry,
                data={
                    **entry.data,
                    CONF_KEY: validated_config.key,
                    CONF_SLOT: validated_config.slot,
                },
            )
        else:
            raise

    entry.runtime_data = YaleXSBLEData(
        entry.title, push_lock, options, configure_report
    )

    @callback
    def _async_device_unavailable(
        _service_info: bluetooth.BluetoothServiceInfoBleak,
    ) -> None:
        """Handle device not longer being seen by the bluetooth stack."""
        push_lock.reset_advertisement_state()

    entry.async_on_unload(
        bluetooth.async_track_unavailable(
            hass, _async_device_unavailable, push_lock.address
        )
    )

    @callback
    def _async_state_changed(
        new_state: LockState, lock_info: LockInfo, connection_info: ConnectionInfo
    ) -> None:
        """Handle state changed."""
        if new_state.auth and not new_state.auth.successful:
            entry.async_start_reauth(hass)

    entry.async_on_unload(push_lock.register_callback(_async_state_changed))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_shutdown)
    )
    return True


async def _async_wait_for_first_update(push_lock: PushLock, local_name: str) -> None:
    """Wait for the first update from the push lock."""
    try:
        await push_lock.wait_for_first_update(DEVICE_TIMEOUT)
    except AuthError as ex:
        raise ConfigEntryAuthFailed(str(ex)) from ex
    except (YaleXSBLEError, TimeoutError) as ex:
        raise ConfigEntryNotReady(
            f"{ex}; Try moving the Bluetooth adapter closer to {local_name}"
        ) from ex


async def async_unload_entry(hass: HomeAssistant, entry: YALEXSBLEConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
