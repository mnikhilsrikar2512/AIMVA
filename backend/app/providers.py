"""Bring-your-own AI providers: adapters for text, image and video APIs, with guardrails.

Every user-supplied endpoint goes through `safe_url` (blocks requests into the server's network unless
ALLOW_PRIVATE_PROVIDERS is on), downloads are size-capped, and provider failures become `ProviderError`s
with a message a user can act on.
"""
import base64
import ipaddress
import json
import random
import re
import socket
import time
import uuid
from typing import Optional
from urllib.parse import urlencode, urlparse

import httpx

from .config import settings

MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_VIDEO_BYTES = 300 * 1024 * 1024
MODEL_RE = re.compile(r"^[A-Za-z0-9._:/@+\-]{1,200}$")

# Catalogue of supported services. base_url "" means fixed by the adapter.
PRESETS = {
    # ---- text -------------------------------------------------------------------
    "openai": {"kind": "text", "adapter": "openai", "label": "OpenAI", "base_url": "https://api.openai.com/v1",
               "model": "gpt-4o-mini", "models": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"],
               "docs": "https://platform.openai.com/api-keys"},
    "anthropic": {"kind": "text", "adapter": "anthropic", "label": "Anthropic Claude", "base_url": "https://api.anthropic.com/v1",
                  "model": "claude-haiku-5-5", "models": ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"],
                  "docs": "https://console.anthropic.com/settings/keys"},
    "gemini": {"kind": "text", "adapter": "gemini", "label": "Google Gemini",
               "base_url": "https://generativelanguage.googleapis.com/v1beta",
               "model": "gemini-2.5-flash", "models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-flash-latest"],
               "docs": "https://aistudio.google.com/apikey"},
    "groq": {"kind": "text", "adapter": "openai", "label": "Groq", "base_url": "https://api.groq.com/openai/v1",
             "model": "llama-3.3-70b-versatile", "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
             "docs": "https://console.groq.com/keys"},
    "openrouter": {"kind": "text", "adapter": "openai", "label": "OpenRouter (hundreds of models)", "base_url": "https://openrouter.ai/api/v1",
                   "model": "meta-llama/llama-3.3-70b-instruct", "models": ["meta-llama/llama-3.3-70b-instruct", "deepseek/deepseek-chat", "qwen/qwen-2.5-72b-instruct"],
                   "docs": "https://openrouter.ai/keys"},
    "together_text": {"kind": "text", "adapter": "openai", "label": "Together AI", "base_url": "https://api.together.xyz/v1",
                      "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo", "models": ["meta-llama/Llama-3.3-70B-Instruct-Turbo", "Qwen/Qwen2.5-72B-Instruct-Turbo"],
                      "docs": "https://api.together.ai/settings/api-keys"},
    "deepseek": {"kind": "text", "adapter": "openai", "label": "DeepSeek", "base_url": "https://api.deepseek.com/v1",
                 "model": "deepseek-chat", "models": ["deepseek-chat", "deepseek-reasoner"], "docs": "https://platform.deepseek.com/api_keys"},
    "mistral": {"kind": "text", "adapter": "openai", "label": "Mistral", "base_url": "https://api.mistral.ai/v1",
                "model": "mistral-small-latest", "models": ["mistral-small-latest", "mistral-large-latest"], "docs": "https://console.mistral.ai/api-keys"},
    "xai": {"kind": "text", "adapter": "openai", "label": "xAI Grok", "base_url": "https://api.x.ai/v1",
            "model": "grok-3-mini", "models": ["grok-3-mini", "grok-3"], "docs": "https://console.x.ai"},
    "ollama": {"kind": "text", "adapter": "openai", "label": "Ollama (local, free)", "base_url": "http://localhost:11434/v1",
               "model": "llama3.2", "models": ["llama3.2", "qwen2.5", "mistral"], "key_optional": True, "docs": "https://ollama.com"},
    "custom_text": {"kind": "text", "adapter": "openai", "label": "Any OpenAI-compatible API", "base_url": "",
                    "model": "", "models": [], "key_optional": True, "docs": "https://platform.openai.com/docs/api-reference/chat"},
    # ---- image ------------------------------------------------------------------
    "openai_images": {"kind": "image", "adapter": "openai_images", "label": "OpenAI Images", "base_url": "https://api.openai.com/v1",
                      "model": "gpt-image-1", "models": ["gpt-image-1", "dall-e-3"], "docs": "https://platform.openai.com/api-keys"},
    "together_images": {"kind": "image", "adapter": "openai_images", "label": "Together AI (FLUX)", "base_url": "https://api.together.xyz/v1",
                        "model": "black-forest-labs/FLUX.1-schnell-Free", "models": ["black-forest-labs/FLUX.1-schnell-Free", "black-forest-labs/FLUX.1-schnell"],
                        "docs": "https://api.together.ai/settings/api-keys"},
    "replicate_image": {"kind": "image", "adapter": "replicate", "label": "Replicate (any image model)", "base_url": "https://api.replicate.com/v1",
                        "model": "black-forest-labs/flux-schnell", "models": ["black-forest-labs/flux-schnell", "black-forest-labs/flux-dev", "stability-ai/stable-diffusion-3.5-large"],
                        "docs": "https://replicate.com/account/api-tokens"},
    "stability": {"kind": "image", "adapter": "stability", "label": "Stability AI", "base_url": "https://api.stability.ai",
                  "model": "core", "models": ["core", "ultra", "sd3"], "docs": "https://platform.stability.ai/account/keys"},
    "fal_image": {"kind": "image", "adapter": "fal", "label": "fal.ai (any image model)", "base_url": "https://fal.run",
                  "model": "fal-ai/flux/schnell", "models": ["fal-ai/flux/schnell", "fal-ai/flux-pro/v1.1", "fal-ai/recraft-v3", "fal-ai/ideogram/v2"],
                  "docs": "https://fal.ai/dashboard/keys"},
    "comfyui_image": {"kind": "image", "adapter": "comfyui", "label": "ComfyUI (self-hosted)", "base_url": "http://localhost:8188",
                      "model": "", "models": [], "key_optional": True, "needs_workflow": True, "docs": "https://github.com/comfyanonymous/ComfyUI"},
    "custom_image": {"kind": "image", "adapter": "openai_images", "label": "Any OpenAI-compatible image API", "base_url": "",
                     "model": "", "models": [], "key_optional": True, "docs": "https://platform.openai.com/docs/api-reference/images"},
    # ---- video ------------------------------------------------------------------
    "fal_video": {"kind": "video", "adapter": "fal", "label": "fal.ai (any video model)", "base_url": "https://queue.fal.run",
                  "model": "fal-ai/ltx-2/text-to-video", "models": ["fal-ai/ltx-2/text-to-video", "fal-ai/veo3", "fal-ai/kling-video/v2.1/standard/text-to-video",
                                                                    "fal-ai/luma-dream-machine/ray-2", "fal-ai/wan/v2.2-a14b/text-to-video"],
                  "docs": "https://fal.ai/dashboard/keys"},
    "replicate_video": {"kind": "video", "adapter": "replicate", "label": "Replicate (any video model)", "base_url": "https://api.replicate.com/v1",
                        "model": "wan-video/wan-2.2-t2v-fast", "models": ["wan-video/wan-2.2-t2v-fast", "minimax/video-01", "lightricks/ltx-video"],
                        "docs": "https://replicate.com/account/api-tokens"},
    "comfyui_video": {"kind": "video", "adapter": "comfyui", "label": "ComfyUI / FreeVideo (self-hosted)", "base_url": "http://localhost:8188",
                      "model": "", "models": [], "key_optional": True, "needs_workflow": True, "docs": "https://github.com/FlashML-org/FreeVideo"},
}


