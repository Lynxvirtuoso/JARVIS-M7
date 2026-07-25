"""
services/tools/registry.py
Extended Tool Registry for Phase 2.3 Tool Execution Layer.
"""

import logging
from typing import Dict, Optional, Callable
from services.tools.models import ToolMetadata

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Registry mapping tool names to metadata and executable handlers.
    """

    def __init__(self):
        self._tools: Dict[str, ToolMetadata] = {}
        self._handlers: Dict[str, Callable] = {}
        self._register_default_tools()

    def _register_default_tools(self):
        self.register_tool(
            ToolMetadata(tool_name="system_control", destructive=False, needs_confirmation=False, offline_capable=True)
        )
        self.register_tool(
            ToolMetadata(tool_name="file_system", destructive=True, needs_confirmation=True, offline_capable=True)
        )
        self.register_tool(
            ToolMetadata(tool_name="calendar_tool", destructive=True, needs_confirmation=True, offline_capable=True)
        )
        self.register_tool(
            ToolMetadata(tool_name="email_tool", destructive=True, needs_confirmation=True, offline_capable=False)
        )
        self.register_tool(
            ToolMetadata(tool_name="media_tool", destructive=False, needs_confirmation=False, offline_capable=True)
        )
        self.register_tool(
            ToolMetadata(tool_name="reminder_tool", destructive=False, needs_confirmation=False, offline_capable=True)
        )
        self.register_tool(
            ToolMetadata(tool_name="llm_summarizer", destructive=False, needs_confirmation=False, offline_capable=True)
        )

    def register_tool(self, metadata: ToolMetadata, handler: Optional[Callable] = None):
        self._tools[metadata.tool_name] = metadata
        if handler:
            self._handlers[metadata.tool_name] = handler
        logger.debug(f"[TOOL_REGISTRY] Registered tool: {metadata.tool_name}")

    def get_metadata(self, tool_name: str) -> Optional[ToolMetadata]:
        return self._tools.get(tool_name)

    def get_handler(self, tool_name: str) -> Optional[Callable]:
        return self._handlers.get(tool_name)


tool_registry = ToolRegistry()
