# Switch PC Controller

Turn a stock Nintendo Switch Lite into a local Wi-Fi controller for a Windows 11 PC. The Switch opens a touch dashboard in its built-in network registration browser. The Windows app handles input and lets you manage macro profiles.

- **Trackpad** with swipe movement, tap-to-point, left and right click, and directional nudges.
- **Live keyboard** with Shift, Space, Tab, Enter, and hold-to-repeat Backspace.
- **Window switcher** with Previous, Next, Select, and Cancel.
- **Macro pad** with nine buttons per profile, a Windows editor, and included Productivity and Media profiles.

## Quick start

You need a Switch Lite and a Windows 11 PC on the same trusted home network. Use Python 3.10 or newer with Tcl/Tk. The dashboard has no third-party Python dependencies.

1. Download and extract the repository, or clone it. Double-click **setup.cmd**. It checks for Python and can install it through Windows Package Manager. If Windows Package Manager is unavailable, install Python with Tcl/Tk from [python.org](https://www.python.org/downloads/windows/).
2. On Windows, double-click **switchControllerLaunch.cmd**. If there is no valid saved address, open **System Settings → Internet** on the Switch and enter its **IP Address** when prompted. The launcher saves the address and uses it automatically next time. If the Switch IP changes, run `.\switchControllerLaunch.cmd --client SWITCH_IP` with the new address to update it. Keep the terminal and **Switch macro pad** window open. The terminal shows the PC address labeled **Switch DNS**.
3. On the Switch, open **System Settings → Internet → Internet Settings → your registered network → Change Settings → DNS Settings**. Note the original DNS setting so you can restore it. Choose **Manual** and enter the printed PC address as both DNS servers. Leading zeros in the displayed address are expected. Save, reconnect, and continue when the Switch prompts you to register.
4. In the Windows app, click **Enable pairing**. Enter that six-digit code on the Switch dashboard. Use **Macros**, **Trackpad**, **Keyboard**, or **Switch apps** to control Windows.

When finished, click **Disable input** or close the Windows app. Restore the console's original DNS settings and reconnect for normal online use.

## Edit a macro

Choose a profile and a slot in the Windows editor. Set its label, accent color, and optional icon. Short ASCII labels render reliably in the Switch browser. To move a mapping, click **Move…**, select the destination slot, and click **Save button**.

Enter one action per line. A macro can contain up to 32 steps. Delays can be up to three seconds per step and eight seconds in total.

| Action | Example |
| --- | --- |
| Tap a key or shortcut | `tap Ctrl+Shift+S` |
| Press and release across steps | `down Ctrl`, `tap A`, and `up Ctrl` on separate lines |
| Wait in milliseconds | `wait 150` |
| Send a media key | `tap PlayPause`, `tap Mute`, or `tap VolumeUp` |
| Open an allowlisted app | `launch notepad` or `launch calculator` |

Profiles are stored under `%LOCALAPPDATA%\SwitchPCController\profiles.json`. Use **File → Export profiles** and **File → Import profiles** to transfer mappings between PCs.

## If the registration page does not open

- Confirm the console is on the same LAN and its IP address has not changed. Guest Wi-Fi, VPN DNS filtering, and client isolation can block the route.
- Check the Windows terminal for **DNS probe answered**, **HTTP probe redirected**, and **diagnostic page requested**. These messages show how far the Switch reached.
- If Windows Firewall blocks access, use the printed firewall command in an administrator PowerShell on a trusted **Private** network. The rule permits UDP 53 and TCP 80 from the console's IP only. Remove project rules with `.\firewall.ps1 -Remove`.
- For manual adapter selection, start the dashboard with `py -3 portal.py --client SWITCH_IP --bind PC_IP --dashboard`, substituting the actual addresses.
- To run browser diagnostics without enabling Windows input, use `py -3 portal.py --client SWITCH_IP`.

## Compatibility and privacy

The baseline portal, touchscreen echo, and configurable keyboard shortcuts were demonstrated on a stock Switch Lite running firmware **23.5.0**. A 100-request test over home Wi-Fi returned all replies, with a median HTTP round trip of 33 ms and a p95 of 51 ms. The HTTP measurement covers the request and echo. End-to-end input latency has yet to be measured. Applet behavior and the newer dashboard controls can vary by firmware. The physical X button closed the applet in the hardware trial.

The portal listens on the selected LAN address and filters connections by the configured Switch IP. Input starts disabled, requires pairing, and can be stopped from Windows. Pairing codes expire after five minutes and paired sessions expire after twenty minutes. The dashboard uses plain HTTP, so use it on a trusted local network and enter passwords directly on the PC. The app keeps no typing history.

## Development

```powershell
py -3 -m unittest -v
node test_client.js
node test_desktop_controls.js
```

Node.js is needed only for the browser-control tests. The optional diagnostic WebSocket echo uses the dependency in `requirements-ws.txt`.

The project is available under the [MIT License](LICENSE).
