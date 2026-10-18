"""Bundled five-provider protocol smoke check with synthetic HTTP responses."""
from __future__ import annotations


def check_online_protocols() -> dict:
    import httpx
    from screen_translator.services.provider_translators import create_translator
    from screen_translator.services.providers import PROVIDERS
    from screen_translator.services.translator import TranslationError

    profiles = {
        "baidu": {"app_id": "synthetic", "secret_key": "synthetic"},
        "aliyun": {"access_key_id": "synthetic", "access_key_secret": "synthetic"},
        "tencent_tokenhub": {"api_key": "synthetic"},
        "huawei": {"access_key_id": "synthetic", "secret_access_key": "synthetic", "project_id": "a" * 32},
        "niutrans": {"app_id": "synthetic", "api_key": "synthetic"},
    }
    responses = {
        "baidu": {"trans_result": [{"dst": "你好"}]},
        "aliyun": {"Code": 200, "Data": {"Translated": "你好"}},
        "tencent_tokenhub": {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "你好"}}]},
        "huawei": {"translated_text": "你好"},
        "niutrans": {"tgtText": "你好"},
    }
    original = httpx.post
    results = {}
    try:
        for provider_id in PROVIDERS:
            calls = []

            def synthetic_post(endpoint, **_kwargs):
                calls.append(endpoint)
                return httpx.Response(200, json=responses[provider_id])

            httpx.post = synthetic_post
            adapter = create_translator(provider_id, profiles[provider_id])
            results[provider_id] = adapter.translate("Hello.", "中文") == "你好" and len(calls) == 1
        unsupported_rejected = True
        for provider_id in ("unsupported-provider",):
            try:
                create_translator(provider_id, {})
            except TranslationError:
                pass
            else:
                unsupported_rejected = False
    finally:
        httpx.post = original
    return {"kind": "mock_http_no_account_calls", "providers": results,
            "unsupported_rejected": unsupported_rejected,
            "passed": len(results) == 5 and all(results.values()) and unsupported_rejected}
