"""The yalexs_ble integration models."""

from dataclasses import dataclass
from typing import TypedDict

from yalexs_ble import PushLock


@dataclass(frozen=True)
class LibraryReport:
    """What the library did with the options it was given.

    Built from the report configure() returns, so the two sets are held
    without naming a library type that the releases this integration also
    runs against do not export.
    """

    accepted: frozenset[str]
    ignored: frozenset[str]


class ParameterRecord(TypedDict):
    """The last value of one lock parameter Home Assistant read or wrote, kept in the entry's data for display.

    value is the four bytes as the lock reported them; at is when the lock
    answered, UTC; written is True when the record came from a write the lock
    confirmed.
    """

    value: int
    at: str
    written: bool


@dataclass(frozen=True)
class LockOptions:
    """The lock options resolved once at setup for the platforms and the options menu.

    unlatch and activity_count are the stored choice and the library's
    acceptance of the key together, so the open action and the unread count
    exist only where the lock can be asked for them. auto_lock and
    unlatch_hold_time are the choice, the library's acceptance of the
    parameters key and, for the hold time, the unlatch resolution together, so
    a parameter page exists only where the lock can be asked for its value.
    """

    unlatch: bool
    secure_mode: bool
    secure_mode_enabled: bool
    battery_reporting: bool
    activity_count: bool
    auto_lock: bool
    unlatch_hold_time: bool


@dataclass
class YaleXSBLEData:
    """Data for the yale xs ble integration."""

    title: str
    lock: PushLock
    options: LockOptions
    configure_report: LibraryReport | None
