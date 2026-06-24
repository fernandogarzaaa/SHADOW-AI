from pathlib import Path

import streamlit as st


APP_DIR = Path(__file__).parent
ASSET_DIR = APP_DIR / "streamlit_assets"

OPTIONS = {
    "3": {
        "name": "Tamagui Bento",
        "tagline": "A distinctive bento-style mobile workspace for private recall.",
        "best_for": "A polished startup-product feel with more personality.",
        "image": ASSET_DIR / "option-3.png",
        "preview": "http://localhost:19009/?concept=3",
        "notes": [
            "Strong first impression and memorable layout.",
            "Best option if the client values visual differentiation.",
            "Keeps the approval-first story visible without feeling corporate.",
        ],
    },
    "4": {
        "name": "Gluestack Utility",
        "tagline": "A clean utility-first control surface for the safest assessment signal.",
        "best_for": "Enterprise-ready clarity, recruiter readability, and practical polish.",
        "image": ASSET_DIR / "option-4.png",
        "preview": "http://localhost:19009/?concept=4",
        "notes": [
            "Most conservative and production-presentable direction.",
            "Clear hierarchy around signed requests, audit, and nonce replay.",
            "Recommended if the goal is to look reliable before looking flashy.",
        ],
    },
    "5": {
        "name": "Craft Editorial",
        "tagline": "A story-led treatment that frames the feature like a premium field note.",
        "best_for": "Presentation-forward storytelling and a more memorable portfolio moment.",
        "image": ASSET_DIR / "option-5.png",
        "preview": "http://localhost:19009/?concept=5",
        "notes": [
            "Most expressive and narrative-driven option.",
            "Good for explaining privacy, consent, and auditability in human terms.",
            "Less conventional for an operational app, but strong as a sample-work artifact.",
        ],
    },
}


def render_css() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 2.1rem;
            padding-bottom: 2.5rem;
            max-width: 1160px;
        }
        [data-testid="stAppViewContainer"] {
            background: #f6f7f9;
        }
        h1, h2, h3, p, li {
            letter-spacing: 0 !important;
        }
        .shadow-hero {
            border: 1px solid #dde3ea;
            border-radius: 18px;
            padding: 24px;
            background: #ffffff;
            margin-bottom: 18px;
        }
        .shadow-kicker {
            color: #2563eb;
            font-size: 0.78rem;
            font-weight: 800;
            text-transform: uppercase;
        }
        .shadow-title {
            color: #111827;
            font-size: 2.25rem;
            line-height: 1.05;
            font-weight: 900;
            margin: 6px 0 10px;
        }
        .shadow-copy {
            color: #536173;
            font-size: 1rem;
            line-height: 1.55;
            max-width: 760px;
        }
        .approval-card {
            border: 1px solid #d9e2ec;
            border-radius: 14px;
            background: #ffffff;
            padding: 16px 18px;
            margin: 12px 0 18px;
        }
        .approval-card strong {
            color: #0f172a;
        }
        .metric-pill {
            display: inline-block;
            border: 1px solid #cfe5d9;
            background: #ecfdf5;
            color: #047857;
            border-radius: 999px;
            padding: 6px 10px;
            font-size: 0.74rem;
            font-weight: 800;
            text-transform: uppercase;
            margin-right: 8px;
            margin-bottom: 8px;
        }
        .option-card {
            border: 1px solid #dde3ea;
            border-radius: 14px;
            background: #ffffff;
            padding: 18px;
            min-height: 100%;
        }
        .option-name {
            color: #0f172a;
            font-size: 1.45rem;
            font-weight: 900;
            margin: 0 0 8px;
        }
        .option-tagline {
            color: #5f6b7a;
            line-height: 1.5;
            margin-bottom: 14px;
        }
        .stRadio label {
            font-weight: 700;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_option(option_id: str) -> None:
    option = OPTIONS[option_id]
    left, right = st.columns([0.82, 1.18], gap="large")

    with left:
        st.image(str(option["image"]), caption=f"Option {option_id}: {option['name']}", use_container_width=True)

    with right:
        st.markdown(
            f"""
            <div class="option-card">
              <div class="shadow-kicker">Option {option_id}</div>
              <div class="option-name">{option["name"]}</div>
              <div class="option-tagline">{option["tagline"]}</div>
              <span class="metric-pill">React Native</span>
              <span class="metric-pill">signed requests</span>
              <span class="metric-pill">approval first</span>
              <p><strong>Best for:</strong> {option["best_for"]}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.write("")
        st.subheader("Why this option")
        for note in option["notes"]:
            st.write(f"- {note}")
        st.info(
            f"Local Expo preview route: `{option['preview']}`. "
            "On a public Streamlit deployment, this page presents the review packet; the React Native web export should be hosted separately if an interactive public URL is required."
        )


def main() -> None:
    st.set_page_config(
        page_title="Shadow Native Design Options",
        page_icon="S",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    render_css()

    st.markdown(
        """
        <div class="shadow-hero">
          <div class="shadow-kicker">Shadow Native sample work</div>
          <div class="shadow-title">Design options for client approval</div>
          <div class="shadow-copy">
            Three separate React Native visual directions are prepared before finalizing the mobile feature.
            The goal is to show an approval-first workflow: choose the direction, then polish the selected build.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="approval-card">
          <strong>Recommendation:</strong> lead with Option 4 if the client wants the safest production signal.
          Choose Option 3 if they want a more memorable startup-product feel, or Option 5 if they want a story-led presentation artifact.
        </div>
        """,
        unsafe_allow_html=True,
    )

    selected_label = st.radio(
        "Select a design option to review",
        ["Option 3: Tamagui Bento", "Option 4: Gluestack Utility", "Option 5: Craft Editorial"],
        index=1,
        horizontal=True,
    )
    selected_id = selected_label.split(":")[0].replace("Option ", "")
    render_option(selected_id)

    st.divider()
    st.subheader("Validation already run")
    st.code(
        "npx tsc --noEmit\n"
        "npx expo export -p web\n"
        "SHADOW_NODE_URL=http://127.0.0.1:8787 npx --yes tsx sim/new-user-sim.ts\n\n"
        "Result: 12 passed, 0 failed",
        language="bash",
    )


if __name__ == "__main__":
    main()
