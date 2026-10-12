# Experimental master/slave test branch

This feature is available on `codex/issue-6-tcp-gateway` (version `2.1.0b2`).
This is a pre-release feature, not part of stable v2.0.2. It has not been verified
as part of this integration on physical hardware. It is based on the working
sequence and six real response frames supplied
by Pocket74 in [issue #6](https://github.com/Ralleberg/solutronic/issues/6).

## Existing installations

Ordinary IP entry, discovery, HTTP parsing, sensor identities, options and energy
storage remain unchanged. There is no new connection selector in normal setup,
and the integration never automatically tries gateway commands if HTTP fails.

The gateway is a separate integration entry with separate inverter identities
and energy storage. Adding it does not migrate or replace an existing HTTP entry.
If both expose the same physical master, do not add both sets of energy sensors
to the Energy Dashboard: that would count its production twice.

## Testing the gateway

1. Back up Home Assistant. Enable pre-release updates for Solutronic in HACS
   (see [the HACS beta switch guide](https://www.hacs.dev/docs/use/entities/switch/)),
   select **v2.1.0b2**, install it and restart Home Assistant. Alternatively, copy
   only `custom_components/solutronic` from this branch.
2. Add Solutronic. Choose manual IP entry if discovery finds devices.
3. Enter the master's address **with port 33330**, for example
   `192.168.1.99:33330`. That explicit port opens the separate test setup. An IP
   without that port continues through the existing HTTP setup.
4. Enter the master bus address and **leave the device list empty**. The integration
   reads the configured slave addresses from the master; no device count is entered.
   For an older firmware that rejects discovery, a manual list remains available
   as `address,serial[,model[,firmware]]` lines, including the master.
5. Read the experimental-mode description and confirm before connecting.

Pocket74's manual fallback address/serial list is:

```text
22031,22031
20835,20835
22025,22025
22030,22030
30536,30536
30535,30537
```

Do not assume these addresses apply to another installation. Model and firmware
are optional user-supplied metadata; omitted fields are not inferred.

For an existing beta-one gateway entry, enable **Find inverters automatically
through the master** in its options. This retains the entry, existing sensor IDs,
known serial aliases and saved energy state. Automatic entries refresh the list
on startup/reload and every ten minutes; new inverters are added dynamically.
Removed inverters become unavailable; their entities and energy history are kept.

Discovery reads the master’s parameters 165–196, documented in Solutronic's
[protocol specification B12](https://www.photovoltaikforum.com/core/file-download/43597/)
(section 2.7). The list supports 32 slaves; zero ends the configured list. It does
not scan arbitrary bus addresses or write slave configuration. Newly discovered
devices are identified by bus address; unconfirmed serials/models are not guessed.
Existing manually confirmed metadata (including 30535 / 30537) is retained.

The integration uses one serialized TCP connection to the master. It presents
power, grid/DC voltage, frequency, temperature, daily energy, reported total
energy and the existing style of derived energy counter for each configured
inverter. It does not decode unknown fields or use the inverter clocks.

The default polling interval is 60 seconds; options allow 60, 120 or 300 seconds.
Failed devices become unavailable independently. Energy state is saved per
inverter, with batched writes and a flush during unload/normal shutdown. As with
existing energy tracking, abrupt power loss can lose unsaved changes and an
outage across a daily reset can leave production uncounted.

## Limits and hardware feedback

The preparation commands reproduce the supplied SolPlus+ sequence. B12 documents
file selection/read operations; its applicability and behavior on this firmware
still require hardware verification. No request is sent before explicit test-mode
confirmation. The measurement sequence must not be described as entirely read-only:
it includes writes selecting the data file, whereas slave-list discovery uses reads. No other commands or arbitrary payloads are
supported. Disable the PC polling software during testing to avoid competing
clients changing session state or timing.

Check all six inverter identities and live readings against the known setup.
Check that one offline slave does not suppress other inverters, and that energy
counters continue after a reload/restart. The physical integration behavior,
connection limits and interaction with the manufacturer's software still need
confirmation. Keep issue #6 open while gathering this feedback.

To return to stable v2.0.2, remove the experimental gateway entry, install the
stable integration folder and restart Home Assistant. Keep existing HTTP entries.
