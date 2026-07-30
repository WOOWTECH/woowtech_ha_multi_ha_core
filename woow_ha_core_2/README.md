# Woowtech HA Core 2

Runs an isolated **Home Assistant Core** instance inside Home Assistant (instance **2**).

| Setting          | Value                     |
| ---------------- | ------------------------- |
| Host port        | `8125` → container `8123` |
| Config directory | `/data` (add-on private partition) |

## Usage

1. Install and start the add-on.
2. Open `http://<your-host>:8125` in your browser.
3. Complete the Home Assistant onboarding for this instance.

Its configuration lives in the add-on's private `/data` partition and is fully independent of
the host Home Assistant and of the other Woowtech HA Core instances. Uninstalling the add-on
wipes this instance's data (a fresh onboarding on reinstall); updating the add-on keeps it.

Based on [jgoakley/hassio-addons](https://github.com/jgoakley/hassio-addons).
