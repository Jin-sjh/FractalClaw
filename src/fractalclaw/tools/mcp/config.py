"""MCP configuration management."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from fractalclaw.tools.mcp.types import McpHttpConfig, McpServerConfig, McpStdioConfig


@dataclass
class McpConfig:
    """Configuration for MCP servers."""

    servers: dict[str, McpServerConfig] = field(default_factory=dict)

    def add_server(self, name: str, config: McpServerConfig) -> None:
        """Add a server configuration."""
        self.servers[name] = config

    def remove_server(self, name: str) -> bool:
        """Remove a server configuration."""
        if name in self.servers:
            del self.servers[name]
            return True
        return False

    def get_server(self, name: str) -> Optional[McpServerConfig]:
        """Get a server configuration by name."""
        return self.servers.get(name)

    def list_servers(self) -> list[str]:
        """List all server names."""
        return list(self.servers.keys())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "McpConfig":
        """Create configuration from a dictionary.

        Args:
            data: Dictionary with server configurations

        Returns:
            McpConfig instance
        """
        config = cls()

        for name, server_data in data.get("servers", data).items():
            if isinstance(server_data, McpServerConfig):
                config.servers[name] = server_data
                continue

            server_type = server_data.get("type", "stdio")

            if server_type == "stdio":
                config.servers[name] = McpStdioConfig(
                    type="stdio",
                    command=server_data.get("command", ""),
                    args=server_data.get("args", []),
                    env=server_data.get("env", {}),
                    cwd=server_data.get("cwd"),
                )
            elif server_type == "http":
                config.servers[name] = McpHttpConfig(
                    type="http",
                    url=server_data.get("url", ""),
                    headers=server_data.get("headers"),
                    timeout=server_data.get("timeout", 30.0),
                )

        return config

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            name: config.to_dict() if hasattr(config, "to_dict") else config
            for name, config in self.servers.items()
        }

    @classmethod
    def from_file(cls, file_path: str) -> "McpConfig":
        """Load configuration from a JSON file.

        Args:
            file_path: Path to the configuration file

        Returns:
            McpConfig instance

        Raises:
            FileNotFoundError: If the file doesn't exist
            json.JSONDecodeError: If the file is not valid JSON
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        mcp_data = data.get("mcp", data)
        return cls.from_dict(mcp_data)

    def to_file(self, file_path: str) -> None:
        """Save configuration to a JSON file.

        Args:
            file_path: Path to save the configuration
        """
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump({"mcp": self.to_dict()}, f, indent=2)


def load_mcp_config(
    config_path: Optional[str] = None,
    search_paths: Optional[list[str]] = None,
) -> McpConfig:
    """Load MCP configuration from standard locations.

    Searches for configuration in:
    1. Specified config_path
    2. Current directory: ./mcp.json
    3. Project config: ./fractalclaw.json
    4. Built-in content configs: content/mcp/*.json
    5. User config: ~/.fractalclaw/mcp.json

    Args:
        config_path: Explicit path to configuration file
        search_paths: Additional paths to search

    Returns:
        McpConfig instance
    """
    content_mcp_dir = Path(__file__).parent.parent.parent / "content" / "mcp"
    
    builtin_configs = []
    if content_mcp_dir.exists():
        for json_file in content_mcp_dir.glob("*.json"):
            builtin_configs.append(str(json_file))
    
    default_search_paths = [
        "./mcp.json",
        "./fractalclaw.json",
        *builtin_configs,
        str(Path.home() / ".fractalclaw" / "mcp.json"),
    ]

    paths = [config_path] if config_path else []
    paths.extend(search_paths or [])
    paths.extend(default_search_paths)
    
    merged_config = McpConfig()
    
    for path in paths:
        if path:
            try:
                config = McpConfig.from_file(path)
                for name, server_config in config.servers.items():
                    if name not in merged_config.servers:
                        merged_config.servers[name] = server_config
            except (FileNotFoundError, json.JSONDecodeError, KeyError):
                continue

    return merged_config


def resolve_stdio_config(
    command: str,
    args: Optional[list[str]] = None,
    env: Optional[dict[str, str]] = None,
    cwd: Optional[str] = None,
) -> McpStdioConfig:
    """Create a stdio MCP configuration.

    Args:
        command: The command to run
        args: Command arguments
        env: Environment variables
        cwd: Working directory

    Returns:
        McpStdioConfig instance
    """
    return McpStdioConfig(
        type="stdio",
        command=command,
        args=args or [],
        env=env or {},
        cwd=cwd,
    )


def resolve_http_config(
    url: str,
    headers: Optional[dict[str, str]] = None,
    timeout: float = 30.0,
) -> McpHttpConfig:
    """Create an HTTP MCP configuration.

    Args:
        url: The server URL
        headers: HTTP headers
        timeout: Request timeout

    Returns:
        McpHttpConfig instance
    """
    return McpHttpConfig(
        type="http",
        url=url,
        headers=headers,
        timeout=timeout,
    )
