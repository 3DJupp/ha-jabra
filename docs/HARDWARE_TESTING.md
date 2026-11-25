# Hardware testing checklist

Nothing in this repository has run against a real Jabra device yet. Work through this list on an
**Evolve2 85** (or any other model) and note the results at the bottom. Only change settings you can
change back.

## 1. jabridge alone (Linux host with the headset plugged in)

```bash
./jabridge setup              # installs udev rules
./jabridge service start
./jabridge ipc ping
./jabridge ipc capabilities
./jabridge ipc devices        # shape of devices.list
./jabridge ipc settings headset
./jabridge ipc watch          # unplug and plug the headset, press buttons
```

Record: USB id, whether `battery` is present, which settings are `editable` with `support.state`
`available`, which events arrive. **Save sanitized copies** (remove serial numbers) of the
`devices` and `settings` output: they become test fixtures in `tests/fixtures/`.

Does `jabridge ipc` offer `device.busylight`? Try `{"jsonrpc":"2.0","id":1,"method":"device.busylight"}`
over the socket and with `"params":{"mode":"on"}`.

## 2. jabra2mqtt in Docker

```bash
docker compose up        # from docker-compose.example.yml, with your broker settings
mosquitto_sub -h <broker> -t '#' -v
```

Check that discovery topics, `state` and `availability` appear, and that unplugging the headset
turns `availability` to `offline`.

## 3. Home Assistant OS add-on

* Does the add-on start with `full_access`? Does it see `/dev/hidraw*`?
* Can the device mapping be narrowed (for example a `devices:` list)? What fails if a node is missing?
* Do the entities appear under one device, with the right classes and units?

## 4. Writes (reversible only)

* Busylight on/off from the Home Assistant UI.
* Noise control: change and change back. Note whether the headset restarts.
* Confirm a refused write (for example an invalid value) does not retry.

## 5. Link dongle vs USB cable

Repeat 1 and 4 through a Jabra Link 380. Note which controls disappear.

## Results

| Date | Model, firmware | Connection | Host | What worked | What did not |
| --- | --- | --- | --- | --- | --- |
| | | | | | |
