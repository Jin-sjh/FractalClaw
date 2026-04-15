"""测试Agent工厂"""

import pytest
from pathlib import Path

from fractalclaw.agent.factory import AgentFactory
from fractalclaw.agent.base import Agent, AgentRole


class TestAgentFactory:
    """AgentFactory测试类"""
    
    @pytest.fixture
    def config_dir(self) -> Path:
        """获取配置目录"""
        return Path(__file__).parent.parent / "configs"
    
    @pytest.fixture
    def factory(self, config_dir: Path) -> AgentFactory:
        """创建Agent工厂"""
        return AgentFactory(config_dir)
    
    def test_create_agent(self, factory: AgentFactory):
        """测试创建Agent"""
        agent = factory.create('agent_b2c3d4e5_coder')
        
        assert isinstance(agent, Agent)
        assert agent.name == 'CodeAgent'
        assert agent.config.role == AgentRole.SPECIALIST
    
    def test_create_agent_with_inheritance(self, factory: AgentFactory):
        """测试创建带继承的Agent"""
        agent = factory.create('agent_b2c3d4e5_coder')
        
        assert agent.config.llm_config.temperature == 0.3
        assert agent.config.llm_config.model == 'gpt-4'
    
    def test_create_agent_with_tools(self, factory: AgentFactory):
        """测试创建带工具的Agent"""
        agent = factory.create('agent_b2c3d4e5_coder')
        
        tools = agent.tools.list_tools()
        tool_names = [t.name for t in tools]
        
        assert 'read_file' in tool_names
        assert 'write_file' in tool_names
    
    def test_create_agent_with_children(self, factory: AgentFactory):
        """测试创建带子Agent的Agent"""
        agent = factory.create('agent_d4e5f6a7_coordinator')
        
        children = agent.get_children()
        assert len(children) == 2
        
        child_names = [c.name for c in children]
        assert 'CodeAgent' in child_names
        assert 'ResearchAgent' in child_names
    
    def test_create_agent_cache(self, factory: AgentFactory):
        """测试Agent缓存"""
        agent1 = factory.create('agent_b2c3d4e5_coder')
        agent2 = factory.create('agent_b2c3d4e5_coder')
        
        assert agent1 is agent2
    
    def test_list_available(self, factory: AgentFactory):
        """测试列出可用Agent"""
        agents = factory.list_available()
        
        assert 'agent_b2c3d4e5_coder' in agents
        assert 'agent_c3d4e5f6_researcher' in agents
        assert 'agent_d4e5f6a7_coordinator' in agents
    
    def test_get_settings(self, factory: AgentFactory):
        """测试获取全局配置"""
        settings = factory.get_settings()
        
        assert settings.llm.get('temperature') == 0.7
        assert settings.behavior.get('max_iterations') == 10
    
    def test_get_agent(self, factory: AgentFactory):
        """测试获取已创建的Agent"""
        factory.create('agent_b2c3d4e5_coder')
        agent = factory.get_agent('agent_b2c3d4e5_coder')
        
        assert agent is not None
        assert agent.name == 'CodeAgent'
    
    def test_clear_agents(self, factory: AgentFactory):
        """测试清除Agent"""
        factory.create('agent_b2c3d4e5_coder')
        factory.clear_agents()
        
        assert factory.get_agent('agent_b2c3d4e5_coder') is None
    
    def test_reload_agent(self, factory: AgentFactory):
        """测试重新加载Agent"""
        agent1 = factory.create('agent_b2c3d4e5_coder')
        agent2 = factory.reload('agent_b2c3d4e5_coder')
        
        assert agent1 is not agent2
        assert agent1.name == agent2.name
    
    def test_create_from_dict(self, factory: AgentFactory):
        """测试从字典创建Agent"""
        config_dict = {
            'name': 'CustomAgent',
            'description': 'Custom Agent',
            'role': 'worker',
            'llm': {
                'temperature': 0.5
            },
            'behavior': {
                'max_iterations': 20
            }
        }
        
        agent = factory.create_from_dict(config_dict)
        
        assert agent.name == 'CustomAgent'
        assert agent.config.description == 'Custom Agent'
        assert agent.config.llm_config.temperature == 0.5
        assert agent.config.max_iterations == 20
    
    def test_register_tool_handler(self, factory: AgentFactory):
        """测试注册工具处理器"""
        async def custom_handler(**kwargs):
            return "custom result"
        
        factory.register_tool_handler('custom_tool', custom_handler)
        
        assert 'custom_tool' in factory._tool_handlers
        assert factory._tool_handlers['custom_tool'] == custom_handler