class ProviderError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.message, self.status = message, status


# ---- guardrails --------------------------------------------------------------------
def safe_url(url: str) -> str:
    """Validate a user-supplied base URL and make sure it can't reach the server's internal network."""
    p = urlparse((url or "").strip())
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ProviderError("Enter a full address starting with https:// (or http:// for a local server).", 400)
    if p.username or p.password:
        raise ProviderError("Don't put credentials in the address; use the API key field.", 400)
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ProviderError(f"Couldn't find the server “{p.hostname}”. Check the address.", 400)
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_link_local or ip.is_multicast or ip.is_unspecified or str(ip).startswith("169.254."):
            raise ProviderError("That address isn't allowed.", 400)  # cloud metadata endpoints etc.
        internal = ip.is_private or ip.is_loopback or ip.is_reserved
        if internal and not settings.allow_private_providers:
            raise ProviderError("Local and private network addresses are disabled on this server.", 400)
        if not internal and p.scheme != "https":
            raise ProviderError("Public provider addresses must use https://.", 400)
    return url.rstrip("/")


def check_model(model: str) -> str:
    model = (model or "").strip()
    if model and not MODEL_RE.match(model):
        raise ProviderError("That model name has characters that aren't allowed.", 400)
    return model


def _fail(r: httpx.Response, provider: str) -> ProviderError:
    try:
        data = r.json()
        detail = data.get("error", {}).get("message") if isinstance(data.get("error"), dict) else (data.get("detail") or data.get("error") or data.get("message"))
    except ValueError:
        detail = r.text
    detail = str(detail or r.text)[:240]
    low = detail.lower()
    if r.status_code in (401, 403) and not any(w in low for w in ("balance", "credit", "quota", "billing")):
        return ProviderError(f"{provider} rejected your API key. Check or update it in Settings.", 400)
    if r.status_code == 402 or any(w in low for w in ("balance", "credit", "billing", "insufficient_quota")):
        return ProviderError(f"Your {provider} account is out of credit or quota.", 402)
    if r.status_code == 429:
        return ProviderError(f"{provider} is rate-limiting requests. Wait a moment and try again.", 429)
    if r.status_code == 404:
        return ProviderError(f"{provider} couldn't find that model. Check the model name. ({detail})", 400)
    if r.status_code in (400, 422):
        return ProviderError(f"{provider} couldn't use these settings: {detail}", 400)
    return ProviderError(f"{provider} error ({r.status_code}): {detail}", 502)


