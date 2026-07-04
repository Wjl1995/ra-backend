class MCPConfigurationError(RuntimeError):
    """Raised when an MCP server or client is misconfigured."""


class MCPConnectionError(RuntimeError):
    """Raised when an MCP server connection is unavailable."""


class MCPToolError(RuntimeError):
    """Raised when an MCP tool call cannot be completed."""
