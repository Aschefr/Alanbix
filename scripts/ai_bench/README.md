# Thinking bench

Measures every AI task of Alanbix with the model's thinking on and off, on the invented demo data.
It answers one question: where can `think: false` be sent without losing quality?

Other apps sharing the same AI server measured it first: thinking off broke their chats with tools
(gemma4:e4b stopped calling tools and invented figures) but was fine, and about 3 times faster, for tasks without tools.

## What it measures

| Task | Tools | Checked automatically |
|---|---|---|
| `chat`: private assistant, as PixelHunter, 9 questions | yes | right fact, a tool used, French, no leaked reasoning; one trap question (a tournament that does not exist) must not get a score |
| `public`: @Alanbix in the public chat, 4 questions | yes | right fact, French |
| `compress`: compact and summary of a seeded conversation | no | every key fact kept (the bold words of the conversation) |
| `translate`: 6 interface strings, French to English and Spanish | no | placeholders kept, target language, one clean line |
| `notify`: closing messages of a 4-player tournament (JSON) | no | a message for each player, French |

Expected answers are read from the demo data before each pass. Every answer is saved, for a reading by hand.
The checks are simple word matches: a FAIL is a reason to read the answer, not a verdict.

## Run it

The thinking switch is a hidden setting for now (`think_chat` for the two chats, `think_tasks` for the rest,
both on by default, so nothing changes for existing installs). The demo server must run an image built from this branch.

```bash
docker build -f Dockerfile.standalone -t alanbix:thinkbench .
python scripts/docs_demo/run.py fr alanbix:thinkbench
python scripts/ai_bench/think_bench.py --dry-run --passes 1
python scripts/ai_bench/think_bench.py --ollama http://SERVER:11434 --models gemma4:e4b bonsai-2:27b qwen3.8:27b
```

`--dry-run` checks the bench itself against the demo's fake Ollama (every answer fails, that is expected).
Options: `--passes` (2), `--modes off,on`, `--tasks chat,public,compress,translate,notify`, `--wait` (minutes).

## On a shared AI server

- Ask whoever owns the server first: a bench run keeps the GPU busy for a long time.
- One model at a time: before each model and each mode, the bench waits while another model is loaded
  (up to `--wait` minutes, then stops), and it unloads each model once measured.
- Knowledge search is turned off during the bench, so no embedding model is loaded next to the chat model.
- The demo server's settings are put back at the end, even after an error.

Results go to `scripts/ai_bench/results/<date>/` (ignored by git): one JSONL file per model and mode, and `summary.md`.
