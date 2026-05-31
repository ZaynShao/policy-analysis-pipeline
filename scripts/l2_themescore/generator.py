import json, re

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)

def parse_json_block(text: str) -> dict:
    m = _FENCE.search(text)
    raw = m.group(1) if m else text
    return json.loads(raw)

def _complete_json(client, system, user, max_tokens=1024) -> dict:
    txt = client.complete(system=system, user=user, max_tokens=max_tokens)
    try:
        return parse_json_block(txt)
    except Exception:
        txt = client.complete(system=system + "\n\n严格:只输出 JSON,不要任何其他字符。",
                              user=user, max_tokens=max_tokens)
        return parse_json_block(txt)

def gen_pass1(client, system: str, user: str) -> dict:
    return _complete_json(client, system, user, max_tokens=896)

def gen_pass2(client, system: str, user: str) -> dict:
    return _complete_json(client, system, user, max_tokens=1024)
