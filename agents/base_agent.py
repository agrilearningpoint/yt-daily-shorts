"""Base agent module providing the abstract foundation for all pipeline agents.

Every concrete agent inherits from :class:`BaseAgent` and implements
the :meth:`execute` method.  Results are returned as :class:`AgentResult`
dataclass instances for uniform downstream handling.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List

from core.configuration import AppConfig
from core.state_manager import StateManager


@dataclass
class AgentResult:
    """Standardised result envelope returned by every agent.

    Attributes:
        success:  Whether the agent completed without critical errors.
        data:     Arbitrary payload produced by the agent.
        errors:   Human-readable error messages collected during execution.
        metadata: Extra contextual information (timings, model versions, etc.).
    """

    success: bool = False
    data: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseAgent(ABC):
    """Abstract base class for all pipeline agents.

    Parameters:
        config:        Application-wide configuration object.
        state_manager: Shared state manager for reading/writing pipeline state.
    """

    name: str = "BaseAgent"

    def __init__(self, config: AppConfig, state_manager: StateManager) -> None:
        self.config = config
        self.state_manager = state_manager
        self.logger = logging.getLogger(f"agents.{self.name}")

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def execute(self, **kwargs: Any) -> AgentResult:
        """Run the agent's primary workload.

        Subclasses **must** override this method.

        Returns:
            AgentResult with the outcome of the execution.
        """
        ...

    def validate_input(self, **kwargs: Any) -> bool:
        """Validate inputs before execution.

        The default implementation accepts everything.  Override in
        subclasses to enforce preconditions.

        Returns:
            ``True`` if inputs are acceptable, ``False`` otherwise.
        """
        return True

    def save_result(self, video_id: str, result: AgentResult) -> None:
        """Persist an agent result into the shared state store.

        Args:
            video_id: Unique identifier of the video being processed.
            result:   The :class:`AgentResult` to persist.
        """
        self.state_manager.log_agent(
            agent_name=self.name,
            video_id=video_id,
            action="execute",
            result=result.data,
            error="; ".join(result.errors) if result.errors else "",
        )
        self.logger.info(
            "Saved result for video_id=%s (success=%s)",
            video_id,
            result.success,
        )
