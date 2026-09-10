"""Test the Yale Access Bluetooth config flow."""

import asyncio
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from bleak import BleakError
from freezegun.api import FrozenDateTimeFactory
import pytest
import voluptuous as vol
from yalexs_ble import AuthError

from homeassistant import config_entries
from homeassistant.components.yalexs_ble.config_flow import _unpack_auto_lock
from homeassistant.components.yalexs_ble.const import (
    AUTO_LOCK_DURATIONS,
    AUTO_LOCK_MODES,
    CONF_ACTIVITY_COUNT,
    CONF_ALWAYS_CONNECTED,
    CONF_AUTO_LOCK,
    CONF_AUTO_LOCK_DURATION,
    CONF_AUTO_LOCK_MODE,
    CONF_BATTERY_REPORTING,
    CONF_DOOR_SENSE,
    CONF_KEY,
    CONF_LATCH_PULL_TIME,
    CONF_LOCAL_NAME,
    CONF_SECURE_MODE,
    CONF_SLOT,
    CONF_UNLATCH,
    DATA_AUTO_LOCK,
    DATA_LATCH_PULL_TIME,
    DOMAIN,
    OPTION_AS_READ,
    OPTION_DEFAULT,
    OPTION_OFF,
    OPTION_ON,
    OPTION_STATES,
    OPTION_UNCONFIGURED,
    PROGRESS_READING_AUTO_LOCK,
    PROGRESS_READING_UNLATCH_HOLD_TIME,
    STEP_AUTO_LOCK,
    STEP_AUTO_LOCK_FORM,
    STEP_LOCK_OPTIONS,
    STEP_UNLATCH_HOLD_TIME,
    STEP_UNLATCH_HOLD_TIME_FORM,
    UNLATCH_HOLD_TIMES,
)
from homeassistant.config_entries import ConfigEntryState, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, UnknownFlow
from homeassistant.helpers import translation
from homeassistant.util import dt as dt_util

from . import (
    LOCK_DISCOVERY_INFO_UUID_ADDRESS,
    NOT_YALE_DISCOVERY_INFO,
    OLD_FIRMWARE_LOCK_DISCOVERY_INFO,
    YALE_ACCESS_LOCK_DISCOVERY_INFO,
    mock_entry,
    mock_push_lock,
    mock_push_lock_class,
    patch_push_lock,
    setup_entry,
)

from tests.common import MockConfigEntry


@pytest.mark.parametrize("slot", [0, 1, 66])
async def test_user_step_success(hass: HomeAssistant, slot: int) -> None:
    """Test user step success path."""
    with patch(
        "homeassistant.components.yalexs_ble.config_flow.async_discovered_service_info",
        return_value=[NOT_YALE_DISCOVERY_INFO, YALE_ACCESS_LOCK_DISCOVERY_INFO],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_ADDRESS: YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
        },
    )
    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "key_slot"
    assert result2["errors"] == {}

    with (
        patch(
            "homeassistant.components.yalexs_ble.config_flow.PushLock.validate",
        ),
        patch(
            "homeassistant.components.yalexs_ble.async_setup_entry",
            return_value=True,
        ) as mock_setup_entry,
    ):
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {
                CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
                CONF_SLOT: slot,
            },
        )
        await hass.async_block_till_done()

    assert result3["type"] is FlowResultType.CREATE_ENTRY
    assert result3["title"] == f"{YALE_ACCESS_LOCK_DISCOVERY_INFO.name} (EEFF)"
    assert result3["data"] == {
        CONF_LOCAL_NAME: YALE_ACCESS_LOCK_DISCOVERY_INFO.name,
        CONF_ADDRESS: YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
        CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
        CONF_SLOT: slot,
    }
    assert result3["result"].unique_id == YALE_ACCESS_LOCK_DISCOVERY_INFO.address
    assert len(mock_setup_entry.mock_calls) == 1


@pytest.mark.parametrize("slot", [0, 1, 66])
async def test_user_step_from_ignored(hass: HomeAssistant, slot: int) -> None:
    """Test user step replaces an ignored entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        unique_id=YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
        source=config_entries.SOURCE_IGNORE,
    )
    entry.add_to_hass(hass)
    with patch(
        "homeassistant.components.yalexs_ble.config_flow.async_discovered_service_info",
        return_value=[NOT_YALE_DISCOVERY_INFO, YALE_ACCESS_LOCK_DISCOVERY_INFO],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_ADDRESS: YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
        },
    )
    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "key_slot"
    assert result2["errors"] == {}

    with (
        patch(
            "homeassistant.components.yalexs_ble.config_flow.PushLock.validate",
        ),
        patch(
            "homeassistant.components.yalexs_ble.async_setup_entry",
            return_value=True,
        ) as mock_setup_entry,
    ):
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {
                CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
                CONF_SLOT: slot,
            },
        )
        await hass.async_block_till_done()

    assert result3["type"] is FlowResultType.CREATE_ENTRY
    assert result3["title"] == f"{YALE_ACCESS_LOCK_DISCOVERY_INFO.name} (EEFF)"
    assert result3["data"] == {
        CONF_LOCAL_NAME: YALE_ACCESS_LOCK_DISCOVERY_INFO.name,
        CONF_ADDRESS: YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
        CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
        CONF_SLOT: slot,
    }
    assert result3["result"].unique_id == YALE_ACCESS_LOCK_DISCOVERY_INFO.address
    assert len(mock_setup_entry.mock_calls) == 1


async def test_user_step_no_devices_found(hass: HomeAssistant) -> None:
    """Test user step with no devices found."""
    with patch(
        "homeassistant.components.yalexs_ble.config_flow.async_discovered_service_info",
        return_value=[NOT_YALE_DISCOVERY_INFO],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_user_step_no_new_devices_found(hass: HomeAssistant) -> None:
    """Test user step with only existing devices found."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_LOCAL_NAME: YALE_ACCESS_LOCK_DISCOVERY_INFO.name,
            CONF_ADDRESS: YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
            CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
            CONF_SLOT: 66,
        },
        unique_id=YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
    )
    entry.add_to_hass(hass)
    with patch(
        "homeassistant.components.yalexs_ble.config_flow.async_discovered_service_info",
        return_value=[YALE_ACCESS_LOCK_DISCOVERY_INFO],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_user_step_invalid_keys(hass: HomeAssistant) -> None:
    """Test user step with invalid keys tried first."""
    with patch(
        "homeassistant.components.yalexs_ble.config_flow.async_discovered_service_info",
        return_value=[YALE_ACCESS_LOCK_DISCOVERY_INFO],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_ADDRESS: YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
        },
    )
    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "key_slot"
    assert result2["errors"] == {}

    result3 = await hass.config_entries.flow.async_configure(
        result2["flow_id"],
        {
            CONF_KEY: "dog",
            CONF_SLOT: 66,
        },
    )
    assert result3["type"] is FlowResultType.FORM
    assert result3["step_id"] == "key_slot"
    assert result3["errors"] == {CONF_KEY: "invalid_key_format"}

    result4 = await hass.config_entries.flow.async_configure(
        result3["flow_id"],
        {
            CONF_KEY: "qfd51b8621c6a139eaffbedcb846b60f",
            CONF_SLOT: 66,
        },
    )
    assert result4["type"] is FlowResultType.FORM
    assert result4["step_id"] == "key_slot"
    assert result4["errors"] == {CONF_KEY: "invalid_key_format"}

    result5 = await hass.config_entries.flow.async_configure(
        result4["flow_id"],
        {
            CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
            CONF_SLOT: 999,
        },
    )
    assert result5["type"] is FlowResultType.FORM
    assert result5["step_id"] == "key_slot"
    assert result5["errors"] == {CONF_SLOT: "invalid_key_index"}

    with (
        patch(
            "homeassistant.components.yalexs_ble.config_flow.PushLock.validate",
        ),
        patch(
            "homeassistant.components.yalexs_ble.async_setup_entry",
            return_value=True,
        ) as mock_setup_entry,
    ):
        result6 = await hass.config_entries.flow.async_configure(
            result5["flow_id"],
            {
                CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
                CONF_SLOT: 66,
            },
        )
        await hass.async_block_till_done()

    assert result6["type"] is FlowResultType.CREATE_ENTRY
    assert result6["title"] == f"{YALE_ACCESS_LOCK_DISCOVERY_INFO.name} (EEFF)"
    assert result6["data"] == {
        CONF_LOCAL_NAME: YALE_ACCESS_LOCK_DISCOVERY_INFO.name,
        CONF_ADDRESS: YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
        CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
        CONF_SLOT: 66,
    }
    assert result6["result"].unique_id == YALE_ACCESS_LOCK_DISCOVERY_INFO.address
    assert len(mock_setup_entry.mock_calls) == 1


async def test_user_step_cannot_connect(hass: HomeAssistant) -> None:
    """Test user step and we cannot connect."""
    with patch(
        "homeassistant.components.yalexs_ble.config_flow.async_discovered_service_info",
        return_value=[YALE_ACCESS_LOCK_DISCOVERY_INFO],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_ADDRESS: YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
        },
    )
    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "key_slot"
    assert result2["errors"] == {}

    with patch(
        "homeassistant.components.yalexs_ble.config_flow.PushLock.validate",
        side_effect=BleakError,
    ):
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {
                CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
                CONF_SLOT: 66,
            },
        )
        await hass.async_block_till_done()

    assert result3["type"] is FlowResultType.FORM
    assert result3["step_id"] == "key_slot"
    assert result3["errors"] == {"base": "cannot_connect"}

    with (
        patch(
            "homeassistant.components.yalexs_ble.config_flow.PushLock.validate",
        ),
        patch(
            "homeassistant.components.yalexs_ble.async_setup_entry",
            return_value=True,
        ) as mock_setup_entry,
    ):
        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"],
            {
                CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
                CONF_SLOT: 66,
            },
        )
        await hass.async_block_till_done()

    assert result4["type"] is FlowResultType.CREATE_ENTRY
    assert result4["title"] == f"{YALE_ACCESS_LOCK_DISCOVERY_INFO.name} (EEFF)"
    assert result4["data"] == {
        CONF_LOCAL_NAME: YALE_ACCESS_LOCK_DISCOVERY_INFO.name,
        CONF_ADDRESS: YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
        CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
        CONF_SLOT: 66,
    }
    assert result4["result"].unique_id == YALE_ACCESS_LOCK_DISCOVERY_INFO.address
    assert len(mock_setup_entry.mock_calls) == 1


