# -*- coding: utf-8 -*-
import asyncio
from Crypto.Cipher import AES
from bleak import BleakClient, BleakScanner
import aiohttp
import logging
import os
import socket

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
THINGSPEAK_API_KEY = os.environ.get("THINGSPEAK_API_KEY")
THINGSPEAK_URL = "https://api.thingspeak.com/update"

# Stable device order is the ThingSpeak data contract.
BM6_DEVICES = (
    ("Simson", "50:54:7B:24:36:A2"),
    ("WSK", "50:54:7B:24:3A:1C"),
    ("Kosiarka", "50:54:7B:24:A8:C8"),
    ("MZ", "3C:AB:72:EA:BD:A2"),
)
BM6_ADDRESSES = [address for _, address in BM6_DEVICES]
KEY = bytearray([108, 101, 97, 103, 101, 110, 100, 255, 254, 48, 49, 48, 48, 48, 48, 57])
INTERVAL_SECONDS, BLE_TIMEOUT, HTTP_TIMEOUT, SCAN_TIMEOUT = 900, 45, 20, 10
_running_task = None

def notify_systemd(message):
    address = os.environ.get("NOTIFY_SOCKET")
    if not address:
        return
    if address.startswith("@"):
        address = "\0" + address[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.connect(address)
            sock.sendall(message.encode())
    except OSError as exc:
        logging.warning("systemd notification failed: %s", exc)

def decrypt(crypted):
    return AES.new(KEY, AES.MODE_CBC, 16 * b'\\0').decrypt(crypted).hex()

def encrypt(plaintext):
    return AES.new(KEY, AES.MODE_CBC, 16 * b'\\0').encrypt(plaintext)

async def is_device_in_range(address):
    try:
        device = await BleakScanner.find_device_by_address(address, timeout=SCAN_TIMEOUT)
        notify_systemd("WATCHDOG=1")
        return device is not None
    except Exception as exc:
        notify_systemd("WATCHDOG=1")
        logging.warning("Scan error %s: %s", address, exc)
        return False

async def get_bm6_data(address):
    bm6_data = {"voltage": None, "soc": None}
    if not await is_device_in_range(address):
        logging.info("Device %s out of range, skipping", address)
        return None
    def notification_handler(sender, data):
        message = decrypt(data)
        if message[0:6] == "d15507":
            try:
                bm6_data["voltage"] = int(message[15:18], 16) / 100
                bm6_data["soc"] = int(message[12:14], 16)
            except (TypeError, ValueError):
                logging.warning("Invalid BM6 notification from %s", address)
    try:
        async with asyncio.timeout(BLE_TIMEOUT):
            async with BleakClient(address, timeout=30) as client:
                await client.write_gatt_char("FFF3", encrypt(bytearray.fromhex("d1550700000000000000000000000000")), response=True)
                await client.start_notify("FFF4", notification_handler)
                for _ in range(50):
                    if bm6_data["voltage"] is not None and bm6_data["soc"] is not None:
                        break
                    await asyncio.sleep(0.1)
                await client.stop_notify("FFF4")
        notify_systemd("WATCHDOG=1")
        return bm6_data
    except asyncio.TimeoutError:
        notify_systemd("WATCHDOG=1")
        logging.warning("BLE timeout for %s", address)
    except Exception as exc:
        notify_systemd("WATCHDOG=1")
        logging.error("BLE error %s: %s", address, exc)
    return None

async def send_to_thingspeak(payload):
    if not THINGSPEAK_API_KEY:
        logging.error("ThingSpeak upload skipped: THINGSPEAK_API_KEY is not configured")
        return False
    try:
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(THINGSPEAK_URL, params={"api_key": THINGSPEAK_API_KEY, **payload}) as response:
                body = (await response.text()).strip()
                if response.status == 200 and body.isdigit() and int(body) > 0:
                    logging.info("ThingSpeak accepted entry %s", body)
                    return True
                logging.warning("ThingSpeak rejected update (HTTP %s, response %r)", response.status, body[:120])
    except Exception as exc:
        logging.error("ThingSpeak send error: %s", exc)
    return False

async def collect_and_send_data():
    global _running_task
    if _running_task is not None and not _running_task.done():
        logging.warning("Previous cycle still running – skipping this iteration")
        return
    _running_task = asyncio.current_task()
    all_data = []
    logging.info("Starting BM6 module readout...")
    for name, address in BM6_DEVICES:
        data = await get_bm6_data(address)
        logging.info("%s (%s): %s", name, address, data if data else "no data")
        all_data.append(data)
        await asyncio.sleep(1)
    if any(item is not None for item in all_data):
        payload = {}
        for index, data in enumerate(all_data, start=1):
            if data is not None:
                if data["voltage"] is not None:
                    payload[f"field{index}"] = data["voltage"]
                if data["soc"] is not None:
                    payload[f"field{index + 4}"] = data["soc"]
        await send_to_thingspeak(payload)

async def sleep_with_watchdog(duration):
    remaining = duration
    while remaining > 0:
        interval = min(20, remaining)
        await asyncio.sleep(interval)
        remaining -= interval
        notify_systemd("WATCHDOG=1")

async def main():
    logging.info("BM6 -> ThingSpeak service started (interval: %s sec)", INTERVAL_SECONDS)
    notify_systemd("READY=1\\nSTATUS=BM6 service ready")
    while True:
        try:
            cycle_timeout = (SCAN_TIMEOUT + BLE_TIMEOUT + 1) * len(BM6_ADDRESSES) + HTTP_TIMEOUT + 10
            notify_systemd("WATCHDOG=1\\nSTATUS=Starting BM6 readout")
            await asyncio.wait_for(collect_and_send_data(), timeout=cycle_timeout)
        except asyncio.TimeoutError:
            logging.error("Full cycle exceeded time limit, waiting for next run")
        except Exception as exc:
            logging.error("Unexpected error in main loop: %s", exc)
        notify_systemd("WATCHDOG=1\\nSTATUS=Readout finished; waiting for next interval")
        await sleep_with_watchdog(INTERVAL_SECONDS)

if __name__ == "__main__":
    asyncio.run(main())
