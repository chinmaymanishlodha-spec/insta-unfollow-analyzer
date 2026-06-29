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
import os

import pandas as pd
import streamlit as st

from analysis import (
    Account,
    AnalysisResult,
    analyze,
    apply_whitelist,
    summary_stats,
)
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


def _monthly_counts(accounts: list[Account], label: str) -> pd.DataFrame:
    """Group accounts by the IST month of their timestamp for a bar chart.

    Returns a DataFrame indexed by 'YYYY-MM' month string with one count column.
    Accounts without a usable timestamp are ignored. Empty if none have dates.
    """
    ts = [a.timestamp for a in accounts if a.timestamp]
    if not ts:
        return pd.DataFrame()
    s = pd.to_datetime(pd.Series(ts), unit="s", utc=True).dt.tz_convert(IST)
    months = s.dt.strftime("%Y-%m")
    counts = months.value_counts().sort_index()
    return pd.DataFrame({label: counts.values}, index=counts.index)


def _checklist(accounts: list[Account], *, key: str) -> None:
    """Assisted manual-unfollow checklist.

    Renders an editable table with a 'Done' checkbox per account plus a progress
    bar. The user ticks each row off as they unfollow it manually in Instagram
    (the profile link opens the account in one tap). Checkbox state persists
    across reruns via the widget key. No automation, no Instagram calls — this is
    purely a personal tracker, which is why it cannot get your account banned.
    """
    if not accounts:
        st.info("🎉 Nothing to unfollow here (after your whitelist).")
        return

    base = _to_dataframe(accounts)
    editable = pd.DataFrame(
        {
            "Done": False,
            "Username": base["Username"],
            "Profile": base["Profile URL"],
            "Followed on (IST)": base["Followed on (IST)"],
        }
    )

    progress_slot = st.empty()
    edited = st.data_editor(
        editable,
        use_container_width=True,
        hide_index=True,
        disabled=["Username", "Profile", "Followed on (IST)"],  # only 'Done' editable
        column_config={
            "Done": st.column_config.CheckboxColumn(
                "Unfollowed?", help="Tick after you unfollow this account in Instagram"
            ),
            "Username": st.column_config.TextColumn("Username", width="medium"),
            "Profile": st.column_config.LinkColumn("Open", display_text="Open ↗"),
            "Followed on (IST)": st.column_config.DatetimeColumn(
                "Followed on (IST)", format="YYYY-MM-DD HH:mm", timezone=IST
            ),
        },
        key=f"editor_{key}",
    )

    total = len(edited)
    done = int(edited["Done"].sum())
    with progress_slot.container():
        st.progress(done / total if total else 0.0, text=f"Unfollowed {done} of {total}")

    # CSV of the still-to-do accounts.
    todo = edited[~edited["Done"]].copy()
    if not todo.empty and "Followed on (IST)" in todo:
        todo["Followed on (IST)"] = pd.to_datetime(
            todo["Followed on (IST)"], errors="coerce"
        ).dt.strftime("%Y-%m-%d %H:%M:%S %z")
    st.download_button(
        "⬇️ Download remaining (to-do) list as CSV",
        data=todo.drop(columns=["Done"]).to_csv(index=False).encode("utf-8"),
        file_name=f"{key}_todo.csv",
        mime="text/csv",
        key=f"dl_{key}",
    )


