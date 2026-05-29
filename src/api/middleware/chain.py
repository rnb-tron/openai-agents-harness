"""Explicit HTTP protocol request-chain installation and lifecycle."""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import FastAPI

from src.api.middleware.base import ProtocolPlugin
from src.core.logging import setup_logger

logger = setup_logger("api.middleware.chain")


class ProtocolRequestChain:
    """An immutable protocol chain ordered as a request experiences it.

    ``request_order`` is outer-to-inner, for example
    ``RequestContext -> Auth -> RateLimit``. This is the public ordering model.
    FastAPI installs middleware in LIFO order, so ``install_on`` contains the
    one framework-specific reversal needed to produce that declared order.
    """

    def __init__(self, request_order: Sequence[ProtocolPlugin] = ()) -> None:
        self._request_order = tuple(request_order)
        self._installed = False

    @property
    def request_order(self) -> tuple[ProtocolPlugin, ...]:
        return self._request_order

    def install_on(self, app: FastAPI) -> None:
        """Install the declared request chain on a FastAPI application."""
        if self._installed:
            return
        # FastAPI middleware registration is LIFO; hide that adapter detail here.
        for plugin in reversed(self._request_order):
            plugin.install(app)
            logger.info("protocol_plugin_installed", extra={"plugin": plugin.name})
        self._installed = True

    async def startup(self) -> None:
        """Start protocol-owned resources in declared request order."""
        for plugin in self._request_order:
            try:
                await plugin.setup()
            except Exception as exc:
                logger.error(
                    "protocol_plugin_setup_failed",
                    extra={"plugin": plugin.name, "error": str(exc)},
                    exc_info=True,
                )
                raise

    async def shutdown(self) -> None:
        """Stop protocol-owned resources in reverse declared order."""
        for plugin in reversed(self._request_order):
            try:
                await plugin.teardown()
            except Exception as exc:
                logger.warning(
                    "protocol_plugin_teardown_failed",
                    extra={"plugin": plugin.name, "error": str(exc)},
                )
