"""测试Agent配置验证器"""

import pytest
from pathlib import Path

from fractalclaw.agent.config_validator import (
    ConfigValidator,
    AgentConfigSchema,
    ValidationResult,
    ValidationLevel,
)


class TestConfigValidator:
    """ConfigValidator测试类"""
    
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
    def validator(self, global_settings: dict) -> ConfigValidator:
        """创建验证器"""
        return ConfigValidator(global_settings)
    
    @pytest.fixture
    def valid_config(self) -> dict:
        """有效配置"""
        return {
            "name": "TestAgent",
            "description": "测试Agent",
            "role": "worker",
            "system_prompt": "这是一个测试Agent，用于验证配置是否正确。",
            "llm": {
                "model": "gpt-4",
                "temperature": 0.5
            },
            "behavior": {
                "max_iterations": 15
            },
            "tools": [
                {
                    "name": "test_tool",
                    "description": "测试工具",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "input": {"type": "string"}
                        },
                        "required": ["input"]
                    }
                }
            ]
        }
    
    def test_validate_valid_config(self, validator: ConfigValidator, valid_config: dict):
        """测试验证有效配置"""
        results = validator.validate(valid_config, "agent_a1b2c3d4_test")
        
        errors = [r for r in results if r.level == ValidationLevel.ERROR]
        assert len(errors) == 0
    
    def test_validate_missing_required_fields(self, validator: ConfigValidator):
        """测试缺少必填字段"""
        config = {"name": "TestAgent"}
        results = validator.validate(config)
        
        errors = [r for r in results if r.level == ValidationLevel.ERROR]
        assert len(errors) > 0
        
        error_fields = [r.field for r in errors]
        assert "description" in error_fields
        assert "role" in error_fields
        assert "system_prompt" in error_fields
    
    def test_validate_invalid_role(self, validator: ConfigValidator, valid_config: dict):
        """测试无效角色"""
        valid_config["role"] = "invalid_role"
        results = validator.validate(valid_config)
        
        errors = [r for r in results if r.level == ValidationLevel.ERROR]
        assert any(r.field == "role" for r in errors)
    
    def test_validate_invalid_temperature(self, validator: ConfigValidator, valid_config: dict):
        """测试无效温度值"""
        valid_config["llm"]["temperature"] = 3.0
        results = validator.validate(valid_config)
        
        errors = [r for r in results if r.level == ValidationLevel.ERROR]
        assert any(r.field == "llm.temperature" for r in errors)
    
    def test_validate_missing_llm_config(self, validator: ConfigValidator, valid_config: dict):
        """测试缺少LLM配置"""
        del valid_config["llm"]
        results = validator.validate(valid_config)
        
        warnings = [r for r in results if r.level == ValidationLevel.WARNING]
        assert any(r.field == "llm" for r in warnings)
    
    def test_validate_missing_model(self, validator: ConfigValidator, valid_config: dict):
        """测试缺少模型配置"""
        del valid_config["llm"]["model"]
        del valid_config["llm"]["temperature"]
        
        validator_no_global = ConfigValidator({})
        results = validator_no_global.validate(valid_config)
        
        errors = [r for r in results if r.level == ValidationLevel.ERROR]
        assert any(r.field == "llm.model" for r in errors)
    
    def test_validate_tool_missing_fields(self, validator: ConfigValidator, valid_config: dict):
        """测试工具缺少必填字段"""
        valid_config["tools"] = [{"name": "incomplete_tool"}]
        results = validator.validate(valid_config)
        
        errors = [r for r in results if r.level == ValidationLevel.ERROR]
        assert any("tools[0]" in r.field for r in errors)
    
    def test_validate_agent_id_format(self, validator: ConfigValidator, valid_config: dict):
        """测试Agent ID格式"""
        results = validator.validate(valid_config, "invalid_id")
        
        errors = [r for r in results if r.level == ValidationLevel.ERROR]
        assert any(r.field == "agent_id" for r in errors)
    
    def test_validate_short_system_prompt(self, validator: ConfigValidator, valid_config: dict):
        """测试过短的系统提示词"""
        valid_config["system_prompt"] = "太短"
        results = validator.validate(valid_config)
        
        warnings = [r for r in results if r.level == ValidationLevel.WARNING]
        assert any(r.field == "system_prompt" for r in warnings)
    
    def test_get_missing_fields(self, validator: ConfigValidator):
        """测试获取缺失字段"""
        config = {"name": "TestAgent"}
        missing = validator.get_missing_fields(config)
        
        assert "description" in missing["required"]
        assert "role" in missing["required"]
    
    def test_get_config_template(self, validator: ConfigValidator):
        """测试获取配置模板"""
        template = validator.get_config_template("worker")
        
        assert "name" in template
        assert "description" in template
        assert "role" in template
        assert template["role"] == "worker"
    
    def test_get_config_template_coordinator(self, validator: ConfigValidator):
        """测试获取协调者配置模板"""
        template = validator.get_config_template("coordinator")
        
        assert template["role"] == "coordinator"
        assert "children" in template


class TestAgentConfigSchema:
    """AgentConfigSchema测试类"""
    
    def test_schema_fields(self):
        """测试模式字段"""
        schema = AgentConfigSchema()
        
        assert "name" in schema.REQUIRED_FIELDS
        assert "description" in schema.REQUIRED_FIELDS
        assert "role" in schema.REQUIRED_FIELDS
        
        assert "worker" in schema.ROLE_VALUES
        assert "specialist" in schema.ROLE_VALUES
        assert "coordinator" in schema.ROLE_VALUES
    
    def test_uuid_pattern(self):
        """测试UUID模式"""
        schema = AgentConfigSchema()
        
        import re
        pattern = re.compile(schema.UUID_PATTERN)
        
        assert pattern.match("agent_a1b2c3d4_coder")
        assert pattern.match("agent_12345678_test_agent")
        assert not pattern.match("invalid_id")
        assert not pattern.match("agent_short_name")


class TestValidationResult:
    """ValidationResult测试类"""
    
    def test_error_result(self):
        """测试错误结果"""
        result = ValidationResult(
            is_valid=False,
            level=ValidationLevel.ERROR,
            field="name",
            message="缺少必填字段",
            suggestion="请添加name字段"
        )
        
        assert result.is_valid == False
        assert result.level == ValidationLevel.ERROR
        assert result.suggestion is not None
    
    def test_warning_result(self):
        """测试警告结果"""
        result = ValidationResult(
            is_valid=True,
            level=ValidationLevel.WARNING,
            field="llm",
            message="未配置LLM参数"
        )
        
        assert result.is_valid == True
        assert result.level == ValidationLevel.WARNING
