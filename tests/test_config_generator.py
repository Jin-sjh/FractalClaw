"""测试Agent配置生成器"""

import pytest
from pathlib import Path
import tempfile
import os

from fractalclaw.agent.config_generator import (
    AgentConfigGenerator,
    GenerationResult,
)


class TestAgentConfigGenerator:
    """AgentConfigGenerator测试类"""
    
    @pytest.fixture
    def temp_dir(self) -> Path:
        """临时目录"""
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)
    
    @pytest.fixture
    def global_settings(self) -> dict:
        """全局配置"""
        return {
            "llm": {
                "temperature": 0.7,
                "max_tokens": 4096
            },
            "behavior": {
                "max_iterations": 10,
                "enable_planning": True
            }
        }
    
    @pytest.fixture
    def generator(self, temp_dir: Path, global_settings: dict) -> AgentConfigGenerator:
        """创建生成器"""
        return AgentConfigGenerator(
            config_dir=temp_dir,
            global_settings=global_settings
        )
    
    def test_generate_basic_config(self, generator: AgentConfigGenerator):
        """测试生成基本配置"""
        result = generator.generate(
            name="TestAgent",
            description="测试Agent",
            role="worker",
            save=False
        )
        
        assert result.success == True
        assert "agent_" in result.agent_id
        assert result.config_content["name"] == "TestAgent"
        assert result.config_content["role"] == "worker"
    
    def test_generate_with_tools(self, generator: AgentConfigGenerator):
        """测试生成带工具的配置"""
        result = generator.generate(
            name="CodeAgent",
            description="代码Agent",
            role="specialist",
            tools=["read_file", "write_file"],
            save=False
        )
        
        assert result.success == True
        assert len(result.config_content["tools"]) == 2
        
        tool_names = [t["name"] for t in result.config_content["tools"]]
        assert "read_file" in tool_names
        assert "write_file" in tool_names
    
    def test_generate_with_capabilities(self, generator: AgentConfigGenerator):
        """测试生成带能力的配置"""
        result = generator.generate(
            name="ResearchAgent",
            description="研究Agent",
            role="specialist",
            capabilities=["信息搜索", "数据分析"],
            save=False
        )
        
        assert result.success == True
        assert "信息搜索" in result.config_content["system_prompt"]
        assert "数据分析" in result.config_content["system_prompt"]
    
    def test_generate_with_parent(self, generator: AgentConfigGenerator):
        """测试生成带父Agent的配置"""
        result = generator.generate(
            name="ChildAgent",
            description="子Agent",
            role="worker",
            parent="agent_parent_base",
            save=False
        )
        
        assert result.success == True
        assert result.config_content["parent"] == "agent_parent_base"
    
    def test_generate_with_children(self, generator: AgentConfigGenerator):
        """测试生成带子Agent的配置"""
        result = generator.generate(
            name="CoordinatorAgent",
            description="协调Agent",
            role="coordinator",
            children=["agent_child1", "agent_child2"],
            save=False
        )
        
        assert result.success == True
        assert "agent_child1" in result.config_content["children"]
        assert "agent_child2" in result.config_content["children"]
    
    def test_generate_with_llm_config(self, generator: AgentConfigGenerator):
        """测试生成带LLM配置的配置"""
        result = generator.generate(
            name="CustomAgent",
            description="自定义Agent",
            role="specialist",
            llm_config={
                "model": "gpt-4-turbo",
                "temperature": 0.3
            },
            save=False
        )
        
        assert result.success == True
        assert result.config_content["llm"]["model"] == "gpt-4-turbo"
        assert result.config_content["llm"]["temperature"] == 0.3
    
    def test_generate_and_save(self, generator: AgentConfigGenerator, temp_dir: Path):
        """测试生成并保存配置"""
        result = generator.generate(
            name="SaveAgent",
            description="保存测试Agent",
            role="worker",
            save=True
        )
        
        assert result.success == True
        assert result.config_path is not None
        assert result.config_path.exists()
        assert result.config_path.parent == temp_dir
    
    async def test_generate_from_requirement_code(self, generator: AgentConfigGenerator):
        """测试从需求生成代码Agent"""
        result = await generator.generate_from_requirement(
            "创建一个代码开发Agent，能够编写和调试代码",
            save=False
        )
        
        assert result.success == True
        assert result.config_content["role"] == "specialist"
        
        tool_names = [t["name"] for t in result.config_content.get("tools", [])]
        assert "read_file" in tool_names or "execute_code" in tool_names
    
    async def test_generate_from_requirement_research(self, generator: AgentConfigGenerator):
        """测试从需求生成研究Agent"""
        result = await generator.generate_from_requirement(
            "需要一个研究分析Agent，能够搜索和分析信息",
            save=False
        )
        
        assert result.success == True
        assert result.config_content["role"] == "specialist"
    
    async def test_generate_from_requirement_coordinator(self, generator: AgentConfigGenerator):
        """测试从需求生成协调Agent"""
        result = await generator.generate_from_requirement(
            "创建一个协调管理Agent，负责分配任务",
            save=False
        )
        
        assert result.success == True
        assert result.config_content["role"] == "coordinator"
    
    def test_generate_agent_id_format(self, generator: AgentConfigGenerator):
        """测试生成的Agent ID格式"""
        result = generator.generate(
            name="Test Agent",
            description="测试",
            role="worker",
            save=False
        )
        
        import re
        pattern = re.compile(r"^agent_[a-f0-9]{8}_[a-z0-9_]+$")
        
        assert pattern.match(result.agent_id)
    
    def test_list_tool_templates(self, generator: AgentConfigGenerator):
        """测试列出工具模板"""
        templates = generator.list_tool_templates()
        
        assert "read_file" in templates
        assert "write_file" in templates
        assert "execute_code" in templates
        assert "web_search" in templates
    
    def test_get_missing_required_config(self, generator: AgentConfigGenerator):
        """测试获取缺失配置"""
        config = {"name": "TestAgent"}
        missing = generator.get_missing_required_config(config)
        
        assert "description" in missing["required"]
        assert "role" in missing["required"]
    
    def test_generate_with_invalid_role(self, generator: AgentConfigGenerator):
        """测试无效角色"""
        result = generator.generate(
            name="InvalidAgent",
            description="无效角色Agent",
            role="invalid_role",
            save=False
        )
        
        assert result.success == False
        assert any("role" in r.field for r in result.validation_results)


class TestGenerationResult:
    """GenerationResult测试类"""
    
    def test_success_result(self):
        """测试成功结果"""
        result = GenerationResult(
            success=True,
            agent_id="agent_test",
            config_path=None,
            config_content={"name": "Test"},
            validation_results=[],
            message="成功"
        )
        
        assert result.success == True
        assert result.agent_id == "agent_test"
    
    def test_failure_result(self):
        """测试失败结果"""
        from fractalclaw.agent.config_validator import ValidationResult, ValidationLevel
        
        result = GenerationResult(
            success=False,
            agent_id="agent_test",
            config_path=None,
            config_content={},
            validation_results=[
                ValidationResult(
                    is_valid=False,
                    level=ValidationLevel.ERROR,
                    field="name",
                    message="缺少名称"
                )
            ],
            message="失败"
        )
        
        assert result.success == False
        assert len(result.validation_results) == 1
