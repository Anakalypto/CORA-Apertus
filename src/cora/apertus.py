"""Minimal OpenAI-compatible client for Apertus v1.5 (Keera Gateway -> CSCS)."""
import json
import re
import time
import urllib.error
import urllib.request


class Apertus:
    def __init__(self, base_url: str, api_key: str, model: str, temperature: float = 0.1,
                 max_tokens: int = 2500, retries: int = 3):
        if not api_key:
            raise SystemExit("LLM_API_KEY is not set (see .env.example)")
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.key, self.model = api_key, model
        self.temperature, self.max_tokens, self.retries = temperature, max_tokens, retries

    def chat(self, messages: list[dict], json_mode: bool = True, model: str | None = None) -> dict:
        body = {"model": model or self.model, "messages": messages,
                "temperature": self.temperature, "max_tokens": self.max_tokens}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(), headers={
            "Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
        for attempt in range(self.retries + 1):
            try:
                t0 = time.time()
                with urllib.request.urlopen(req, timeout=300) as r:
                    res = json.load(r)
                return {"content": res["choices"][0]["message"]["content"],
                        "usage": res.get("usage", {}), "seconds": round(time.time() - t0, 2),
                        "model": res.get("model", body["model"]),
                        "finish_reason": res["choices"][0].get("finish_reason")}
            except (urllib.error.URLError, TimeoutError, KeyError) as e:
                if attempt == self.retries:
                    raise
                time.sleep(2 ** attempt * 3)
        raise RuntimeError("unreachable")

    def chat_json(self, messages: list[dict], model: str | None = None) -> tuple[dict, dict]:
        """Ask for JSON; on a parse failure, feed the error back once per retry."""
        meta = {"attempts": 0, "usage": [], "seconds": 0.0}
        msgs = list(messages)
        for _ in range(self.retries):
            meta["attempts"] += 1
            res = self.chat(msgs, model=model)
            meta["usage"].append(res["usage"])
            meta["seconds"] += res["seconds"]
            meta["model"] = res["model"]
            try:
                return parse_json(res["content"]), meta
            except ValueError as e:
                msgs = messages + [{"role": "assistant", "content": res["content"]},
                                   {"role": "user", "content": f"That was not valid JSON ({e}). Reply with the corrected JSON object only."}]
        raise ValueError("no valid JSON after retries")


def parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError as e:
                raise ValueError(str(e))
        raise ValueError("no JSON object found")
