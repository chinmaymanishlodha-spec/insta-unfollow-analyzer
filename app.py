"""Streamlit UI for the 'Who doesn't follow me back' analyzer.

Privacy: the uploaded social graph is processed entirely in memory for the
current session and is never written to disk by this app. When deployed to a
hosting provider (e.g. Streamlit Community Cloud) the upload is processed in
memory *on that server*; it is not persisted by our code and not sent to any
third party beyond the host. Each browser session is isolated, so multiple
people can use the app at once without seeing each other's data.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import hmac

import pandas as pd
import streamlit as st

from analysis import Account, AnalysisResult, analyze, apply_whitelist
from parser import HTMLExportError, NoDataError, ParsedExport, parse_upload

IST = "Asia/Kolkata"

st.set_page_config(page_title="Who doesn't follow me back?", page_icon="🔍", layout="wide")


def check_password() -> bool:
    """Optional shared-password gate for public deployments.

    If an ``APP_PASSWORD`` secret is configured (Streamlit secrets or env), the
    user must enter it before the app runs. If no password is set, the app is
    open to everyone (suitable for purely local use). The comparison uses
    ``hmac.compare_digest`` to avoid timing leaks; the entered password is not
    retained in session state.
    """

    try:
        expected = st.secrets.get("APP_PASSWORD")
    except Exception:
        expected = None
    if not expected:
        return True  # no gate configured

    if st.session_state.get("authenticated"):
        return True

    def _verify() -> None:
        entered = st.session_state.get("password_input", "")
        if hmac.compare_digest(str(entered), str(expected)):
            st.session_state["authenticated"] = True
        else:
            st.session_state["authenticated"] = False
        st.session_state.pop("password_input", None)  # don't keep the secret around

    st.text_input("Enter access password", type="password", key="password_input", on_change=_verify)
    if st.session_state.get("authenticated") is False:
        st.error("Incorrect password.")
    st.stop()
    return False  # unreachable; st.stop() halts the run


check_password()


def _profile_url(acct: Account) -> str:
    """Build a clickable profile URL from the export href or the username."""
    if acct.href and acct.href.startswith("http"):
        return acct.href
    return f"https://www.instagram.com/{acct.username}"


def _to_dataframe(accounts: list[Account]) -> pd.DataFrame:
    """Render a list of accounts as a display DataFrame with IST follow dates."""
    rows = [
        {
            "Username": a.username,
            "Profile URL": _profile_url(a),
            "Followed on (IST)": a.timestamp,
        }
        for a in accounts
    ]
    df = pd.DataFrame(rows, columns=["Username", "Profile URL", "Followed on (IST)"])
    if not df.empty:
        # Unix seconds -> tz-aware IST. NaT for missing/zero timestamps.
        df["Followed on (IST)"] = (
            pd.to_datetime(df["Followed on (IST)"], unit="s", utc=True, errors="coerce")
            .dt.tz_convert(IST)
        )
    return df


def _show_table(accounts: list[Account], *, key: str, empty_msg: str) -> None:
    """Render an accounts table with clickable links + a CSV download button."""
    if not accounts:
        st.info(empty_msg)
        return
    df = _to_dataframe(accounts)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Username": st.column_config.TextColumn("Username", width="medium"),
            "Profile URL": st.column_config.LinkColumn(
                "Profile", display_text="Open profile ↗"
            ),
            "Followed on (IST)": st.column_config.DatetimeColumn(
                "Followed on (IST)", format="YYYY-MM-DD HH:mm", timezone=IST
            ),
        },
    )
    # CSV export: serialize the displayed frame (in-memory, never written to disk).
    csv_df = df.copy()
    if not csv_df.empty:
        csv_df["Followed on (IST)"] = csv_df["Followed on (IST)"].dt.strftime(
            "%Y-%m-%d %H:%M:%S %z"
        )
    st.download_button(
        "⬇️ Download this list as CSV",
        data=csv_df.to_csv(index=False).encode("utf-8"),
        file_name=f"{key}.csv",
        mime="text/csv",
        key=f"dl_{key}",
    )


def _run_analysis(parsed: ParsedExport) -> AnalysisResult:
    return analyze(parsed.following, parsed.followers)


# --- UI --------------------------------------------------------------------

st.title("🔍 Who doesn't follow me back?")
st.caption(
    "Read-only. No Instagram login, no API, no automation. Your export is "
    "processed in memory for this session only — it is never stored or shared. "
    "Sessions are isolated, so others using the app can't see your data."
)

with st.expander("How to get your data (one-time, ~5 min)", expanded=False):
    st.markdown(
        """
