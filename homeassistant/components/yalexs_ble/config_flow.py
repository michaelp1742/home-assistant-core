"""Config flow for Yale Access Bluetooth integration."""

import asyncio
from collections.abc import Callable, Coroutine, Mapping
from datetime import datetime
import logging
from typing import Any, Self, override

from bleak_retry_connector import BleakError, BLEDevice
import voluptuous as vol
from yalexs_ble import (
    AuthError,
    DisconnectedError,
    PushLock,
    ValidatedLockConfig,
    YaleXSBLEError,
    local_name_is_unique,
)
from yalexs_ble.const import YALE_MFR_ID

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers import translation
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.helpers.typing import DiscoveryInfoType
from homeassistant.util import dt as dt_util

from .config_cache import async_add_validated_config, async_get_validated_config
from .const import (
    AUTO_LOCK_DEFAULT_DURATION,
    AUTO_LOCK_DURATIONS,
    AUTO_LOCK_MODE_INSTANT,
    AUTO_LOCK_MODE_OFF,
    AUTO_LOCK_MODE_TIMED,
    AUTO_LOCK_MODES,
    CONF_ALWAYS_CONNECTED,
    CONF_AUTO_LOCK_DURATION,
    CONF_AUTO_LOCK_MODE,
    CONF_KEY,
    CONF_LATCH_PULL_TIME,
    CONF_LOCAL_NAME,
    CONF_SLOT,
    DATA_AUTO_LOCK,
    DATA_LATCH_PULL_TIME,
    DOMAIN,
    FEATURE_GATES,
    FEATURE_OPTIONS,
    OPTION_AS_READ,
    OPTION_STATES,
    OPTION_UNCONFIGURED,
    PARAMETER_LATCH_PULL_TIME,
    PARAMETER_RELOCK_SEC,
    PROGRESS_READING_AUTO_LOCK,
    PROGRESS_READING_UNLATCH_HOLD_TIME,
    STEP_AUTO_LOCK,
    STEP_AUTO_LOCK_FORM,
    STEP_LOCK_OPTIONS,
    STEP_UNLATCH_HOLD_TIME,
    STEP_UNLATCH_HOLD_TIME_FORM,
    UNLATCH_HOLD_TIMES,
)
from .models import ParameterRecord
from .util import async_find_existing_service_info, human_readable_name

_LOGGER = logging.getLogger(__name__)


async def async_validate_lock_or_error(
    local_name: str, device: BLEDevice, key: str, slot: int
) -> dict[str, str]:
    """Validate the lock and return errors if any."""
    if len(key) != 32:
        return {CONF_KEY: "invalid_key_format"}
    try:
        bytes.fromhex(key)
    except ValueError:
        return {CONF_KEY: "invalid_key_format"}
    if not isinstance(slot, int) or not 0 <= slot <= 255:
        return {CONF_SLOT: "invalid_key_index"}
    try:
        await PushLock(local_name, device.address, device, key, slot).validate()
    except DisconnectedError, AuthError, ValueError:
        return {CONF_KEY: "invalid_auth"}
    except BleakError:
        return {"base": "cannot_connect"}
    except Exception:
        _LOGGER.exception("Unexpected error")
        return {"base": "unknown"}
    return {}


class YalexsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Yale Access Bluetooth."""

    VERSION = 1

    _address: str | None = None
    _local_name_is_unique = False
    active = False
    local_name: str | None = None

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}
        self._lock_cfg: ValidatedLockConfig | None = None

    @override
    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle the bluetooth discovery step."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self.local_name = discovery_info.name
        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {
            "name": human_readable_name(
                None, discovery_info.name, discovery_info.address
            ),
        }
        if lock_cfg := async_get_validated_config(self.hass, discovery_info.address):
            self._lock_cfg = lock_cfg
            return await self.async_step_integration_discovery_confirm()
        return await self.async_step_key_slot()

    @override
    async def async_step_integration_discovery(
        self, discovery_info: DiscoveryInfoType
    ) -> ConfigFlowResult:
        """Handle a discovered integration."""
        lock_cfg = ValidatedLockConfig(
            discovery_info["name"],
            discovery_info["address"],
            discovery_info["serial"],
            discovery_info["key"],
            discovery_info["slot"],
        )
        async_add_validated_config(self.hass, lock_cfg.address, lock_cfg)

        address = lock_cfg.address
        self.local_name = lock_cfg.local_name
        self._local_name_is_unique = local_name_is_unique(self.local_name)

        # We do not want to raise on progress as integration_discovery takes
        # precedence over other discovery flows since we already have the keys.
        #
        # After we do discovery we will abort the flows that do not have the keys
        # below unless the user is already setting them up.
        await self.async_set_unique_id(address, raise_on_progress=False)
        new_data = {CONF_KEY: lock_cfg.key, CONF_SLOT: lock_cfg.slot}
        self._abort_if_unique_id_configured(updates=new_data)
        for entry in self._async_current_entries():
            if (
                self._local_name_is_unique
                and entry.data.get(CONF_LOCAL_NAME) == lock_cfg.local_name
            ):
                return self.async_update_reload_and_abort(
                    entry, data={**entry.data, **new_data}, reason="already_configured"
                )

        self._discovery_info = async_find_existing_service_info(
            self.hass, self.local_name, address
        )
        if not self._discovery_info:
            return self.async_abort(reason="no_devices_found")

        self._address = address
        if self.hass.config_entries.flow.async_has_matching_flow(self):
            raise AbortFlow("already_in_progress")

        self._lock_cfg = lock_cfg
        self.context["title_placeholders"] = {
            "name": human_readable_name(
                lock_cfg.name, lock_cfg.local_name, self._discovery_info.address
            )
        }
        return await self.async_step_integration_discovery_confirm()

    @override
    def is_matching(self, other_flow: Self) -> bool:
        """Return True if other_flow is matching this flow."""
        # Integration discovery should abort other flows unless they
        # are already in the process of being set up since this discovery
        # will already have all the keys and the user can simply confirm.
        if (
            self._local_name_is_unique and other_flow.local_name == self.local_name
        ) or other_flow.unique_id == self._address:
            if other_flow.active:
                # The user has already started interacting with this flow
                # and entered the keys. We abort the discovery flow since
                # we assume they do not want to use the discovered keys for
                # some reason.
                return True
            self.hass.config_entries.flow.async_abort(other_flow.flow_id)

        return False

    async def async_step_integration_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a confirmation of discovered integration."""
        assert self._discovery_info is not None
        assert self._lock_cfg is not None
        if user_input is not None:
            return self.async_create_entry(
                title=self._lock_cfg.name,
                data={
                    CONF_LOCAL_NAME: self._discovery_info.name,
                    CONF_ADDRESS: self._discovery_info.address,
                    CONF_KEY: self._lock_cfg.key,
                    CONF_SLOT: self._lock_cfg.slot,
                },
            )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="integration_discovery_confirm",
            description_placeholders={
                "name": self._lock_cfg.name,
                "address": self._discovery_info.address,
            },
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle configuration by re-auth."""
        return await self.async_step_reauth_validate()

    async def async_step_reauth_validate(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reauth and validation."""
        errors = {}
        reauth_entry = self._get_reauth_entry()
        if user_input is not None:
            if (
                device := async_ble_device_from_address(
                    self.hass, reauth_entry.data[CONF_ADDRESS], True
                )
            ) is None:
                errors = {"base": "no_longer_in_range"}
            elif not (
                errors := await async_validate_lock_or_error(
                    reauth_entry.data[CONF_LOCAL_NAME],
                    device,
                    user_input[CONF_KEY],
                    user_input[CONF_SLOT],
                )
            ):
                return self.async_update_reload_and_abort(
                    reauth_entry, data_updates=user_input
                )

        return self.async_show_form(
            step_id="reauth_validate",
            data_schema=vol.Schema(
                {vol.Required(CONF_KEY): str, vol.Required(CONF_SLOT): int}
            ),
            description_placeholders={
                "address": reauth_entry.data[CONF_ADDRESS],
                "title": reauth_entry.title,
            },
            errors=errors,
        )

    async def async_step_key_slot(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the key and slot step."""
        errors: dict[str, str] = {}
        discovery_info = self._discovery_info
        assert discovery_info is not None
        address = discovery_info.address
        validated_config = async_get_validated_config(self.hass, address)

        if user_input is not None or validated_config:
            local_name = discovery_info.name
            if validated_config:
                key = validated_config.key
                slot = validated_config.slot
                title = validated_config.name
            else:
                assert user_input is not None
                key = user_input[CONF_KEY]
                slot = user_input[CONF_SLOT]
                title = human_readable_name(None, local_name, address)
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            if not (
                errors := await async_validate_lock_or_error(
                    local_name, discovery_info.device, key, slot
                )
            ):
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_LOCAL_NAME: discovery_info.name,
                        CONF_ADDRESS: discovery_info.address,
                        CONF_KEY: key,
                        CONF_SLOT: slot,
                    },
                )

        return self.async_show_form(
            step_id="key_slot",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_KEY): str,
                    vol.Required(CONF_SLOT): int,
                }
            ),
            errors=errors,
            description_placeholders={
                "address": address,
                "title": self._async_get_name_from_address(address),
            },
        )

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user step to pick discovered device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self.active = True
            address = user_input[CONF_ADDRESS]
            self._discovery_info = self._discovered_devices[address]
            return await self.async_step_key_slot()

        current_addresses = self._async_current_ids(include_ignore=False)
        current_unique_names = {
            entry.data.get(CONF_LOCAL_NAME)
            for entry in self._async_current_entries()
            if local_name_is_unique(entry.data.get(CONF_LOCAL_NAME))
        }
        for discovery in async_discovered_service_info(self.hass):
            if (
                discovery.address in current_addresses
                or discovery.name in current_unique_names
                or discovery.address in self._discovered_devices
                or YALE_MFR_ID not in discovery.manufacturer_data
            ):
                continue
            self._discovered_devices[discovery.address] = discovery

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        data_schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): vol.In(
                    {
                        service_info.address: self._async_get_name_from_address(
                            service_info.address
                        )
                        for service_info in self._discovered_devices.values()
                    }
                )
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    @callback
    def _async_get_name_from_address(self, address: str) -> str:
        """Get the name of a device from its address."""
        if validated_config := async_get_validated_config(self.hass, address):
            return f"{validated_config.name} ({address})"
        if address in self._discovered_devices:
            service_info = self._discovered_devices[address]
            return f"{service_info.name} ({service_info.address})"
        assert self._discovery_info is not None
        assert self._discovery_info.address == address
        return f"{self._discovery_info.name} ({address})"

    @staticmethod
    @callback
    @override
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> YaleXSBLEOptionsFlowHandler:
        """Get the options flow for this handler."""
        return YaleXSBLEOptionsFlowHandler()


def _pack_auto_lock(mode: str, seconds: int) -> int:
    """Pack a mode and a duration as the vendor app does."""
    if mode == AUTO_LOCK_MODE_OFF:
        return 0
    if mode == AUTO_LOCK_MODE_TIMED:
        return seconds | seconds << 16
    return seconds


def _unpack_auto_lock(value: int) -> tuple[str, int]:
    """Decode a RELOCK_SEC value.

    A set high half is On a timer with the door-close wait, a low half alone
    is Instant with its never-opened wait, and zero is Off.
    """
    if value == 0:
        return AUTO_LOCK_MODE_OFF, 0
    if (door_close_seconds := (value >> 16) & 0xFFFF) > 0:
        return AUTO_LOCK_MODE_TIMED, door_close_seconds
    return AUTO_LOCK_MODE_INSTANT, value & 0xFFFF


def _when(at: str) -> str:
    """Return a record's time in local time, without the date when it is today."""
    local = dt_util.as_local(datetime.fromisoformat(at))
    if local.date() == dt_util.now().date():
        return local.strftime("%H:%M")
    return local.strftime("%Y-%m-%d %H:%M")


def _duration_text(
    translations: dict[str, str], translation_key: str, seconds: int
) -> str:
    """Return a duration select's word for the seconds, or the bare seconds off the list."""
    word = translations.get(
        f"component.{DOMAIN}.selector.{translation_key}.options.{seconds}"
    )
    return word or translations[f"component.{DOMAIN}.common.seconds"].format(
        seconds=seconds
    )


def _parameter_status(
    translations: dict[str, str], record: ParameterRecord | None, value: str
) -> str:
    """Return a menu row's status from its kept record, or that nothing was read."""
    if record is None:
        return translations[f"component.{DOMAIN}.common.not_read"]
    fragment = "written_at" if record["written"] else "read_at"
    return translations[f"component.{DOMAIN}.common.{fragment}"].format(
        value=value, when=_when(record["at"])
    )


class YaleXSBLEOptionsFlowHandler(OptionsFlowWithReload):
    """Handle YaleXSBLE options."""

    _read_task: asyncio.Task[int] | None = None
    _read_value: int | None = None
    _read_error: str | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the menu: Lock options, and the parameter pages the stored choices and the library's report allow."""
        auto_lock = False
        unlatch_hold_time = False
        if self.config_entry.state is ConfigEntryState.LOADED:
            options = self.config_entry.runtime_data.options
            auto_lock = options.auto_lock
            unlatch_hold_time = options.unlatch_hold_time
        menu_options = [STEP_LOCK_OPTIONS]
        placeholders = {"title": self.config_entry.title}
        translations: dict[str, str] = {}
        if auto_lock or unlatch_hold_time:
            # The frontend fills a placeholder with the text it is given, so a
            # row's words are composed here, in the server's language, while
            # the rest of the dialog is in the viewer's.
            translations = {
                **await translation.async_get_translations(
                    self.hass, self.hass.config.language, "selector", {DOMAIN}
                ),
                **await translation.async_get_translations(
                    self.hass, self.hass.config.language, "common", {DOMAIN}
                ),
            }
        if auto_lock:
            menu_options.append(STEP_AUTO_LOCK)
            record: ParameterRecord | None = self.config_entry.data.get(DATA_AUTO_LOCK)
            setting = ""
            if record is not None:
                mode, seconds = _unpack_auto_lock(record["value"])
                setting = translations[
                    f"component.{DOMAIN}.selector.{CONF_AUTO_LOCK_MODE}.options.{mode}"
                ]
                if mode != AUTO_LOCK_MODE_OFF:
                    duration = _duration_text(
                        translations, CONF_AUTO_LOCK_DURATION, seconds
                    )
                    setting = f"{setting}, {duration}"
            placeholders[STEP_AUTO_LOCK] = _parameter_status(
                translations, record, setting
            )
        if unlatch_hold_time:
            menu_options.append(STEP_UNLATCH_HOLD_TIME)
            held: ParameterRecord | None = self.config_entry.data.get(
                DATA_LATCH_PULL_TIME
            )
            placeholders[STEP_UNLATCH_HOLD_TIME] = _parameter_status(
                translations,
                held,
                ""
                if held is None
                else _duration_text(translations, "unlatch_hold_time", held["value"]),
            )
        return self.async_show_menu(
            step_id="init",
            menu_options=menu_options,
            description_placeholders=placeholders,
        )

    async def async_step_lock_options(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the lock options: the connection and the features."""
        stored = self.config_entry.options
        if user_input is not None:
            # Every rendered field is explicit: "not set" clears the key, so a
            # lock can return to unconfigured, and a stored key outside
            # FEATURE_OPTIONS, left there by another release, survives.
            options = {**stored, **user_input}
            for key in FEATURE_OPTIONS:
                if options.get(key) == OPTION_UNCONFIGURED:
                    del options[key]
            return self.async_create_entry(data=options)

        # The classmethod arrives with the library release that carries the
        # options channel, so it is read with a default rather than named.
        supported_options = getattr(PushLock, "supported_options", None)
        supported: frozenset[str] = (
            supported_options() if supported_options is not None else frozenset()
        )
        supported_text = ", ".join(sorted(supported)) or "none"
        _LOGGER.debug(
            "%s: library-supported options: %s",
            self.config_entry.title,
            supported_text,
        )
        if (
            self.config_entry.state is ConfigEntryState.LOADED
            and (report := self.config_entry.runtime_data.configure_report) is not None
        ):
            _LOGGER.debug(
                "%s: options report at setup: accepted %s; ignored %s",
                self.config_entry.title,
                ", ".join(sorted(report.accepted)) or "none",
                ", ".join(sorted(report.ignored)) or "none",
            )
        feature_state = SelectSelector(
            SelectSelectorConfig(
                options=OPTION_STATES,
                translation_key="feature_state",
                mode=SelectSelectorMode.DROPDOWN,
            )
        )
        schema: dict[vol.Marker, Any] = {
            vol.Optional(
                CONF_ALWAYS_CONNECTED,
                default=stored.get(CONF_ALWAYS_CONNECTED, False),
            ): bool
        }
        for key in FEATURE_OPTIONS:
            # A feature the integration carries alone has no gate; the rest
            # appear when the installed library advertises the key the gate
            # names, and a key that is already stored appears whatever the
            # library says, so it can be returned to not set after a library
            # change.
            gate = FEATURE_GATES[key]
            if gate is not None and gate not in supported and key not in stored:
                continue
            schema[vol.Optional(key, default=stored.get(key, OPTION_UNCONFIGURED))] = (
                feature_state
            )
        return self.async_show_form(
            step_id=STEP_LOCK_OPTIONS,
            data_schema=vol.Schema(schema),
        )

    async def async_step_auto_lock(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Read the auto-lock setting from the lock, then show its form."""
        if self._read_task is not None and self._read_task.done():
            return self._finish_read(
                PARAMETER_RELOCK_SEC, DATA_AUTO_LOCK, STEP_AUTO_LOCK_FORM
            )
        return await self._start_read(
            PARAMETER_RELOCK_SEC,
            DATA_AUTO_LOCK,
            STEP_AUTO_LOCK,
            PROGRESS_READING_AUTO_LOCK,
            self.async_step_auto_lock_form,
        )

    async def async_step_auto_lock_form(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the auto-lock mode and duration and write a change."""
        record: ParameterRecord | None = self.config_entry.data.get(DATA_AUTO_LOCK)
        value = self._read_value
        if value is None and record is not None:
            value = record["value"]
        mode: str | None = None
        read_seconds: int | None = None
        selected: str | None = None
        as_read = False
        if value is not None:
            mode, read_seconds = _unpack_auto_lock(value)
            # Off holds no duration, so the form offers the one the app arms
            # when its switch is turned on.
            if mode == AUTO_LOCK_MODE_OFF:
                read_seconds = AUTO_LOCK_DEFAULT_DURATION
            as_read = read_seconds not in AUTO_LOCK_DURATIONS
            selected = OPTION_AS_READ if as_read else str(read_seconds)
        errors = {"base": self._read_error} if self._read_error is not None else {}

        if user_input is not None:
            chosen_mode: str = user_input[CONF_AUTO_LOCK_MODE]
            chosen_duration: str = user_input[CONF_AUTO_LOCK_DURATION]
            # As read from the lock stands for the seconds last read: kept
            # unchanged after a read the lock answered, and written back from
            # the record after one it did not, as any submit is then.
            seconds = (
                read_seconds
                if chosen_duration == OPTION_AS_READ
                else int(chosen_duration)
            )
            assert seconds is not None
            packed = _pack_auto_lock(chosen_mode, seconds)
            # The comparison is on the decoded pair: a value the lock holds
            # with unequal halves shows as one setting, and a submit of that
            # setting writes nothing.
            if self._read_value is not None and _unpack_auto_lock(
                packed
            ) == _unpack_auto_lock(self._read_value):
                return await self.async_step_init()
            error = await self._write(PARAMETER_RELOCK_SEC, DATA_AUTO_LOCK, packed)
            if error is None:
                return await self.async_step_init()
            errors = {"base": error}
            mode = chosen_mode
            selected = chosen_duration

        durations = [str(duration) for duration in AUTO_LOCK_DURATIONS]
        if as_read:
            durations.append(OPTION_AS_READ)
        as_read_note = await self._as_read_note(read_seconds if as_read else None)
        return self.async_show_form(
            step_id=STEP_AUTO_LOCK_FORM,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_AUTO_LOCK_MODE,
                        default=mode if mode is not None else vol.UNDEFINED,
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=AUTO_LOCK_MODES,
                            translation_key=CONF_AUTO_LOCK_MODE,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(
                        CONF_AUTO_LOCK_DURATION,
                        default=selected if selected is not None else vol.UNDEFINED,
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=durations,
                            translation_key=CONF_AUTO_LOCK_DURATION,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "as_read": as_read_note,
                "when": _when(record["at"]) if record is not None else "",
            },
        )

    async def async_step_unlatch_hold_time(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Read the unlatch hold time from the lock, then show its form."""
        if self._read_task is not None and self._read_task.done():
            return self._finish_read(
                PARAMETER_LATCH_PULL_TIME,
                DATA_LATCH_PULL_TIME,
                STEP_UNLATCH_HOLD_TIME_FORM,
            )
        return await self._start_read(
            PARAMETER_LATCH_PULL_TIME,
            DATA_LATCH_PULL_TIME,
            STEP_UNLATCH_HOLD_TIME,
            PROGRESS_READING_UNLATCH_HOLD_TIME,
            self.async_step_unlatch_hold_time_form,
        )

    async def async_step_unlatch_hold_time_form(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the unlatch hold time and write a change."""
        record: ParameterRecord | None = self.config_entry.data.get(
            DATA_LATCH_PULL_TIME
        )
        read_seconds = self._read_value
        if read_seconds is None and record is not None:
            read_seconds = record["value"]
        selected: str | None = None
        as_read = False
        if read_seconds is not None:
            as_read = read_seconds not in UNLATCH_HOLD_TIMES
            selected = OPTION_AS_READ if as_read else str(read_seconds)
        errors = {"base": self._read_error} if self._read_error is not None else {}

        if user_input is not None:
            chosen: str = user_input[CONF_LATCH_PULL_TIME]
            # As read from the lock stands for the seconds last read: kept
            # unchanged after a read the lock answered, and written back from
            # the record after one it did not, as any submit is then.
            seconds = read_seconds if chosen == OPTION_AS_READ else int(chosen)
            assert seconds is not None
            if self._read_value is not None and seconds == self._read_value:
                return await self.async_step_init()
            error = await self._write(
                PARAMETER_LATCH_PULL_TIME, DATA_LATCH_PULL_TIME, seconds
            )
            if error is None:
                return await self.async_step_init()
            errors = {"base": error}
            selected = chosen

        hold_times = [str(hold_time) for hold_time in UNLATCH_HOLD_TIMES]
        if as_read:
            hold_times.append(OPTION_AS_READ)
        as_read_note = await self._as_read_note(read_seconds if as_read else None)
        return self.async_show_form(
            step_id=STEP_UNLATCH_HOLD_TIME_FORM,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_LATCH_PULL_TIME,
                        default=selected if selected is not None else vol.UNDEFINED,
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=hold_times,
                            translation_key="unlatch_hold_time",
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            errors=errors,
            description_placeholders={
                "as_read": as_read_note,
                "when": _when(record["at"]) if record is not None else "",
            },
        )

    async def _as_read_note(self, seconds: int | None) -> str:
        """Return the note naming seconds the list does not hold, or nothing."""
        if seconds is None:
            return ""
        translations = await translation.async_get_translations(
            self.hass, self.hass.config.language, "common", {DOMAIN}
        )
        return translations[f"component.{DOMAIN}.common.as_read_note"].format(
            seconds=seconds
        )

    async def _start_read(
        self,
        parameter: int,
        key: str,
        step_id: str,
        progress_action: str,
        form_step: Callable[[], Coroutine[Any, Any, ConfigFlowResult]],
    ) -> ConfigFlowResult:
        """Start the read of a parameter and show its progress screen.

        An entry that is no longer loaded has no lock to ask, so the form is
        shown at once, as after a read the lock did not answer. A read that is
        already running keeps its progress screen.
        """
        if self._read_task is None:
            self._read_value = None
            self._read_error = None
            if self.config_entry.state is not ConfigEntryState.LOADED:
                _LOGGER.debug(
                    "%s: parameter 0x%02x: the entry is not loaded",
                    self.config_entry.title,
                    parameter,
                )
                self._read_error = self._no_answer(key)
                return await form_step()
            self._read_task = self.hass.async_create_task(
                self.config_entry.runtime_data.lock.get_parameter(parameter)
            )
        return self.async_show_progress(
            step_id=step_id,
            progress_action=progress_action,
            progress_task=self._read_task,
        )

    @callback
    def _finish_read(
        self, parameter: int, key: str, next_step_id: str
    ) -> ConfigFlowResult:
        """Take the read's outcome from its task and move on to the form.

        A value is kept in the entry's data as the last one read; an exception
        becomes the form's error.
        """
        task = self._read_task
        assert task is not None
        self._read_task = None
        try:
            value = task.result()
        except AuthError:
            self._read_error = "invalid_auth"
        except (TimeoutError, YaleXSBLEError, BleakError, RuntimeError) as err:
            _LOGGER.debug(
                "%s: parameter 0x%02x: no answer: %s",
                self.config_entry.title,
                parameter,
                err,
            )
            self._read_error = self._no_answer(key)
        # The read runs in a progress task with no caller to surface to, so
        # any other failure is logged with its traceback and shown as a lock
        # that did not answer.
        except Exception:
            _LOGGER.exception(
                "%s: parameter 0x%02x: the read failed",
                self.config_entry.title,
                parameter,
            )
            self._read_error = self._no_answer(key)
        else:
            _LOGGER.debug(
                "%s: read parameter 0x%02x: 0x%08x",
                self.config_entry.title,
                parameter,
                value,
            )
            self._read_value = value
            self._keep(key, value, written=False)
        return self.async_show_progress_done(next_step_id=next_step_id)

    async def _write(self, parameter: int, key: str, value: int) -> str | None:
        """Write a parameter and keep the value the lock reports it stored.

        Returns the form's error key when the lock did not answer, or None when
        the write went through.
        """
        if self.config_entry.state is not ConfigEntryState.LOADED:
            _LOGGER.debug(
                "%s: parameter 0x%02x: the entry is not loaded",
                self.config_entry.title,
                parameter,
            )
            return "no_answer"
        try:
            stored = await self.config_entry.runtime_data.lock.set_parameter(
                parameter, value
            )
        except AuthError:
            return "invalid_auth"
        except (TimeoutError, YaleXSBLEError, BleakError, RuntimeError) as err:
            _LOGGER.debug(
                "%s: parameter 0x%02x: no answer: %s",
                self.config_entry.title,
                parameter,
                err,
            )
            return "no_answer"
        _LOGGER.debug(
            "%s: wrote parameter 0x%02x: 0x%08x",
            self.config_entry.title,
            parameter,
            value,
        )
        if stored != value:
            _LOGGER.warning(
                "%s: the lock stored 0x%08x for parameter 0x%02x, not 0x%08x",
                self.config_entry.title,
                stored,
                parameter,
                value,
            )
        self._keep(key, stored, written=True)
        return None

    @callback
    def _keep(self, key: str, value: int, written: bool) -> None:
        """Keep a parameter value in the entry's data as the last one read or written."""
        record = ParameterRecord(
            value=value, at=dt_util.utcnow().isoformat(), written=written
        )
        self.hass.config_entries.async_update_entry(
            self.config_entry, data={**self.config_entry.data, key: record}
        )

    def _no_answer(self, key: str) -> str:
        """Return the no-answer error, naming the kept value when there is one."""
        return "no_answer_last_value" if key in self.config_entry.data else "no_answer"