async def test_user_step_auth_exception(hass: HomeAssistant) -> None:
    """Test user step with an authentication exception."""
    with patch(
        "homeassistant.components.yalexs_ble.config_flow.async_discovered_service_info",
        return_value=[YALE_ACCESS_LOCK_DISCOVERY_INFO, NOT_YALE_DISCOVERY_INFO],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_ADDRESS: YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
        },
    )
    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "key_slot"
    assert result2["errors"] == {}

    with patch(
        "homeassistant.components.yalexs_ble.config_flow.PushLock.validate",
        side_effect=AuthError,
    ):
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {
                CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
                CONF_SLOT: 66,
            },
        )
        await hass.async_block_till_done()

    assert result3["type"] is FlowResultType.FORM
    assert result3["step_id"] == "key_slot"
    assert result3["errors"] == {CONF_KEY: "invalid_auth"}

    with (
        patch(
            "homeassistant.components.yalexs_ble.config_flow.PushLock.validate",
        ),
        patch(
            "homeassistant.components.yalexs_ble.async_setup_entry",
            return_value=True,
        ) as mock_setup_entry,
    ):
        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"],
            {
                CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
                CONF_SLOT: 66,
            },
        )
        await hass.async_block_till_done()

    assert result4["type"] is FlowResultType.CREATE_ENTRY
    assert result4["title"] == f"{YALE_ACCESS_LOCK_DISCOVERY_INFO.name} (EEFF)"
    assert result4["data"] == {
        CONF_LOCAL_NAME: YALE_ACCESS_LOCK_DISCOVERY_INFO.name,
        CONF_ADDRESS: YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
        CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
        CONF_SLOT: 66,
    }
    assert result4["result"].unique_id == YALE_ACCESS_LOCK_DISCOVERY_INFO.address
    assert len(mock_setup_entry.mock_calls) == 1


async def test_user_step_unknown_exception(hass: HomeAssistant) -> None:
    """Test user step with an unknown exception."""
    with patch(
        "homeassistant.components.yalexs_ble.config_flow.async_discovered_service_info",
        return_value=[NOT_YALE_DISCOVERY_INFO, YALE_ACCESS_LOCK_DISCOVERY_INFO],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_ADDRESS: YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
        },
    )
    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "key_slot"
    assert result2["errors"] == {}

    with patch(
        "homeassistant.components.yalexs_ble.config_flow.PushLock.validate",
        side_effect=RuntimeError,
    ):
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {
                CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
                CONF_SLOT: 66,
            },
        )
        await hass.async_block_till_done()

    assert result3["type"] is FlowResultType.FORM
    assert result3["step_id"] == "key_slot"
    assert result3["errors"] == {"base": "unknown"}

    with (
        patch(
            "homeassistant.components.yalexs_ble.config_flow.PushLock.validate",
        ),
        patch(
            "homeassistant.components.yalexs_ble.async_setup_entry",
            return_value=True,
        ) as mock_setup_entry,
    ):
        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"],
            {
                CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
                CONF_SLOT: 66,
            },
        )
        await hass.async_block_till_done()

    assert result4["type"] is FlowResultType.CREATE_ENTRY
    assert result4["title"] == f"{YALE_ACCESS_LOCK_DISCOVERY_INFO.name} (EEFF)"
    assert result4["data"] == {
        CONF_LOCAL_NAME: YALE_ACCESS_LOCK_DISCOVERY_INFO.name,
        CONF_ADDRESS: YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
        CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
        CONF_SLOT: 66,
    }
    assert result4["result"].unique_id == YALE_ACCESS_LOCK_DISCOVERY_INFO.address
    assert len(mock_setup_entry.mock_calls) == 1


