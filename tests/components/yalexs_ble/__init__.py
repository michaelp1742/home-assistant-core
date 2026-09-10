"""Tests for the Yale Access Bluetooth integration."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from yalexs_ble import ConnectionInfo, DoorStatus, LockInfo, LockState, LockStatus

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.components.yalexs_ble.const import (
    CONF_KEY,
    CONF_LOCAL_NAME,
    CONF_SLOT,
    DOMAIN,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry
from tests.components.bluetooth import generate_advertisement_data, generate_ble_device

YALE_ACCESS_LOCK_DISCOVERY_INFO = BluetoothServiceInfoBleak(
    name="M1012LU",
    address="AA:BB:CC:DD:EE:FF",
    rssi=-60,
    manufacturer_data={
        465: b"\x00\x00\xd1\xf0b;\xd8\x1dE\xd6\xba\xeeL\xdd]\xf5\xb2\xe9",
        76: b"\x061\x00Z\x8f\x93\xb2\xec\x85\x06\x00i\x00\x02\x02Q\xed\x1d\xf0",
    },
    service_uuids=[],
    service_data={},
    source="local",
    device=generate_ble_device(address="AA:BB:CC:DD:EE:FF", name="M1012LU"),
    advertisement=generate_advertisement_data(),
    time=0,
    connectable=True,
    tx_power=-127,
)


LOCK_DISCOVERY_INFO_UUID_ADDRESS = BluetoothServiceInfoBleak(
    name="M1012LU",
    address="61DE521B-F0BF-9F44-64D4-75BBE1738105",
    rssi=-60,
    manufacturer_data={
        465: b"\x00\x00\xd1\xf0b;\xd8\x1dE\xd6\xba\xeeL\xdd]\xf5\xb2\xe9",
        76: b"\x061\x00Z\x8f\x93\xb2\xec\x85\x06\x00i\x00\x02\x02Q\xed\x1d\xf0",
    },
    service_uuids=[],
    service_data={},
    source="local",
    device=generate_ble_device(address="AA:BB:CC:DD:EE:FF", name="M1012LU"),
    advertisement=generate_advertisement_data(),
    time=0,
    connectable=True,
    tx_power=-127,
)

OLD_FIRMWARE_LOCK_DISCOVERY_INFO = BluetoothServiceInfoBleak(
    name="Aug",
    address="AA:BB:CC:DD:EE:FF",
    rssi=-60,
    manufacturer_data={
        465: b"\x00\x00\xd1\xf0b;\xd8\x1dE\xd6\xba\xeeL\xdd]\xf5\xb2\xe9",
        76: b"\x061\x00Z\x8f\x93\xb2\xec\x85\x06\x00i\x00\x02\x02Q\xed\x1d\xf0",
    },
    service_uuids=[],
    service_data={},
    source="local",
    device=generate_ble_device(address="AA:BB:CC:DD:EE:FF", name="Aug"),
    advertisement=generate_advertisement_data(),
    time=0,
    connectable=True,
    tx_power=-127,
)


NOT_YALE_DISCOVERY_INFO = BluetoothServiceInfoBleak(
    name="Not",
    address="AA:BB:CC:DD:EE:FF",
    rssi=-60,
    manufacturer_data={
        33: b"\x00\x00\xd1\xf0b;\xd8\x1dE\xd6\xba\xeeL\xdd]\xf5\xb2\xe9",
        21: b"\x061\x00Z\x8f\x93\xb2\xec\x85\x06\x00i\x00\x02\x02Q\xed\x1d\xf0",
    },
    service_uuids=[],
    service_data={},
    source="local",
    device=generate_ble_device(address="AA:BB:CC:DD:EE:FF", name="Aug"),
    advertisement=generate_advertisement_data(),
    time=0,
    connectable=True,
    tx_power=-127,
)


KEY = "2fd51b8621c6a139eaffbedcb846b60f"


def mock_entry(
    options: dict[str, Any] | None = None,
    data_extra: dict[str, Any] | None = None,
) -> MockConfigEntry:
    """Return a config entry for the lock, carrying the options given.

    data_extra joins the credentials in the entry's data, for the parameter
    records the options flow keeps there.
    """
    return MockConfigEntry(
        domain=DOMAIN,
        title="Front Door",
        data={
            CONF_LOCAL_NAME: YALE_ACCESS_LOCK_DISCOVERY_INFO.name,
            CONF_ADDRESS: YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
            CONF_KEY: KEY,
            CONF_SLOT: 66,
            **(data_extra or {}),
        },
        options=options or {},
        unique_id=YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
    )


def mock_push_lock(
    *,
    lock: LockStatus = LockStatus.UNLOCKED,
    door: DoorStatus = DoorStatus.CLOSED,
    model: str = "M1XXX012LU",
    door_sense: bool | None = True,
    accepted: frozenset[str] = frozenset(),
    ignored: frozenset[str] = frozenset(),
) -> MagicMock:
    """Return a PushLock instance mock with the state the platforms read.

    door_sense is the value of the PushLock.door_sense property; None deletes
    the attribute, which is what a library without the property looks like.
    accepted and ignored are the sets the configure report comes back with.
    """
    push_lock = MagicMock()
    push_lock.start = AsyncMock(return_value=MagicMock())
    push_lock.wait_for_first_update = AsyncMock()
    push_lock.stop = AsyncMock()
    push_lock.lock = AsyncMock()
    push_lock.unlock = AsyncMock()
    push_lock.securemode = AsyncMock()
    push_lock.unlatch = AsyncMock()
    push_lock.get_parameter = AsyncMock()
    push_lock.set_parameter = AsyncMock()
    push_lock.configure = MagicMock(
        return_value=Mock(accepted=accepted, ignored=ignored)
    )
    push_lock.lock_state = LockState(
        lock=lock,
        door=door,
        battery=None,
        auth=None,
        auto_lock=None,
        auto_lock_prev=None,
    )
    push_lock.lock_info = LockInfo("Front Door", model, "1.0.0", "1.0.0")
    push_lock.connection_info = ConnectionInfo(rssi=-60)
    push_lock.address = YALE_ACCESS_LOCK_DISCOVERY_INFO.address
    if door_sense is None:
        del push_lock.door_sense
    else:
        push_lock.door_sense = door_sense
    return push_lock


def mock_push_lock_class(
    push_lock: MagicMock,
    *,
    has: frozenset[str] = frozenset(),
    supported: frozenset[str] = frozenset(),
) -> MagicMock:
    """Return a PushLock class mock that constructs push_lock.

    has names the entry points the installed library is to have; every other
    guarded name is deleted from the class and from the instance, so hasattr
    answers False for it and the version of the library in the environment
    decides no branch. supported is the set supported_options() answers with.
    """
    cls = MagicMock(return_value=push_lock)
    cls.supported_options.return_value = supported
    for name in {"configure", "supported_options", "unlatch"} - has:
        delattr(cls, name)
        # The integration reads configure() and unlatch() from the instance, so
        # the absence has to reach it as well as the class.
        if hasattr(push_lock, name):
            delattr(push_lock, name)
    return cls


@contextmanager
def patch_push_lock(push_lock_class: MagicMock) -> Iterator[None]:
    """Patch both names the integration reads PushLock through."""
    with (
        patch("homeassistant.components.yalexs_ble.close_stale_connections_by_address"),
        patch("homeassistant.components.yalexs_ble.PushLock", push_lock_class),
        patch(
            "homeassistant.components.yalexs_ble.config_flow.PushLock", push_lock_class
        ),
    ):
        yield


async def setup_entry(
    hass: HomeAssistant, entry: MockConfigEntry, push_lock_class: MagicMock
) -> None:
    """Set up a config entry against a PushLock class mock."""
    entry.add_to_hass(hass)
    with patch_push_lock(push_lock_class):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
