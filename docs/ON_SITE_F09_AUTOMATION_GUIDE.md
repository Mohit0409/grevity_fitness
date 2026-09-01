# On-site F09 configuration and Admin Portal startup

Use this guide for the Windows host workflow. The production Android/Termux tablet must use `docs/TABLET_F09_APPROVAL_RUNBOOK.md` instead; joining gym Wi-Fi alone never authorizes or triggers F09 configuration.

Use this guide when the host PC has reached the gym and is connected to the same local network as the ZKTeco F09. The script starts the Gravity Admin Portal, optionally brings up the approved ngrok public URL, saves the F09 direct-TCP configuration, tests it, and syncs device users/events.

It does **not** touch the separate customer website at `C:\movieXsuggestion\MyProject\gravity_fitness_website`.

## What to collect before going to the gym

Keep these details with the owner or device administrator. Do not send any password or Comm Key in chat, screenshots, Git, or a command line.

| Needed item | Known value / where to get it |
| --- | --- |
| F09 model | ZKTeco F09 |
| F09 IP address | `192.168.1.201` |
| F09 TCP port | `4370` |
| F09 device ID | `1` |
| F09 subnet / gateway / DNS | `255.255.255.0` / `192.168.1.1` / `8.8.8.8` |
| F09 Comm Key | Read it from the F09 device administrator menu; it must be the real numeric value. Never guess. |
| F09 admin access | Required only to view/fix the device’s own network or Comm Key settings. |
| Gravity portal login | An active owner or administrator username, password, and the current TOTP code or an unused recovery code. |
| Gravity protected config | Normally `C:\ProgramData\GravityFitness\gravity.env`. |
| Public tunnel details | The approved ngrok config and executable paths, normally `C:\ProgramData\GravityFitness\ngrok.yml` and `C:\Program Files\ngrok\ngrok.exe`. |
| Internet access | Needed only if the `pyzk` direct-TCP driver is not already installed or if an ngrok public URL is required. |

Record the device serial number from the F09’s system information screen as an extra confirmation, but do not record any fingerprint template or face data. Gravity never stores those templates.

## Prepare the F09 itself first

The automation script deliberately does not overwrite hardware settings, ADMS settings, device users, templates, or attendance logs. A wrong device command can affect the whole gym entrance, so make these checks from the F09’s own menu with its administrator present:

1. Connect the F09 by Ethernet or the gym Wi-Fi/LAN so it is on the `192.168.1.x` network.
2. Confirm its IP, subnet, gateway, DNS, and TCP communication port match the values above. Confirm that `192.168.1.201` is not already used by another device.
3. Confirm the device time and date are correct for India.
4. Obtain the numeric Comm Key. Do not reset it just to make the script work.
5. Leave ADMS unchanged. Gravity uses direct TCP at `192.168.1.201:4370`; it does not need the old `192.168.1.8:8088` ADMS address. Change ADMS only with a confirmed vendor-approved design.
6. Confirm that the people who should use attendance already have a fingerprint enrolled on the F09. Enrollment remains on the F09.

From the host PC, this must pass before running the script:

```powershell
Test-NetConnection 192.168.1.201 -Port 4370
```

If `TcpTestSucceeded` is false, stop there and correct the network/device settings. The script will not try to guess or repair them.

## Run the automation

Open PowerShell on the **Gravity host PC**. Use the deployed Admin Portal checkout, not the customer-website project. Confirm that checkout contains `scripts\configure-zkteco-f09.ps1`, `server\migrations\012_biometric_attendance.sql`, and the biometric Admin Portal code before going on site. Do not copy only this script into an older release: it depends on the matching migration and API. The first run can install the pinned, hash-checked F09 driver; this requires internet access and permission to change the Python environment.