async def test_bluetooth_step_success(hass: HomeAssistant) -> None:
    """Test bluetooth step success path."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=YALE_ACCESS_LOCK_DISCOVERY_INFO,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "key_slot"
    assert result["errors"] == {}

    with (
        patch(
            "homeassistant.components.yalexs_ble.config_flow.PushLock.validate",
        ),
        patch(
            "homeassistant.components.yalexs_ble.async_setup_entry",
            return_value=True,
        ) as mock_setup_entry,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
                CONF_SLOT: 66,
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["title"] == f"{YALE_ACCESS_LOCK_DISCOVERY_INFO.name} (EEFF)"
    assert result2["data"] == {
        CONF_LOCAL_NAME: YALE_ACCESS_LOCK_DISCOVERY_INFO.name,
        CONF_ADDRESS: YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
        CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
        CONF_SLOT: 66,
    }
    assert result2["result"].unique_id == YALE_ACCESS_LOCK_DISCOVERY_INFO.address
    assert len(mock_setup_entry.mock_calls) == 1


async def test_integration_discovery_success(hass: HomeAssistant) -> None:
    """Test integration discovery step success path."""
    with patch(
        "homeassistant.components.yalexs_ble.util.async_discovered_service_info",
        return_value=[YALE_ACCESS_LOCK_DISCOVERY_INFO],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
            data={
                "name": "Front Door",
                "address": YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
                "key": "2fd51b8621c6a139eaffbedcb846b60f",
                "slot": 66,
                "serial": "M1XXX012LU",
            },
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "integration_discovery_confirm"
    assert result["errors"] is None

    with patch(
        "homeassistant.components.yalexs_ble.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {},
        )
        await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["title"] == "Front Door"
    assert result2["data"] == {
        CONF_LOCAL_NAME: YALE_ACCESS_LOCK_DISCOVERY_INFO.name,
        CONF_ADDRESS: YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
        CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
        CONF_SLOT: 66,
    }
    assert result2["result"].unique_id == YALE_ACCESS_LOCK_DISCOVERY_INFO.address
    assert len(mock_setup_entry.mock_calls) == 1


async def test_integration_discovery_device_not_found(hass: HomeAssistant) -> None:
    """Test integration discovery when the device is not found."""
    with patch(
        "homeassistant.components.yalexs_ble.util.async_discovered_service_info",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
            data={
                "name": "Front Door",
                "address": YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
                "key": "2fd51b8621c6a139eaffbedcb846b60f",
                "slot": 66,
                "serial": "M1XXX012LU",
            },
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_integration_discovery_takes_precedence_over_bluetooth(
    hass: HomeAssistant,
) -> None:
    """Test integration discovery dismisses bluetooth discovery."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=YALE_ACCESS_LOCK_DISCOVERY_INFO,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "key_slot"
    assert result["errors"] == {}
    flows = list(hass.config_entries.flow._handler_progress_index[DOMAIN])
    assert len(flows) == 1
    assert flows[0].unique_id == YALE_ACCESS_LOCK_DISCOVERY_INFO.address
    assert flows[0].local_name == YALE_ACCESS_LOCK_DISCOVERY_INFO.name

    with patch(
        "homeassistant.components.yalexs_ble.util.async_discovered_service_info",
        return_value=[YALE_ACCESS_LOCK_DISCOVERY_INFO],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
            data={
                "name": "Front Door",
                "address": YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
                "key": "2fd51b8621c6a139eaffbedcb846b60f",
                "slot": 66,
                "serial": "M1XXX012LU",
            },
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "integration_discovery_confirm"
    assert result["errors"] is None

    # the bluetooth flow should get dismissed in favor
    # of the integration discovery flow since the integration
    # discovery flow will have the keys and the bluetooth
    # flow will not
    flows = [
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["handler"] == DOMAIN
    ]
    assert len(flows) == 1

    with patch(
        "homeassistant.components.yalexs_ble.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {},
        )
        await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["title"] == "Front Door"
    assert result2["data"] == {
        CONF_LOCAL_NAME: YALE_ACCESS_LOCK_DISCOVERY_INFO.name,
        CONF_ADDRESS: YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
        CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
        CONF_SLOT: 66,
    }
    assert result2["result"].unique_id == YALE_ACCESS_LOCK_DISCOVERY_INFO.address
    assert len(mock_setup_entry.mock_calls) == 1
    flows = [
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["handler"] == DOMAIN
    ]
    assert len(flows) == 0


async def test_bluetooth_discovery_with_cached_config(
    hass: HomeAssistant,
) -> None:
    """Test bluetooth discovery when validated config is already in cache."""
    # First, populate the cache via integration discovery
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
        data={
            "name": "Front Door",
            "address": YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
            "key": "2fd51b8621c6a139eaffbedcb846b60f",
            "slot": 66,
            "serial": "M1XXX012LU",
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"

    # Now do bluetooth discovery with the cached config
    with patch(
        "homeassistant.components.yalexs_ble.PushLock.validate",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_BLUETOOTH},
            data=YALE_ACCESS_LOCK_DISCOVERY_INFO,
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "integration_discovery_confirm"
    assert result["description_placeholders"] == {
        "name": "Front Door",
        "address": YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
    }

    # Confirm the discovery
    with patch(
        "homeassistant.components.yalexs_ble.async_setup_entry",
        return_value=True,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Front Door"
    assert result["data"] == {
        CONF_LOCAL_NAME: YALE_ACCESS_LOCK_DISCOVERY_INFO.name,
        CONF_ADDRESS: YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
        CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
        CONF_SLOT: 66,
    }


async def test_integration_discovery_updates_key_unique_local_name(
    hass: HomeAssistant,
) -> None:
    """Test integration discovery updates the key with a unique local name."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_LOCAL_NAME: LOCK_DISCOVERY_INFO_UUID_ADDRESS.name,
            CONF_ADDRESS: "61DE521B-F0BF-9F44-64D4-75BBE1738105",
            CONF_KEY: "5fd51b8621c6a139eaffbedcb846b60f",
            CONF_SLOT: 11,
        },
        unique_id="61DE521B-F0BF-9F44-64D4-75BBE1738105",
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "homeassistant.components.yalexs_ble.util.async_discovered_service_info",
            return_value=[LOCK_DISCOVERY_INFO_UUID_ADDRESS],
        ),
        patch(
            "homeassistant.components.yalexs_ble.async_setup_entry",
            return_value=True,
        ) as mock_setup_entry,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
            data={
                "name": "Front Door",
                "address": "AA:BB:CC:DD:EE:FF",
                "key": "2fd51b8621c6a139eaffbedcb846b60f",
                "slot": 66,
                "serial": "M1XXX012LU",
            },
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_KEY] == "2fd51b8621c6a139eaffbedcb846b60f"
    assert entry.data[CONF_SLOT] == 66
    assert len(mock_setup_entry.mock_calls) == 1


async def test_integration_discovery_updates_key_without_unique_local_name(
    hass: HomeAssistant,
) -> None:
    """Test integration discovery updates the key without a unique local name."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_LOCAL_NAME: OLD_FIRMWARE_LOCK_DISCOVERY_INFO.name,
            CONF_ADDRESS: OLD_FIRMWARE_LOCK_DISCOVERY_INFO.address,
            CONF_KEY: "5fd51b8621c6a139eaffbedcb846b60f",
            CONF_SLOT: 11,
        },
        unique_id=OLD_FIRMWARE_LOCK_DISCOVERY_INFO.address,
    )
    entry.add_to_hass(hass)

    with patch(
        "homeassistant.components.yalexs_ble.util.async_discovered_service_info",
        return_value=[LOCK_DISCOVERY_INFO_UUID_ADDRESS],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
            data={
                "name": "Front Door",
                "address": OLD_FIRMWARE_LOCK_DISCOVERY_INFO.address,
                "key": "2fd51b8621c6a139eaffbedcb846b60f",
                "slot": 66,
                "serial": "M1XXX012LU",
            },
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_KEY] == "2fd51b8621c6a139eaffbedcb846b60f"
    assert entry.data[CONF_SLOT] == 66


async def test_integration_discovery_updates_key_duplicate_local_name(
    hass: HomeAssistant,
) -> None:
    """Test integration discovery updates the key with duplicate local names."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_LOCAL_NAME: "Aug",
            CONF_ADDRESS: OLD_FIRMWARE_LOCK_DISCOVERY_INFO.address,
            CONF_KEY: "5fd51b8621c6a139eaffbedcb846b60f",
            CONF_SLOT: 11,
        },
        unique_id=OLD_FIRMWARE_LOCK_DISCOVERY_INFO.address,
    )
    entry.add_to_hass(hass)
    entry2 = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_LOCAL_NAME: "Aug",
            CONF_ADDRESS: "CC:DD:CC:DD:CC:DD",
            CONF_KEY: "5fd51b8621c6a139eaffbedcb846b60f",
            CONF_SLOT: 11,
        },
        unique_id="CC:DD:CC:DD:CC:DD",
    )
    entry2.add_to_hass(hass)

    with patch(
        "homeassistant.components.yalexs_ble.util.async_discovered_service_info",
        return_value=[LOCK_DISCOVERY_INFO_UUID_ADDRESS],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
            data={
                "name": "Front Door",
                "address": OLD_FIRMWARE_LOCK_DISCOVERY_INFO.address,
                "key": "2fd51b8621c6a139eaffbedcb846b60f",
                "slot": 66,
                "serial": "M1XXX012LU",
            },
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_KEY] == "2fd51b8621c6a139eaffbedcb846b60f"
    assert entry.data[CONF_SLOT] == 66

    assert entry2.data[CONF_KEY] == "5fd51b8621c6a139eaffbedcb846b60f"
    assert entry2.data[CONF_SLOT] == 11


async def test_integration_discovery_takes_precedence_over_bluetooth_uuid_address(
    hass: HomeAssistant,
) -> None:
    """Test integration discovery dismisses bluetooth discovery with a uuid address."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=LOCK_DISCOVERY_INFO_UUID_ADDRESS,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "key_slot"
    assert result["errors"] == {}
    flows = list(hass.config_entries.flow._handler_progress_index[DOMAIN])
    assert len(flows) == 1
    assert flows[0].unique_id == LOCK_DISCOVERY_INFO_UUID_ADDRESS.address
    assert flows[0].local_name == LOCK_DISCOVERY_INFO_UUID_ADDRESS.name

    with patch(
        "homeassistant.components.yalexs_ble.util.async_discovered_service_info",
        return_value=[LOCK_DISCOVERY_INFO_UUID_ADDRESS],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
            data={
                "name": "Front Door",
                "address": "AA:BB:CC:DD:EE:FF",
                "key": "2fd51b8621c6a139eaffbedcb846b60f",
                "slot": 66,
                "serial": "M1XXX012LU",
            },
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "integration_discovery_confirm"
    assert result["errors"] is None

    # the bluetooth flow should get dismissed in favor
    # of the integration discovery flow since the integration
    # discovery flow will have the keys and the bluetooth
    # flow will not
    flows = [
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["handler"] == DOMAIN
    ]
    assert len(flows) == 1

    with patch(
        "homeassistant.components.yalexs_ble.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {},
        )
        await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["title"] == "Front Door"
    assert result2["data"] == {
        CONF_LOCAL_NAME: LOCK_DISCOVERY_INFO_UUID_ADDRESS.name,
        CONF_ADDRESS: LOCK_DISCOVERY_INFO_UUID_ADDRESS.address,
        CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
        CONF_SLOT: 66,
    }
    assert result2["result"].unique_id == OLD_FIRMWARE_LOCK_DISCOVERY_INFO.address
    assert len(mock_setup_entry.mock_calls) == 1
    flows = [
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["handler"] == DOMAIN
    ]
    assert len(flows) == 0


async def test_integration_discovery_precedence_over_bt_non_unique_name(
    hass: HomeAssistant,
) -> None:
    """Test integration discovery dismisses non-unique BT discovery."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=OLD_FIRMWARE_LOCK_DISCOVERY_INFO,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "key_slot"
    assert result["errors"] == {}
    flows = list(hass.config_entries.flow._handler_progress_index[DOMAIN])
    assert len(flows) == 1
    assert flows[0].unique_id == OLD_FIRMWARE_LOCK_DISCOVERY_INFO.address
    assert flows[0].local_name == OLD_FIRMWARE_LOCK_DISCOVERY_INFO.name

    with patch(
        "homeassistant.components.yalexs_ble.util.async_discovered_service_info",
        return_value=[OLD_FIRMWARE_LOCK_DISCOVERY_INFO],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
            data={
                "name": "Front Door",
                "address": OLD_FIRMWARE_LOCK_DISCOVERY_INFO.address,
                "key": "2fd51b8621c6a139eaffbedcb846b60f",
                "slot": 66,
                "serial": "M1XXX012LU",
            },
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "integration_discovery_confirm"
    assert result["errors"] is None

    # the bluetooth flow should get dismissed in favor
    # of the integration discovery flow since the integration
    # discovery flow will have the keys and the bluetooth
    # flow will not
    flows = [
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["handler"] == DOMAIN
    ]
    assert len(flows) == 1


async def test_user_is_setting_up_lock_and_discovery_happens_in_the_middle(
    hass: HomeAssistant,
) -> None:
    """Test user lock setup when discovery happens mid-validation.

    In this case the integration discovery should abort and let the
    user continue setting up the lock.
    """
    with patch(
        "homeassistant.components.yalexs_ble.config_flow.async_discovered_service_info",
        return_value=[NOT_YALE_DISCOVERY_INFO, YALE_ACCESS_LOCK_DISCOVERY_INFO],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_ADDRESS: YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
        },
    )
    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "key_slot"

    user_flow_event = asyncio.Event()
    valdidate_started = asyncio.Event()

    async def _wait_for_user_flow():
        valdidate_started.set()
        await user_flow_event.wait()

    with (
        patch(
            "homeassistant.components.yalexs_ble.config_flow.PushLock.validate",
            side_effect=_wait_for_user_flow,
        ),
        patch(
            "homeassistant.components.yalexs_ble.async_setup_entry",
            return_value=True,
        ) as mock_setup_entry,
    ):
        user_flow_task = asyncio.create_task(
            hass.config_entries.flow.async_configure(
                result2["flow_id"],
                {
                    CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
                    CONF_SLOT: 66,
                },
            )
        )
        await valdidate_started.wait()

        with patch(
            "homeassistant.components.yalexs_ble.util.async_discovered_service_info",
            return_value=[LOCK_DISCOVERY_INFO_UUID_ADDRESS],
        ):
            discovery_result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
                data={
                    "name": "Front Door",
                    "address": OLD_FIRMWARE_LOCK_DISCOVERY_INFO.address,
                    "key": "2fd51b8621c6a139eaffbedcb846b60f",
                    "slot": 66,
                    "serial": "M1XXX012LU",
                },
            )
            await hass.async_block_till_done()
        assert discovery_result["type"] is FlowResultType.ABORT
        assert discovery_result["reason"] == "already_in_progress"

        user_flow_event.set()
        user_flow_result = await user_flow_task

    assert user_flow_result["type"] is FlowResultType.CREATE_ENTRY
    assert user_flow_result["title"] == f"{YALE_ACCESS_LOCK_DISCOVERY_INFO.name} (EEFF)"
    assert user_flow_result["data"] == {
        CONF_LOCAL_NAME: YALE_ACCESS_LOCK_DISCOVERY_INFO.name,
        CONF_ADDRESS: YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
        CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
        CONF_SLOT: 66,
    }
    assert (
        user_flow_result["result"].unique_id == YALE_ACCESS_LOCK_DISCOVERY_INFO.address
    )
    assert len(mock_setup_entry.mock_calls) == 1


async def test_reauth(hass: HomeAssistant) -> None:
    """Test reauthentication."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_LOCAL_NAME: YALE_ACCESS_LOCK_DISCOVERY_INFO.name,
            CONF_ADDRESS: YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
            CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
            CONF_SLOT: 66,
        },
        unique_id=YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
    )
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_validate"

    with patch(
        "homeassistant.components.yalexs_ble.config_flow.PushLock.validate",
        side_effect=RuntimeError,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
                CONF_SLOT: 66,
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "reauth_validate"
    assert result2["errors"] == {"base": "no_longer_in_range"}

    with (
        patch(
            "homeassistant.components.yalexs_ble.config_flow.async_ble_device_from_address",
            return_value=YALE_ACCESS_LOCK_DISCOVERY_INFO,
        ),
        patch(
            "homeassistant.components.yalexs_ble.config_flow.PushLock.validate",
        ),
        patch(
            "homeassistant.components.yalexs_ble.async_setup_entry",
            return_value=True,
        ) as mock_setup_entry,
    ):
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {
                CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
                CONF_SLOT: 67,
            },
        )
        await hass.async_block_till_done()

    assert result3["type"] is FlowResultType.ABORT
    assert result3["reason"] == "reauth_successful"
    assert len(mock_setup_entry.mock_calls) == 1


