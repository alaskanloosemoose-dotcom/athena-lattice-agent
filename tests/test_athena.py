import json

import pytest

from athena import config, images, memory, prompts, tags


# ── [[IMAGE: ...]] tags ────────────────────────────────────────────────────

def test_extracts_tag_and_cleans_text():
    text, reqs = tags.extract_image_requests("The cubes turn slowly.\n[[IMAGE: a violet tesseract over snow]]")
    assert text == "The cubes turn slowly."
    assert reqs == ["a violet tesseract over snow"]


def test_extract_handles_case_spacing_and_unclosed_tag():
    assert tags.extract_image_requests("x [[ image :  aurora ]]")[1] == ["aurora"]
    text, reqs = tags.extract_image_requests("Here it is.\n[[IMAGE: a lone raven on a spruce")
    assert text == "Here it is."
    assert reqs == ["a lone raven on a spruce"]


def test_no_tag_leaves_text_alone():
    assert tags.extract_image_requests("matrix [[1, 2], [3, 4]]") == ("matrix [[1, 2], [3, 4]]", [])


def _stream(chunks):
    sink = []
    shown = "".join(tags.visible_stream(iter(chunks), sink))
    return shown, sink[0]


def test_visible_stream_hides_tag_split_across_chunks():
    shown, full = _stream(["The flow is ", "warm. [", "[IMA", "GE: golden spirals]]"])
    assert shown == "The flow is warm. "
    assert full == "The flow is warm. [[IMAGE: golden spirals]]"


def test_visible_stream_releases_brackets_that_are_not_a_tag():
    shown, _ = _stream(["grid = [", "[0, 1], [1, 0]]"])
    assert shown == "grid = [[0, 1], [1, 0]]"


def test_visible_stream_holds_back_partial_marker_at_end():
    shown, full = _stream(["done [[IM"])
    assert shown == "done [[IM"         # never became a tag, so it is flushed at the end
    assert full == "done [[IM"


# ── Memory ─────────────────────────────────────────────────────────────────

def test_memory_roundtrip(tmp_path):
    path = tmp_path / "m.json"
    msgs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello", "images": []}]
    memory.save(msgs, path)
    assert memory.load(path) == msgs
    assert memory.load(tmp_path / "missing.json") == []
    path.write_text("not json")
    assert memory.load(path) == []


def test_for_model_keeps_recent_turns_and_notes_paintings():
    msgs = [
        {"role": "assistant", "content": "a" * 50},
        {"role": "user", "content": "b" * 50},
        {"role": "assistant", "content": "c", "images": [{"prompt": "a raven"}]},
        {"role": "assistant", "content": ""},
    ]
    out = memory.for_model(msgs, max_chars=80)
    assert [m["content"][0] for m in out] == ["b", "c"]
    assert "[You painted: a raven]" in out[-1]["content"]
    assert all(set(m) == {"role", "content"} for m in out)


# ── Images ─────────────────────────────────────────────────────────────────

def test_aspects_are_valid_flux_sizes():
    for width, height in images.ASPECTS.values():
        assert width % 16 == 0 and height % 16 == 0
    assert images.ASPECTS["Panoramic 5:2"][0] / images.ASPECTS["Panoramic 5:2"][1] == 2.5


def test_build_command(tmp_path):
    cmd = images.build_command("a fox", 1024, 1024, 4, 7, tmp_path / "o.png")
    assert cmd[0].endswith("mflux-generate-flux2")
    for flag, value in (("--prompt", "a fox"), ("--seed", "7"), ("--steps", "4"), ("--base-model", "flux2-klein-4b")):
        assert cmd[cmd.index(flag) + 1] == value


@pytest.fixture(autouse=True)
def isolated_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "LOCK_FILE", tmp_path / "render.lock")


def test_render_writes_sidecar_and_gallery_lists_it(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "IMAGES_DIR", tmp_path)

    def fake_run(cmd, **kwargs):
        out = cmd[cmd.index("--output") + 1]
        open(out, "wb").write(b"png")

        class Done:
            returncode, stdout, stderr = 0, "", ""
        return Done()

    monkeypatch.setattr(images.subprocess, "run", fake_run)
    record = images.render("a fox", aspect="Square 1:1", seed=42, style="Photoreal")
    assert record["seed"] == 42 and record["style"] == "Photoreal"
    assert json.loads((tmp_path / f"{record['id']}.json").read_text())["prompt"] == "a fox"
    assert [r["id"] for r in images.gallery()] == [record["id"]]


def test_render_failure_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "IMAGES_DIR", tmp_path)

    class Failed:
        returncode, stdout, stderr = 1, "", "out of memory"
    monkeypatch.setattr(images.subprocess, "run", lambda cmd, **kw: Failed())
    with pytest.raises(images.RenderError, match="out of memory"):
        images.render("a fox", aspect="Square 1:1")


# ── Prompts ────────────────────────────────────────────────────────────────

def test_sixty_four_hexagrams():
    assert len(prompts.HEXAGRAMS) == 64
    assert prompts.HEXAGRAMS[0][1] == "The Creative" and prompts.HEXAGRAMS[63][1] == "Before Completion"
    number, chinese, english = prompts.cast_hexagram()
    assert prompts.HEXAGRAMS[number - 1] == (chinese, english)


def test_image_brief_includes_style():
    assert "sumi-e" in prompts.image_brief("hexagram 29", "I Ching ink wash")
    assert "Choose the style" in prompts.image_brief("hexagram 29", "Athena's choice")


def test_persona_is_generic_unless_configured(monkeypatch):
    monkeypatch.setattr(config, "USER_NAME", "")
    monkeypatch.setattr(config, "USER_PLACE", "")
    assert "You talk with" not in prompts.persona()
    assert prompts.greeting().startswith("The lattice is quiet")
    monkeypatch.setattr(config, "USER_NAME", "Sam")
    monkeypatch.setattr(config, "USER_PLACE", "Lisbon")
    assert "You talk with Sam, who lives in Lisbon." in prompts.persona()
    assert prompts.greeting().startswith("Sam... the lattice is quiet")


def test_env_file_is_read_but_real_environment_wins(tmp_path, monkeypatch):
    monkeypatch.delenv("ATHENA_TEST_A", raising=False)
    monkeypatch.setenv("ATHENA_TEST_B", "from-env")
    env = tmp_path / ".env"
    env.write_text('# comment\nATHENA_TEST_A="from file"\nATHENA_TEST_B=from-file\nnot a setting\n')
    config._load_env_file(env)
    import os
    assert os.environ["ATHENA_TEST_A"] == "from file" and os.environ["ATHENA_TEST_B"] == "from-env"
    monkeypatch.delenv("ATHENA_TEST_A")
