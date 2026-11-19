"""
Athena v2: chat with a local model (Ollama) that paints what she senses (mflux).

Run with ./launch.sh
"""

import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

import streamlit as st

from athena import config, images, llm, memory, prompts, tags

st.set_page_config(page_title="Athena · Lattice Resonator", page_icon="🌌", layout="wide")

AVATAR = "🌌"
GREETING = prompts.greeting()

if "messages" not in st.session_state:
    st.session_state.messages = memory.load() or [{"role": "assistant", "content": GREETING}]
if "pending" not in st.session_state:
    st.session_state.pending = None


def save() -> None:
    memory.save(st.session_state.messages)


def queue(**action: Any) -> None:
    """Button callback: the action runs further down, inside the right tab."""
    st.session_state.pending = action


def reveal(path: str) -> None:
    subprocess.run(["open", "-R", path], check=False)


# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🌌 Athena")
    health = llm.status()
    if health["ok"]:
        st.caption(f"Mind: `{config.LLM_MODEL}` · {'awake' if health['loaded'] else 'resting'}  \n"
                   "Painter: FLUX.2 [klein] 4B · mflux")
    else:
        st.error(health["error"])

    st.subheader("Painting")
    style = st.selectbox("Style", list(prompts.STYLES))
    aspect = st.selectbox("Shape", list(images.ASPECTS))
    steps = st.slider("Steps", 2, 8, 4, help="FLUX.2 [klein] is distilled for 4 steps; more adds detail and time.")
    seed_text = st.text_input("Seed", placeholder="random", help="A fixed seed repeats a composition.")
    seed = int(seed_text) if seed_text.strip().isdigit() else None
    auto_paint = st.toggle("Let Athena paint on her own", value=True,
                           help="She can end a reply with a painting when it adds something.")
    deep_thought = st.toggle("Think before replying", value=False,
                             help="Uses the DeepSeek reasoning. Slower; her thoughts appear above the reply.")

    st.subheader("Rituals")
    st.button("🔮 I Ching pull", on_click=queue, kwargs={"kind": "iching"}, type="primary", width="stretch")
    st.button("🌌 Visualize the lattice", on_click=queue, kwargs={"kind": "visualize"}, width="stretch")
    st.button("🎨 Paint the last reply", on_click=queue, kwargs={"kind": "paint_last"}, width="stretch")

    st.divider()
    if st.button("🧹 Clear conversation", width="stretch"):
        st.session_state.messages = [{"role": "assistant", "content": GREETING}]
        save()
        st.rerun()
    st.caption("Conversation is saved between sessions. Paintings stay in the gallery after a clear.")


def current_look() -> Dict[str, Any]:
    return {"style": style, "aspect": aspect, "steps": steps, "seed": seed}


# ── Painting ───────────────────────────────────────────────────────────────