def _inject_css() -> None:
    """Inject the app's visual theme (works on both light and dark Streamlit)."""
    st.markdown(
        """
        <style>
        /* Instagram-style gradient accent reused across the app */
        :root { --ig: linear-gradient(95deg,#feda75,#fa7e1e,#d62976,#962fbf,#4f5bd5); }

        /* Hero header */
        .hero { padding: 1.6rem 0 0.4rem 0; }
        .hero h1 {
            font-size: 2.7rem; font-weight: 800; letter-spacing:-0.5px; margin:0;
            background: var(--ig); -webkit-background-clip: text;
            background-clip: text; -webkit-text-fill-color: transparent;
        }
        .hero p { font-size: 1.05rem; opacity: 0.8; margin: 0.35rem 0 0.7rem 0; }
        .chips { margin: 0.2rem 0 0.6rem 0; }
        .chip {
            display:inline-block; padding:4px 12px; margin:3px 6px 3px 0;
            border-radius:999px; font-size:0.8rem; font-weight:600;
            background: rgba(150,150,150,0.12);
            border:1px solid rgba(150,150,150,0.22);
        }

        /* Metric cards */
        .cards { display:flex; flex-wrap:wrap; gap:14px; margin:0.4rem 0 0.6rem 0; }
        .card {
            flex:1 1 180px; border-radius:18px; padding:16px 18px;
            background: rgba(150,150,150,0.08);
            border:1px solid rgba(150,150,150,0.18);
            position:relative; overflow:hidden;
        }
        .card::before {
            content:""; position:absolute; left:0; top:0; bottom:0; width:5px;
            background: var(--ig);
        }
        .card .lbl { font-size:0.82rem; opacity:0.72; font-weight:600; }
        .card .val { font-size:2rem; font-weight:800; line-height:1.15; margin-top:2px; }
        .card .sub { font-size:0.78rem; opacity:0.6; margin-top:2px; }

        /* Tighten the gradient progress + buttons */
        .stButton>button { border-radius:10px; font-weight:600; }
        div[data-testid="stFileUploader"] {
            border:1.5px dashed rgba(150,150,150,0.35); border-radius:16px; padding:10px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _metric_cards(cards: list[tuple[str, str, str]]) -> None:
    """Render a row of styled metric cards. Each card = (label, value, sub)."""
    html = '<div class="cards">'
    for label, value, sub in cards:
        html += (
            f'<div class="card"><div class="lbl">{label}</div>'
            f'<div class="val">{value}</div>'
            f'<div class="sub">{sub}</div></div>'
        )
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


# --- UI --------------------------------------------------------------------

_inject_css()

st.markdown(
    """
    <div class="hero">
      <h1>Who doesn't follow me back?</h1>
      <p>See who you follow that doesn't follow you back — plus a dashboard,
         an assisted unfollow checklist, and more insights.</p>
      <div class="chips">
        <span class="chip">🔒 No login</span>
        <span class="chip">🛡️ No password</span>
        <span class="chip">⚡ In-memory only</span>
        <span class="chip">🙈 Sessions isolated</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Determine the data source: a fresh upload, or the bundled sample demo.
uploads = st.file_uploader(
    "Drop your Instagram export ZIP here (or the loose followers_*.json / following.json files)",
    type=["zip", "json"],
    accept_multiple_files=True,
    label_visibility="visible",
)

if "use_sample" not in st.session_state:
    st.session_state.use_sample = False

if not uploads:
    cta1, cta2 = st.columns([1, 2])
    with cta1:
        if st.button("✨ Try it with sample data", use_container_width=True, type="primary"):
            st.session_state.use_sample = True
    with cta2:
        st.caption(
            "No export yet? Click **Try it with sample data** to explore the full "
            "experience instantly with a fake account."
        )

    with st.expander("📥 How to get your real Instagram data (one-time, ~5 min)"):
        st.markdown(
            """
1. **Instagram → Accounts Center → Your information and permissions → Download your information**
2. **Download or transfer information** → your account → **Some of your information**
3. Under **Connections**, tick **Followers and following**
4. **Format: JSON** (⚠️ *not* HTML), date range **All time** → **Create files**
5. When Instagram emails you the **ZIP**, upload it above. (Loose `followers_*.json` /
   `following.json` files work too.)
            """
        )

    if not st.session_state.use_sample:
        st.stop()

# Parse the chosen source.
parsed: ParsedExport | None = None
try:
    if uploads:
        st.session_state.use_sample = False  # a real upload overrides the demo
        merged_following: dict[str, Account] = {}
        merged_followers: dict[str, Account] = {}
        merged_extras: dict[str, dict[str, Account]] = {}
        sources: list[str] = []
        for up in uploads:
            p = parse_upload(up.name, up.getvalue())
            for k, v in p.following.items():
                merged_following.setdefault(k, v)
            for k, v in p.followers.items():
                merged_followers.setdefault(k, v)
            for label, m in p.extras.items():
                merged_extras.setdefault(label, {}).update(m)
            sources.extend(p.sources)
        parsed = ParsedExport(merged_following, merged_followers, sources, merged_extras)
    else:
        # Bundled sample demo.
        import parser as _parser

        sample_zip = os.path.join(os.path.dirname(__file__), "sample_data", "export.zip")
        with open(sample_zip, "rb") as fh:
            parsed = _parser.parse_zip(fh.read())
        st.info("👀 You're viewing **sample data**. Upload your own export above to analyze your account.")
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

following_n = len(parsed.following)
followers_n = len(parsed.followers)
st.success(f"✅ Analyzed **{following_n:,}** following and **{followers_n:,}** followers.")
with st.expander("Source files detected"):
    st.write(parsed.sources or "—")

# Whitelist (used by the candidate list + checklist). Put it in the sidebar so it
# applies across tabs.
with st.sidebar:
    st.header("⚙️ Settings")
    whitelist_raw = st.text_area(
        "Whitelist — keep these (one username per line)",
        help="Removed from the 'not following me back' candidate list & checklist.",
        placeholder="celebrity_i_like\nmy_alt_account",
        height=140,
    )
whitelist = whitelist_raw.splitlines() if whitelist_raw else []
headline = apply_whitelist(result.not_following_back, whitelist)
excluded_n = len(result.not_following_back) - len(headline)

tab_dash, tab_unfollow, tab_fans, tab_mutual, tab_more = st.tabs(
    [
        "📊 Dashboard",
        f"✅ Unfollow candidates ({len(headline)})",
        f"🙈 I don't follow back ({result.counts['not_followed_back']})",
        f"🤝 Mutuals ({result.counts['mutuals']})",
        "🧩 More insights",
    ]
)

# --- Dashboard -------------------------------------------------------------
with tab_dash:
    stats = summary_stats(following_n, followers_n, result)

    _metric_cards([
        ("👣 Following", f"{following_n:,}", "accounts you follow"),
        ("👥 Followers", f"{followers_n:,}", "accounts following you"),
        ("⚖️ Ratio", f"{stats['follower_following_ratio']}", "followers per following"),
        ("🚫 Don't follow back", f"{result.counts['not_following_back']:,}", "your unfollow candidates"),
    ])
    _metric_cards([
        ("🙈 You ignore", f"{result.counts['not_followed_back']:,}", "fans you don't follow back"),
        ("🤝 Mutuals", f"{result.counts['mutuals']:,}", f"{stats['mutual_rate']}% mutual rate"),
        ("📉 Ignored by", f"{stats['pct_following_not_back']}%", "of accounts you follow"),
        ("📈 You ignore", f"{stats['pct_followers_not_back']}%", "of your followers"),
    ])

    st.divider()
    st.subheader("📈 Your following activity over time")
    follow_hist = _monthly_counts(list(parsed.following.values()), "Accounts you followed")
    if follow_hist.empty:
        st.caption("No follow-date timestamps available in this export.")
    else:
        st.bar_chart(follow_hist)

    foll_hist = _monthly_counts(list(parsed.followers.values()), "New followers")
    if not foll_hist.empty:
        st.subheader("📈 When people followed you")
        st.bar_chart(foll_hist)

# --- Unfollow candidates (assisted checklist) ------------------------------
with tab_unfollow:
    st.markdown(
        "Accounts **you follow** that **don't follow you back**. Tick each one off "
        "as you unfollow it manually in Instagram — the **Open ↗** link takes you "
        "straight to the profile."
    )
    st.caption(
        "ℹ️ This is a personal tracker — it never logs in or unfollows for you, so "
        "it can't get your account flagged. Unfollow at a human pace."
    )
    if excluded_n:
        st.caption(f"{excluded_n} account(s) hidden by your whitelist (sidebar).")
    _checklist(headline, key="unfollow_candidates")

# --- Fans I don't follow back ----------------------------------------------
with tab_fans:
    st.markdown("Accounts that **follow you** but **you don't follow back**.")
    _show_table(
        result.not_followed_back,
        key="not_followed_back",
        empty_msg="You follow back everyone who follows you.",
    )

# --- Mutuals ---------------------------------------------------------------
with tab_mutual:
    st.markdown("Accounts where the follow is **mutual**.")
    _show_table(result.mutuals, key="mutuals", empty_msg="No mutual follows found.")

# --- More insights ---------------------------------------------------------
with tab_more:
    st.subheader("🕰️ Oldest accounts that don't follow you back")
    st.caption("Long-standing one-way follows — often the best to clear out first.")
    dated = [a for a in result.not_following_back if a.timestamp]
    oldest = sorted(dated, key=lambda a: a.timestamp)[:25]
    _show_table(oldest, key="oldest_non_followers", empty_msg="No dated follows found.")

    if parsed.extras:
        st.divider()
        st.subheader("📂 Other relationship lists in your export")
        st.caption("These appear only because your export included them.")
        for label, accounts_map in parsed.extras.items():
            accounts = sorted(accounts_map.values(), key=lambda a: a.username.lower())
            with st.expander(f"{label} ({len(accounts)})"):
                _show_table(
                    accounts,
                    key=f"extra_{label}".replace(" ", "_"),
                    empty_msg="—",
                )
    else:
        st.divider()
        st.caption(
            "💡 Tip: include 'close friends', 'recently unfollowed', 'pending follow "
            "requests', 'blocked' etc. in your export and they'll show up here too."
        )
