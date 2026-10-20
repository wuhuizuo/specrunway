"""Installed `type: hub` step shim.

The Specify runtime loads this file from the control checkout's
``.specify/workflows/steps/hub/``. It immediately delegates to the
production bridge classes and actions in the same Python environment
(the ``hubcoord`` distribution), so step behavior lives in one package.
"""

from hubcoord.bridge import HubActionError, HubStep, envelope

__all__ = ["HubActionError", "HubStep", "envelope"]
