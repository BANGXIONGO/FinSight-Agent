"""
搜索节点实现
负责生成搜索查询和反思查询
"""

import json
from typing import Dict, Any
from json.decoder import JSONDecodeError
from loguru import logger

from .base_node import BaseNode
from ..prompts import SYSTEM_PROMPT_FIRST_SEARCH, SYSTEM_PROMPT_REFLECTION
from ..utils.text_processing import (
    remove_reasoning_from_output,
    clean_json_tags,
    extract_clean_response,
    fix_incomplete_json
)


class FirstSearchNode(BaseNode):
    """为段落生成首次搜索查询的节点"""
    
    def __init__(self, llm_client):
        """
        初始化首次搜索节点
        
        Args:
            llm_client: LLM客户端
        """
        super().__init__(llm_client, "FirstSearchNode")
    
    def validate_input(self, input_data: Any) -> bool:
        """验证输入数据"""
        if isinstance(input_data, str):
            try:
                data = json.loads(input_data)
                return "title" in data and "content" in data
            except JSONDecodeError:
                return False
        elif isinstance(input_data, dict):
            return "title" in input_data and "content" in input_data
        return False
    
    def run(self, input_data: Any, **kwargs) -> Dict[str, Any]:
        """
        调用LLM生成搜索查询和理由
        
        Args:
            input_data: 包含title和content的字符串或字典
            **kwargs: 额外参数
            
        Returns:
            包含search_query和reasoning的字典
        """
        try:
            if not self.validate_input(input_data):
                raise ValueError("输入数据格式错误，需要包含title和content字段")
            
            # 准备输入数据
            if isinstance(input_data, str):
                message = input_data
            else:
                message = json.dumps(input_data, ensure_ascii=False)
            
            logger.info("正在生成首次搜索查询")
            
            # 调用LLM（流式，安全拼接UTF-8）
            response = self.llm_client.stream_invoke_to_string(SYSTEM_PROMPT_FIRST_SEARCH, message)
            
            # 处理响应
            processed_response = self.process_output(response, input_data)
            
            logger.info(f"生成搜索查询: {processed_response.get('search_query', 'N/A')}")
            return processed_response
            
        except Exception as e:
            logger.exception(f"生成首次搜索查询失败: {str(e)}")
            raise e
    
    def process_output(self, output: str, input_data: Any = None) -> Dict[str, Any]:
        """
        处理LLM输出，提取搜索查询和推理
        
        Args:
            output: LLM原始输出
            
        Returns:
            包含search_query和reasoning的字典
        """
        try:
            # 清理响应文本
            cleaned_output = remove_reasoning_from_output(output)
            cleaned_output = clean_json_tags(cleaned_output)
            
            # 记录清理后的输出用于调试
            logger.info(f"清理后的输出: {cleaned_output}")
            
            # 解析JSON
            try:
                result = json.loads(cleaned_output)
                logger.info("JSON解析成功")
            except JSONDecodeError as e:
                logger.error(f"JSON解析失败: {str(e)}")
                # 使用更强大的提取方法
                result = extract_clean_response(cleaned_output)
                if "error" in result:
                    logger.error("JSON解析失败，尝试修复...")
                    # 尝试修复JSON
                    fixed_json = fix_incomplete_json(cleaned_output)
                    if fixed_json:
                        try:
                            result = json.loads(fixed_json)
                            logger.info("JSON修复成功")
                        except JSONDecodeError:
                            logger.error("JSON修复失败")
                            # 返回默认查询
                            return self._get_default_search_query(input_data)
                    else:
                        logger.error("无法修复JSON，使用默认查询")
                        return self._get_default_search_query(input_data)
            
            # 兼容解析后为列表的情况（部分修复逻辑会返回数组）
            if isinstance(result, list):
                if result and isinstance(result[0], dict):
                    result = result[0]
                else:
                    return self._get_default_search_query(input_data)
            
            # 验证和清理结果
            search_query = result.get("search_query", "")
            reasoning = result.get("reasoning", "")
            
            if not search_query:
                logger.warning("未找到搜索查询，使用默认查询")
                return self._get_default_search_query(input_data)

            parsed_output: Dict[str, Any] = {
                "search_query": search_query,
                "reasoning": reasoning
            }

            # 保留工具与参数，避免上游总是回退到默认工具
            optional_fields = [
                "search_tool",
                "start_date",
                "end_date",
                "platform",
                "time_period",
                "enable_sentiment",
                "texts",
            ]
            for field in optional_fields:
                value = result.get(field)
                if value not in (None, ""):
                    parsed_output[field] = value

            return parsed_output
            
        except Exception as e:
            self.log_error(f"处理输出失败: {str(e)}")
            # 返回默认查询
            return self._get_default_search_query(input_data)
    
    def _extract_topic_hint(self, input_data: Any) -> str:
        """从输入中提取一个可用的话题提示，避免固定兜底查询。"""
        if isinstance(input_data, str):
            try:
                input_data = json.loads(input_data)
            except JSONDecodeError:
                input_data = {"title": input_data}

        if isinstance(input_data, dict):
            title = str(input_data.get("title", "")).strip()
            content = str(input_data.get("content", "")).strip()
            hint = title or content
            return hint[:32] if hint else ""

        return ""

    def _get_default_search_query(self, input_data: Any = None) -> Dict[str, Any]:
        """
        获取默认搜索查询
        
        Returns:
            默认的搜索查询字典
        """
        topic_hint = self._extract_topic_hint(input_data)
        fallback_query = topic_hint if topic_hint else "相关主题研究"
        return {
            "search_query": fallback_query,
            "search_tool": "search_topic_globally",
            "reasoning": "由于解析失败，使用段落标题/内容作为兜底查询"
        }


