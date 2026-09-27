#!/usr/bin/env python3
"""Voice typing for the chat box, using the browser's own speech recognition.

The Web Speech API is already in Chrome, Edge and Safari, so this costs nothing
to run and needs nothing installed — no model download, no second API key, no
audio ever passing through this app. The browser does the recognition and hands
back text; all this module does is carry that text into Python.

It is a Custom Component v2, which renders into the page's own DOM rather than
an iframe. That detail matters: microphone permission is granted per origin, so
an inline component inherits the page's grant instead of asking again inside a
sandbox that cannot receive it.

The transcript lands in the chat input rather than being sent, so a misheard
ticker can be fixed before it becomes a question. That is why this is called
voice *typing*.

Not supported in Firefox, which has never shipped the API. The button says so
rather than failing silently.
"""

from __future__ import annotations

import streamlit as st

# Recognition languages worth offering here. The dashboard and the model both
# work in English; the other two are for dictating rather than for answers.
LANGUAGES = {
    "en-GB": "English",
    "fr-FR": "Français",
    "ar-QA": "العربية",
}

_HTML = """
<div class="vt">
  <button class="vt-btn" type="button" aria-label="Start voice typing">
    <svg class="vt-ic" viewBox="0 0 24 24" width="15" height="15" aria-hidden="true">
      <path fill="currentColor" d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3z"/>
      <path fill="currentColor" d="M17.3 11a.7.7 0 0 0-1.4 0 3.9 3.9 0 0 1-7.8 0 .7.7 0 0 0-1.4 0 5.3 5.3 0 0 0 4.6 5.2V19h-2a.7.7 0 0 0 0 1.4h5.4a.7.7 0 0 0 0-1.4h-2v-2.8a5.3 5.3 0 0 0 4.6-5.2z"/>
    </svg>
    <span class="vt-label">Speak</span>
  </button>
  <span class="vt-out" aria-live="polite"></span>
</div>
"""

_CSS = """
.vt{display:flex;align-items:center;gap:.5rem;min-height:2.1rem}
.vt-btn{display:inline-flex;align-items:center;gap:.35rem;cursor:pointer;
        font:inherit;font-size:.85rem;padding:.32rem .7rem;
        color:var(--st-text-color);background:var(--st-background-color);
        border:1px solid var(--st-widget-border-color, var(--st-border-color));
        border-radius:var(--st-button-radius, .5rem);
        transition:border-color .15s, color .15s}
.vt-btn:hover:not(:disabled){border-color:var(--st-primary-color);
                             color:var(--st-primary-color)}
.vt-btn:disabled{opacity:.5;cursor:not-allowed}
.vt.on .vt-btn{color:#fff;background:#C00000;border-color:#C00000}
.vt.on .vt-ic{animation:vtpulse 1.1s ease-in-out infinite}
@keyframes vtpulse{0%,100%{opacity:1}50%{opacity:.35}}
@media (prefers-reduced-motion:reduce){.vt.on .vt-ic{animation:none}}
.vt-out{font-size:.78rem;color:var(--st-text-color);opacity:.75;
        overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
"""

_JS = """
export default function (component) {
  const { data, parentElement, setTriggerValue } = component

  const wrap = parentElement.querySelector(".vt")
  const btn = parentElement.querySelector(".vt-btn")
  const label = parentElement.querySelector(".vt-label")
  const out = parentElement.querySelector(".vt-out")
  if (!wrap || !btn || !out) return

  const SR = window.SpeechRecognition || window.webkitSpeechRecognition
  if (!SR) {
    btn.disabled = true
    out.textContent = "Voice typing needs Chrome, Edge or Safari."
    return
  }

  // Survives re-renders of this mount, so clicking Speak does not re-wire the
  // button underneath a session that is already running.
  const state = parentElement._voice || (parentElement._voice = {})
  state.lang = (data && data.lang) || "en-GB"
  if (state.wired) return
  state.wired = true

  btn.onclick = () => {
    if (state.rec) { try { state.rec.stop() } catch (e) {} ; return }

    const rec = new SR()
    state.rec = rec
    rec.lang = state.lang
    rec.continuous = true      // do not cut off at the first pause
    rec.interimResults = true  // so the user can see it is hearing them
    let settled = ""

    rec.onstart = () => {
      wrap.classList.add("on")
      label.textContent = "Stop"
      out.textContent = "Listening …"
    }
    rec.onresult = (event) => {
      let pending = ""
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const piece = event.results[i][0].transcript
        if (event.results[i].isFinal) settled += piece
        else pending += piece
      }
      out.textContent = (settled + pending).trim() || "Listening …"
    }
    rec.onerror = (event) => {
      out.textContent =
        event.error === "not-allowed"
          ? "Microphone blocked — allow it for this site, then try again."
          : event.error === "no-speech"
          ? "Nothing heard."
          : event.error === "network"
          ? "Speech service unreachable."
          : "Voice error: " + event.error
    }
    rec.onend = () => {
      state.rec = null
      wrap.classList.remove("on")
      label.textContent = "Speak"
      const said = settled.trim()
      if (said) {
        out.textContent = ""
        setTriggerValue("transcript", said)
      }
    }

    try {
      rec.start()
    } catch (err) {
      state.rec = null
      out.textContent = "Could not start the microphone."
    }
  }
}
"""

_COMPONENT = st.components.v2.component(
    "voice_typing", html=_HTML, css=_CSS, js=_JS,
)


def mic(*, lang: str = "en-GB", key: str = "voice_typing"):
    """Render the mic button. `result.transcript` holds the text, once, on the
    rerun that follows the user stopping the recording."""
    return _COMPONENT(
        key=key,
        data={"lang": lang},
        on_transcript_change=lambda: None,
    )