async def test_user_step_with_cached_config(hass: HomeAssistant) -> None:
    """Test user step when config is already cached from integration discovery."""
    # First, simulate integration discovery to populate the cache
    discovery_result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
        data={
            "name": "Front Door",
            "address": YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
            "key": "2fd51b8621c6a139eaffbedcb846b60f",
            "slot": 66,
            "serial": "M1XXX012LU",
        },
    )
    assert discovery_result["type"] is FlowResultType.ABORT
    assert discovery_result["reason"] == "no_devices_found"

    # Now start a user flow - it should use the cached config
    with patch(
        "homeassistant.components.yalexs_ble.config_flow.async_discovered_service_info",
        return_value=[YALE_ACCESS_LOCK_DISCOVERY_INFO],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    # The dropdown should show "Front Door (AA:BB:CC:DD:EE:FF)" from cached config
    # This is the line 346 case we're testing
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_ADDRESS: YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
        },
    )
    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "key_slot"

    # The key_slot step should auto-complete with cached values
    # When no user input is provided, it should use the cached config
    with (
        patch(
            "homeassistant.components.yalexs_ble.config_flow.PushLock.validate",
        ),
        patch(
            "homeassistant.components.yalexs_ble.async_setup_entry",
            return_value=True,
        ) as mock_setup_entry,
    ):
        # No user input triggers using cached config
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            None,  # None triggers checking for cached config
        )
        await hass.async_block_till_done()

    assert result3["type"] is FlowResultType.CREATE_ENTRY
    assert result3["title"] == "Front Door"  # Uses the name from cached config
    assert result3["data"] == {
        CONF_LOCAL_NAME: YALE_ACCESS_LOCK_DISCOVERY_INFO.name,
        CONF_ADDRESS: YALE_ACCESS_LOCK_DISCOVERY_INFO.address,
        CONF_KEY: "2fd51b8621c6a139eaffbedcb846b60f",
        CONF_SLOT: 66,
    }
    assert result3["result"].unique_id == YALE_ACCESS_LOCK_DISCOVERY_INFO.address
    assert len(mock_setup_entry.mock_calls) == 1


async def _open_lock_options(
    hass: HomeAssistant, entry: MockConfigEntry
) -> ConfigFlowResult:
    """Open the options flow and choose the Lock options row."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": STEP_LOCK_OPTIONS}
    )


async def test_options_opens_on_the_menu_with_lock_options_alone(
    hass: HomeAssistant,
) -> None:
    """Test the options flow opens on a menu with the Lock options row alone."""
    entry = mock_entry()
    push_lock_class = mock_push_lock_class(
        mock_push_lock(), has=frozenset({"configure", "supported_options"})
    )
    await setup_entry(hass, entry, push_lock_class)

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "init"
    assert result["menu_options"] == [STEP_LOCK_OPTIONS]
    assert result["description_placeholders"] == {"title": "Front Door"}


async def test_options_menu_has_one_row_on_an_entry_that_is_not_loaded(
    hass: HomeAssistant,
) -> None:
    """Test the menu offers Lock options alone on an entry that is not loaded."""
    entry = mock_entry()
    entry.add_to_hass(hass)
    push_lock_class = mock_push_lock_class(
        mock_push_lock(), has=frozenset({"configure", "supported_options"})
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["menu_options"] == [STEP_LOCK_OPTIONS]
        assert result["description_placeholders"] == {"title": "Front Door"}
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": STEP_LOCK_OPTIONS}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == STEP_LOCK_OPTIONS


async def test_options_lock_options_shows_secure_mode_on_an_older_library(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Test a library that advertises nothing leaves secure mode on the form."""
    caplog.set_level(logging.DEBUG, logger="homeassistant.components.yalexs_ble")
    entry = mock_entry()
    push_lock_class = mock_push_lock_class(mock_push_lock())
    await setup_entry(hass, entry, push_lock_class)

    with patch_push_lock(push_lock_class):
        result = await _open_lock_options(hass, entry)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == STEP_LOCK_OPTIONS
    assert {str(key) for key in result["data_schema"].schema} == {
        CONF_ALWAYS_CONNECTED,
        CONF_SECURE_MODE,
    }
    assert "library-supported options: none" in caplog.text


async def test_options_lock_options_renders_the_fields_in_the_ruled_order(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Test the form renders the connection field and the features in the ruled order, and logs the report."""
    caplog.set_level(logging.DEBUG, logger="homeassistant.components.yalexs_ble")
    entry = mock_entry()
    push_lock_class = mock_push_lock_class(
        mock_push_lock(
            accepted=frozenset({"always_connected", "door_sense"}),
            ignored=frozenset({"secure_mode"}),
        ),
        has=frozenset({"configure", "supported_options"}),
        supported=frozenset(
            {
                "activity_count",
                "always_connected",
                "battery_reporting",
                "door_sense",
                "parameters",
                "secure_mode",
                "unlatch",
            }
        ),
    )
    await setup_entry(hass, entry, push_lock_class)

    with patch_push_lock(push_lock_class):
        result = await _open_lock_options(hass, entry)

    assert [str(key) for key in result["data_schema"].schema] == [
        CONF_ALWAYS_CONNECTED,
        CONF_DOOR_SENSE,
        CONF_AUTO_LOCK,
        CONF_SECURE_MODE,
        CONF_UNLATCH,
        CONF_BATTERY_REPORTING,
        CONF_ACTIVITY_COUNT,
    ]
    assert (
        "options report at setup: accepted always_connected, door_sense; ignored "
        "secure_mode" in caplog.text
    )


async def test_the_feature_selects_are_translated(hass: HomeAssistant) -> None:
    """Test every feature select state has a label under the selector's translation key."""
    entry = mock_entry()
    push_lock_class = mock_push_lock_class(mock_push_lock())
    await setup_entry(hass, entry, push_lock_class)

    with patch_push_lock(push_lock_class):
        result = await _open_lock_options(hass, entry)

    select = result["data_schema"].schema[CONF_SECURE_MODE]
    assert select.config["translation_key"] == "feature_state"
    translations = await translation.async_get_translations(
        hass, "en", "selector", {DOMAIN}
    )
    assert all(
        f"component.{DOMAIN}.selector.feature_state.options.{state}" in translations
        for state in OPTION_STATES
    )


async def test_the_parameter_selects_are_translated(hass: HomeAssistant) -> None:
    """Test every option of the three parameter selects has a label under its key."""
    translations = await translation.async_get_translations(
        hass, "en", "selector", {DOMAIN}
    )

    assert all(
        f"component.{DOMAIN}.selector.{key}" in translations
        for key in (
            *(f"auto_lock_mode.options.{mode}" for mode in AUTO_LOCK_MODES),
            *(
                f"auto_lock_duration.options.{seconds}"
                for seconds in (*AUTO_LOCK_DURATIONS, OPTION_AS_READ)
            ),
            *(
                f"unlatch_hold_time.options.{seconds}"
                for seconds in (*UNLATCH_HOLD_TIMES, OPTION_AS_READ)
            ),
        )
    )


@pytest.mark.parametrize(
    ("supported", "keys"),
    [
        pytest.param(
            frozenset({"parameters"}),
            {CONF_ALWAYS_CONNECTED, CONF_AUTO_LOCK, CONF_SECURE_MODE},
            id="advertised",
        ),
        pytest.param(
            frozenset(),
            {CONF_ALWAYS_CONNECTED, CONF_SECURE_MODE},
            id="not advertised",
        ),
    ],
)
async def test_options_lock_options_shows_auto_lock_when_parameters_is_advertised(
    hass: HomeAssistant, supported: frozenset[str], keys: set[str]
) -> None:
    """Test the Auto-Lock select appears when the parameters key is advertised."""
    entry = mock_entry()
    push_lock_class = mock_push_lock_class(
        mock_push_lock(),
        has=frozenset({"configure", "supported_options"}),
        supported=supported,
    )
    await setup_entry(hass, entry, push_lock_class)

    with patch_push_lock(push_lock_class):
        result = await _open_lock_options(hass, entry)

    assert {str(key) for key in result["data_schema"].schema} == keys


async def test_options_lock_options_stores_the_choices(hass: HomeAssistant) -> None:
    """Test the submit merges the choices over the stored options."""
    entry = mock_entry({CONF_ACTIVITY_COUNT: OPTION_ON, "another_release_key": "on"})
    push_lock = mock_push_lock()
    push_lock_class = mock_push_lock_class(
        push_lock,
        has=frozenset({"configure", "supported_options"}),
        supported=frozenset({"door_sense"}),
    )
    await setup_entry(hass, entry, push_lock_class)

    with patch_push_lock(push_lock_class):
        result = await _open_lock_options(hass, entry)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_ALWAYS_CONNECTED: True,
                CONF_SECURE_MODE: OPTION_OFF,
                CONF_DOOR_SENSE: OPTION_DEFAULT,
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    # A stored key this release has no field for survives; the library default
    # choice is stored and sends nothing.
    assert entry.options == {
        CONF_ALWAYS_CONNECTED: True,
        CONF_ACTIVITY_COUNT: OPTION_ON,
        CONF_SECURE_MODE: OPTION_OFF,
        CONF_DOOR_SENSE: OPTION_DEFAULT,
        "another_release_key": "on",
    }
    assert push_lock.configure.mock_calls[-1].args[0] == {
        "always_connected": True,
        "activity_count": True,
        "secure_mode": False,
    }


async def test_options_not_set_clears_the_key(hass: HomeAssistant) -> None:
    """Test choosing not set returns a key to unconfigured."""
    entry = mock_entry({CONF_DOOR_SENSE: OPTION_ON})
    push_lock = mock_push_lock()
    push_lock_class = mock_push_lock_class(
        push_lock,
        has=frozenset({"configure", "supported_options"}),
        supported=frozenset({"door_sense"}),
    )
    await setup_entry(hass, entry, push_lock_class)

    with patch_push_lock(push_lock_class):
        result = await _open_lock_options(hass, entry)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_ALWAYS_CONNECTED: False,
                CONF_SECURE_MODE: OPTION_UNCONFIGURED,
                CONF_DOOR_SENSE: OPTION_UNCONFIGURED,
            },
        )
        await hass.async_block_till_done()

    assert entry.options == {CONF_ALWAYS_CONNECTED: False}
    assert push_lock.configure.mock_calls[-1].args[0] == {"always_connected": False}