class ReflectionNode(BaseNode):
    """反思段落并生成新搜索查询的节点"""
    
    def __init__(self, llm_client):
        """
        初始化反思节点
        
        Args:
            llm_client: LLM客户端
        """
        super().__init__(llm_client, "ReflectionNode")
    
    def validate_input(self, input_data: Any) -> bool:
        """验证输入数据"""
        if isinstance(input_data, str):
            try:
                data = json.loads(input_data)
                required_fields = ["title", "content", "paragraph_latest_state"]
                return all(field in data for field in required_fields)
            except JSONDecodeError:
                return False
        elif isinstance(input_data, dict):
            required_fields = ["title", "content", "paragraph_latest_state"]
            return all(field in input_data for field in required_fields)
        return False
    
    def run(self, input_data: Any, **kwargs) -> Dict[str, Any]:
        """
        调用LLM反思并生成搜索查询
        
        Args:
            input_data: 包含title、content和paragraph_latest_state的字符串或字典
            **kwargs: 额外参数
            
        Returns:
            包含search_query和reasoning的字典
        """
        try:
            if not self.validate_input(input_data):
                raise ValueError("输入数据格式错误，需要包含title、content和paragraph_latest_state字段")
            
            # 准备输入数据
            if isinstance(input_data, str):
                message = input_data
            else:
                message = json.dumps(input_data, ensure_ascii=False)
            
            logger.info("正在进行反思并生成新搜索查询")
            
            # 调用LLM（流式，安全拼接UTF-8）
            response = self.llm_client.stream_invoke_to_string(SYSTEM_PROMPT_REFLECTION, message)
            
            # 处理响应
            processed_response = self.process_output(response, input_data)
            
            logger.info(f"反思生成搜索查询: {processed_response.get('search_query', 'N/A')}")
            return processed_response
            
        except Exception as e:
            logger.exception(f"反思生成搜索查询失败: {str(e)}")
            raise e
    
    def process_output(self, output: str, input_data: Any = None) -> Dict[str, Any]:
        """
        处理LLM输出，提取搜索查询和推理
        
        Args:
            output: LLM原始输出
            
        Returns:
            包含search_query和reasoning的字典
        """
        try:
            # 清理响应文本
            cleaned_output = remove_reasoning_from_output(output)
            cleaned_output = clean_json_tags(cleaned_output)
            
            # 记录清理后的输出用于调试
            logger.info(f"清理后的输出: {cleaned_output}")
            
            # 解析JSON
            try:
                result = json.loads(cleaned_output)
                logger.info("JSON解析成功")
            except JSONDecodeError as e:
                logger.error(f"JSON解析失败: {str(e)}")
                # 使用更强大的提取方法
                result = extract_clean_response(cleaned_output)
                if "error" in result:
                    logger.error("JSON解析失败，尝试修复...")
                    # 尝试修复JSON
                    fixed_json = fix_incomplete_json(cleaned_output)
                    if fixed_json:
                        try:
                            result = json.loads(fixed_json)
                            logger.info("JSON修复成功")
                        except JSONDecodeError:
                            logger.error("JSON修复失败")
                            # 返回默认查询
                            return self._get_default_reflection_query(input_data)
                    else:
                        logger.error("无法修复JSON，使用默认查询")
                        return self._get_default_reflection_query(input_data)
            
            # 兼容解析后为列表的情况（部分修复逻辑会返回数组）
            if isinstance(result, list):
                if result and isinstance(result[0], dict):
                    result = result[0]
                else:
                    return self._get_default_reflection_query(input_data)
            
            # 验证和清理结果
            search_query = result.get("search_query", "")
            reasoning = result.get("reasoning", "")
            
            if not search_query:
                logger.warning("未找到搜索查询，使用默认查询")
                return self._get_default_reflection_query(input_data)

            parsed_output: Dict[str, Any] = {
                "search_query": search_query,
                "reasoning": reasoning
            }

            optional_fields = [
                "search_tool",
                "start_date",
                "end_date",
                "platform",
                "time_period",
                "enable_sentiment",
                "texts",
            ]
            for field in optional_fields:
                value = result.get(field)
                if value not in (None, ""):
                    parsed_output[field] = value

            return parsed_output
            
        except Exception as e:
            logger.exception(f"处理输出失败: {str(e)}")
            # 返回默认查询
            return self._get_default_reflection_query(input_data)
    
    def _extract_topic_hint(self, input_data: Any) -> str:
        """从反思输入中提取话题提示，避免固定兜底查询。"""
        if isinstance(input_data, str):
            try:
                input_data = json.loads(input_data)
            except JSONDecodeError:
                input_data = {"title": input_data}

        if isinstance(input_data, dict):
            title = str(input_data.get("title", "")).strip()
            content = str(input_data.get("content", "")).strip()
            latest = str(input_data.get("paragraph_latest_state", "")).strip()
            hint = title or content or latest
            return hint[:32] if hint else ""

        return ""

    def _get_default_reflection_query(self, input_data: Any = None) -> Dict[str, Any]:
        """
        获取默认反思搜索查询
        
        Returns:
            默认的反思搜索查询字典
        """
        topic_hint = self._extract_topic_hint(input_data)
        fallback_query = f"{topic_hint} 补充信息" if topic_hint else "深度研究补充信息"
        return {
            "search_query": fallback_query,
            "search_tool": "search_topic_globally",
            "reasoning": "由于解析失败，使用段落上下文作为兜底查询"
        }
