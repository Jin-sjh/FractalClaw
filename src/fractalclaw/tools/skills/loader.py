"""Skill loader for discovering and loading SKILL.md files."""

import os
from pathlib import Path
from typing import ClassVar, Optional

from fractalclaw.tools.skills.parser import parse_skill_file
from fractalclaw.tools.skills.types import SkillEntry


class SkillLoader:
    """Loader for discovering and loading skills from directories.

    Skills are loaded from:
    1. Built-in skills directory (package bundled)
    2. User skills directory (~/.fractalclaw/skills)
    3. Project skills directory (./skills)
    4. Additional directories specified at load time

    Example:
        skills = SkillLoader.load_all(["./custom_skills"])
        for skill in skills:
            print(f"Loaded: {skill.name}")
    """

    BUILTIN_SKILLS_DIR: ClassVar[str] = "skills"
    USER_SKILLS_DIR: ClassVar[str] = "~/.fractalclaw/skills"
    PROJECT_SKILLS_DIR: ClassVar[str] = "skills"
    SKILL_FILE_NAME: ClassVar[str] = "SKILL.md"

    @classmethod
    def load_all(
        cls,
        extra_dirs: Optional[list[str]] = None,
        include_builtin: bool = True,
        include_user: bool = True,
        include_project: bool = True,
        project_root: Optional[str] = None,
    ) -> list[SkillEntry]:
        """Load skills from all sources.

        Args:
            extra_dirs: Additional directories to search
            include_builtin: Whether to load built-in skills
            include_user: Whether to load user skills
            include_project: Whether to load project skills
            project_root: Project root directory (defaults to current directory)

        Returns:
            List of loaded skills
        """
        skills: list[SkillEntry] = []
        loaded_names: set[str] = set()

        def add_skill(skill: SkillEntry) -> None:
            if skill.name not in loaded_names:
                skills.append(skill)
                loaded_names.add(skill.name)

        if include_builtin:
            for skill in cls._load_builtin():
                add_skill(skill)

        if include_user:
            for skill in cls._load_user_skills():
                add_skill(skill)

        if include_project:
            for skill in cls._load_project_skills(project_root):
                add_skill(skill)

        for dir_path in extra_dirs or []:
            for skill in cls._load_from_dir(dir_path):
                add_skill(skill)

        return skills

    @classmethod
    def _load_builtin(cls) -> list[SkillEntry]:
        """Load built-in skills from package."""
        skills: list[SkillEntry] = []
        
        builtin_path = Path(__file__).parent.parent.parent.parent / cls.BUILTIN_SKILLS_DIR
        if builtin_path.exists():
            skills.extend(cls._load_from_dir(str(builtin_path)))
        
        content_skills_path = Path(__file__).parent.parent.parent / "content" / "skills"
        if content_skills_path.exists():
            skills.extend(cls._load_from_dir(str(content_skills_path)))
        
        return skills

    @classmethod
    def _load_user_skills(cls) -> list[SkillEntry]:
        """Load skills from user directory."""
        user_path = Path(cls.USER_SKILLS_DIR).expanduser()
        if user_path.exists():
            return cls._load_from_dir(str(user_path))
        return []

    @classmethod
    def _load_project_skills(cls, project_root: Optional[str] = None) -> list[SkillEntry]:
        """Load skills from project directory."""
        root = Path(project_root or ".")
        project_path = root / cls.PROJECT_SKILLS_DIR

        if project_path.exists():
            return cls._load_from_dir(str(project_path.absolute()))
        return []

    @classmethod
    def _load_from_dir(cls, dir_path: str) -> list[SkillEntry]:
        """Load all skills from a directory.

        Looks for SKILL.md files in subdirectories.

        Args:
            dir_path: Directory to search

        Returns:
            List of loaded skills
        """
        skills: list[SkillEntry] = []
        path = Path(dir_path)

        if not path.exists():
            return skills

        if path.is_file() and path.name == cls.SKILL_FILE_NAME:
            try:
                skill = parse_skill_file(str(path))
                skills.append(skill)
            except Exception:
                pass
            return skills

        for item in path.iterdir():
            if item.is_dir():
                skill_file = item / cls.SKILL_FILE_NAME
                if skill_file.exists():
                    try:
                        skill = parse_skill_file(str(skill_file))
                        skills.append(skill)
                    except Exception:
                        pass
            elif item.is_file() and item.name == cls.SKILL_FILE_NAME:
                try:
                    skill = parse_skill_file(str(item))
                    skills.append(skill)
                except Exception:
                    pass

        return skills

    @classmethod
    def load_single(cls, file_path: str) -> Optional[SkillEntry]:
        """Load a single skill file.

        Args:
            file_path: Path to the SKILL.md file

        Returns:
            Loaded skill or None if loading fails
        """
        try:
            return parse_skill_file(file_path)
        except Exception:
            return None

    @classmethod
    def discover_skill_directories(cls, start_path: str = ".") -> list[str]:
        """Discover all directories that might contain skills.

        Searches upward from start_path for 'skills' directories.

        Args:
            start_path: Starting directory for search

        Returns:
            List of discovered skill directories
        """
        discovered: list[str] = []
        current = Path(start_path).resolve()

        while True:
            skills_dir = current / cls.PROJECT_SKILLS_DIR
            if skills_dir.exists() and str(skills_dir) not in discovered:
                discovered.append(str(skills_dir))

            parent = current.parent
            if parent == current:
                break
            current = parent

        user_dir = Path(cls.USER_SKILLS_DIR).expanduser()
        if user_dir.exists() and str(user_dir) not in discovered:
            discovered.append(str(user_dir))

        return discovered

    @classmethod
    def get_skill_path(cls, skill_name: str, search_dirs: Optional[list[str]] = None) -> Optional[str]:
        """Get the file path for a skill by name.

        Args:
            skill_name: Name of the skill
            search_dirs: Directories to search (defaults to all)

        Returns:
            Path to the skill file or None if not found
        """
        dirs = search_dirs or cls.discover_skill_directories()

        for dir_path in dirs:
            skill_dir = Path(dir_path) / skill_name
            skill_file = skill_dir / cls.SKILL_FILE_NAME

            if skill_file.exists():
                return str(skill_file)

            direct_file = Path(dir_path) / cls.SKILL_FILE_NAME
            if direct_file.exists():
                try:
                    skill = parse_skill_file(str(direct_file))
                    if skill.name == skill_name:
                        return str(direct_file)
                except Exception:
                    pass

        return None
