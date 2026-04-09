from __future__ import annotations

import argparse
import unittest

from flowctl import stack_ops


class StackOpsTests(unittest.TestCase):
    def test_command_stack_up_can_limit_services(self) -> None:
        calls: list[list[str]] = []

        def ensure_devcontainer_env() -> int:
            return 0

        def run_compose(args: list[str], _interactive: bool | None) -> int:
            calls.append(args)
            return 0

        rc = stack_ops.command_stack_up(
            argparse.Namespace(build=False),
            ensure_devcontainer_env=ensure_devcontainer_env,
            run_compose=run_compose,
            services=["workspace"],
        )

        self.assertEqual(0, rc)
        self.assertEqual([["up", "-d", "workspace"]], calls)

    def test_command_stack_up_build_keeps_build_flag_before_services(self) -> None:
        calls: list[list[str]] = []

        def ensure_devcontainer_env() -> int:
            return 0

        def run_compose(args: list[str], _interactive: bool | None) -> int:
            calls.append(args)
            return 0

        rc = stack_ops.command_stack_up(
            argparse.Namespace(build=True),
            ensure_devcontainer_env=ensure_devcontainer_env,
            run_compose=run_compose,
            services=["workspace"],
        )

        self.assertEqual(0, rc)
        self.assertEqual([["up", "-d", "--build", "workspace"]], calls)


if __name__ == "__main__":
    unittest.main()
