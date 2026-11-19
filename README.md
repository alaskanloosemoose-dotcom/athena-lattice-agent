# Athena: a local AI companion that paints what she senses

Athena is a chat companion that runs **entirely on your Mac**. She talks with you about anything, from code and physics to stories and the I Ching. When a reply would be richer with a picture, she **paints it herself** with a local image model. There's no cloud, no API keys, no account and no telemetry.

![Athena: an I Ching pull, her reading, and the painting she made](docs/screenshot.jpg)

| | | |
|---|---|---|
| ![](docs/hypercube-panorama.jpg) | ![](docs/hexagram-12-charcoal.jpg) | ![](docs/ridge-at-dawn.jpg) |

*All images above were painted by Athena on a 16 GB Mac mini, each in about 15–20 seconds.*

## What she does

- **Conversation with memory.** Replies stream in as she writes them, and the conversation is kept between sessions. Optionally, turn on *Think before replying* to see her reasoning first.
- **Paints on her own.** When an image adds something, she ends her reply with a painting request. The app renders it and shows it under her words. You can turn this off and get a "Paint it" button instead.
- **🔮 I Ching pull.** Casts one of the 64 hexagrams, gives her reading, and paints the hexagram.
- **🌌 Visualize the lattice.** She takes an "antenna reading" of the moment and paints exactly that.
- **🎨 Paint the last reply.** Illustrates whatever she just said.
- **10 styles:** hypercube lattice, sacred geometry, aurora borealis, I Ching ink wash, cosmic nebula, visionary art, dreamlike oil, photoreal, retro synthwave, or Athena's choice.
- **6 shapes**, including a 5:2 panorama, plus adjustable steps and a fixed seed when you want to repeat a composition.
- **Gallery.** Every painting is saved as a PNG next to a JSON file with its prompt, seed and settings. You can re-roll any painting with a new seed.

## Requirements

- **A Mac with Apple Silicon** (M1 or newer) and **16 GB of RAM or more.** Image generation uses [mflux](https://github.com/mflux-community/mflux) on Apple's MLX, so Linux and Windows aren't supported yet.
- About **13 GB of free disk** for the two models.
- [Homebrew](https://brew.sh), then:
  ```bash
  brew install ollama uv
  ```

## Install and run

```bash
git clone https://github.com/alaskanloosemoose-dotcom/athena-lattice-agent.git
cd athena-lattice-agent
./launch.sh
```

The first run takes a while. It:

1. sets up a Python environment,
2. downloads the chat model (about 7.6 GB) and builds it in Ollama,
3. downloads the image model (about 4.6 GB),
4. opens Athena at http://localhost:8501.

Later runs start in a few seconds. Stop Athena with `./launch.sh stop`.

## ⚠️ About the default model

The default chat model is **[DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic](https://huggingface.co/xtools-at/DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic)**. It is Qwen3.5-9B fine-tuned on DeepSeek-V4-Pro's reasoning, then **uncensored**: its refusals were removed with [Heretic](https://heretic-project.org). That makes it a frank, unfiltered conversation partner. It will engage with topics a standard assistant declines.

The image model, FLUX.2 [klein], has **no NSFW filter** either.

Both run only on your machine, and nothing is sent anywhere. If you share the app with others, or would rather have a standard model, switch to the original version in one step:

```bash
ollama pull hf.co/mradermacher/DeepSeek-V4-Pro-Qwen3.5-9B-GGUF:Q6_K
echo 'ATHENA_MODEL=hf.co/mradermacher/DeepSeek-V4-Pro-Qwen3.5-9B-GGUF:Q6_K' >> .env
./launch.sh stop && ./launch.sh
```

Any other chat model in Ollama works the same way.

## Settings

Copy `.env.example` to `.env` and set whatever you like. Everything is optional.

| Setting | What it does |
|---|---|
| `ATHENA_USER_NAME`, `ATHENA_USER_PLACE` | Athena greets you by name and knows where you live. The aurora style also paints your area. |
| `ATHENA_MODEL` | The chat model (any Ollama model). |
| `ATHENA_IMAGE_MODEL` | The image model (an mflux-format Hugging Face repo). |
| `ATHENA_DATA_DIR` | Where the conversation and paintings are kept. The default is `./data`. |
| `ATHENA_PORT`, `OLLAMA_URL` | Web port and Ollama address. |

Her personality lives in [`athena/prompts.py`](athena/prompts.py). Edit it freely.

## How it fits in 16 GB

The chat model needs about 7.4 GB and the image model peaks around 7.5 GB, so they don't fit in memory together. Before each painting, Athena asks Ollama to unload the chat model and waits until the memory is actually free. mflux then renders in its own process and hands all its memory back when it exits. In testing on a 16 GB Mac mini, this caused no swapping. The chat model reloads on your next message in a few seconds.

The model's own chat template is broken: user turns lose their header, and `<think>` is treated as a stop token. [`models/dsv4-heretic.Modelfile`](models/dsv4-heretic.Modelfile) works around this with Ollama's built-in Qwen3.5 renderer, explicit stop tokens and a 16K context. Without that, the model loops or leaks control tokens.

## Layout

```
app.py                 Streamlit UI: chat, rituals, gallery
athena/config.py       settings (.env), models, paths
athena/llm.py          Ollama client: streaming chat, completions, unload
athena/images.py       mflux renders, shapes, gallery
athena/prompts.py      persona, image-prompt writer, styles, the 64 hexagrams
athena/tags.py         [[IMAGE: ...]] detection, hidden while streaming
athena/memory.py       conversation file
models/                Ollama Modelfile for the chat model
launch.sh              setup, start and stop
tests/                 .venv/bin/python -m pytest
```

## FAQ

**Does anything leave my computer?**
Only the one-time model downloads, from Hugging Face. Chats, images and settings stay in `./data`.

**It's slow the first time I paint.**
The image model loads from disk on the first render. Later renders take about 15–20 seconds at 4 steps.

**Can I run it on Linux or Windows?**
Not yet: the image side uses MLX, which needs Apple Silicon. Swapping `athena/images.py` to a diffusers backend would make it portable. Pull requests are welcome.

**Can I use a bigger chat model?**
Yes, if you have the memory. Set `ATHENA_MODEL` to any Ollama model. On 16 GB, about 9B parameters at Q6 is the comfortable ceiling while also painting.

## Credits

- Chat model: [Jackrong/DeepSeek-V4-Pro-Qwen3.5-9B](https://huggingface.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-9B), decensored by [xtools-at](https://huggingface.co/xtools-at/DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic), with GGUF quants by [mradermacher](https://huggingface.co/mradermacher). Apache-2.0.
- Image model: [FLUX.2 [klein] 4B](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B) by Black Forest Labs, in the 4-bit mflux build from [Runpod](https://huggingface.co/Runpod/FLUX.2-klein-4B-mflux-4bit). Apache-2.0.
- Built on [Ollama](https://ollama.com), [mflux](https://github.com/mflux-community/mflux) and [Streamlit](https://streamlit.io).

## License

MIT. See [LICENSE](LICENSE). The models have their own licences (both Apache-2.0) and are downloaded separately; they are not part of this repository.