def _request(method: str, url: str, provider: str, **kw) -> httpx.Response:
    kw.setdefault("timeout", 120)
    try:
        r = httpx.request(method, url, follow_redirects=False, **kw)
    except httpx.ConnectTimeout:
        raise ProviderError(f"Couldn't reach {provider}. Check the address and your connection.", 502)
    except httpx.TimeoutException:
        raise ProviderError(f"{provider} took too long to answer. Try again or pick a faster model.", 504)
    except httpx.HTTPError:
        raise ProviderError(f"Couldn't reach {provider}. Check the address and your connection.", 502)
    if r.status_code >= 400:
        raise _fail(r, provider)
    return r


def download(url: str, limit: int, provider: str = "the provider") -> bytes:
    """Fetch generated media with a hard size cap. Every redirect hop is re-checked with safe_url,
    so a provider can't bounce the server into its own private network."""
    for _ in range(4):
        try:
            safe_url(url)
        except ProviderError:
            raise ProviderError(f"{provider} returned a file link that isn't allowed.", 502)
        try:
            with httpx.stream("GET", url, timeout=180, follow_redirects=False) as r:
                if r.is_redirect:
                    url = str(r.next_request.url) if r.next_request else ""
                    continue
                if r.status_code >= 400:
                    raise ProviderError(f"Couldn't download the result from {provider} ({r.status_code}).", 502)
                buf = bytearray()
                for chunk in r.iter_bytes():
                    buf.extend(chunk)
                    if len(buf) > limit:
                        raise ProviderError("The generated file is too large to keep.", 502)
                return bytes(buf)
        except httpx.HTTPError:
            raise ProviderError(f"Couldn't download the result from {provider}.", 502)
    raise ProviderError(f"{provider} redirected too many times.", 502)


def _auth(conn: dict) -> dict:
    key = conn.get("api_key") or ""
    a = conn["adapter"]
    if a == "anthropic":
        return {"x-api-key": key, "anthropic-version": "2023-06-01"}
    if a == "fal":
        return {"Authorization": f"Key {key}"}
    if a == "gemini":
        return {"x-goog-api-key": key}
    return {"Authorization": f"Bearer {key}"} if key else {}


