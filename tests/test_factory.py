"""Tests for unified agent factory and runtime child creation."""

import asyncio
from pathlib import Path

from fractalclaw.agent.base import AgentConfig, AgentRole, BaseAgent, SubAgentRequirement
from fractalclaw.agent.factory import AgentFactory
from fractalclaw.llm import LLMConfig
from fractalclaw.scheduler.agent_workspace import AgentWorkspaceManager


class DummyProvider:
    async def complete(self, messages, config, tools=None):
        raise NotImplementedError

    async def stream(self, messages, config, tools=None):
        if False:
            yield ""


class TestAgentFactory:
    def test_create_agent(self):
        config_dir = Path(__file__).parent.parent / "configs"
        factory = AgentFactory(config_dir)

        agent = factory.create("agent_b2c3d4e5_coder")

        assert isinstance(agent, BaseAgent)
        assert agent.name == "CodeAgent"
        assert agent.config.role == AgentRole.SPECIALIST

        tool_names = {tool.name for tool in agent.tools.list_tools()}
        assert {"read_file", "write_file", "execute_code"} <= tool_names

    def test_create_from_dict_with_workflow(self):
        config_dir = Path(__file__).parent.parent / "configs"
        factory = AgentFactory(config_dir)

        agent = factory.create_from_dict(
            {
                "name": "WorkflowAgent",
                "description": "Runs a predefined workflow",
                "role": "coordinator",
                "system_prompt": "Coordinate steps.",
                "tools": [{"name": "read_file"}],
                "workflow": {
                    "name": "demo",
                    "steps": [
                        {
                            "step": 1,
                            "name": "inspect",
                            "description": "Inspect files",
                            "action": "read relevant files",
                        }
                    ],
                },
            }
        )

        assert agent.config.workflow is not None
        assert agent.config.workflow.name == "demo"
        assert len(agent.config.workflow.steps) == 1
        assert agent.config.workflow.steps[0].action == "read relevant files"

    def test_create_runtime_child_persists_config_and_inherits_runtime(self, tmp_path):
        async def _run():
            config_dir = Path(__file__).parent.parent / "configs"
            workspace_manager = AgentWorkspaceManager(tmp_path)
            provider = DummyProvider()
            factory = AgentFactory(
                config_dir=config_dir,
                llm_provider=provider,
                workspace_manager=workspace_manager,
            )

            parent = factory.create_from_config(
                AgentConfig(
                    name="Root",
                    description="Coordinate the task",
                    role=AgentRole.ROOT,
                    llm_config=LLMConfig(model="gpt-4-turbo", stream=False),
                    enable_planning=True,
                )
            )
            parent_workspace = await workspace_manager.create_agent_workspace(parent)
            parent.set_workspace(parent_workspace, workspace_manager)

            requirement = SubAgentRequirement(
                agent_name="CodeChild",
                agent_type="coder",
                task_description="Implement a small code fix",
                required_tools=["read_file", "execute_code"],
                expected_output="Patch and summary",
            )

            child = await parent._create_subagent(requirement, depth=1)

            assert child.get_parent() is parent
            assert child.workspace_path is not None
            assert child.llm._provider is provider
            assert child.config.role == AgentRole.SPECIALIST
            assert child.config.plan_config is not None
            assert child.config.memory_config is not None

            child_tool_names = {tool.name for tool in child.tools.list_tools()}
            assert {"read", "bash"} <= child_tool_names

            runtime_config = child.workspace_path / "runtime_agent.yaml"
            copied_config = child.workspace_path / "agent_config.yaml"
            task_doc = child.workspace_path / "memory" / "semantic" / "task_requirements.md"

            assert runtime_config.exists()
            assert copied_config.exists()
            assert task_doc.exists()
            assert runtime_config.read_text(encoding="utf-8") == copied_config.read_text(encoding="utf-8")

            runtime_yaml = runtime_config.read_text(encoding="utf-8")
            assert "runtime_generated: true" in runtime_yaml
            assert "parent_agent_id:" in runtime_yaml
            assert "branch_path: root" in runtime_yaml
            assert "model_selection:" in runtime_yaml

        asyncio.run(_run())

    def test_simple_runtime_child_prefers_lower_cost_model(self, tmp_path):
        async def _run():
            config_dir = Path(__file__).parent.parent / "configs"
            workspace_manager = AgentWorkspaceManager(tmp_path)
            factory = AgentFactory(
                config_dir=config_dir,
                llm_provider=DummyProvider(),
                workspace_manager=workspace_manager,
            )

            parent = factory.create_from_config(
                AgentConfig(
                    name="Root",
                    description="Top-level coordinator",
                    role=AgentRole.ROOT,
                    llm_config=LLMConfig(model="gpt-4-turbo", stream=False),
                )
            )
            parent_workspace = await workspace_manager.create_agent_workspace(parent)
            parent.set_workspace(parent_workspace, workspace_manager)

            requirement = SubAgentRequirement(
                agent_name="CheapChild",
                agent_type="coder",
                task_description="Simple quick code edit",
                required_tools=["execute_code"],
                expected_output="Updated file",
            )

            artifacts = await factory.create_runtime_child(parent, requirement, depth=1)

            assert artifacts.agent.config.llm_config is not None
            assert artifacts.agent.config.llm_config.model != parent.config.llm_config.model
            assert artifacts.agent.config.llm_config.model == "deepseek-coder"
            assert artifacts.config["llm"]["selection_reason"]
            assert artifacts.config["metadata"]["model_selection"]["reason"]
            assert artifacts.config["metadata"]["lineage"]["parent_agent_id"] == parent.id

        asyncio.run(_run())
