"""DeepSeek Chat API 集成"""
import json
import re
import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


async def call_deepseek(
    messages: list,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    timeout: int = None,
) -> str:
    """调用 DeepSeek Chat API（异步）

    Args:
        messages: OpenAI 格式的消息列表
        temperature: 采样温度
        max_tokens: 最大输出 token 数
        timeout: 超时秒数

    Returns:
        API 返回的文本内容
    """
    if not settings.deepseek_available:
        raise RuntimeError('DeepSeek API key not configured')

    headers = {
        'Authorization': f'Bearer {settings.DEEPSEEK_API_KEY}',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': settings.DEEPSEEK_MODEL,
        'messages': messages,
        'temperature': temperature,
        'max_tokens': max_tokens,
    }

    async with httpx.AsyncClient(
        timeout=timeout or settings.DEEPSEEK_TIMEOUT,
        trust_env=False,  # 不走系统代理，DeepSeek 国内直连更快
    ) as client:
        response = await client.post(settings.DEEPSEEK_API_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data['choices'][0]['message']['content']


async def call_deepseek_stream(
    messages: list,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    timeout: int = None,
):
    """调用 DeepSeek Chat API（流式，异步生成器）

    Yields:
        str: 每次 yield 一段增量文本内容
    """
    if not settings.deepseek_available:
        raise RuntimeError('DeepSeek API key not configured')

    headers = {
        'Authorization': f'Bearer {settings.DEEPSEEK_API_KEY}',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': settings.DEEPSEEK_MODEL,
        'messages': messages,
        'temperature': temperature,
        'max_tokens': max_tokens,
        'stream': True,
    }

    async with httpx.AsyncClient(
        timeout=timeout or settings.DEEPSEEK_TIMEOUT,
        trust_env=False,  # 不走系统代理，DeepSeek 国内直连更快
    ) as client:
        async with client.stream('POST', settings.DEEPSEEK_API_URL, json=payload, headers=headers) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith('data: '):
                    data_str = line[6:]
                    if data_str.strip() == '[DONE]':
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get('choices', [{}])[0].get('delta', {})
                        content = delta.get('content', '')
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue


def extract_json(text: str) -> list | dict:
    """从 LLM 返回文本中提取 JSON"""
    # 尝试匹配 ```json ... ``` 代码块
    m = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if m:
        text = m.group(1)
    text = text.strip()
    if text.startswith('[') or text.startswith('{'):
        return json.loads(text)
    # 尝试找到第一个 [ 或 {
    arr = text.find('[')
    obj = text.find('{')
    if arr != -1 and (obj == -1 or arr < obj):
        end = text.rfind(']')
        if end != -1:
            text = text[arr:end + 1]
    elif obj != -1:
        end = text.rfind('}')
        if end != -1:
            text = text[obj:end + 1]
    return json.loads(text)