async def test_options_lock_options_defaults_to_the_stored_choice(
    hass: HomeAssistant,
) -> None:
    """Test a stored choice is the rendered default and an absent key is not set."""
    entry = mock_entry({CONF_ALWAYS_CONNECTED: True, CONF_DOOR_SENSE: OPTION_OFF})
    push_lock_class = mock_push_lock_class(
        mock_push_lock(),
        has=frozenset({"configure", "supported_options"}),
        supported=frozenset({"door_sense"}),
    )
    await setup_entry(hass, entry, push_lock_class)

    with patch_push_lock(push_lock_class):
        result = await _open_lock_options(hass, entry)

    defaults = {str(key): key.default() for key in result["data_schema"].schema}
    assert defaults == {
        CONF_ALWAYS_CONNECTED: True,
        CONF_SECURE_MODE: OPTION_UNCONFIGURED,
        CONF_DOOR_SENSE: OPTION_OFF,
    }


async def test_options_lock_options_shows_a_stored_key_the_library_dropped(
    hass: HomeAssistant,
) -> None:
    """Test a key left by a library change can be returned to not set."""
    entry = mock_entry({CONF_DOOR_SENSE: OPTION_OFF})
    push_lock_class = mock_push_lock_class(
        mock_push_lock(), has=frozenset({"configure", "supported_options"})
    )
    await setup_entry(hass, entry, push_lock_class)

    with patch_push_lock(push_lock_class):
        result = await _open_lock_options(hass, entry)
        assert {str(key) for key in result["data_schema"].schema} == {
            CONF_ALWAYS_CONNECTED,
            CONF_SECURE_MODE,
            CONF_DOOR_SENSE,
        }
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_ALWAYS_CONNECTED: False,
                CONF_SECURE_MODE: OPTION_UNCONFIGURED,
                CONF_DOOR_SENSE: OPTION_UNCONFIGURED,
            },
        )
        await hass.async_block_till_done()

    assert entry.options == {CONF_ALWAYS_CONNECTED: False}


async def test_options_lock_options_submit_ends_the_flow_and_reloads_the_entry(
    hass: HomeAssistant,
) -> None:
    """Test a Lock options submit ends the flow and reloads the entry."""
    entry = mock_entry()
    push_lock = mock_push_lock()
    push_lock_class = mock_push_lock_class(
        push_lock, has=frozenset({"configure", "supported_options"})
    )
    await setup_entry(hass, entry, push_lock_class)

    with patch_push_lock(push_lock_class):
        result = await _open_lock_options(hass, entry)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_ALWAYS_CONNECTED: True, CONF_SECURE_MODE: OPTION_ON},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.state is ConfigEntryState.LOADED
    assert push_lock_class.call_count == 2
    assert push_lock.configure.mock_calls[1].args[0] == {
        "always_connected": True,
        "secure_mode": True,
    }


PARAMETERS_ACCEPTED = frozenset({"parameters"})
BOTH_PAGES_ACCEPTED = frozenset({"parameters", "unlatch"})
# 1800 seconds in both halves: On a timer, 30 min.
TIMED_1800 = 0x07080708
# 30 seconds in the low half alone: Instant, 30 s.
INSTANT_30 = 0x0000001E
# 45 seconds in both halves, a duration the list does not hold.
TIMED_45 = 0x002D002D
# 90 seconds in the high half over 1800 in the low: the halves differ, and
# the high half is the duration shown.
TIMED_90_OVER_1800 = 0x005A0708


async def _stores_the_value(parameter: int, value: int) -> int:
    """Answer a write as a lock that stored what it was sent."""
    return value


async def _setup_parameter_entry(
    hass: HomeAssistant,
    push_lock: MagicMock,
    options: dict[str, Any],
    data_extra: dict[str, Any] | None = None,
) -> tuple[MockConfigEntry, MagicMock]:
    """Set up an entry against a library that carries the parameter ioctls."""
    entry = mock_entry(options, data_extra)
    push_lock_class = mock_push_lock_class(
        push_lock, has=frozenset({"configure", "supported_options"})
    )
    await setup_entry(hass, entry, push_lock_class)
    return entry, push_lock_class


async def _open_parameter_page(
    hass: HomeAssistant, flow_id: str, step_id: str, progress_action: str
) -> ConfigFlowResult:
    """Choose a parameter row, let its read finish, and return the form."""
    result = await hass.config_entries.options.async_configure(
        flow_id, {"next_step_id": step_id}
    )
    assert result["type"] is FlowResultType.SHOW_PROGRESS
    assert result["progress_action"] == progress_action
    await hass.async_block_till_done()
    return await hass.config_entries.options.async_configure(flow_id)


async def test_options_menu_shows_the_rows_whose_choices_are_on_and_accepted(
    hass: HomeAssistant,
) -> None:
    """Test both parameter rows follow Lock options when the choices are on."""
    entry, push_lock_class = await _setup_parameter_entry(
        hass,
        mock_push_lock(accepted=BOTH_PAGES_ACCEPTED),
        {CONF_AUTO_LOCK: OPTION_ON, CONF_UNLATCH: OPTION_ON},
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["menu_options"] == [
        STEP_LOCK_OPTIONS,
        STEP_AUTO_LOCK,
        STEP_UNLATCH_HOLD_TIME,
    ]
    assert result["description_placeholders"] == {
        "title": "Front Door",
        "auto_lock": "Not read yet",
        "unlatch_hold_time": "Not read yet",
    }


async def test_options_menu_hides_a_row_when_parameters_was_not_accepted(
    hass: HomeAssistant,
) -> None:
    """Test a library that did not take the parameters key leaves no page."""
    entry, push_lock_class = await _setup_parameter_entry(
        hass,
        mock_push_lock(accepted=frozenset({"unlatch"})),
        {CONF_AUTO_LOCK: OPTION_ON, CONF_UNLATCH: OPTION_ON},
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["menu_options"] == [STEP_LOCK_OPTIONS]
    assert result["description_placeholders"] == {"title": "Front Door"}


async def test_options_menu_hides_the_hold_time_row_when_unlatch_is_off(
    hass: HomeAssistant,
) -> None:
    """Test the hold time page needs the unlatch choice as well as the ioctls."""
    entry, push_lock_class = await _setup_parameter_entry(
        hass,
        mock_push_lock(accepted=BOTH_PAGES_ACCEPTED),
        {CONF_AUTO_LOCK: OPTION_ON, CONF_UNLATCH: OPTION_OFF},
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["menu_options"] == [STEP_LOCK_OPTIONS, STEP_AUTO_LOCK]


async def test_auto_lock_page_reads_the_lock_and_shows_the_decoded_value(
    hass: HomeAssistant,
) -> None:
    """Test the page reads the parameter once and shows the decoded value."""
    push_lock = mock_push_lock(accepted=PARAMETERS_ACCEPTED)
    push_lock.get_parameter.return_value = TIMED_1800
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_AUTO_LOCK: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass, result["flow_id"], STEP_AUTO_LOCK, PROGRESS_READING_AUTO_LOCK
        )

    push_lock.get_parameter.assert_awaited_once_with(0x28)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == STEP_AUTO_LOCK_FORM
    assert {str(key): key.default() for key in result["data_schema"].schema} == {
        CONF_AUTO_LOCK_MODE: "timed",
        CONF_AUTO_LOCK_DURATION: "1800",
    }
    assert result["description_placeholders"]["as_read"] == ""
    durations = result["data_schema"].schema[CONF_AUTO_LOCK_DURATION].config["options"]
    assert durations[-1] == "1800"
    assert OPTION_AS_READ not in durations


async def test_auto_lock_page_shows_off_with_the_default_duration_for_zero(
    hass: HomeAssistant,
) -> None:
    """Test a zero value is Off, with the duration the app arms as the default."""
    push_lock = mock_push_lock(accepted=PARAMETERS_ACCEPTED)
    push_lock.get_parameter.return_value = 0
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_AUTO_LOCK: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass, result["flow_id"], STEP_AUTO_LOCK, PROGRESS_READING_AUTO_LOCK
        )

    assert {str(key): key.default() for key in result["data_schema"].schema} == {
        CONF_AUTO_LOCK_MODE: "off",
        CONF_AUTO_LOCK_DURATION: "90",
    }


def test_unpack_auto_lock_decodes_off_as_zero_seconds() -> None:
    """Test the decoder returns Off with zero seconds."""
    assert _unpack_auto_lock(0) == ("off", 0)


async def test_auto_lock_page_shows_instant_from_the_low_half(
    hass: HomeAssistant,
) -> None:
    """Test a value in the low half alone decodes to Instant."""
    push_lock = mock_push_lock(accepted=PARAMETERS_ACCEPTED)
    push_lock.get_parameter.return_value = INSTANT_30
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_AUTO_LOCK: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass, result["flow_id"], STEP_AUTO_LOCK, PROGRESS_READING_AUTO_LOCK
        )

    assert {str(key): key.default() for key in result["data_schema"].schema} == {
        CONF_AUTO_LOCK_MODE: "instant",
        CONF_AUTO_LOCK_DURATION: "30",
    }


