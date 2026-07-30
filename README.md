# Woowtech Multi HA Core Add-ons

A Home Assistant add-on repository that lets you run **Home Assistant inside Home Assistant**. Each
add-on launches an independent Home Assistant Core instance with its own configuration directory, so
you can operate multiple isolated HA cores on a single host.

Based on [jgoakley/hassio-addons](https://github.com/jgoakley/hassio-addons).

## Add-ons & Port Mapping

This repository contains 5 add-ons. Each exposes its internal Home Assistant port (`8123`) on a
distinct host port in the range **8124–8128**:

| Add-on           | Instance | Host Port |
| ---------------- | -------- | --------- |
| `woow_ha_core_1` | 1        | `8124`    |
| `woow_ha_core_2` | 2        | `8125`    |
| `woow_ha_core_3` | 3        | `8126`    |
| `woow_ha_core_4` | 4        | `8127`    |
| `woow_ha_core_5` | 5        | `8128`    |

Once an add-on is running, open `http://<your-host>:<port>` (e.g. `http://homeassistant.local:8124`
for instance 1) to reach that Home Assistant instance.

## How It Works

Each add-on:

- Runs a Home Assistant Core image (`ghcr.io/woowtech/woowtech-ha` on amd64, the official
  `ghcr.io/home-assistant/home-assistant:stable` on other architectures).
- Stores its configuration in the add-on's own private `/data` partition, keeping each
  instance fully isolated from the host and from the other instances. Uninstalling the add-on
  wipes that instance's data (fresh onboarding on reinstall); updating the add-on keeps it.
- Maps the container's `8123/tcp` port to a unique host port (8124–8128).

## Installation

1. In Home Assistant, go to **Settings → Add-ons → Add-on Store**.
2. Open the **⋮** menu (top right) → **Repositories**.
3. Add this repository URL:
   `https://github.com/WOOWTECH/woowtech_ha_multi_ha_core`
4. The five **Woowtech HA Core** add-ons appear in the store. Install the ones you need.
5. Start an add-on, then open its host port in your browser to complete onboarding for that instance.

## Credits

Based on [jgoakley/hassio-addons](https://github.com/jgoakley/hassio-addons).
