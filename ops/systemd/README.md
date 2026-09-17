# Optional systemd user timer

These `.example` units are templates only. They are not installed by the
repository scheduler or by the background runner. Use them only after the
operator has checked every Group URL, source terms, retention, and the
`--visibility public` decision.

Before enabling the timer:

1. Install Playwright and Chromium in the project `.venv`. On Debian/Ubuntu,
   install `python3.14-venv` first when `ensurepip` is unavailable:

   ```bash
   sudo apt update
   sudo apt install python3.14-venv
   python3 -m venv --clear .venv
   .venv/bin/python -m pip install playwright
   .venv/bin/python -m playwright install-deps chromium
   .venv/bin/playwright install chromium
   ```

   Install the full `requirements.txt` only when other scrapers need it.
2. Run the runner once with `--login-only --headed` using the dedicated
   profile path from the service unit.
3. Create `%h/.config/solo-empire/facebook-groups.txt` with one authorised
   Group URL per line.
4. Create the profile, capture, and lock parent directories:

   ```bash
   mkdir -p ~/.local/share/solo-empire/facebook-playwright \
     ~/.local/share/solo-empire/facebook-captures \
     ~/.local/state/solo-empire ~/.config/solo-empire
   ```

Copy the templates into the per-user unit directory, remove the `.example`
suffix, and edit the checkout paths if needed:

```bash
mkdir -p ~/.config/systemd/user
cp ops/systemd/facebook-group-background.service.example \
  ~/.config/systemd/user/facebook-group-background.service
cp ops/systemd/facebook-group-background.timer.example \
  ~/.config/systemd/user/facebook-group-background.timer
systemctl --user daemon-reload
systemctl --user enable --now facebook-group-background.timer
```

Inspect the first run before relying on the timer:

```bash
systemctl --user start facebook-group-background.service
systemctl --user status facebook-group-background.service
journalctl --user -u facebook-group-background.service --since today
```

The timer writes the latest raw CSV to the configured output path, replacing
that snapshot on the next run. Import or archive each snapshot separately if
you need history; the importer creates its own history file. The timer never
approves a lead or sends outreach. Disable it with
`systemctl --user disable --now facebook-group-background.timer` if the source
terms, profile, or visibility decision changes.