async def test_auto_lock_page_offers_as_read_for_a_duration_outside_the_list(
    hass: HomeAssistant,
) -> None:
    """Test a duration the list does not hold is offered as read, and named."""
    push_lock = mock_push_lock(accepted=PARAMETERS_ACCEPTED)
    push_lock.get_parameter.return_value = TIMED_45
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_AUTO_LOCK: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass, result["flow_id"], STEP_AUTO_LOCK, PROGRESS_READING_AUTO_LOCK
        )

    schema = result["data_schema"].schema
    assert {str(key): key.default() for key in schema} == {
        CONF_AUTO_LOCK_MODE: "timed",
        CONF_AUTO_LOCK_DURATION: OPTION_AS_READ,
    }
    duration = next(
        value for key, value in schema.items() if str(key) == CONF_AUTO_LOCK_DURATION
    )
    assert duration.config["options"][-1] == OPTION_AS_READ
    assert result["description_placeholders"]["as_read"] == (
        "The lock holds 45 s, which is not on the list. As read from the lock keeps it."
    )


async def test_auto_lock_submit_writes_the_packed_value_and_returns_to_the_menu(
    hass: HomeAssistant,
) -> None:
    """Test a submit writes the packed value, keeps it, and shows the menu again."""
    push_lock = mock_push_lock(accepted=PARAMETERS_ACCEPTED)
    push_lock.get_parameter.return_value = 0
    push_lock.set_parameter = AsyncMock(side_effect=_stores_the_value)
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_AUTO_LOCK: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass, result["flow_id"], STEP_AUTO_LOCK, PROGRESS_READING_AUTO_LOCK
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_AUTO_LOCK_MODE: "timed", CONF_AUTO_LOCK_DURATION: "1800"},
        )
        await hass.async_block_till_done()

    push_lock.set_parameter.assert_awaited_once_with(0x28, TIMED_1800)
    assert result["type"] is FlowResultType.MENU
    record = entry.data[DATA_AUTO_LOCK]
    assert record["value"] == TIMED_1800
    assert record["written"] is True
    assert isinstance(record["at"], str)
    # Nothing was stored in the options, so the entry was not reloaded.
    assert entry.options == {CONF_AUTO_LOCK: OPTION_ON}
    assert push_lock_class.call_count == 1


@pytest.mark.parametrize(
    ("read_value", "mode", "duration"),
    [
        pytest.param(TIMED_1800, "timed", "1800", id="equal_halves"),
        pytest.param(TIMED_90_OVER_1800, "timed", "90", id="unequal_halves"),
    ],
)
async def test_auto_lock_submit_without_a_change_writes_nothing(
    hass: HomeAssistant, read_value: int, mode: str, duration: str
) -> None:
    """Test a submit of the fields as they were read writes nothing."""
    push_lock = mock_push_lock(accepted=PARAMETERS_ACCEPTED)
    push_lock.get_parameter.return_value = read_value
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_AUTO_LOCK: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass, result["flow_id"], STEP_AUTO_LOCK, PROGRESS_READING_AUTO_LOCK
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_AUTO_LOCK_MODE: mode, CONF_AUTO_LOCK_DURATION: duration},
        )

    assert result["type"] is FlowResultType.MENU
    push_lock.set_parameter.assert_not_called()


async def test_auto_lock_submit_with_as_read_writes_nothing(
    hass: HomeAssistant,
) -> None:
    """Test keeping the duration the lock holds writes nothing."""
    push_lock = mock_push_lock(accepted=PARAMETERS_ACCEPTED)
    push_lock.get_parameter.return_value = TIMED_45
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_AUTO_LOCK: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass, result["flow_id"], STEP_AUTO_LOCK, PROGRESS_READING_AUTO_LOCK
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_AUTO_LOCK_MODE: "timed", CONF_AUTO_LOCK_DURATION: OPTION_AS_READ},
        )

    assert result["type"] is FlowResultType.MENU
    push_lock.set_parameter.assert_not_called()


async def test_auto_lock_submit_off_writes_zero(hass: HomeAssistant) -> None:
    """Test Off is written as zero whatever the duration field says."""
    push_lock = mock_push_lock(accepted=PARAMETERS_ACCEPTED)
    push_lock.get_parameter.return_value = INSTANT_30
    push_lock.set_parameter = AsyncMock(side_effect=_stores_the_value)
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_AUTO_LOCK: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass, result["flow_id"], STEP_AUTO_LOCK, PROGRESS_READING_AUTO_LOCK
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_AUTO_LOCK_MODE: "off", CONF_AUTO_LOCK_DURATION: "30"},
        )
        await hass.async_block_till_done()

    push_lock.set_parameter.assert_awaited_once_with(0x28, 0)
    assert entry.data[DATA_AUTO_LOCK]["value"] == 0


async def test_auto_lock_off_with_another_duration_writes_nothing(
    hass: HomeAssistant,
) -> None:
    """Test a duration change under Off packs the zero the lock holds already."""
    push_lock = mock_push_lock(accepted=PARAMETERS_ACCEPTED)
    push_lock.get_parameter.return_value = 0
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_AUTO_LOCK: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass, result["flow_id"], STEP_AUTO_LOCK, PROGRESS_READING_AUTO_LOCK
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_AUTO_LOCK_MODE: "off", CONF_AUTO_LOCK_DURATION: "30"},
        )

    assert result["type"] is FlowResultType.MENU
    push_lock.set_parameter.assert_not_called()


async def test_auto_lock_mode_change_with_as_read_keeps_the_seconds(
    hass: HomeAssistant,
) -> None:
    """Test a mode change that keeps the read duration packs those seconds."""
    push_lock = mock_push_lock(accepted=PARAMETERS_ACCEPTED)
    push_lock.get_parameter.return_value = TIMED_45
    push_lock.set_parameter = AsyncMock(side_effect=_stores_the_value)
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_AUTO_LOCK: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass, result["flow_id"], STEP_AUTO_LOCK, PROGRESS_READING_AUTO_LOCK
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_AUTO_LOCK_MODE: "instant", CONF_AUTO_LOCK_DURATION: OPTION_AS_READ},
        )
        await hass.async_block_till_done()

    push_lock.set_parameter.assert_awaited_once_with(0x28, 0x0000002D)


async def test_auto_lock_record_stores_the_value_the_lock_returned(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Test the record holds the lock's confirmation, and the difference is warned."""
    push_lock = mock_push_lock(accepted=PARAMETERS_ACCEPTED)
    push_lock.get_parameter.return_value = 0
    push_lock.set_parameter.return_value = 0x0708070A
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_AUTO_LOCK: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass, result["flow_id"], STEP_AUTO_LOCK, PROGRESS_READING_AUTO_LOCK
        )
        await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_AUTO_LOCK_MODE: "timed", CONF_AUTO_LOCK_DURATION: "1800"},
        )
        await hass.async_block_till_done()

    assert entry.data[DATA_AUTO_LOCK]["value"] == 0x0708070A
    warnings = [
        record for record in caplog.records if record.levelno == logging.WARNING
    ]
    assert len(warnings) == 1
    assert (
        "the lock stored 0x0708070a for parameter 0x28, not 0x07080708"
        in warnings[0].getMessage()
    )


async def test_auto_lock_read_that_times_out_shows_the_error_and_the_kept_value(
    hass: HomeAssistant,
) -> None:
    """Test a read the lock does not answer falls back to the kept record."""
    push_lock = mock_push_lock(accepted=PARAMETERS_ACCEPTED)
    push_lock.get_parameter.side_effect = TimeoutError
    entry, push_lock_class = await _setup_parameter_entry(
        hass,
        push_lock,
        {CONF_AUTO_LOCK: OPTION_ON},
        {
            DATA_AUTO_LOCK: {
                "value": INSTANT_30,
                "at": dt_util.utcnow().isoformat(),
                "written": False,
            }
        },
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass, result["flow_id"], STEP_AUTO_LOCK, PROGRESS_READING_AUTO_LOCK
        )

    assert result["errors"] == {"base": "no_answer_last_value"}
    assert result["description_placeholders"]["when"] != ""
    assert {str(key): key.default() for key in result["data_schema"].schema} == {
        CONF_AUTO_LOCK_MODE: "instant",
        CONF_AUTO_LOCK_DURATION: "30",
    }


async def test_auto_lock_read_that_times_out_with_no_record_shows_no_answer(
    hass: HomeAssistant,
) -> None:
    """Test a failed read with nothing kept leaves both fields to be chosen."""
    push_lock = mock_push_lock(accepted=PARAMETERS_ACCEPTED)
    push_lock.get_parameter.side_effect = TimeoutError
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_AUTO_LOCK: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass, result["flow_id"], STEP_AUTO_LOCK, PROGRESS_READING_AUTO_LOCK
        )

    assert result["errors"] == {"base": "no_answer"}
    assert result["description_placeholders"] == {"as_read": "", "when": ""}
    assert [key.default for key in result["data_schema"].schema] == [
        vol.UNDEFINED,
        vol.UNDEFINED,
    ]


