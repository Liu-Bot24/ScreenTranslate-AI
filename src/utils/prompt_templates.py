"""
内置Prompt模板模块

提供预定义的Prompt模板，用于不同类型的文本处理任务。
支持模板的动态参数替换和自定义模板管理。
"""

from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class PromptTemplate:
    """Prompt模板数据类"""
    name: str
    description: str
    template: str
    category: str
    variables: List[str]  # 模板中使用的变量列表


class PromptTemplateManager:
    """Prompt模板管理器"""

    def __init__(self):
        self._templates: Dict[str, PromptTemplate] = {}
        self._load_builtin_templates()

    def _load_builtin_templates(self):
        """加载内置模板"""

        # 1. 纯翻译模板
        translate_template = PromptTemplate(
            name="translate",
            description="纯翻译模板 - 将文本翻译为目标语言",
            template="""请将以下文本翻译为{target_language}，要求：
1. 保持原文的格式和结构
2. 翻译要准确、自然、流畅
3. 专业术语要使用标准译法
4. 如果原文包含多种语言，请分别翻译
5. 不要添加任何解释或说明，只返回翻译结果

原文：
{text}

翻译结果：""",
            category="translation",
            variables=["text", "target_language"]
        )

        # 2. 代码解释模板
        code_explain_template = PromptTemplate(
            name="code_explain",
            description="代码解释模板 - 解释代码的功能和实现",
            template="""请分析并解释以下代码，要求：
1. 说明代码的主要功能和目的
2. 解释关键算法和逻辑
3. 指出可能的改进点或潜在问题
4. 如果有错误，请指出并提供修正建议
5. 使用{target_language}回答

代码：
{text}

代码解释：""",
            category="code",
            variables=["text", "target_language"]
        )

        # 3. 通用解释模板
        general_explain_template = PromptTemplate(
            name="general_explain",
            description="通用解释模板 - 解释和分析任意文本内容",
            template="""请分析并解释以下内容，要求：
1. 首先判断内容的类型（如：技术文档、用户界面、错误信息等）
2. 解释主要含义和关键信息
3. 如果是技术内容，请解释相关概念
4. 如果是界面文本，请说明功能和操作
5. 如果是错误信息，请解释原因和解决方法
6. 使用{target_language}回答

内容：
{text}

解释分析：""",
            category="explanation",
            variables=["text", "target_language"]
        )

        # 4. 翻译+解释组合模板
        translate_explain_template = PromptTemplate(
            name="translate_explain",
            description="翻译+解释模板 - 先翻译再解释",
            template="""请对以下文本进行翻译和解释，要求：

第一步：翻译
将文本翻译为{target_language}，保持原有格式

第二步：解释
解释文本的含义、用途或背景信息

原文：
{text}

翻译：


解释：""",
            category="hybrid",
            variables=["text", "target_language"]
        )

        # 5. 技术文档专用模板
        tech_doc_template = PromptTemplate(
            name="tech_doc",
            description="技术文档模板 - 专门处理技术文档和API文档",
            template="""请分析以下技术文档内容，要求：
1. 如果是API文档，解释接口功能、参数和返回值
2. 如果是配置文件，解释各项配置的作用
3. 如果是错误日志，分析错误原因和解决方案
4. 如果是命令行输出，解释执行结果的含义
5. 提供实用的使用建议
6. 使用{target_language}回答

技术文档：
{text}

分析结果：""",
            category="technical",
            variables=["text", "target_language"]
        )

        # 6. 界面文本专用模板
        ui_text_template = PromptTemplate(
            name="ui_text",
            description="界面文本模板 - 专门处理用户界面文本",
            template="""请分析以下用户界面文本，要求：
1. 翻译所有界面元素为{target_language}
2. 解释各个界面元素的功能
3. 说明可能的操作流程
4. 如果有错误提示，解释错误原因
5. 提供使用建议

界面文本：
{text}

翻译和说明：""",
            category="ui",
            variables=["text", "target_language"]
        )

        # 添加到模板字典
        templates = [
            translate_template,
            code_explain_template,
            general_explain_template,
            translate_explain_template,
            tech_doc_template,
            ui_text_template
        ]

        for template in templates:
            self._templates[template.name] = template

    def get_template(self, name: str) -> Optional[PromptTemplate]:
        """获取指定名称的模板"""
        return self._templates.get(name)

    def get_all_templates(self) -> Dict[str, PromptTemplate]:
        """获取所有模板"""
        return self._templates.copy()

    def get_templates_by_category(self, category: str) -> Dict[str, PromptTemplate]:
        """根据分类获取模板"""
        return {
            name: template for name, template in self._templates.items()
            if template.category == category
        }

    def get_template_names(self) -> List[str]:
        """获取所有模板名称"""
        return list(self._templates.keys())

    def get_categories(self) -> List[str]:
        """获取所有分类"""
        categories = set(template.category for template in self._templates.values())
        return sorted(list(categories))

    def add_template(self, template: PromptTemplate) -> bool:
        """添加自定义模板"""
        try:
            self._templates[template.name] = template
            return True
        except Exception:
            return False

    def remove_template(self, name: str) -> bool:
        """删除模板"""
        try:
            if name in self._templates:
                del self._templates[name]
                return True
            return False
        except Exception:
            return False

    def format_template(self, template_name: str, **kwargs) -> Optional[str]:
        """
        格式化模板，替换变量

        Args:
            template_name: 模板名称
            **kwargs: 变量值

        Returns:
            格式化后的prompt字符串，失败时返回None
        """
        try:
            template = self.get_template(template_name)
            if not template:
                return None

            # 设置默认值
            format_kwargs = {
                "text": kwargs.get("text", ""),
                "target_language": kwargs.get("target_language", "简体中文")
            }

            # 添加其他参数
            for key, value in kwargs.items():
                if key not in format_kwargs:
                    format_kwargs[key] = value

            # 格式化模板
            formatted_prompt = template.template.format(**format_kwargs)
            return formatted_prompt

        except Exception:
            return None

    def validate_template(self, template: PromptTemplate) -> List[str]:
        """
        验证模板格式

        Returns:
            错误列表，空列表表示验证通过
        """
        errors = []

        if not template.name:
            errors.append("模板名称不能为空")

        if not template.template:
            errors.append("模板内容不能为空")

        # 检查模板变量格式
        try:
            # 尝试格式化模板，检查语法错误
            test_kwargs = {var: f"test_{var}" for var in template.variables}
            template.template.format(**test_kwargs)
        except KeyError as e:
            errors.append(f"模板中使用了未声明的变量: {e}")
        except Exception as e:
            errors.append(f"模板格式错误: {str(e)}")

        return errors


# 全局模板管理器实例
template_manager = PromptTemplateManager()


# 便捷函数
def get_prompt_template(name: str) -> Optional[PromptTemplate]:
    """获取Prompt模板"""
    return template_manager.get_template(name)


def format_prompt(template_name: str, text: str, target_language: str = "简体中文", **kwargs) -> Optional[str]:
    """
    格式化Prompt模板

    Args:
        template_name: 模板名称
        text: 要处理的文本
        target_language: 目标语言
        **kwargs: 其他变量

    Returns:
        格式化后的prompt字符串
    """
    return template_manager.format_template(
        template_name,
        text=text,
        target_language=target_language,
        **kwargs
    )


def get_available_templates() -> List[str]:
    """获取可用的模板名称列表"""
    return template_manager.get_template_names()


def get_template_categories() -> List[str]:
    """获取模板分类列表"""
    return template_manager.get_categories()