# BM6 data contract

The Raspberry Pi BLE collector and dashboard share this fixed module order:

| Position | Device | BLE address | Voltage | SoC |
|---:|---|---|---|---|
| 1 | Simson | `50:54:7B:24:36:A2` | Field 1 | Field 5 |
| 2 | WSK | `50:54:7B:24:3A:1C` | Field 2 | Field 6 |
| 3 | Kosiarka | `50:54:7B:24:A8:C8` | Field 3 | Field 7 |
| 4 | MZ | `3C:AB:72:EA:BD:A2` | Field 4 | Field 8 |

The collector preserves each device's position even when a module is unavailable.
The dashboard must map voltage fields as `[1, 2, 3, 4]` and SoC fields as
`[5, 6, 7, 8]`. ThingSpeak field labels are not authoritative; payload order
is defined by `BM6_DEVICES` in the collector.

Do not reorder the collector list without updating the dashboard mapping and
this document in the same change.
