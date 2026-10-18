"""DeepSeek chat adapter. Credentials stay in process environment; no automatic billable retries."""
import json
import os
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from layer_cache import cached_layer

SYSTEM = ('你是数字人助手。用简短中文回答，最多60个汉字。只返回一个JSON对象，不要代码块或解释。'
          'text为回答正文；expression只能是neutral-with-blink、smile、curious、surprised之一；'
          'motion只能是idle-v1、nod、shake、explain之一。'
          'JSON示例：{"text":"你好，很高兴见到你。","expression":"smile","motion":"nod"}')


def parse_reply(raw):
    """Distinguish transport/schema failures from model JSON failures without echoing secrets."""
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError, TypeError):
        raise ValueError('DeepSeek 接口响应不是有效 JSON；请检查网络或代理；未自动重试') from None
    if not isinstance(data, dict):
        raise ValueError('DeepSeek 接口响应结构无效：应为 JSON 对象；未自动重试')
    choices = data.get('choices')
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError('DeepSeek 接口响应缺少有效 choices；未自动重试')
    choice = choices[0]
    if choice.get('finish_reason') != 'stop':
        raise ValueError('DeepSeek 回复未完整结束（可能达到输出上限）；未自动重试')
    message = choice.get('message')
    content = message.get('content') if isinstance(message, dict) else None
    if content is None or isinstance(content, str) and not content.strip():
        raise ValueError('DeepSeek 返回空回复；可修改问题后手动重试；未自动重试')
    if not isinstance(content, str):
        raise ValueError('DeepSeek 回复 content 类型无效；未自动重试')
    content = content.strip().lstrip('\ufeff').strip()
    # Accept only a whole JSON code fence, never arbitrary surrounding prose.
    lines = content.splitlines()
    if len(lines) >= 3 and lines[0].lower() in ('```json', '```') and lines[-1] == '```':
        content = '\n'.join(lines[1:-1]).strip()
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        # In normal text mode a valid conversational answer need not contain
        # behavior JSON. Use fixed local intents, never interpret it as commands.
        if content.startswith(('{', '[', '```')):
            raise ValueError('DeepSeek 回复正文不是有效 JSON；可修改问题后手动重试；未自动重试') from None
        result = dict(text=content, expression='neutral-with-blink', motion='idle-v1',
                      behavior_source='local-default-for-plain-text')
    validate_response(result)
    result.update(usage=data.get('usage'), source='deepseek', returned_model=data.get('model'))
    return result


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def chat(prompt, root, provider='mock', model=None, context=None, revision=None):
    if provider not in ('mock', 'deepseek') or not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 2000:
        raise ValueError('请选择有效提供商并输入1—2000字问题')
    revision = revision or os.environ.get('DEEPSEEK_MODEL_REVISION', 'v1')
    model = model or os.environ.get('DEEPSEEK_MODEL', 'deepseek-flash')
    messages = [{'role': 'system', 'content': SYSTEM}]
    for item in context or []:
        if set(item) != {'role', 'content'} or item['role'] not in ('user', 'assistant') or not isinstance(item['content'], str):
            raise ValueError('Invalid conversation context')
        messages.append(dict(item))
    messages.append({'role': 'user', 'content': prompt})
    identity = dict(provider=provider, model=model if provider == 'deepseek' else 'fixed-test-v1', revision=revision,
                    messages=messages, temperature=0.2, max_tokens=1024, format='text', thinking='disabled', adapter='v2')
    def produce(folder):
        if provider == 'mock':
            result = dict(text='你好，我正在测试数字人的表情、嘴型和动作。', expression='smile', motion='explain', usage=None, source='mock-not-ai')
        else:
            secret = os.environ.get('DEEPSEEK_API_KEY', '').strip()
            if not secret:
                raise ValueError('缺少 DEEPSEEK_API_KEY，请在桌面控制台设置会话密钥')
            if len(secret)>1024 or any(not 33<=ord(c)<=126 for c in secret):
                raise ValueError('密钥格式无效，请勿包含空白、换行或非 ASCII 字符')
            # JSON mode can return an empty completion. Request normal text with
            # the explicit JSON prompt instead; still strictly validate the result.
            body = dict(model=model, messages=messages, temperature=0.2, max_tokens=1024, stream=False,
                        response_format={'type': 'text'}, thinking={'type':'disabled'})
            req = Request('https://api.deepseek.com/chat/completions', data=json.dumps(body).encode(),
                          headers={'Authorization': 'Bearer '+secret, 'Content-Type': 'application/json'})
            try:
                with build_opener(NoRedirect()).open(req, timeout=60) as response:
                    raw = response.read(1_000_001)
                    if len(raw) > 1_000_000:
                        raise ValueError('API response too large')
                result = parse_reply(raw)
            except HTTPError as error:
                labels = {401:'密钥无效',402:'余额不足',429:'请求限流',400:'参数或模型不受支持'}
                raise ValueError(f'DeepSeek HTTP {error.code}: {labels.get(error.code, "服务请求失败")}；未自动重试') from None
            except (URLError, TimeoutError, OSError):
                raise ValueError('DeepSeek 网络失败或超时；为避免重复计费未自动重试') from None
        validate_response(result)
        (folder/'response.json').write_text(json.dumps(result, ensure_ascii=False), 'utf-8')
    folder, hit = cached_layer(root, identity, produce)
    result = json.loads((folder/'response.json').read_text('utf-8'))
    validate_response(result)
    return result, hit


def validate_response(result):
    from behavior import EXPRESSIONS, MOTIONS
    if (not isinstance(result, dict) or not isinstance(result.get('text'), str) or not 1 <= len(result['text']) <= 120
            or result.get('expression') not in EXPRESSIONS or result.get('motion') not in MOTIONS):
        raise ValueError('AI 回复文本或行为意图无效；不执行任意命令')
