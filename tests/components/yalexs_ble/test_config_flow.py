"""Test the Yale Access Bluetooth config flow."""

import asyncio
import logging
from unittest.mock import patch

from bleak import BleakError
import pytest
from yalexs_ble import AuthError

from homeassistant import config_entries
from homeassistant.components.yalexs_ble.const import (
    CONF_ACTIVITY_COUNT,
    CONF_ALWAYS_CONNECTED,
    CONF_AUTO_LOCK,
    CONF_BATTERY_REPORTING,
    CONF_DOOR_SENSE,
    CONF_KEY,
    CONF_LOCAL_NAME,
    CONF_SECURE_MODE,
    CONF_SLOT,
    CONF_UNLATCH,
    DOMAIN,
    OPTION_DEFAULT,
    OPTION_OFF,
    OPTION_ON,
    OPTION_STATES,
    OPTION_UNCONFIGURED,
    STEP_LOCK_OPTIONS,
)
from homeassistant.config_entries import ConfigEntryState, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import translation

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
