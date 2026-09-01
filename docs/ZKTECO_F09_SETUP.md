# ZKTeco F09 setup for Gravity Fitness Admin

This guide is for the on-site setup day at the gym. The software is prepared, but the physical F09 connection is not configured until the machine, network, and communication key are available.

## What Gravity stores

Gravity stores attendance events, visit summaries, device user IDs, and the member/staff mapping. Gravity does not store raw fingerprint templates, face templates, or biometric images. Enrollment remains on the ZKTeco F09.

## Known device details

- Model: ZKTeco F09
- Device IP: `192.168.1.201`
- Subnet: `255.255.255.0`
- Gateway: `192.168.1.1`
- DNS: `8.8.8.8`
- Device ID: `1`
- TCP COMM port: `4370`
- Timezone: `Asia/Kolkata`
- Comm Key: collect on site from the device/admin; do not guess it.

The old ADMS screen was reported as `192.168.1.8:8088`, domain mode disabled. Do not change ADMS until the chosen final connection mode is confirmed.

## Automated on-site setup

Use [the on-site F09 automation guide](ON_SITE_F09_AUTOMATION_GUIDE.md) when the host PC is on the gym network. Its PowerShell script starts the Admin Portal, can bring up the approved public ngrok URL, stores the F09 direct-TCP settings, tests the real Comm Key, and syncs user IDs/events without exposing the key or modifying the customer website.

## Software path

In the Admin Portal:

1. Open `More tools -> Biometric Devices`.
2. Add or edit the device:
   - Name: `Gravity Entrance F09`
   - Vendor/model: `ZKTeco / F09`
   - Mode: `ZKTeco TCP`
   - Device ID: `1`
   - IP address: `192.168.1.201`
   - Port: `4370`
   - Timezone: `Asia/Kolkata`
   - Comm Key: enter the real value from the machine.
3. Click `Test`.
4. Click `Sync`.
5. Map unmatched fingerprint IDs to Gravity members or staff.
6. Ask one mapped member and one mapped staff record to scan on the F09.
7. Confirm the scans appear under `Attendance` and inside each person profile.

## On-site network checks

Run these from the same Windows machine that hosts Gravity:

```powershell
ping 192.168.1.201
Test-NetConnection 192.168.1.201 -Port 4370
```

If either fails, fix Wi-Fi/LAN/IP settings before changing Gravity.

## Attendance rules

- The Admin Portal remains the source of truth for members, staff, memberships, and fees.
- F09 user IDs are only identifiers until mapped to a Gravity person.
- Staff mappings are allowed, but staff never receive memberships, fees, coaching memberships, customer-login behavior, or renewal follow-ups from attendance.
- Duplicate scans inside the configured duplicate window are retained as raw events and folded into the same visit.
- Repeated scans inside the visit gap remain one visit; a later scan starts a new visit.
- Attendance dates are calculated in `Asia/Kolkata`.

## Public access/reboot note

The admin service should run continuously as a Windows service/scheduled task and be exposed only through the approved tunnel or private network path. Tailscale can solve reboot/private access problems when the machine rejoins the tailnet automatically, but the admin URL must point to the admin service port, not the separate customer website.

Do not point the Gravity customer website project at this admin service, and do not modify `C:\movieXsuggestion\MyProject\gravity_fitness_website`.
