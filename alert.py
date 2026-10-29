import json
import os
import re
from xml.sax.saxutils import escape

import requests

STATE_PATH = "apple-pickup-alert.json"


def notify_if_changed(result, authorization, test=False):
    if not _allowed(authorization):
        return {"sent": False, "reason": "not a cron request"}

    if test:
        message = "这是苹果取货提醒测试。收到这条就说明电话和短信已经接通。"
        return _deliver(message, message)

    current = _fingerprint(result.get("available") or [])
    try:
        previous = _load_fingerprint()
    except Exception as error:
        return {"sent": False, "reason": f"无法读取提醒记录: {error}"}

    if current == previous:
        return {"sent": False, "reason": "unchanged"}

    if not current:
        try:
            _save_fingerprint([])
        except Exception as error:
            return {"sent": False, "reason": f"库存已空，但提醒记录没有更新: {error}"}
        return {"sent": False, "reason": "cleared"}

    sms, speech = _messages(result["available"])
    delivery = _deliver(sms, speech)
    if not delivery.get("sent"):
        return delivery

    try:
        _save_fingerprint(current)
    except Exception as error:
        delivery["stateSaved"] = False
        delivery["warning"] = f"提醒已发出，但记录没有保存，下次查询可能会再发一次: {error}"
    return delivery


def _allowed(authorization):
    secret = os.environ.get("CRON_SECRET")
    if not secret:
        return True
    return authorization == f"Bearer {secret}"


def _fingerprint(available):
    return sorted(
        f"{item.get('store')}|{item.get('partNumber')}" for item in available
    )


def _messages(available):
    shown = available[:4]
    details = []
    spoken = []
    for item in shown:
        title = _clean(item.get("title") or item.get("partNumber"))
        store = _clean(item.get("store"))
        details.append(f"{store} {title} {item.get('buyUrl', '')}".strip())
        spoken.append(f"{store}，{title}")
    extra = len(available) - len(shown)
    sms = "苹果取货有货：" + " | ".join(details)
    speech = "苹果店有货了。" + "。".join(spoken) + "。"
    if extra > 0:
        sms += f" | 另有 {extra} 条"
        speech += f"另外还有 {extra} 家店有货。"
    return sms, speech


def _deliver(sms, speech):
    config = _twilio_config()
    if config is None:
        return {
            "sent": False,
            "reason": "缺少 Twilio 环境变量",
        }

    sent = []
    errors = []
    try:
        _send_sms(config, sms)
        sent.append("sms")
    except Exception as error:
        errors.append(f"短信失败: {error}")

    if _calls_enabled():
        try:
            _call(config, speech)
            sent.append("call")
        except Exception as error:
            errors.append(f"电话失败: {error}")

    if not sent:
        return {"sent": False, "reason": "；".join(errors)}

    result = {"sent": True, "channels": sent}
    if errors:
        result["warning"] = "；".join(errors)
    return result


def _twilio_config():
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_FROM_NUMBER")
    to_number = os.environ.get("ALERT_TO_NUMBER")
    if not all((sid, token, from_number, to_number)):
        return None
    return {
        "sid": sid,
        "token": token,
        "from": _e164(from_number),
        "to": _e164(to_number),
    }


def _calls_enabled():
    return os.environ.get("ALERT_CALL", "").strip().lower() in {"1", "true", "yes"}


def _send_sms(config, body):
    _twilio_post(config, "Messages.json", {"To": config["to"], "From": config["from"], "Body": body})


def _call(config, speech):
    twiml = (
        "<Response>"
        f'<Say language="zh-CN" voice="Polly.Zhiyu">{escape(speech)}</Say>'
        "<Pause length=\"1\"/>"
        f'<Say language="zh-CN" voice="Polly.Zhiyu">{escape(speech)}</Say>'
        "</Response>"
    )
    _twilio_post(
        config,
        "Calls.json",
        {"To": config["to"], "From": config["from"], "Twiml": twiml},
    )


def _twilio_post(config, resource, data):
    url = (
        "https://api.twilio.com/2010-04-01/Accounts/"
        f"{config['sid']}/{resource}"
    )
    response = requests.post(url, data=data, auth=(config["sid"], config["token"]), timeout=15)
    if response.status_code >= 400:
        detail = response.text[:300]
        raise RuntimeError(f"Twilio {response.status_code}: {detail}")


def _e164(number):
    compact = re.sub(r"[^\d+]", "", number.strip())
    if compact.startswith("+"):
        return compact
    if compact.startswith("0"):
        return "+61" + compact[1:]
    if compact.startswith("61"):
        return "+" + compact
    return compact


def _clean(value):
    return " ".join(str(value or "").split())


def _blob():
    from vercel.blob import sync as blob

    access = os.environ.get("BLOB_ACCESS", "private").strip().lower()
    if access not in {"private", "public"}:
        access = "private"
    return blob, access


def _load_fingerprint():
    blob, access = _blob()
    try:
        stored = blob.get_blob(STATE_PATH, access=access)
    except Exception as error:
        if error.__class__.__name__ == "BlobNotFoundError" or isinstance(error, FileNotFoundError):
            return []
        raise
    payload = json.loads(stored.body.decode("utf-8"))
    return list(payload.get("fingerprint") or [])


def _save_fingerprint(fingerprint):
    blob, access = _blob()
    body = json.dumps({"fingerprint": fingerprint}).encode("utf-8")
    blob.put_blob(
        STATE_PATH,
        body,
        access=access,
        allow_overwrite=True,
        cache_control_max_age=60,
        content_type="application/json",
    )