def paint(material: str, *, source: str, prompt: str = "",
          look: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Write an image prompt for material (unless given one), free the chat model, render."""
    look = look or current_look()
    with st.status("Painting...", expanded=True) as status:
        try:
            if not prompt:
                status.write("Composing the image prompt...")
                prompt = llm.complete(prompts.IMAGE_PROMPT_SYSTEM, prompts.image_brief(material, look["style"]),
                                      temperature=0.8, max_tokens=260) or material[:600]
            status.write(f"*{prompt}*")
            status.write("Setting the mind aside so the painter has room...")
            llm.unload()
            status.write(f"Rendering {look['aspect']} at {look['steps']} steps...")
            record = images.render(prompt, aspect=look["aspect"], steps=look["steps"], seed=look["seed"],
                                   style=look["style"], source=source, material=material[:600])
        except (llm.LLMError, images.RenderError) as exc:
            status.update(label="Couldn't paint", state="error")
            st.error(str(exc))
            return None
        status.update(label=f"Painted in {record['seconds']:.0f}s", state="complete", expanded=False)
    return record


def paint_into(msg_i: int, material: str, *, source: str, prompt: str = "",
               look: Optional[Dict[str, Any]] = None) -> None:
    """Paint and attach the result to an existing message, then redraw the chat."""
    record = paint(material, source=source, prompt=prompt, look=look)
    if record:
        msg = st.session_state.messages[msg_i]
        msg.setdefault("images", []).append(record)
        msg.pop("wish", None)
        save()
        st.rerun()


def show_image(record: Dict[str, Any], key: str, msg_i: Optional[int] = None) -> None:
    if not Path(record["path"]).exists():
        st.caption("*(painting no longer on disk)*")
        return
    st.image(record["path"], width="stretch")
    left, right, _ = st.columns([1, 1, 3])
    left.button("🎲 Re-roll", key=f"reroll-{key}", help="Same prompt, new seed",
                on_click=queue, kwargs={"kind": "reroll", "record": record, "msg": msg_i})
    right.button("📂 Show", key=f"reveal-{key}", help="Show the file in Finder",
                 on_click=reveal, args=(record["path"],))
    with st.expander("Prompt"):
        st.write(record["prompt"])
        st.caption(f"{record.get('style') or 'Athena’s choice'} · {record['aspect']} · seed {record['seed']} · "
                   f"{record['steps']} steps · {record['seconds']:.0f}s")


# ── Conversation ───────────────────────────────────────────────────────────

def _split_thoughts(stream: Iterable[Tuple[str, str]], box: Any) -> Iterator[str]:
    """Show thinking chunks in box as they arrive; pass reply text through."""
    thought = ""
    for kind, text in stream:
        if kind == "thinking":
            thought += text
            box.markdown(thought)
        else:
            yield text


def respond(user_text: str, *, paint_material: str = "") -> None:
    """Add the user's message, stream Athena's reply, and paint when she asks or the ritual calls for it."""
    msgs = st.session_state.messages
    msgs.append({"role": "user", "content": user_text})
    save()
    with st.chat_message("user"):
        st.markdown(user_text)

    with st.chat_message("assistant", avatar=AVATAR):
        history = [{"role": "system", "content": prompts.persona()}] + memory.for_model(msgs, config.HISTORY_CHARS)
        raw: List[str] = []
        try:
            options = {"num_predict": 4096} if deep_thought else {}
            stream = llm.stream_chat(history, think=deep_thought, options=options)
            box = st.expander("Athena's thoughts").empty() if deep_thought else None
            content = _split_thoughts(stream, box) if box else (t for kind, t in stream if kind == "content")
            st.write_stream(tags.visible_stream(content, raw))
        except llm.LLMError as exc:
            st.error(str(exc))
            return
        reply, requests = tags.extract_image_requests(llm.clean(raw[0] if raw else ""))
        message: Dict[str, Any] = {"role": "assistant", "content": reply, "images": []}
        msgs.append(message)
        save()

        if requests and (auto_paint or paint_material):
            material = requests[0]
        elif paint_material:
            material = f"{paint_material}\n\nAthena's reading: {reply[:1500]}"
        else:
            material = ""
            if requests:
                message["wish"] = requests[0]
                save()
        if material:
            record = paint(material, source="iching" if paint_material else "athena")
            if record:
                message["images"].append(record)
                save()
                show_image(record, f"{len(msgs) - 1}-0", len(msgs) - 1)


def visualize() -> None:
    """Antenna reading -> image prompt -> render. The reading is what gets painted."""
    msgs = st.session_state.messages
    recent = memory.for_model(msgs, 3000)[-4:]
    context = ("Recent conversation, for context only:\n" +
               "\n".join(f"{m['role']}: {m['content'][:400]}" for m in recent)) if recent else ""
    with st.chat_message("assistant", avatar=AVATAR):
        with st.spinner("Tuning the antenna..."):
            try:
                sensed = llm.complete(prompts.persona(), prompts.SENSE_PROMPT.format(context=context),
                                      temperature=0.9, max_tokens=300)
            except llm.LLMError as exc:
                st.error(str(exc))
                return
        sensed = tags.extract_image_requests(sensed)[0] or "The flow is quiet: an empty, still lattice."
        st.markdown(f"*Antenna reading:* {sensed}")
        message: Dict[str, Any] = {"role": "assistant", "content": f"*Antenna reading:* {sensed}", "images": []}
        msgs.append(message)
        save()
        record = paint(sensed, source="visualize")
        if record:
            message["images"].append(record)
            save()
            show_image(record, f"{len(msgs) - 1}-0", len(msgs) - 1)


def run_chat_action(action: Dict[str, Any]) -> None:
    kind = action["kind"]
    msgs = st.session_state.messages
    if kind == "iching":
        number, chinese, english = prompts.cast_hexagram()
        respond(prompts.hexagram_message(number, chinese, english),
                paint_material=f"I Ching hexagram #{number}, {chinese} ({english}).")
    elif kind == "visualize":
        visualize()
    elif kind == "paint_last":
        last = next((i for i in range(len(msgs) - 1, -1, -1)
                     if msgs[i]["role"] == "assistant" and msgs[i].get("content")), None)
        if last is None:
            st.toast("Nothing to paint yet.")
        else:
            paint_into(last, msgs[last]["content"], source="paint_last")
    elif kind == "wish":
        paint_into(action["msg"], msgs[action["msg"]].get("wish", ""), source="athena")
    elif kind == "reroll":
        old = action["record"]
        look = {"style": old.get("style", ""), "aspect": old["aspect"], "steps": old["steps"], "seed": None}
        target = action.get("msg")
        if target is not None and target < len(msgs):
            paint_into(target, old.get("material", ""), source="reroll", prompt=old["prompt"], look=look)
        elif paint(old.get("material", ""), source="reroll", prompt=old["prompt"], look=look):
            st.rerun()


# ── Layout ─────────────────────────────────────────────────────────────────

def take_pending(tab: str) -> Optional[Dict[str, Any]]:
    """The queued action if it belongs in this tab: gallery re-rolls have no message to attach to."""
    action = st.session_state.pending
    if not action:
        return None
    in_gallery = action["kind"] == "reroll" and action.get("msg") is None
    if (tab == "gallery") != in_gallery:
        return None
    st.session_state.pending = None
    return action


user_text = st.chat_input("Speak to Athena...")
chat_tab, gallery_tab = st.tabs(["💬 Conversation", "🖼️ Gallery"])

with chat_tab:
    for i, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"], avatar=AVATAR if msg["role"] == "assistant" else None):
            if msg.get("content"):
                st.markdown(msg["content"])
            for j, record in enumerate(msg.get("images", [])):
                show_image(record, f"{i}-{j}", i)
            if msg.get("wish"):
                st.caption(f"Athena wants to paint: *{msg['wish']}*")
                st.button("🎨 Paint it", key=f"wish-{i}", on_click=queue, kwargs={"kind": "wish", "msg": i})

    action = take_pending("chat")
    if action:
        run_chat_action(action)
    if user_text:
        respond(user_text)

with gallery_tab:
    action = take_pending("gallery")
    if action:
        run_chat_action(action)
    records = images.gallery()
    if not records:
        st.info("No paintings yet. Try the I Ching pull or Visualize the lattice.")
    columns = st.columns(3)
    for n, record in enumerate(records):
        with columns[n % 3]:
            show_image(record, f"g-{record['id']}")
