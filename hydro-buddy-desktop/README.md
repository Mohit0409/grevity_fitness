# Hydro Buddy Desktop

Floating Ubuntu desktop pet for hydration and stretch reminders.

## Run

```bash
npm install
npm run start
```

## Electron sandbox note

If Electron fails with `chrome-sandbox is not configured correctly`, run:

```bash
sudo chown root:root node_modules/electron/dist/chrome-sandbox
sudo chmod 4755 node_modules/electron/dist/chrome-sandbox
```

Hydro Buddy writes the Ubuntu autostart entry to:

```text
~/.config/autostart/hydro-buddy.desktop
```
