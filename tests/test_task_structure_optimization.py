#!/usr/bin/env python3
"""测试任务工作区文件结构优化"""

import asyncio
import tempfile
from pathlib import Path

from fractalclaw.scheduler.scheduler import TaskScheduler, TaskStatus, TaskPriority
from fractalclaw.scheduler.agent_workspace import AgentWorkspaceManager, WorkDocument
from fractalclaw.memory import MemoryManager, MemoryConfig


async def test_task_structure():
    """测试任务创建后的文件结构"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_root = Path(tmpdir) / "workspace"
        workspace_root.mkdir(parents=True)
        
        scheduler = TaskScheduler(workspace_root=str(workspace_root))
        
        task = scheduler.create_task(
            name="测试任务",
            description="这是一个测试任务",
            instruction="测试任务工作区文件结构优化",
            priority=TaskPriority.HIGH
        )
        
        print(f"任务创建成功: {task.id}")
        print(f"工作区路径: {task.workspace_path}")
        
        task_path = Path(task.workspace_path)
        
        print("\n=== 验证文件结构 ===")
        
        print("\n1. 检查 output 目录:")
        output_dir = task_path / "output"
        if output_dir.exists():
            print("   ✅ output 目录存在")
        else:
            print("   ❌ output 目录不存在")
        
        print("\n2. 检查 README.md 是否删除:")
        readme_path = task_path / "README.md"
        if not readme_path.exists():
            print("   ✅ README.md 已删除")
        else:
            print("   ❌ README.md 仍然存在")
        
        print("\n3. 检查 task_metadata.json 是否删除:")
        old_metadata_path = task_path / "task_metadata.json"
        if not old_metadata_path.exists():
            print("   ✅ task_metadata.json 已删除")
        else:
            print("   ❌ task_metadata.json 仍然存在")
        
        print("\n4. 检查 memory/semantic/task_metadata.yaml:")
        new_metadata_path = task_path / "memory" / "semantic" / "task_metadata.yaml"
        if new_metadata_path.exists():
            print("   ✅ task_metadata.yaml 存在")
            import yaml
            with open(new_metadata_path, 'r', encoding='utf-8') as f:
                metadata = yaml.safe_load(f)
            print(f"   任务ID: {metadata['id']}")
            print(f"   任务名称: {metadata['name']}")
            print(f"   任务状态: {metadata['status']}")
        else:
            print("   ❌ task_metadata.yaml 不存在")
        
        print("\n5. 检查 memory 目录结构:")
        memory_path = task_path / "memory"
        if memory_path.exists():
            print("   ✅ memory 目录存在")
            
            semantic_dir = memory_path / "semantic"
            episodic_dir = memory_path / "episodic"
            shared_dir = memory_path / "shared"
            
            if semantic_dir.exists():
                print("   ✅ semantic 目录存在")
            else:
                print("   ❌ semantic 目录不存在")
            
            if episodic_dir.exists():
                print("   ✅ episodic 目录存在")
                daily_dir = episodic_dir / "daily"
                sessions_dir = episodic_dir / "sessions"
                if daily_dir.exists():
                    print("   ✅ episodic/daily 目录存在")
                else:
                    print("   ❌ episodic/daily 目录不存在")
                if sessions_dir.exists():
                    print("   ✅ episodic/sessions 目录存在")
                else:
                    print("   ❌ episodic/sessions 目录不存在")
            else:
                print("   ❌ episodic 目录不存在")
            
            if shared_dir.exists():
                print("   ✅ shared 目录存在")
            else:
                print("   ❌ shared 目录不存在")
        else:
            print("   ❌ memory 目录不存在")
        
        print("\n6. 检查 memory/INDEX.md:")
        index_path = memory_path / "INDEX.md"
        if index_path.exists():
            print("   ✅ INDEX.md 存在")
            content = index_path.read_text(encoding='utf-8')
            print(f"   内容预览:\n{content[:200]}...")
        else:
            print("   ❌ INDEX.md 不存在")
        
        print("\n=== 测试完成 ===")


async def test_work_document():
    """测试 work.md 迁移到 memory/semantic/task_requirements.md"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_root = Path(tmpdir) / "workspace"
        workspace_root.mkdir(parents=True)
        
        workspace_manager = AgentWorkspaceManager(workspace_root)
        
        test_workspace = workspace_root / "test_task"
        test_workspace.mkdir(parents=True)
        
        work_doc = WorkDocument(
            task_requirement="测试任务需求",
            acceptance_criteria="验收标准",
            created_at="2026-04-14T10:00:00",
            updated_at="2026-04-14T10:00:00"
        )
        
        workspace_manager.write_work_document(test_workspace, work_doc)
        
        print("\n=== 测试 work.md 迁移 ===")
        
        old_work_path = test_workspace / "work.md"
        if not old_work_path.exists():
            print("   ✅ work.md 已删除")
        else:
            print("   ❌ work.md 仍然存在")
        
        new_work_path = test_workspace / "memory" / "semantic" / "task_requirements.md"
        if new_work_path.exists():
            print("   ✅ task_requirements.md 存在")
            content = new_work_path.read_text(encoding='utf-8')
            print(f"   内容预览:\n{content[:200]}...")
        else:
            print("   ❌ task_requirements.md 不存在")
        
        print("\n=== 测试完成 ===")


if __name__ == "__main__":
    print("开始测试任务工作区文件结构优化...\n")
    
    asyncio.run(test_task_structure())
    asyncio.run(test_work_document())
    
    print("\n所有测试完成！")
