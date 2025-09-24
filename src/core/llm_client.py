"""
LLM API客户端模块

使用httpx库进行异步HTTP请求，支持多个LLM API提供商。
集成Prompt模板，支持流式响应和完整的错误处理机制。
"""

import asyncio
import json
import logging
import os
from typing import Optional, Dict, Any, List, AsyncGenerator, Callable
from dataclasses import dataclass
from enum import Enum

import httpx
from PyQt6.QtCore import QObject, pyqtSignal, QThread

from ..utils.prompt_templates import format_prompt, get_available_templates


class APIProvider(Enum):
    """API提供商枚举"""
    OPENAI = "openai"
    SILICONFLOW = "siliconflow"
    DOUBAO = "doubao"
    OLLAMA = "ollama"
    CUSTOM = "custom"


@dataclass
class LLMConfig:
    """LLM配置数据类"""
    provider: APIProvider
    api_key: str
    api_endpoint: str
    model_name: str
    max_tokens: int = 2048
    temperature: float = 0.7
    timeout: int = 30
    max_retries: int = 3


@dataclass
class LLMResponse:
    """LLM响应数据类"""
    content: str
    provider: str
    model: str
    usage: Dict[str, Any] = None
    metadata: Dict[str, Any] = None


class LLMError(Exception):
    """LLM相关错误基类"""
    pass


class APIKeyError(LLMError):
    """API密钥错误"""
    pass


class RateLimitError(LLMError):
    """请求限制错误"""
    pass


class ModelNotFoundError(LLMError):
    """模型不存在错误"""
    pass


class NetworkError(LLMError):
    """网络错误"""
    pass


