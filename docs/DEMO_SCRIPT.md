# Demo video script (target: 30 seconds)

The launch tweet/HN post die without a demo video. This is the script.

## Setup (do once before recording)

1. Fresh Claude Code session, fresh terminal.
2. `prime-intellect-mcp` already configured in `claude_desktop_config.json` with a real `PRIME_API_KEY` and conservative caps (`PRIME_MAX_HOURLY_USD=2`, `PRIME_MAX_TOTAL_USD=4`).
3. SSH key already configured (`prime config set-ssh-key-path`).
4. Wallet pre-loaded with at least $5 of credit.
5. Record at 1080p+ with system audio off (we'll add captions over the video, no narration).

## Take

| Time | Frame | Caption (overlay) |
|---|---|---|
| 0:00 | Claude Code prompt: *"Rent the cheapest GPU you can find for 30 minutes, run `nvidia-smi`, then terminate it. Spend cap: $1."* | "Asking Claude to rent a GPU." |
| 0:03 | Claude calls `list_gpu_types` → `list_availability` → `pod_quote`. Quote shows hourly rate. | "Two-step gate: quote first." |
| 0:08 | Claude calls `pod_create(confirm=True)`. Pod ID returned. | "confirm=True provisions." |
| 0:12 | `pod_status(wait_for_ssh=True)` polls for ~10 seconds. SSH string appears. | "Pod ready, SSH info handed back." |
| 0:18 | Claude's `Bash` tool: `ssh ... "nvidia-smi"`. Output of `nvidia-smi` shows the GPU. | "Agent uses its own Bash to drive the pod." |
| 0:24 | `pod_terminate(confirm=True)`. | "Termination is also confirm-gated." |
| 0:28 | Final frame: "Total spend: $0.34". | "Total: $0.34." |

## Recording the video

- macOS: QuickTime or `screencapture -V <duration>` for screen+audio. We don't need audio.
- Crop to a 16:9 frame around the Claude Code panel. Avoid showing the API key (paranoia: blur or pre-set the env in the harness).
- Export as MP4 at ≤ 5MB if going on Twitter, ≤ 10MB for HN/LinkedIn. GIFs are fine for the README.

## After recording

- Convert to GIF for the README hero: `ffmpeg -i demo.mp4 -vf "fps=15,scale=900:-1:flags=lanczos" -loop 0 demo.gif`
- Upload to YouTube unlisted as the high-quality permalink. Use that URL on the launch tweet/HN.
- Embed the GIF in `README.md` (replace the placeholder line at the top).

## What can go wrong on the take

- Provisioning sometimes takes 60–90s. Don't speed up the video — just edit out the dead time (or let it sit, agent waiting is part of the story).
- Wallet balance flashing on screen. Either pre-zero it visually or re-record.
- Stock might be empty for the cheapest GPU. Pre-check `prime availability list --gpu-type T4` before recording.
