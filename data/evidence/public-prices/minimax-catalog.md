> ## Documentation Index
> Fetch the complete documentation index at: https://platform.minimax.io/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# Model List

> View the models currently available on the MiniMax API platform and those that have been retired.

For model pricing, see the [Pricing Overview](https://platform.minimax.io/docs/pricing/overview.md).

> [accordion] MiniMax M2.5 and M2.7 Model Retirement Notice
>
> As we roll out newer models, we’ll be retiring the MiniMax M2.5 and M2.7 model families. To give existing users time to migrate, we’ll follow this schedule:
>
> * **October 19, 2026:** These models will no longer be available to new users.
> * **November 18, 2026:** These models will be retired.
>
> **Pay-as-you-go API users**
>
> Existing users can continue accessing these models until their retirement on November 18, 2026. Once retired, API requests to these models will no longer work. Please review your usage of these models and complete your migration before the retirement date.
>
> **M Plan and Token Plan users**
>
> Starting October 19, 2026, all requests to M2.5 and M2.7 models under these plans will automatically be routed to **M3.1 Flash**.
>
> Existing model names will continue to work for backward compatibility, so you won’t need to update the model names in your requests. Your plan’s usage allowances will remain unchanged.
>
> To avoid service disruptions, **please check whether your applications rely on these models and start planning your migration now.**
>
> Thank you for your continued support and trust in MiniMax.

## Available Models

### LLM

| Model | Description |
| :- | :- |
| [MiniMax-M3.1-Flash](https://platform.minimax.io/docs/guides/text-generation.md) | Frontier multimodal coding model with a 1M context window and tunable thinking depth. |
| [MiniMax-M3](https://platform.minimax.io/docs/guides/text-generation.md) | Frontier multimodal coding model with a 1M context window. |

### Video Models

| Model | Description |
| :- | :- |
| [MiniMax-H3](https://platform.minimax.io/docs/guides/video-generation.md) | Next-generation open, general-purpose multimodal video model supporting text-to-video, image-to-video, first-and-last-frame generation, and multimodal references. Supports 768P / 2K output and videos from 4 to 15 seconds. |
| [MiniMax-Hailuo-2.3](https://platform.minimax.io/docs/guides/video-generation.md) | Text-to-video and image-to-video generation with state-of-the-art instruction following and extreme physics mastery. |
| [MiniMax-Hailuo-2.3-Fast](https://platform.minimax.io/docs/guides/video-generation.md) | Image-to-video generation with extreme physics mastery and a focus on value and efficiency. |
| [MiniMax-Hailuo-02](https://platform.minimax.io/docs/guides/video-generation.md) | Text-to-video and image-to-video generation with state-of-the-art instruction following and extreme physics mastery. |

### Image Models

| Model | Description |
| :- | :- |
| [MiniMax-H3-Image](https://platform.minimax.io/docs/guides/image-generation.md) | Image generation model supporting text-to-image and image editing (1–16 reference images). Output dimensions can be specified by width and height, or by area tier and aspect ratio. Supports streaming output. |
| [image-01](https://platform.minimax.io/docs/guides/image-generation.md) | Supports text-to-image and image-to-image generation. |
| [image-01-live](https://platform.minimax.io/docs/guides/image-generation.md) | Generates images from a text prompt and a reference image. |

### Speech Models

| Model | Description |
| :- | :- |
| [speech-2.8-hd](https://platform.minimax.io/docs/guides/speech-t2a-websocket.md) | Ultra-realistic quality featuring sound tags. |
| [speech-2.8-turbo](https://platform.minimax.io/docs/guides/speech-t2a-websocket.md) | Seamless speed meets natural flow. |
| [speech-2.6-hd](https://platform.minimax.io/docs/guides/speech-t2a-websocket.md) | Ultimate similarity and ultra-high quality. |
| [speech-2.6-turbo](https://platform.minimax.io/docs/guides/speech-t2a-websocket.md) | Ultimate value and low latency. |
| [speech-02-hd](https://platform.minimax.io/docs/guides/speech-t2a-websocket.md) | Stronger replication similarity and high-quality voice generation. |
| [speech-02-turbo](https://platform.minimax.io/docs/guides/speech-t2a-websocket.md) | Superior rhythm and stability with low latency. |

## Retired Models

The following models have been retired and are no longer available.

| Model | Type | Status |
| :- | :- | :- |
| MiniMax-M2.7 | LLM | Retired |
| MiniMax-M2.7-highspeed | LLM | Retired |
| MiniMax-M2.5 | LLM | Retired |
| MiniMax-M2.5-highspeed | LLM | Retired |
| MiniMax-M2.1 | LLM | Retired |
| MiniMax-M2.1-highspeed | LLM | Retired |
| MiniMax-M2 | LLM | Retired |
| M2-her | LLM | Retired |
| music-3.0 | Music | Retired |
| music-2.6 | Music | Retired |
| music-cover | Music | Retired |
| music-3.0-free | Music | Retired |
| music-2.6-free | Music | Retired |
| music-cover-free | Music | Retired |
| Music-2.5+ | Music | Retired |
| Music-2.5 | Music | Retired |
| Music-2.0 | Music | Retired |

> [accordion] Music Generation Guide
>
> As of August 20, 2026, the music generation and lyrics generation APIs are no longer available to new users. Existing paying users can continue using these APIs. To generate music, visit [MiniMax Audio](https://www.minimax.io/audio) or try the open-source MiniMax Music 3 model on [Hugging Face](https://huggingface.co/MiniMaxAI/MiniMax-Music3) or [ModelScope](https://modelscope.cn/models/MiniMax/MiniMax-Music3).
>
> Existing paying users can refer to:
>
> * [Music Generation guide](https://platform.minimax.io/docs/guides/music-generation): set style with `prompt`, provide lyrics with `lyrics`, and the one-step / two-step cover workflows
> * [Music Generation API](https://platform.minimax.io/docs/api-reference/music-generation): `POST /v1/music_generation`, generate a song from lyrics and a description
> * [Music Cover Preprocess API](https://platform.minimax.io/docs/api-reference/music-cover-preprocess): `POST /v1/music_cover_preprocess`, extract features and lyrics from reference audio for two-step covers
> * [Lyrics Generation API](https://platform.minimax.io/docs/api-reference/lyrics-generation): `POST /v1/lyrics_generation`, write full lyrics or edit and continue existing lyrics
