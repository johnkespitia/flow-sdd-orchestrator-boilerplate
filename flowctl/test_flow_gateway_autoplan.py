from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import unittest
from pathlib import Path


FLOW_PATH = Path(__file__).resolve().parents[1] / "flow"
FLOW_SPEC = importlib.util.spec_from_loader(
    "flow_cli",
    importlib.machinery.SourceFileLoader("flow_cli", str(FLOW_PATH)),
)
FLOW = importlib.util.module_from_spec(FLOW_SPEC)
assert FLOW_SPEC.loader is not None
FLOW_SPEC.loader.exec_module(FLOW)


class FlowGatewayAutoPlanWiringTests(unittest.TestCase):
    def test_command_gateway_poll_wires_auto_plan_callback_to_command_plan(self) -> None:
        recorded_specs: list[str] = []

        original_command_plan = FLOW.command_plan
        original_gateway_poll = FLOW.flow_gateway_ops.command_gateway_poll
        try:
            FLOW.command_plan = lambda args: recorded_specs.append(str(args.spec)) or 0

            def _fake_gateway_poll(args, **kwargs):  # type: ignore[no-untyped-def]
                self.assertIn("auto_plan_callback", kwargs)
                callback = kwargs["auto_plan_callback"]
                self.assertEqual(0, callback("demo-spec"))
                return 0

            FLOW.flow_gateway_ops.command_gateway_poll = _fake_gateway_poll
            rc = FLOW.command_gateway_poll(argparse.Namespace())
        finally:
            FLOW.command_plan = original_command_plan
            FLOW.flow_gateway_ops.command_gateway_poll = original_gateway_poll

        self.assertEqual(0, rc)
        self.assertEqual(["demo-spec"], recorded_specs)

    def test_command_gateway_watch_wires_auto_plan_callback_to_command_plan(self) -> None:
        recorded_specs: list[str] = []

        original_command_plan = FLOW.command_plan
        original_gateway_watch = FLOW.flow_gateway_ops.command_gateway_watch
        try:
            FLOW.command_plan = lambda args: recorded_specs.append(str(args.spec)) or 0

            def _fake_gateway_watch(args, **kwargs):  # type: ignore[no-untyped-def]
                self.assertIn("auto_plan_callback", kwargs)
                callback = kwargs["auto_plan_callback"]
                self.assertEqual(0, callback("demo-watch"))
                return 0

            FLOW.flow_gateway_ops.command_gateway_watch = _fake_gateway_watch
            rc = FLOW.command_gateway_watch(argparse.Namespace())
        finally:
            FLOW.command_plan = original_command_plan
            FLOW.flow_gateway_ops.command_gateway_watch = original_gateway_watch

        self.assertEqual(0, rc)
        self.assertEqual(["demo-watch"], recorded_specs)


if __name__ == "__main__":
    unittest.main()
