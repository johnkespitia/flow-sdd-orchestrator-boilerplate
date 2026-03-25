#!/usr/bin/env python3

from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FLOW_PATH = ROOT / "flow"


class FlowCallCollector(ast.NodeVisitor):
    def __init__(self, import_map: dict[str, tuple[str, str]]) -> None:
        self.import_map = import_map
        self.function_stack: list[str] = []
        self.calls: list[dict[str, object]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            callee = node.func.id
            if callee in self.import_map:
                module_name, function_name = self.import_map[callee]
                kwargs = [kw.arg for kw in node.keywords if kw.arg is not None]
                self.calls.append(
                    {
                        "lineno": node.lineno,
                        "wrapper": self.function_stack[-1] if self.function_stack else "<module>",
                        "callee_alias": callee,
                        "module_name": module_name,
                        "function_name": function_name,
                        "kwargs": kwargs,
                    }
                )
        self.generic_visit(node)


def build_import_map(flow_tree: ast.AST) -> dict[str, tuple[str, str]]:
    mapping: dict[str, tuple[str, str]] = {}
    for node in getattr(flow_tree, "body", []):
        if not isinstance(node, ast.ImportFrom):
            continue
        module_name = node.module or ""
        if not module_name.startswith("flowctl."):
            continue
        for imported in node.names:
            local_name = imported.asname or imported.name
            mapping[local_name] = (module_name, imported.name)
    return mapping


def function_signature(module_name: str, function_name: str) -> tuple[set[str], bool] | None:
    module_path = ROOT / (module_name.replace(".", "/") + ".py")
    if not module_path.is_file():
        return None

    module_tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    for node in module_tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            args = node.args
            param_names = {
                arg.arg
                for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]
            }
            accepts_var_kw = args.kwarg is not None
            return param_names, accepts_var_kw
    return None


def main() -> int:
    flow_tree = ast.parse(FLOW_PATH.read_text(encoding="utf-8"), filename=str(FLOW_PATH))
    import_map = build_import_map(flow_tree)
    collector = FlowCallCollector(import_map)
    collector.visit(flow_tree)

    findings: list[str] = []
    signature_cache: dict[tuple[str, str], tuple[set[str], bool] | None] = {}
    for call in collector.calls:
        module_name = str(call["module_name"])
        function_name = str(call["function_name"])
        cache_key = (module_name, function_name)
        if cache_key not in signature_cache:
            signature_cache[cache_key] = function_signature(module_name, function_name)
        signature = signature_cache[cache_key]
        if signature is None:
            continue
        param_names, accepts_var_kw = signature
        if accepts_var_kw:
            continue
        unknown = [kw for kw in call["kwargs"] if kw not in param_names]
        if not unknown:
            continue
        findings.append(
            f"{FLOW_PATH.name}:{call['lineno']} wrapper `{call['wrapper']}` -> "
            f"`{module_name}.{function_name}` usa kwargs inexistentes: {', '.join(sorted(unknown))}"
        )

    if findings:
        print("Flow/flowctl signature drift detected:", file=sys.stderr)
        for item in findings:
            print(f"- {item}", file=sys.stderr)
        return 1

    print("flow/flowctl signature check: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