```powershell
Set-Location 'C:\ProgramData\GravityFitness\releases\<release-sha>'

PowerShell -NoProfile -ExecutionPolicy Bypass -File .\scripts\configure-zkteco-f09.ps1 `
  -ConfigPath 'C:\ProgramData\GravityFitness\gravity.env' `
  -InstallZkDriver `
  -StartNgrok `
  -NgrokConfigPath 'C:\ProgramData\GravityFitness\ngrok.yml' `
  -NgrokExecutablePath 'C:\Program Files\ngrok\ngrok.exe'
```

The script asks interactively for:

1. Owner/administrator username and password.
2. A TOTP code or unused recovery code when two-factor authentication is enabled.
3. The numeric F09 Comm Key. The entry is masked, never written to command history, and never printed. Gravity encrypts it in its database.

The script then performs these actions in order:

1. Checks F09 TCP connectivity on the gym network.
2. Installs/verifies the pinned `pyzk` direct-TCP driver when requested.
3. Starts the loopback-only Admin Portal and verifies `/api/health`.
4. Starts/verifies the approved ngrok HTTPS tunnel when `-StartNgrok` is supplied. The tunnel always targets the Admin Portal’s loopback port, never the customer website.
5. Authenticates as an admin with CSRF protection.
6. Creates or updates exactly one ZKTeco device record for F09 Device ID `1`.
7. Runs a TCP test and then a real sync. A sync proves the driver/Comm Key path works; a TCP test alone only proves that the port can be reached.
8. Writes a secret-free completion line to Gravity’s operations log and prints the admin URL plus unmatched-ID count.

To inspect without changing anything, use:

```powershell
.\scripts\configure-zkteco-f09.ps1 `
  -ConfigPath 'C:\ProgramData\GravityFitness\gravity.env' `
  -PreflightOnly
```

For a later recheck, omit `-InstallZkDriver`. If you do not want to pull events during a network diagnostic, add `-SkipSync`; do not call that a complete F09 validation.

## After the script reports success

Open the printed `https://…/admin` URL. This is the Admin Portal, not the customer site.

1. Go to **More tools → Biometric Devices** and confirm the F09 shows `online`.
2. Sync again if device users changed.
3. Map every F09 user ID to the correct Gravity member or staff record. This is intentionally human-controlled: the script cannot safely infer whether device user ID `101` belongs to a particular person.
4. Ask one mapped member and one mapped staff person to scan. Confirm both scans appear in **Attendance** and the respective person profile.
5. Confirm staff attendance has not created a membership, fee, customer login, or coaching membership.
6. Confirm the `GravityFitness-Watchdog`, `GravityFitness-DailyBackup`, and `GravityFitness-Notifications` tasks are present. These are what make the admin service recover after reboot. If they are missing, use the controlled task-install procedure in `docs/OPERATIONS_RUNBOOK.md`; do not create ad-hoc tasks with secrets on the command line.

## If it stops

| Script message | Meaning and safe response |
| --- | --- |
| F09 TCP port is unreachable | Check gym Wi-Fi/LAN, F09 IP settings, cable/power, and port `4370`. Do not change Gravity data. |
| ZKTeco driver is missing | Run again with `-InstallZkDriver` while internet is available, or install the pinned driver from the managed release before visiting the gym. |
| Production configuration requires HTTPS | Start the approved ngrok tunnel with `-StartNgrok`; production cookies cannot be safely used over loopback HTTP. |
| Admin authentication did not complete | Check owner/admin credentials and current TOTP/recovery code. Do not retry repeatedly, because login rate limiting is intentional. |
| TCP test passed but sync failed | Recheck the real numeric Comm Key and F09 compatibility. Do not reset the machine or clear logs/templates. |
| Multiple devices use Device ID 1 | Resolve the duplicate device record in the Admin Portal before retrying. |

The direct-TCP driver is the pinned `pyzk` 0.9 release used by the existing `ZKTecoF09Adapter`; its package is installed only when requested and is hash-checked by the script. The F09 connection remains an on-site acceptance step because physical network, firmware, Comm Key, and enrolled user data cannot be verified from another location.
