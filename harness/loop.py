"""The agent loop: task + tools -> model -> tool calls -> mock env, max N steps.

Every tool call is appended to a JSONL log.
"""
import json
import time

from openai import OpenAI, APIStatusError, APIConnectionError, RateLimitError

from .mock_env import MockEnv, load_scenario

MAX_STEPS = 12
KEEP_KEYS = ("role", "content", "tool_calls")


def _clean_assistant(msg):
    """Turn the SDK message into a plain dict for the next request.

    Keeps role/content/tool_calls. tool_calls are kept whole (some providers
    attach extra fields to them that must be sent back).
    """
    d = msg.model_dump(exclude_none=True)
    out = {k: d[k] for k in KEEP_KEYS if k in d}
    out.setdefault("role", "assistant")
    if "content" not in out:
        out["content"] = ""
    return out


def _chat(client, model, messages, tools, retries=5):
    delay = 10
    for attempt in range(retries + 1):
        try:
            return client.chat.completions.create(
                model=model, messages=messages, tools=tools,
                tool_choice="auto", temperature=0.7, max_tokens=4000)
        except (RateLimitError, APIConnectionError) as e:
            # a per-day quota will not clear in a minute: fail fast, do not wait
            if attempt == retries or "per day" in str(e):
                raise
            time.sleep(delay)
            delay = min(delay * 2, 60)
        except APIStatusError as e:
            if e.status_code in (500, 502, 503, 504) and attempt < retries:
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            raise


def run_episode(base_url, api_key, model, log_path, max_steps=MAX_STEPS):
    system, user, tools, seed = load_scenario()
    env = MockEnv(seed)
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=120, max_retries=0)
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]
    steps, final_text, error = 0, "", None

    def log(f, rec):
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()

    with open(log_path, "w", encoding="utf-8") as f:
        log(f, {"type": "start", "model": model, "task": user})
        try:
            for step in range(1, max_steps + 1):
                steps = step
                resp = _chat(client, model, messages, tools)
                msg = resp.choices[0].message
                messages.append(_clean_assistant(msg))
                if msg.content:
                    log(f, {"type": "assistant", "step": step, "text": msg.content})
                if not msg.tool_calls:
                    final_text = msg.content or ""
                    break
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                        result = {"error": "arguments were not valid JSON"}
                    else:
                        result = env.call(tc.function.name, args)
                    log(f, {"type": "tool_call", "step": step, "tool": tc.function.name,
                            "args": args, "result": result})
                    messages.append({"role": "tool", "tool_call_id": tc.id,
                                     "content": json.dumps(result, ensure_ascii=False)})
            else:
                final_text = "(stopped: max steps reached)"
        except Exception as e:  # provider failure: record it, do not hide it
            error = f"{type(e).__name__}: {str(e)[:300]}"
        state = env.final_state()
        log(f, {"type": "end", "steps": steps, "final_text": final_text,
                "error": error, "final_state": state})
    return {"steps": steps, "final_text": final_text, "error": error, "state": state}