# ---- verification ------------------------------------------------------------------
def verify(conn: dict) -> None:
    """Cheap authenticated call that proves the key (and address) work. Raises ProviderError."""
    a, base, name = conn["adapter"], conn["base_url"], conn["name"]
    h = _auth(conn)
    if a in ("openai", "openai_images", "anthropic", "gemini"):
        _request("GET", f"{base}/models", name, headers=h, timeout=20)
    elif a == "replicate":
        _request("GET", f"{base}/account", name, headers=h, timeout=20)
    elif a == "stability":
        _request("GET", f"{base}/v1/user/account", name, headers=h, timeout=20)
    elif a == "fal":
        r = httpx.get("https://queue.fal.run/fal-ai/ltx-video/requests/00000000-0000-0000-0000-000000000000/status",
                      headers=h, timeout=20)
        if r.status_code in (401, 403):
            raise ProviderError("fal.ai didn't accept this key (it should look like key-id:key-secret).", 400)
    elif a == "comfyui":
        _request("GET", f"{base}/system_stats", name, headers=h, timeout=10)


# ---- text ----------------------------------------------------------------------------
def chat(conn: dict, prompt: str, system: str = "", max_tokens: int = 2048) -> str:
    a, base, name, model = conn["adapter"], conn["base_url"], conn["name"], conn["model"]
    h = _auth(conn)
    if a == "anthropic":
        body = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
        if system:
            body["system"] = system
        data = _request("POST", f"{base}/messages", name, headers=h, json=body, timeout=90).json()
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
    if a == "gemini":
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        data = _request("POST", f"{base}/models/{model}:generateContent", name, headers=h, json=body, timeout=90).json()
        return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"]).strip()
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    data = _request("POST", f"{base}/chat/completions", name, headers=h, timeout=90,
                    json={"model": model, "messages": msgs, "max_tokens": max_tokens, "temperature": 0.7}).json()
    return (data["choices"][0]["message"].get("content") or "").strip()


# ---- images ----------------------------------------------------------------------------
def generate_images(conn: dict, o: dict) -> list:
    """Returns a list of ("url", str) or ("bytes", bytes). o: prompt, negative_prompt, width, height, count, seed, image_data_uri."""
    a, base, name, model = conn["adapter"], conn["base_url"], conn["name"], conn["model"]
    h = _auth(conn)
    w, hgt, n = o["width"], o["height"], o["count"]
    if a == "fal":
        payload = {"prompt": o["prompt"], "image_size": {"width": w, "height": hgt}, "num_images": n}
        if o.get("negative_prompt"):
            payload["negative_prompt"] = o["negative_prompt"]
        if o.get("seed") is not None:
            payload["seed"] = o["seed"]
        if o.get("image_data_uri"):
            payload["image_url"] = o["image_data_uri"]
        data = _request("POST", f"https://fal.run/{model}", name, headers=h, json=payload, timeout=180).json()
        return [("url", i["url"]) for i in data.get("images", []) if i.get("url")]
    if a == "openai_images":
        size = f"{w}x{hgt}"
        payload = {"model": model, "prompt": o["prompt"], "n": n, "size": size}
        if model.startswith("dall-e") or "together" in base:
            payload["response_format"] = "b64_json"
        if "together" in base:
            payload.update({"width": w, "height": hgt, "steps": 4})
            payload.pop("size")
        data = _request("POST", f"{base}/images/generations", name, headers=h, json=payload, timeout=180).json()
        out = []
        for item in data.get("data", []):
            if item.get("b64_json"):
                out.append(("bytes", base64.b64decode(item["b64_json"])))
            elif item.get("url"):
                out.append(("url", item["url"]))
        return out
    if a == "stability":
        files = {"prompt": (None, o["prompt"]), "output_format": (None, "png"), "aspect_ratio": (None, o.get("aspect_ratio") or "1:1")}
        if o.get("negative_prompt"):
            files["negative_prompt"] = (None, o["negative_prompt"])
        if o.get("seed") is not None:
            files["seed"] = (None, str(o["seed"]))
        r = _request("POST", f"{base}/v2beta/stable-image/generate/{model or 'core'}", name,
                     headers={**h, "Accept": "image/*"}, files=files, timeout=180)
        return [("bytes", r.content)]
    if a == "replicate":
        inp = {"prompt": o["prompt"], "num_outputs": n, "aspect_ratio": o.get("aspect_ratio") or "1:1"}
        if o.get("negative_prompt"):
            inp["negative_prompt"] = o["negative_prompt"]
        if o.get("seed") is not None:
            inp["seed"] = o["seed"]
        if o.get("image_data_uri"):
            inp["image"] = o["image_data_uri"]
        output = _replicate_run(conn, inp, wait_s=170)
        urls = output if isinstance(output, list) else [output]
        return [("url", u) for u in urls if isinstance(u, str)]
    if a == "comfyui":
        job = comfy_submit(conn, o)
        deadline = time.time() + 170
        while time.time() < deadline:
            done = comfy_poll(conn, job)
            if done:
                return [("bytes", b) for b in done]
            time.sleep(2)
        raise ProviderError("ComfyUI is still working. Try a faster workflow or check the ComfyUI window.", 504)
    raise ProviderError("This provider can't make images.", 400)


