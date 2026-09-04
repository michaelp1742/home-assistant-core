"""Constants for the Yale Access Bluetooth integration."""

DOMAIN = "yalexs_ble"

CONF_LOCAL_NAME = "local_name"
CONF_KEY = "key"
CONF_SLOT = "slot"
CONF_ALWAYS_CONNECTED = "always_connected"
CONF_UNLATCH = "unlatch"
CONF_SECURE_MODE = "secure_mode"
CONF_BATTERY_REPORTING = "battery_reporting"
CONF_DOOR_SENSE = "door_sense"
CONF_ACTIVITY_COUNT = "activity_count"
CONF_AUTO_LOCK = "auto_lock"

STEP_LOCK_OPTIONS = "lock_options"

# The states of a feature option. "Not set" is the absence of a choice: it is
# rendered for a key the user never set and is never stored. "Library default"
# is a choice the user made to leave the feature to the library and is stored
# like any other. Both send nothing to the library, so its own answer, model
# gates included, holds for either; the record of which one the user made is
# what differs.
OPTION_UNCONFIGURED = "unconfigured"
OPTION_DEFAULT = "default"
OPTION_ON = "on"
OPTION_OFF = "off"
OPTION_STATES = [OPTION_UNCONFIGURED, OPTION_DEFAULT, OPTION_ON, OPTION_OFF]
OPTION_VALUES = {OPTION_ON: True, OPTION_OFF: False}

# The wire names of the option keys, kept apart from the CONF_ names even where
# the strings coincide: these are the library's vocabulary, those are the
# config entry's. A key a library version does not know comes back in the
# report's ignored set.
OPTION_ALWAYS_CONNECTED = "always_connected"
# The library key the integration passes when a parameter page can exist.
OPTION_PARAMETERS = "parameters"
LIBRARY_KEYS = {
    CONF_UNLATCH: "unlatch",
    CONF_SECURE_MODE: "secure_mode",
    CONF_BATTERY_REPORTING: "battery_reporting",
    CONF_DOOR_SENSE: "door_sense",
    CONF_ACTIVITY_COUNT: "activity_count",
}

# The feature options in the order the form shows them, and for each the
# library key that must be advertised for it to appear, None for a feature
# the integration carries alone. Auto-Lock is not a library key: it needs
# the parameter ioctls, which the parameters key advertises.
FEATURE_GATES: dict[str, str | None] = {
    CONF_DOOR_SENSE: LIBRARY_KEYS[CONF_DOOR_SENSE],
    CONF_AUTO_LOCK: OPTION_PARAMETERS,
    CONF_SECURE_MODE: None,
    CONF_UNLATCH: LIBRARY_KEYS[CONF_UNLATCH],
    CONF_BATTERY_REPORTING: LIBRARY_KEYS[CONF_BATTERY_REPORTING],
    CONF_ACTIVITY_COUNT: LIBRARY_KEYS[CONF_ACTIVITY_COUNT],
}
FEATURE_OPTIONS = tuple(FEATURE_GATES)

DEVICE_TIMEOUT = 55
