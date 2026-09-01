# Tablet F09 approval-gated integration

This runbook is for the Gravity Admin production tablet. Joining the gym Wi-Fi must never configure or contact the fingerprint machine by itself.

## Safety contract

The existing gym software and ZKTeco F09 remain authoritative. Gravity integration is additive and read-only from the device side.

Gravity must not automatically change or clear:

- F09 IP, subnet, gateway, DNS, TCP port, or ADMS settings;
- device date/time or timezone;
- enrolled users, fingerprints, face templates, cards, passwords, or privileges;
- attendance logs already stored on the F09;
- current gym software configuration or services.

There is no F09 Wi-Fi watcher, boot hook, or periodic biometric polling service in this design. The device is contacted only during an explicitly approved one-shot configuration/sync.

## Prepared commands

`deploy/termux/f09-onsite.sh prepare` installs only the pinned/hash-checked local `pyzk` driver. It does not contact the F09.

`deploy/termux/f09-onsite.sh status` checks tablet/Gravity readiness only. It does not contact the F09.

`deploy/termux/f09-onsite.sh configure` is blocked unless a short-lived approval file exists. It creates a verified Gravity backup before any integration change.

## When the owner explicitly approves

Only after the owner says to configure the F09:

1. Confirm the tablet is already on the gym LAN.
2. Run `f09-onsite.sh status`; this still does not contact the F09.
3. Create the one-time approval with `approve-f09-once.py`. The approval requires the exact phrase `APPROVE F09 READ-ONLY INTEGRATION`, is tied to the current Git commit and `192.168.1.201:4370`, expires after 15 minutes by default, and is stored mode 600.
4. Run `f09-onsite.sh configure`. The approval is validated and deleted before device contact so it cannot be reused.
5. Enter the real numeric Comm Key securely. Never guess or reset it.
6. Gravity creates/updates its own device record and performs one read-only sync of users and attendance events.

The approved run does not enable any background F09 polling. Future syncs remain human-triggered until a separate compatibility decision is made with the existing gym software.

## Device-side operations used by Gravity

The `ZKTecoF09Adapter` uses only connection/read operations: serial number, platform, users, and attendance. It disconnects after each read. It does not call pyzk setters, delete/clear methods, device disable/enable commands, restart/power commands, or enrollment commands.

A read-only TCP session can still briefly occupy a device connection on some F09 firmware. For that reason Gravity does not poll continuously and the initial approved sync should be run when the gym operator can observe that the existing software continues normally.