1. Open **Instagram → Accounts Center → Your information and permissions → "
   Download your information**.
2. Choose **Download or transfer information** → your account → **Some of your
   information**.
3. Under **Connections**, select **Followers and following**.
4. Set **Format: JSON** (⚠️ *not* HTML), date range **All time**, then **Create files**.
5. When the download is ready, save the **ZIP** and upload it below. You can also
   unzip it and upload the individual `followers_*.json` / `following.json` files.
        """
    )

uploads = st.file_uploader(
    "Upload your export ZIP (or the loose followers_*.json / following.json files)",
    type=["zip", "json"],
    accept_multiple_files=True,
)

if not uploads:
    st.stop()

# Combine multiple uploads: if any ZIP is present parse it; merge any loose JSONs.
parsed: ParsedExport | None = None
try:
    merged_following: dict[str, Account] = {}
    merged_followers: dict[str, Account] = {}
    sources: list[str] = []
    for up in uploads:
        p = parse_upload(up.name, up.getvalue())
        for k, v in p.following.items():
            merged_following.setdefault(k, v)
        for k, v in p.followers.items():
            merged_followers.setdefault(k, v)
        sources.extend(p.sources)
    parsed = ParsedExport(merged_following, merged_followers, sources)
except HTMLExportError as exc:
    st.error(str(exc))
    st.stop()
except NoDataError as exc:
    st.error(str(exc))
    st.stop()
except Exception as exc:  # pragma: no cover - defensive UI guard
    st.error(f"Something went wrong reading the upload: {exc}")
    st.stop()

if not parsed.following:
    st.warning(
        "Found follower data but no 'following' list. The headline 'not following "
        "me back' list needs your following.json — make sure it's included."
    )

result = _run_analysis(parsed)

st.success(
    f"Parsed **{len(parsed.following)}** following and "
    f"**{len(parsed.followers)}** followers."
)
with st.expander("Source files detected"):
    st.write(parsed.sources or "—")

c1, c2, c3 = st.columns(3)
c1.metric("🚫 Not following me back", result.counts["not_following_back"])
c2.metric("🙈 I don't follow back", result.counts["not_followed_back"])
c3.metric("🤝 Mutuals", result.counts["mutuals"])

st.divider()

# Whitelist for the headline list.
st.subheader("Whitelist (keep these, exclude from candidates)")
whitelist_raw = st.text_area(
    "One username per line. These are removed from the 'not following me back' "
    "list below (e.g. accounts you intentionally keep).",
    placeholder="celebrity_i_like\nmy_alt_account",
    height=100,
)
whitelist = whitelist_raw.splitlines() if whitelist_raw else []

headline = apply_whitelist(result.not_following_back, whitelist)
excluded_n = len(result.not_following_back) - len(headline)

tab1, tab2, tab3 = st.tabs(
    [
        f"🚫 Not following me back ({len(headline)})",
        f"🙈 I don't follow back ({result.counts['not_followed_back']})",
        f"🤝 Mutuals ({result.counts['mutuals']})",
    ]
)

with tab1:
    st.markdown(
        "Accounts **you follow** that **don't follow you back** — your unfollow "
        "candidates."
    )
    if excluded_n:
        st.caption(f"{excluded_n} account(s) hidden by your whitelist.")
    _show_table(
        headline,
        key="not_following_back",
        empty_msg="🎉 Everyone you follow follows you back (after whitelist).",
    )

with tab2:
    st.markdown("Accounts that **follow you** but **you don't follow back**.")
    _show_table(
        result.not_followed_back,
        key="not_followed_back",
        empty_msg="You follow back everyone who follows you.",
    )

with tab3:
    st.markdown("Accounts where the follow is **mutual**.")
    _show_table(
        result.mutuals,
        key="mutuals",
        empty_msg="No mutual follows found.",
    )
