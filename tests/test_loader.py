"""测试Agent配置加载器"""

import pytest
from pathlib import Path

from fractalclaw.agent.loader import ConfigLoader, AgentConfigData, GlobalSettings


class TestConfigLoader:
    """ConfigLoader测试类"""
    
    @pytest.fixture
    def config_dir(self) -> Path:
        """获取配置目录"""
        return Path(__file__).parent.parent / "configs"
    
    @pytest.fixture
    def loader(self, config_dir: Path) -> ConfigLoader:
        """创建配置加载器"""
        return ConfigLoader(config_dir)
    
    def test_load_settings(self, loader: ConfigLoader):
        """测试加载全局配置"""
        settings = loader.load_settings()
        
        assert isinstance(settings, GlobalSettings)
        assert settings.llm.get('temperature') == 0.7
        assert settings.behavior.get('max_iterations') == 10
        assert settings.behavior.get('enable_planning') == True
    
    def test_load_agent(self, loader: ConfigLoader):
        """测试加载Agent配置"""
        config = loader.load('agent_b2c3d4e5_coder')
        
        assert isinstance(config, AgentConfigData)
        assert config.name == 'CodeAgent'
        assert config.role == 'specialist'
        assert config.parent == ''
    
    def test_load_agent_with_inheritance(self, loader: ConfigLoader):
        """测试加载带继承的Agent配置"""
        config = loader.load('agent_b2c3d4e5_coder')
        
        assert config.llm.get('temperature') == 0.3
        assert config.llm.get('max_tokens') == 8192
        assert config.behavior.get('max_iterations') == 15
    
    def test_load_agent_with_tools(self, loader: ConfigLoader):
        """测试加载带工具的Agent配置"""
        config = loader.load('agent_b2c3d4e5_coder')
        
        assert len(config.tools) > 0
        tool_names = [t.get('name') for t in config.tools]
        assert 'read_file' in tool_names
        assert 'write_file' in tool_names
    
    def test_load_agent_with_children(self, loader: ConfigLoader):
        """测试加载带子Agent的配置"""
        config = loader.load('agent_d4e5f6a7_coordinator')
        
        assert len(config.children) > 0
        assert 'agent_b2c3d4e5_coder' in config.children
        assert 'agent_c3d4e5f6_researcher' in config.children
    
    def test_list_agents(self, loader: ConfigLoader):
        """测试列出所有Agent"""
        agents = loader.list_agents()
        
        assert 'agent_b2c3d4e5_coder' in agents
        assert 'agent_c3d4e5f6_researcher' in agents
        assert 'agent_d4e5f6a7_coordinator' in agents
        assert 'agent_a1b2c3d4_base_worker' in agents
    
    def test_load_nonexistent_agent(self, loader: ConfigLoader):
        """测试加载不存在的Agent"""
        with pytest.raises(FileNotFoundError):
            loader.load('nonexistent_agent')
    
    def test_cache(self, loader: ConfigLoader):
        """测试配置缓存"""
        config1 = loader.load('agent_b2c3d4e5_coder')
        config2 = loader.load('agent_b2c3d4e5_coder')
        
        assert config1 is config2
    
    def test_clear_cache(self, loader: ConfigLoader):
        """测试清除缓存"""
        loader.load('agent_b2c3d4e5_coder')
        loader.clear_cache()
        
        assert 'agent_b2c3d4e5_coder' not in loader._cache
    
    def test_reload(self, loader: ConfigLoader):
        """测试重新加载配置"""
        config1 = loader.load('agent_b2c3d4e5_coder')
        config2 = loader.reload('agent_b2c3d4e5_coder')
        
        assert config1 is not config2
        assert config1.name == config2.name


class TestGlobalSettings:
    """GlobalSettings测试类"""
    
    def test_default_values(self):
        """测试默认值"""
        settings = GlobalSettings()
        
        assert settings.llm.get('model') == 'gpt-4'
        assert settings.behavior.get('max_iterations') == 10
    
    def test_custom_values(self):
        """测试自定义值"""
        settings = GlobalSettings(
            llm={'model': 'gpt-3.5-turbo'},
            behavior={'max_iterations': 20}
        )
        
        assert settings.llm.get('model') == 'gpt-3.5-turbo'
        assert settings.behavior.get('max_iterations') == 20


class TestAgentConfigData:
    """AgentConfigData测试类"""
    
    def test_default_values(self):
        """测试默认值"""
        config = AgentConfigData(name='TestAgent')
        
        assert config.name == 'TestAgent'
        assert config.role == 'worker'
        assert config.description == ''
        assert config.tools == []
    
    def test_custom_values(self):
        """测试自定义值"""
        config = AgentConfigData(
            name='TestAgent',
            description='Test Description',
            role='specialist',
            tools=[{'name': 'test_tool'}]
        )
        
        assert config.name == 'TestAgent'
        assert config.description == 'Test Description'
        assert config.role == 'specialist'
        assert len(config.tools) == 1