class LLMClient(QObject):
    """LLM API客户端"""

    # 响应完成信号
    response_completed = pyqtSignal(object)  # LLMResponse
    # 流式响应信号
    response_chunk_received = pyqtSignal(str)  # 响应片段
    # 错误信号
    error_occurred = pyqtSignal(str)
    # 进度信号
    progress_updated = pyqtSignal(str)

    # 预定义的API端点
    API_ENDPOINTS = {
        APIProvider.OPENAI: "https://api.openai.com/v1/chat/completions",
        APIProvider.SILICONFLOW: "https://api.siliconflow.cn/v1/chat/completions",
        APIProvider.DOUBAO: "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        APIProvider.OLLAMA: "http://localhost:11434/api/generate"
    }

    # 默认模型
    DEFAULT_MODELS = {
        APIProvider.OPENAI: "gpt-3.5-turbo",
        APIProvider.SILICONFLOW: "deepseek-ai/deepseek-chat",
        APIProvider.DOUBAO: "ep-20241010211228-dpc2p",
        APIProvider.OLLAMA: "llama2"
    }

    def __init__(self, config: Optional[LLMConfig] = None):
        super().__init__()
        self.config = config
        self.client: Optional[httpx.AsyncClient] = None
        self.logger = logging.getLogger(__name__)

    def set_config(self, config: LLMConfig):
        """设置LLM配置"""
        self.config = config

    def get_default_config(self, provider: APIProvider, api_key: str, model_name: str = None) -> LLMConfig:
        """获取默认配置"""
        if not model_name:
            model_name = self.DEFAULT_MODELS.get(provider, "default")

        api_endpoint = self.API_ENDPOINTS.get(provider, "")

        return LLMConfig(
            provider=provider,
            api_key=api_key,
            api_endpoint=api_endpoint,
            model_name=model_name
        )

    async def _create_client(self) -> httpx.AsyncClient:
        """创建HTTP客户端"""
        if self.client and not self.client.is_closed:
            return self.client

        headers = {
            "User-Agent": "ScreenTranslate-AI/1.0",
            "Content-Type": "application/json"
        }

        # 根据提供商设置认证头
        if self.config.provider == APIProvider.OPENAI:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        elif self.config.provider == APIProvider.SILICONFLOW:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        elif self.config.provider == APIProvider.DOUBAO:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        self.client = httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(self.config.timeout),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        )

        return self.client

    def _prepare_openai_request(self, prompt: str, stream: bool = False) -> Dict[str, Any]:
        """准备OpenAI格式的请求"""
        return {
            "model": self.config.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "stream": stream
        }


    def _prepare_ollama_request(self, prompt: str, stream: bool = False) -> Dict[str, Any]:
        """准备Ollama格式的请求"""
        return {
            "model": self.config.model_name,
            "prompt": prompt,
            "stream": stream,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens
            }
        }

    def _prepare_request_data(self, prompt: str, stream: bool = False) -> Dict[str, Any]:
        """根据提供商准备请求数据"""
        if self.config.provider in [APIProvider.OPENAI, APIProvider.SILICONFLOW, APIProvider.DOUBAO]:
            return self._prepare_openai_request(prompt, stream)
        elif self.config.provider == APIProvider.OLLAMA:
            return self._prepare_ollama_request(prompt, stream)
        else:
            # 默认使用OpenAI格式
            return self._prepare_openai_request(prompt, stream)

    def _parse_openai_response(self, response_data: Dict[str, Any]) -> LLMResponse:
        """解析OpenAI格式的响应"""
        try:
            content = response_data["choices"][0]["message"]["content"]
            usage = response_data.get("usage", {})

            return LLMResponse(
                content=content,
                provider=self.config.provider.value,
                model=self.config.model_name,
                usage=usage,
                metadata={"finish_reason": response_data["choices"][0].get("finish_reason")}
            )
        except (KeyError, IndexError) as e:
            raise LLMError(f"响应格式解析错误: {str(e)}")


    def _parse_ollama_response(self, response_data: Dict[str, Any]) -> LLMResponse:
        """解析Ollama格式的响应"""
        try:
            content = response_data["response"]

            return LLMResponse(
                content=content,
                provider=self.config.provider.value,
                model=self.config.model_name,
                usage={},
                metadata={"done": response_data.get("done", True)}
            )
        except KeyError as e:
            raise LLMError(f"响应格式解析错误: {str(e)}")

    def _parse_response(self, response_data: Dict[str, Any]) -> LLMResponse:
        """根据提供商解析响应"""
        if self.config.provider in [APIProvider.OPENAI, APIProvider.SILICONFLOW, APIProvider.DOUBAO]:
            return self._parse_openai_response(response_data)
        elif self.config.provider == APIProvider.OLLAMA:
            return self._parse_ollama_response(response_data)
        else:
            return self._parse_openai_response(response_data)

    def _handle_http_error(self, response: httpx.Response) -> None:
        """处理HTTP错误"""
        if response.status_code == 401:
            raise APIKeyError("API密钥无效或已过期")
        elif response.status_code == 429:
            raise RateLimitError("请求过于频繁，已达到限制")
        elif response.status_code == 404:
            raise ModelNotFoundError(f"模型 {self.config.model_name} 不存在")
        elif response.status_code >= 500:
            raise NetworkError(f"服务器错误: {response.status_code}")
        else:
            raise LLMError(f"API请求失败: {response.status_code} - {response.text}")

    async def generate_response(self, prompt: str, stream: bool = False) -> LLMResponse:
        """
        生成LLM响应

        Args:
            prompt: 输入的prompt
            stream: 是否使用流式响应

        Returns:
            LLMResponse: LLM响应结果
        """
        if not self.config:
            raise LLMError("LLM配置未设置")

        for attempt in range(self.config.max_retries):
            try:
                self.progress_updated.emit(f"正在发送请求到 {self.config.provider.value}...")

                client = await self._create_client()
                request_data = self._prepare_request_data(prompt, stream)

                if stream:
                    return await self._generate_streaming_response(client, request_data)
                else:
                    return await self._generate_simple_response(client, request_data)

            except (NetworkError, httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < self.config.max_retries - 1:
                    self.progress_updated.emit(f"请求失败，正在重试 ({attempt + 1}/{self.config.max_retries})...")
                    await asyncio.sleep(2 ** attempt)  # 指数退避
                    continue
                else:
                    raise NetworkError(f"网络请求失败: {str(e)}")

            except Exception as e:
                if attempt < self.config.max_retries - 1:
                    self.progress_updated.emit(f"请求失败，正在重试 ({attempt + 1}/{self.config.max_retries})...")
                    await asyncio.sleep(1)
                    continue
                else:
                    raise

    async def _generate_simple_response(self, client: httpx.AsyncClient, request_data: Dict[str, Any]) -> LLMResponse:
        """生成简单响应（非流式）"""
        response = await client.post(
            self.config.api_endpoint,
            json=request_data
        )

        if response.status_code != 200:
            self._handle_http_error(response)

        response_data = response.json()
        llm_response = self._parse_response(response_data)

        self.progress_updated.emit("响应生成完成")
        return llm_response

    async def _generate_streaming_response(self, client: httpx.AsyncClient, request_data: Dict[str, Any]) -> LLMResponse:
        """生成流式响应"""
        full_content = ""

        async with client.stream('POST', self.config.api_endpoint, json=request_data) as response:
            if response.status_code != 200:
                self._handle_http_error(response)

            async for line in response.aiter_lines():
                if line.startswith('data: '):
                    data = line[6:]  # 移除 'data: ' 前缀

                    if data.strip() == '[DONE]':
                        break

                    try:
                        chunk_data = json.loads(data)
                        chunk_content = self._extract_chunk_content(chunk_data)

                        if chunk_content:
                            full_content += chunk_content
                            self.response_chunk_received.emit(chunk_content)

                    except json.JSONDecodeError:
                        continue

        # 返回完整响应
        return LLMResponse(
            content=full_content,
            provider=self.config.provider.value,
            model=self.config.model_name,
            usage={},
            metadata={"streaming": True}
        )

    def _extract_chunk_content(self, chunk_data: Dict[str, Any]) -> str:
        """从流式响应块中提取内容"""
        try:
            if self.config.provider in [APIProvider.OPENAI, APIProvider.SILICONFLOW, APIProvider.DOUBAO]:
                delta = chunk_data["choices"][0]["delta"]
                return delta.get("content", "")
            elif self.config.provider == APIProvider.OLLAMA:
                return chunk_data.get("response", "")

        except (KeyError, IndexError):
            pass

        return ""

    async def generate_with_template(self, template_name: str, text: str,
                                   target_language: str = "简体中文",
                                   stream: bool = False, **kwargs) -> LLMResponse:
        """
        使用模板生成响应

        Args:
            template_name: 模板名称
            text: 输入文本
            target_language: 目标语言
            stream: 是否使用流式响应
            **kwargs: 其他模板变量

        Returns:
            LLMResponse: LLM响应结果
        """
        prompt = format_prompt(template_name, text, target_language, **kwargs)
        if not prompt:
            raise LLMError(f"模板 {template_name} 不存在或格式化失败")

        return await self.generate_response(prompt, stream)

    async def cleanup(self):
        """清理资源"""
        if self.client and not self.client.is_closed:
            await self.client.aclose()
            self.client = None


class LLMClientThread(QThread):
    """LLM客户端线程，用于异步处理"""

    response_ready = pyqtSignal(object)  # LLMResponse
    chunk_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    progress_updated = pyqtSignal(str)

    def __init__(self, config: LLMConfig, prompt: str, stream: bool = False):
        super().__init__()
        self.config = config
        self.prompt = prompt
        self.stream = stream
        self.client = LLMClient(config)

    def run(self):
        """运行LLM请求"""
        try:
            # 连接信号
            self.client.response_chunk_received.connect(self.chunk_received.emit)
            self.client.progress_updated.connect(self.progress_updated.emit)

            # 运行异步任务
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                response = loop.run_until_complete(
                    self.client.generate_response(self.prompt, self.stream)
                )
                self.response_ready.emit(response)
            finally:
                loop.run_until_complete(self.client.cleanup())
                loop.close()

        except Exception as e:
            self.error_occurred.emit(str(e))


# 便捷函数
async def quick_llm_request(provider: APIProvider, api_key: str, model_name: str,
                          prompt: str, target_language: str = "简体中文") -> str:
    """
    快速LLM请求（异步函数）

    Args:
        provider: API提供商
        api_key: API密钥
        model_name: 模型名称
        prompt: 输入prompt
        target_language: 目标语言

    Returns:
        str: LLM响应文本，失败时返回空字符串
    """
    try:
        config = LLMConfig(
            provider=provider,
            api_key=api_key,
            api_endpoint=LLMClient.API_ENDPOINTS.get(provider, ""),
            model_name=model_name
        )

        client = LLMClient(config)
        response = await client.generate_response(prompt)
        await client.cleanup()

        return response.content

    except Exception:
        return ""


def create_llm_config_from_env(provider_name: str = "siliconflow") -> Optional[LLMConfig]:
    """
    从环境变量创建LLM配置

    Args:
        provider_name: 提供商名称

    Returns:
        LLMConfig: 配置对象，失败时返回None
    """
    try:
        provider = APIProvider(provider_name.lower())
        api_key = os.getenv(f"{provider_name.upper()}_API_KEY")

        if not api_key:
            return None

        model_name = os.getenv(f"{provider_name.upper()}_MODEL",
                              LLMClient.DEFAULT_MODELS.get(provider))

        return LLMConfig(
            provider=provider,
            api_key=api_key,
            api_endpoint=LLMClient.API_ENDPOINTS.get(provider, ""),
            model_name=model_name
        )

    except Exception:
        return None