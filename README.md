# 🔍 Who doesn't follow me back? — Instagram export analyzer

A **read-only, privacy-first** tool that tells you which Instagram accounts you
follow that **don't follow you back** — plus the reverse (fans you don't follow
back) and your mutuals.

It does **not** log into Instagram, does **not** use the Instagram API, does
**not** store credentials, and does **not** automate follow/unfollow. The only
input is Instagram's official **"Download Your Information"** export (JSON). Your
data is processed **in memory only** for the session — nothing is written to disk
and no network calls are made at runtime.

---

## Why an export instead of the API?

Instagram's official Graph API does not expose follow lists for personal
accounts, and login-based automation gets accounts banned. The export is the
only safe, supported, complete source of your follow graph.

## Get your data (one-time, ~5 min)

1. Instagram → **Accounts Center → Your information and permissions → Download
   your information**.
2. **Download or transfer information** → your account → **Some of your information**.
3. Under **Connections**, pick **Followers and following**.
4. **Format: JSON** (⚠️ not HTML), **date range: All time** → **Create files**.
5. Download the **ZIP** when ready.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then upload the **ZIP** (or the loose `followers_*.json` / `following.json`
files) in the browser. The app finds the relevant files anywhere inside the ZIP.

## Features

- **📊 Dashboard:** following/followers counts, follower-to-following ratio,
  % of people you follow who ignore you, % of fans you ignore, mutual rate, and
  bar charts of your **following activity over time** and **when people followed
  you** (IST months).
- **✅ Assisted unfollow checklist:** the *not following me back* list as an
  interactive checklist — tick each account off as you unfollow it manually in
  Instagram, with a live progress bar and one-tap profile links. No login, no
  automation, **so it cannot get your account flagged.** Download the remaining
  to-do list as CSV.
- **🙈 I don't follow back** and **🤝 Mutuals** views.
- **🧩 More insights:** oldest one-way follows (best to clear first), plus any
  extra relationship lists your export contains (close friends, recently
  unfollowed, pending follow requests, blocked, restricted, …) shown
  automatically when present.
- **Clickable profile links** and **follow dates rendered in IST (Asia/Kolkata)**.
- **Whitelist** (sidebar): usernames to exclude from the candidate list/checklist.
- **CSV download** of any list.
- **Defensive parser:** handles ZIP or loose files, both export schema shapes
  (top-level list *and* `relationships_*` wrapper), split `followers_1/2/...`
  parts, case differences, extra relationship files, and rejects HTML exports
  with a clear message.

### Why there's no "log in and auto-unfollow" button

Instagram's official API does not expose personal follow lists or an unfollow
action, so the only way to automate it is an unofficial bot driven by your
password — which **violates Instagram's Terms and reliably gets accounts banned**
(bulk unfollowing is the most-detected bot behavior, and logins from a cloud/
datacenter IP get challenged immediately). This tool deliberately keeps *you* in
control of the actual unfollowing and just makes deciding + tracking effortless.

## Deploy to the cloud (Streamlit Community Cloud — free)

This makes the app reachable from any device via a URL. Multiple people can use
it at once — each browser session is isolated, so they only ever see their own
uploaded data.

> ⚠️ **Privacy note:** once hosted, uploads are processed in memory **on
> Streamlit's servers** (not stored by this app, not sent to third parties). If
> you need data to never leave your own machine, run it locally / on your LAN
> instead.

1. Push this folder to a **public GitHub repo** (private repos need a paid tier).
2. Go to **https://share.streamlit.io** → sign in with GitHub → **Create app**.
3. Pick your repo, branch `main`, main file `app.py`. Choose Python 3.12.
4. *(Recommended for a shared link)* Open **Advanced settings → Secrets** and add:
   ```toml
   APP_PASSWORD = "your-strong-password"
   ```
   Share that password only with people you want to let in. Omit it to leave the
   app fully open to anyone with the URL.
5. **Deploy.** You'll get a `*.streamlit.app` URL that works on phone and desktop.

To update later, just push to GitHub — the app redeploys automatically.

### Optional shared-password gate

If `APP_PASSWORD` is set (via Streamlit secrets or `.streamlit/secrets.toml`
locally — see `.streamlit/secrets.toml.example`), the app shows a password
prompt before anything else. If it's unset, the app is open. The password is
compared with `hmac.compare_digest` and not retained after verification.

## Project layout

```
app.py                  Streamlit UI only
parser.py               File discovery + defensive JSON parsing
analysis.py             Pure set logic (no I/O, unit-tested)
sample_data/            Generated test fixtures + make_fixtures.py
tests/                  pytest suites for analysis & parser
requirements.txt
.streamlit/config.toml  Telemetry off; upload size cap
```

## Tests

```bash
pip install pytest
python -m pytest -q
```

Regenerate fixtures with `python sample_data/make_fixtures.py`.

## Privacy guarantees (in code)

- Uploads are read from memory (`UploadedFile.getvalue()`); the social graph is
  **never written to disk**.
- **No runtime network calls** — the only URLs produced are clickable
  `instagram.com/<user>` links rendered in your browser, which you choose to
  open.
- Streamlit's anonymous usage stats are disabled in `.streamlit/config.toml`.

## Known limitations

- Instagram silently omits some accounts (restricted/deactivated) from exports;
  those won't appear here. This is an Instagram limitation, not a bug.
- Follow dates come from the export's `timestamp`; if Instagram omits it, the
  date shows blank.
- The export is a point-in-time snapshot — re-export to refresh.
```
