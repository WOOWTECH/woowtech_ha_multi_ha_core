# Woowtech HA Core 4

Runs an isolated **Home Assistant Core** instance inside Home Assistant (instance **4**).

| Setting          | Value                     |
| ---------------- | ------------------------- |
| Host port        | `8127` → container `8123` |
| Config directory | `/config/woow_ha_core_4` |

## Usage

1. Install and start the add-on.
2. Open `http://<your-host>:8127` in your browser.
3. Complete the Home Assistant onboarding for this instance.

Its configuration lives in `/config/woow_ha_core_4` and is fully independent of the host Home
Assistant and of the other Woowtech HA Core instances.

Based on [jgoakley/hassio-addons](https://github.com/jgoakley/hassio-addons).