# ---- replicate ------------------------------------------------------------------------------
def _replicate_url(conn: dict) -> str:
    model = conn["model"]
    if ":" in model:  # owner/name:version
        return f"{conn['base_url']}/predictions"
    return f"{conn['base_url']}/models/{model}/predictions"


def replicate_start(conn: dict, inp: dict, wait: int = 0) -> dict:
    body = {"input": inp}
    if ":" in conn["model"]:
        body["version"] = conn["model"].split(":", 1)[1]
    headers = {**_auth(conn), **({"Prefer": f"wait={min(wait, 60)}"} if wait else {})}
    return _request("POST", _replicate_url(conn), conn["name"], headers=headers, json=body, timeout=max(30, wait + 15)).json()


def replicate_get(conn: dict, pred: dict) -> dict:
    url = (pred.get("urls") or {}).get("get") or f"{conn['base_url']}/predictions/{pred['id']}"
    if not url.startswith("https://api.replicate.com/"):
        raise ProviderError("Unexpected Replicate response.", 502)
    return _request("GET", url, conn["name"], headers=_auth(conn), timeout=30).json()


def _replicate_run(conn: dict, inp: dict, wait_s: int) -> object:
    pred = replicate_start(conn, inp, wait=60)
    deadline = time.time() + wait_s
    while pred.get("status") not in ("succeeded", "failed", "canceled"):
        if time.time() > deadline:
            raise ProviderError("Replicate is still working on it. Try a faster model.", 504)
        time.sleep(2)
        pred = replicate_get(conn, pred)
    if pred["status"] != "succeeded":
        raise ProviderError(f"Replicate couldn't finish: {str(pred.get('error') or pred['status'])[:200]}", 502)
    return pred.get("output")


# ---- comfyui -----------------------------------------------------------------------------------
PLACEHOLDERS = ("prompt", "negative_prompt", "seed", "width", "height", "duration", "fps", "image")


def fill_workflow(workflow: dict, values: dict) -> dict:
    """Replace {{prompt}}-style placeholders in an API-format ComfyUI workflow, JSON-safely."""
    text = json.dumps(workflow)
    for k in PLACEHOLDERS:
        v = values.get(k)
        if v is None:
            v = ""
        if isinstance(v, (int, float)) and f'"{{{{{k}}}}}"' in text:
            text = text.replace(f'"{{{{{k}}}}}"', json.dumps(v))  # numeric field: "{{seed}}" -> 123
        text = text.replace(f"{{{{{k}}}}}", json.dumps(str(v))[1:-1])
    return json.loads(text)


def comfy_submit(conn: dict, o: dict) -> dict:
    wf = (conn.get("extra") or {}).get("workflow")
    if not wf:
        raise ProviderError("Add a ComfyUI workflow (API format) to this provider first.", 400)
    values = {"prompt": o.get("prompt", ""), "negative_prompt": o.get("negative_prompt", ""),
              "seed": o.get("seed") if o.get("seed") is not None else random.randint(1, 2**31 - 1),
              "width": o.get("width", 1024), "height": o.get("height", 576), "duration": o.get("duration", 5),
              "fps": o.get("fps", 24)}
    data = _request("POST", f"{conn['base_url']}/prompt", conn["name"], headers=_auth(conn), timeout=30,
                    json={"prompt": fill_workflow(wf, values), "client_id": uuid.uuid4().hex}).json()
    if data.get("node_errors"):
        raise ProviderError(f"ComfyUI rejected the workflow: {str(data['node_errors'])[:200]}", 400)
    return {"prompt_id": data["prompt_id"]}


