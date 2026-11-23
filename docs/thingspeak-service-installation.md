# Raspberry Pi installation

The service requires Raspberry Pi OS with Bluetooth LE support and Python 3.11+
(for `asyncio.timeout`). Keep the ThingSpeak write key outside Git.

1. Copy `thingspeak-service/` to `/home/pi/bm6/thingspeak-service/`.
2. Create a virtual environment and install dependencies:

```sh
python3 -m venv /home/pi/myenv
/home/pi/myenv/bin/pip install -r /home/pi/bm6/thingspeak-service/requirements.txt
```

3. Create `/etc/default/bm6-thingspeak` containing
   `THINGSPEAK_API_KEY=YOUR_WRITE_KEY`, then run
   `sudo chown root:root /etc/default/bm6-thingspeak && sudo chmod 600 /etc/default/bm6-thingspeak`.
4. Copy the unit to `/etc/systemd/system/bm6_thingspeak.service`, then run
   `sudo systemctl daemon-reload && sudo systemctl enable --now bm6_thingspeak`.
5. Check logs with `sudo journalctl -u bm6_thingspeak -f`.

The migration PR does not change the running Raspberry Pi service. Apply this
installation only when intentionally migrating the Pi to the monorepo layout.