async def test_auto_lock_read_that_raises_unexpectedly_shows_no_answer(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Test an exception the read does not expect is logged and shown as no answer."""
    push_lock = mock_push_lock(accepted=PARAMETERS_ACCEPTED)
    push_lock.get_parameter.side_effect = ValueError("bad frame")
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_AUTO_LOCK: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass, result["flow_id"], STEP_AUTO_LOCK, PROGRESS_READING_AUTO_LOCK
        )

    assert result["errors"] == {"base": "no_answer"}
    errors = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "the read failed" in errors[0].getMessage()


async def test_auto_lock_submit_after_a_failed_read_writes_the_fields(
    hass: HomeAssistant,
) -> None:
    """Test a submit after a failed read writes what the user chose."""
    push_lock = mock_push_lock(accepted=PARAMETERS_ACCEPTED)
    push_lock.get_parameter.side_effect = TimeoutError
    push_lock.set_parameter = AsyncMock(side_effect=_stores_the_value)
    entry, push_lock_class = await _setup_parameter_entry(
        hass,
        push_lock,
        {CONF_AUTO_LOCK: OPTION_ON},
        {
            DATA_AUTO_LOCK: {
                "value": INSTANT_30,
                "at": dt_util.utcnow().isoformat(),
                "written": False,
            }
        },
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass, result["flow_id"], STEP_AUTO_LOCK, PROGRESS_READING_AUTO_LOCK
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_AUTO_LOCK_MODE: "timed", CONF_AUTO_LOCK_DURATION: "1800"},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.MENU
    push_lock.set_parameter.assert_awaited_once_with(0x28, TIMED_1800)


async def test_auto_lock_write_that_times_out_shows_the_error_and_keeps_the_fields(
    hass: HomeAssistant,
) -> None:
    """Test a write the lock does not answer renders the form with what was sent."""
    push_lock = mock_push_lock(accepted=PARAMETERS_ACCEPTED)
    push_lock.get_parameter.return_value = 0
    push_lock.set_parameter.side_effect = TimeoutError
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_AUTO_LOCK: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass, result["flow_id"], STEP_AUTO_LOCK, PROGRESS_READING_AUTO_LOCK
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_AUTO_LOCK_MODE: "timed", CONF_AUTO_LOCK_DURATION: "1800"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == STEP_AUTO_LOCK_FORM
    assert result["errors"] == {"base": "no_answer"}
    assert {str(key): key.default() for key in result["data_schema"].schema} == {
        CONF_AUTO_LOCK_MODE: "timed",
        CONF_AUTO_LOCK_DURATION: "1800",
    }
    # The read kept its record, which the failed write left as it was.
    assert entry.data[DATA_AUTO_LOCK]["value"] == 0


async def test_auto_lock_write_on_an_unloaded_entry_shows_the_no_answer_error(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Test an entry unloaded between the read and the submit is asked nothing."""
    caplog.set_level(logging.DEBUG, logger="homeassistant.components.yalexs_ble")
    push_lock = mock_push_lock(accepted=PARAMETERS_ACCEPTED)
    push_lock.get_parameter.return_value = 0
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_AUTO_LOCK: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass, result["flow_id"], STEP_AUTO_LOCK, PROGRESS_READING_AUTO_LOCK
        )
        await hass.config_entries.async_unload(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_AUTO_LOCK_MODE: "timed", CONF_AUTO_LOCK_DURATION: "1800"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_answer"}
    push_lock.set_parameter.assert_not_called()
    assert "parameter 0x28: the entry is not loaded" in caplog.text


async def test_auto_lock_write_that_fails_authentication_shows_invalid_auth(
    hass: HomeAssistant,
) -> None:
    """Test a write that fails authentication shows the invalid authentication error."""
    push_lock = mock_push_lock(accepted=PARAMETERS_ACCEPTED)
    push_lock.get_parameter.return_value = 0
    push_lock.set_parameter.side_effect = AuthError
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_AUTO_LOCK: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass, result["flow_id"], STEP_AUTO_LOCK, PROGRESS_READING_AUTO_LOCK
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_AUTO_LOCK_MODE: "timed", CONF_AUTO_LOCK_DURATION: "1800"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_auto_lock_auth_error_shows_invalid_auth(hass: HomeAssistant) -> None:
    """Test a read that fails authentication shows the invalid authentication error."""
    push_lock = mock_push_lock(accepted=PARAMETERS_ACCEPTED)
    push_lock.get_parameter.side_effect = AuthError
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_AUTO_LOCK: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass, result["flow_id"], STEP_AUTO_LOCK, PROGRESS_READING_AUTO_LOCK
        )

    assert result["errors"] == {"base": "invalid_auth"}


async def test_auto_lock_read_keeps_the_value_in_entry_data(
    hass: HomeAssistant,
) -> None:
    """Test the value a read returned is kept as the last one read."""
    push_lock = mock_push_lock(accepted=PARAMETERS_ACCEPTED)
    push_lock.get_parameter.return_value = INSTANT_30
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_AUTO_LOCK: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        await _open_parameter_page(
            hass, result["flow_id"], STEP_AUTO_LOCK, PROGRESS_READING_AUTO_LOCK
        )

    record = entry.data[DATA_AUTO_LOCK]
    assert record["value"] == INSTANT_30
    assert record["written"] is False
    assert isinstance(record["at"], str)


@pytest.mark.parametrize(
    ("value", "setting"),
    [
        pytest.param(TIMED_1800, "On a timer, 30 min", id="timed"),
        pytest.param(0, "Off", id="off"),
    ],
)
async def test_options_menu_row_shows_the_kept_value_and_its_time(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, value: int, setting: str
) -> None:
    """Test the Auto-Lock row names the mode, the duration when there is one, and when it was read."""
    freezer.move_to("2026-09-11 10:32:00+00:00")
    entry, push_lock_class = await _setup_parameter_entry(
        hass,
        mock_push_lock(accepted=PARAMETERS_ACCEPTED),
        {CONF_AUTO_LOCK: OPTION_ON},
        {
            DATA_AUTO_LOCK: {
                "value": value,
                "at": dt_util.utcnow().isoformat(),
                "written": False,
            }
        },
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["description_placeholders"]["auto_lock"] == (
        f"{setting}, read from the lock at {dt_util.now():%H:%M}"
    )


async def test_options_menu_row_names_seconds_the_list_does_not_hold(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Test a kept duration outside the list is shown in seconds on the row."""
    freezer.move_to("2026-09-11 10:32:00+00:00")
    entry, push_lock_class = await _setup_parameter_entry(
        hass,
        mock_push_lock(accepted=PARAMETERS_ACCEPTED),
        {CONF_AUTO_LOCK: OPTION_ON},
        {
            DATA_AUTO_LOCK: {
                "value": TIMED_45,
                "at": dt_util.utcnow().isoformat(),
                "written": False,
            }
        },
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["description_placeholders"]["auto_lock"] == (
        f"On a timer, 45 s, read from the lock at {dt_util.now():%H:%M}"
    )


async def test_options_menu_row_shows_a_written_value(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Test a record from a write says so on the row."""
    freezer.move_to("2026-09-11 10:34:00+00:00")
    entry, push_lock_class = await _setup_parameter_entry(
        hass,
        mock_push_lock(accepted=BOTH_PAGES_ACCEPTED),
        {CONF_UNLATCH: OPTION_ON},
        {
            DATA_LATCH_PULL_TIME: {
                "value": 5,
                "at": dt_util.utcnow().isoformat(),
                "written": True,
            }
        },
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["description_placeholders"]["unlatch_hold_time"] == (
        f"5 s, written to the lock at {dt_util.now():%H:%M}"
    )


async def test_auto_lock_page_keeps_the_progress_screen_while_the_read_runs(
    hass: HomeAssistant,
) -> None:
    """Test the page reached again during a read shows the same progress screen."""
    never = asyncio.Event()

    async def _never_answers(parameter: int) -> int:
        """Wait for an answer that the test never gives."""
        await never.wait()
        return 0

    push_lock = mock_push_lock(accepted=PARAMETERS_ACCEPTED)
    push_lock.get_parameter = AsyncMock(side_effect=_never_answers)
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_AUTO_LOCK: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": STEP_AUTO_LOCK}
        )
        assert result["type"] is FlowResultType.SHOW_PROGRESS
        result = await hass.config_entries.options.async_configure(result["flow_id"])
        assert result["type"] is FlowResultType.SHOW_PROGRESS
        assert result["progress_action"] == PROGRESS_READING_AUTO_LOCK
        hass.config_entries.options.async_abort(result["flow_id"])
        await hass.async_block_till_done()

    push_lock.get_parameter.assert_called_once_with(0x28)


async def test_a_page_opened_after_another_carries_no_earlier_read(
    hass: HomeAssistant,
) -> None:
    """Test a second page in one dialog starts from its own read, not the first page's."""
    push_lock = mock_push_lock(accepted=BOTH_PAGES_ACCEPTED)
    push_lock.get_parameter.return_value = TIMED_1800
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_AUTO_LOCK: OPTION_ON, CONF_UNLATCH: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass, result["flow_id"], STEP_AUTO_LOCK, PROGRESS_READING_AUTO_LOCK
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_AUTO_LOCK_MODE: "timed", CONF_AUTO_LOCK_DURATION: "1800"},
        )
        assert result["type"] is FlowResultType.MENU
        push_lock.get_parameter.side_effect = TimeoutError
        result = await _open_parameter_page(
            hass,
            result["flow_id"],
            STEP_UNLATCH_HOLD_TIME,
            PROGRESS_READING_UNLATCH_HOLD_TIME,
        )

    assert result["errors"] == {"base": "no_answer"}
    assert [key.default for key in result["data_schema"].schema] == [vol.UNDEFINED]