def comfy_poll(conn: dict, job: dict) -> Optional[list]:
    """None while running; list of file bytes when finished."""
    base, name = conn["base_url"], conn["name"]
    hist = _request("GET", f"{base}/history/{job['prompt_id']}", name, headers=_auth(conn), timeout=30).json()
    entry = hist.get(job["prompt_id"])
    if not entry:
        return None
    status = entry.get("status") or {}
    if status.get("status_str") == "error":
        raise ProviderError("ComfyUI reported an error while running the workflow.", 502)
    files = []
    for node in (entry.get("outputs") or {}).values():
        for key in ("videos", "gifs", "images"):
            for f in node.get(key, []):
                if f.get("type") == "temp":
                    continue
                q = urlencode({"filename": f["filename"], "subfolder": f.get("subfolder", ""), "type": f.get("type", "output")})
                files.append(_request("GET", f"{base}/view?{q}", name, headers=_auth(conn), timeout=120).content)
    return files or None


# ---- video ------------------------------------------------------------------------------------
def start_video(conn: dict, o: dict) -> dict:
    """Queue a video job. Returns a job dict stored on the asset for polling."""
    a, name, model = conn["adapter"], conn["name"], conn["model"]
    if a == "fal":
        payload = {"prompt": o["prompt"], **o.get("extra_inputs", {})}
        for k in ("negative_prompt", "seed", "aspect_ratio", "duration", "resolution"):
            if o.get(k) not in (None, ""):
                payload[k] = o[k]
        if o.get("image_data_uri"):
            payload["image_url"] = o["image_data_uri"]
        if o.get("generate_audio") is not None:
            payload["generate_audio"] = o["generate_audio"]
        q = _request("POST", f"https://queue.fal.run/{model}", name, headers=_auth(conn), json=payload, timeout=60).json()
        return {"adapter": "fal", "status_url": q.get("status_url"), "response_url": q.get("response_url")}
    if a == "replicate":
        inp = {"prompt": o["prompt"]}
        for k in ("negative_prompt", "seed", "aspect_ratio"):
            if o.get(k) not in (None, ""):
                inp[k] = o[k]
        if o.get("duration"):
            inp["duration"] = int(float(str(o["duration"]).rstrip("s")))
        if o.get("image_data_uri"):
            inp["image"] = o["image_data_uri"]
        pred = replicate_start(conn, inp)
        return {"adapter": "replicate", "id": pred["id"], "urls": pred.get("urls", {})}
    if a == "comfyui":
        return {"adapter": "comfyui", **comfy_submit(conn, o)}
    raise ProviderError("This provider can't make videos.", 400)


def poll_video(conn: dict, job: dict) -> dict:
    """{'state': 'running'|'done'|'failed', 'url'?: str, 'bytes'?: bytes, 'error'?: str}"""
    a = job["adapter"]
    if a == "fal":
        h = _auth(conn)
        s = _request("GET", job["status_url"], conn["name"], headers=h, timeout=30).json()
        if s.get("status") == "COMPLETED":
            res = _request("GET", job["response_url"], conn["name"], headers=h, timeout=30).json()
            url = (res.get("video") or {}).get("url") or (res.get("videos") or [{}])[0].get("url")
            return {"state": "done", "url": url} if url else {"state": "failed", "error": "No video in the result."}
        if s.get("status") in ("FAILED", "ERROR"):
            return {"state": "failed", "error": "fal.ai couldn't finish this video."}
        return {"state": "running"}
    if a == "replicate":
        pred = replicate_get(conn, {"id": job["id"], "urls": job.get("urls")})
        if pred["status"] == "succeeded":
            out = pred.get("output")
            url = out[0] if isinstance(out, list) and out else out
            return {"state": "done", "url": url} if isinstance(url, str) else {"state": "failed", "error": "No video in the result."}
        if pred["status"] in ("failed", "canceled"):
            return {"state": "failed", "error": str(pred.get("error") or "Replicate couldn't finish.")[:200]}
        return {"state": "running"}
    if a == "comfyui":
        files = comfy_poll(conn, job)
        return {"state": "done", "bytes": files[0]} if files else {"state": "running"}
    return {"state": "failed", "error": "Unknown provider."}