async def test_options_menu_row_dates_a_value_read_on_another_day(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Test a record from another day carries its date as well as its time."""
    freezer.move_to("2026-09-11 10:32:00+00:00")
    entry, push_lock_class = await _setup_parameter_entry(
        hass,
        mock_push_lock(accepted=PARAMETERS_ACCEPTED),
        {CONF_AUTO_LOCK: OPTION_ON},
        {
            DATA_AUTO_LOCK: {
                "value": TIMED_1800,
                "at": "2026-09-04T10:32:00+00:00",
                "written": False,
            }
        },
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)

    # The test runs in US/Pacific, seven hours behind the record's UTC.
    assert result["description_placeholders"]["auto_lock"] == (
        "On a timer, 30 min, read from the lock at 2026-09-04 03:32"
    )


async def test_closing_the_dialog_during_the_read_cancels_it(
    hass: HomeAssistant,
) -> None:
    """Test closing the dialog cancels the read and writes nothing."""
    canceled = asyncio.Event()
    never = asyncio.Event()

    async def _never_answers(parameter: int) -> int:
        """Wait for the cancellation the closed dialog brings."""
        try:
            await never.wait()
        except asyncio.CancelledError:
            canceled.set()
            raise
        return 0

    push_lock = mock_push_lock(accepted=PARAMETERS_ACCEPTED)
    push_lock.get_parameter = AsyncMock(side_effect=_never_answers)
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_AUTO_LOCK: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": STEP_AUTO_LOCK}
        )
        assert result["type"] is FlowResultType.SHOW_PROGRESS
        hass.config_entries.options.async_abort(result["flow_id"])
        await hass.async_block_till_done()

    assert canceled.is_set()
    push_lock.set_parameter.assert_not_called()
    assert DATA_AUTO_LOCK not in entry.data


async def test_closing_the_dialog_during_the_write_keeps_the_record(
    hass: HomeAssistant,
) -> None:
    """Test a write in flight when the dialog closes finishes and is kept."""
    writing = asyncio.Event()
    answer = asyncio.Event()

    async def _answers_when_released(parameter: int, value: int) -> int:
        """Hold the write open until the test releases it."""
        writing.set()
        await answer.wait()
        return value

    push_lock = mock_push_lock(accepted=PARAMETERS_ACCEPTED)
    push_lock.get_parameter.return_value = 0
    push_lock.set_parameter = AsyncMock(side_effect=_answers_when_released)
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_AUTO_LOCK: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass, result["flow_id"], STEP_AUTO_LOCK, PROGRESS_READING_AUTO_LOCK
        )
        submit = hass.async_create_task(
            hass.config_entries.options.async_configure(
                result["flow_id"],
                {CONF_AUTO_LOCK_MODE: "timed", CONF_AUTO_LOCK_DURATION: "1800"},
            )
        )
        await writing.wait()
        hass.config_entries.options.async_abort(result["flow_id"])
        answer.set()
        with pytest.raises(UnknownFlow):
            await submit

    assert push_lock.set_parameter.await_count == 1
    record = entry.data[DATA_AUTO_LOCK]
    assert record["value"] == TIMED_1800
    assert record["written"] is True


async def test_auto_lock_page_treats_an_unloaded_entry_as_no_answer(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Test an entry unloaded after the menu was drawn asks the lock nothing."""
    caplog.set_level(logging.DEBUG, logger="homeassistant.components.yalexs_ble")
    push_lock = mock_push_lock(accepted=PARAMETERS_ACCEPTED)
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_AUTO_LOCK: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["menu_options"] == [STEP_LOCK_OPTIONS, STEP_AUTO_LOCK]
        await hass.config_entries.async_unload(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": STEP_AUTO_LOCK}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == STEP_AUTO_LOCK_FORM
    assert result["errors"] == {"base": "no_answer"}
    push_lock.get_parameter.assert_not_called()
    assert "parameter 0x28: the entry is not loaded" in caplog.text


async def test_unlatch_hold_time_page_reads_and_writes_the_parameter(
    hass: HomeAssistant,
) -> None:
    """Test the hold time page reads its parameter and writes the seconds chosen."""
    push_lock = mock_push_lock(accepted=BOTH_PAGES_ACCEPTED)
    push_lock.get_parameter.return_value = 5
    push_lock.set_parameter = AsyncMock(side_effect=_stores_the_value)
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_UNLATCH: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass,
            result["flow_id"],
            STEP_UNLATCH_HOLD_TIME,
            PROGRESS_READING_UNLATCH_HOLD_TIME,
        )
        assert result["step_id"] == STEP_UNLATCH_HOLD_TIME_FORM
        assert {str(key): key.default() for key in result["data_schema"].schema} == {
            CONF_LATCH_PULL_TIME: "5"
        }
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_LATCH_PULL_TIME: "10"}
        )
        await hass.async_block_till_done()

    push_lock.get_parameter.assert_awaited_once_with(0xB2)
    push_lock.set_parameter.assert_awaited_once_with(0xB2, 10)
    assert result["type"] is FlowResultType.MENU
    assert entry.data[DATA_LATCH_PULL_TIME]["value"] == 10


async def test_unlatch_hold_time_page_offers_as_read_for_a_value_outside_the_list(
    hass: HomeAssistant,
) -> None:
    """Test a hold time the list does not hold is offered as read, and named."""
    push_lock = mock_push_lock(accepted=BOTH_PAGES_ACCEPTED)
    push_lock.get_parameter.return_value = 7
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_UNLATCH: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass,
            result["flow_id"],
            STEP_UNLATCH_HOLD_TIME,
            PROGRESS_READING_UNLATCH_HOLD_TIME,
        )

    assert {str(key): key.default() for key in result["data_schema"].schema} == {
        CONF_LATCH_PULL_TIME: OPTION_AS_READ
    }
    assert result["description_placeholders"]["as_read"] == (
        "The lock holds 7 s, which is not on the list. As read from the lock keeps it."
    )


async def test_unlatch_hold_time_row_shows_the_kept_value(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Test the hold time row names the seconds and when they were read."""
    freezer.move_to("2026-09-11 10:32:00+00:00")
    entry, push_lock_class = await _setup_parameter_entry(
        hass,
        mock_push_lock(accepted=BOTH_PAGES_ACCEPTED),
        {CONF_UNLATCH: OPTION_ON},
        {
            DATA_LATCH_PULL_TIME: {
                "value": 5,
                "at": dt_util.utcnow().isoformat(),
                "written": False,
            }
        },
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["description_placeholders"]["unlatch_hold_time"] == (
        f"5 s, read from the lock at {dt_util.now():%H:%M}"
    )


async def test_unlatch_hold_time_read_that_times_out_shows_the_kept_value(
    hass: HomeAssistant,
) -> None:
    """Test a hold time the lock does not answer for falls back to the record."""
    push_lock = mock_push_lock(accepted=BOTH_PAGES_ACCEPTED)
    push_lock.get_parameter.side_effect = TimeoutError
    entry, push_lock_class = await _setup_parameter_entry(
        hass,
        push_lock,
        {CONF_UNLATCH: OPTION_ON},
        {
            DATA_LATCH_PULL_TIME: {
                "value": 20,
                "at": dt_util.utcnow().isoformat(),
                "written": False,
            }
        },
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass,
            result["flow_id"],
            STEP_UNLATCH_HOLD_TIME,
            PROGRESS_READING_UNLATCH_HOLD_TIME,
        )

    assert result["errors"] == {"base": "no_answer_last_value"}
    assert {str(key): key.default() for key in result["data_schema"].schema} == {
        CONF_LATCH_PULL_TIME: "20"
    }


async def test_unlatch_hold_time_read_that_times_out_with_no_record_shows_no_answer(
    hass: HomeAssistant,
) -> None:
    """Test a failed hold time read with nothing kept leaves the field to be chosen."""
    push_lock = mock_push_lock(accepted=BOTH_PAGES_ACCEPTED)
    push_lock.get_parameter.side_effect = TimeoutError
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_UNLATCH: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass,
            result["flow_id"],
            STEP_UNLATCH_HOLD_TIME,
            PROGRESS_READING_UNLATCH_HOLD_TIME,
        )

    assert result["errors"] == {"base": "no_answer"}
    assert [key.default for key in result["data_schema"].schema] == [vol.UNDEFINED]


async def test_unlatch_hold_time_submit_without_a_change_writes_nothing(
    hass: HomeAssistant,
) -> None:
    """Test a hold time submitted as it was read writes nothing."""
    push_lock = mock_push_lock(accepted=BOTH_PAGES_ACCEPTED)
    push_lock.get_parameter.return_value = 5
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_UNLATCH: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass,
            result["flow_id"],
            STEP_UNLATCH_HOLD_TIME,
            PROGRESS_READING_UNLATCH_HOLD_TIME,
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_LATCH_PULL_TIME: "5"}
        )

    assert result["type"] is FlowResultType.MENU
    push_lock.set_parameter.assert_not_called()


async def test_unlatch_hold_time_submit_with_as_read_writes_nothing(
    hass: HomeAssistant,
) -> None:
    """Test keeping the hold time the lock holds writes nothing."""
    push_lock = mock_push_lock(accepted=BOTH_PAGES_ACCEPTED)
    push_lock.get_parameter.return_value = 7
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_UNLATCH: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass,
            result["flow_id"],
            STEP_UNLATCH_HOLD_TIME,
            PROGRESS_READING_UNLATCH_HOLD_TIME,
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_LATCH_PULL_TIME: OPTION_AS_READ}
        )

    assert result["type"] is FlowResultType.MENU
    push_lock.set_parameter.assert_not_called()


async def test_unlatch_hold_time_write_that_times_out_shows_the_error(
    hass: HomeAssistant,
) -> None:
    """Test a hold time write the lock does not answer renders the form again."""
    push_lock = mock_push_lock(accepted=BOTH_PAGES_ACCEPTED)
    push_lock.get_parameter.return_value = 5
    push_lock.set_parameter.side_effect = TimeoutError
    entry, push_lock_class = await _setup_parameter_entry(
        hass, push_lock, {CONF_UNLATCH: OPTION_ON}
    )

    with patch_push_lock(push_lock_class):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await _open_parameter_page(
            hass,
            result["flow_id"],
            STEP_UNLATCH_HOLD_TIME,
            PROGRESS_READING_UNLATCH_HOLD_TIME,
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_LATCH_PULL_TIME: "10"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == STEP_UNLATCH_HOLD_TIME_FORM
    assert result["errors"] == {"base": "no_answer"}
    assert {str(key): key.default() for key in result["data_schema"].schema} == {
        CONF_LATCH_PULL_TIME: "10"
    }
