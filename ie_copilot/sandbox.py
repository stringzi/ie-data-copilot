# -*- coding: utf-8 -*-
"""模型生成代码的受限执行环境。

三层防护：
1. AST 白名单：禁止 import、文件读写、系统调用与下划线属性；
2. 安全 builtins：只暴露分析所需的少量内置函数；
3. 超时与结果校验：防止死循环拖垮页面，并限制返回体大小。

注意：这是应用层防护，不能替代容器级隔离。若部署在公网，仍建议限制 CPU/内存。
"""

from __future__ import annotations

import ast
import builtins
import threading
from typing import Any

import numpy as np
import pandas as pd

MAX_CODE_LENGTH = 4000
MAX_AST_NODES = 800
DEFAULT_TIMEOUT_SECONDS = 20.0

SAFE_BUILTIN_NAMES = [
    "abs",
    "all",
    "any",
    "bool",
    "dict",
    "divmod",
    "enumerate",
    "filter",
    "float",
    "format",
    "frozenset",
    "int",
    "isinstance",
    "len",
    "list",
    "map",
    "max",
    "min",
    "pow",
    "range",
    "repr",
    "reversed",
    "round",
    "set",
    "slice",
    "sorted",
    "str",
    "sum",
    "tuple",
    "zip",
    "Exception",
    "ValueError",
    "TypeError",
    "KeyError",
    "IndexError",
    "ZeroDivisionError",
    "ArithmeticError",
]
SAFE_BUILTINS = {name: getattr(builtins, name) for name in SAFE_BUILTIN_NAMES}

FORBIDDEN_NODES = (
    ast.Import,
    ast.ImportFrom,
    ast.Global,
    ast.Nonlocal,
    ast.With,
    ast.AsyncWith,
    ast.ClassDef,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.Await,
    ast.AsyncFor,
    ast.Yield,
    ast.YieldFrom,
)

FORBIDDEN_NAMES = {
    "eval",
    "exec",
    "compile",
    "open",
    "input",
    "globals",
    "locals",
    "vars",
    "getattr",
    "setattr",
    "delattr",
    "dir",
    "breakpoint",
    "help",
    "exit",
    "quit",
    "os",
    "sys",
    "subprocess",
    "socket",
    "shutil",
    "pathlib",
    "importlib",
    "pickle",
    "requests",
    "urllib",
    "ctypes",
    "builtins",
    "__import__",
}

FORBIDDEN_ATTRS = {
    "system",
    "popen",
    "spawn",
    "spawnl",
    "spawnv",
    "fork",
    "execv",
    "execve",
    "eval",
    "compile",
    "open",
    "os",
    "sys",
    "subprocess",
    "socket",
    "shutil",
    "pathlib",
    "importlib",
    "pickle",
    "requests",
    "urllib",
    "ctypes",
    "io",
    "glob",
    "tempfile",
    "inspect",
    "traceback",
    "plot",
    "read_csv",
    "read_table",
    "read_pickle",
    "read_excel",
    "read_json",
    "read_html",
    "read_sql",
    "read_sql_query",
    "read_sql_table",
    "read_parquet",
    "read_feather",
    "read_hdf",
    "read_stata",
    "read_sas",
    "read_spss",
    "read_xml",
    "read_clipboard",
    "read_fwf",
    "read_orc",
    "to_csv",
    "to_pickle",
    "to_excel",
    "to_json",
    "to_html",
    "to_xml",
    "to_sql",
    "to_parquet",
    "to_feather",
    "to_hdf",
    "to_stata",
    "to_sas",
    "to_clipboard",
    "to_latex",
    "to_markdown",
    "to_gbq",
    "to_orc",
    "load",
    "loadtxt",
    "genfromtxt",
    "save",
    "savetxt",
    "savez",
    "fromfile",
    "memmap",
}


class UnsafeCodeError(ValueError):
    """代码未通过安全检查。"""


class CodeExecutionError(RuntimeError):
    """代码执行失败。"""


class CodeTimeoutError(TimeoutError):
    """代码执行超时。"""


def validate_code(code: str) -> ast.Module:
    """静态检查模型生成的代码，返回 AST。"""
    if not code or not code.strip():
        raise UnsafeCodeError("模型没有返回可执行代码。")
    if len(code) > MAX_CODE_LENGTH:
        raise UnsafeCodeError(f"生成的代码过长（超过 {MAX_CODE_LENGTH} 字符）。")

    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise CodeExecutionError(f"生成的代码存在语法错误：{exc.msg}") from exc

    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_AST_NODES:
        raise UnsafeCodeError("生成的代码过于复杂，已拒绝执行。")

    for node in nodes:
        if isinstance(node, FORBIDDEN_NODES):
            raise UnsafeCodeError(f"不允许使用 {type(node).__name__} 语句。")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                raise UnsafeCodeError(f"不允许访问下划线属性：{node.attr}")
            if node.attr in FORBIDDEN_ATTRS:
                raise UnsafeCodeError(f"不允许调用：{node.attr}")
        elif isinstance(node, ast.Name):
            if node.id.startswith("_"):
                raise UnsafeCodeError(f"不允许使用名称：{node.id}")
            if node.id in FORBIDDEN_NAMES:
                raise UnsafeCodeError(f"不允许使用名称：{node.id}")
    return tree


def _friendly_error(exc: BaseException) -> str:
    if isinstance(exc, NameError):
        return f"代码使用了不允许或未定义的名称：{exc}"
    if isinstance(exc, KeyError):
        return f"数据中不存在该字段：{exc}"
    if isinstance(exc, AttributeError):
        return f"不支持的属性访问：{exc}"
    if isinstance(exc, (ValueError, TypeError)):
        return f"计算失败：{exc}"
    return f"{type(exc).__name__}: {exc}"


def run_generated_code(
    df: pd.DataFrame,
    code: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> Any:
    """在受限命名空间中执行代码，并返回变量 result。"""
    validate_code(code)

    namespace: dict[str, Any] = {
        "df": df.copy(deep=True),
        "pd": pd,
        "np": np,
        "result": None,
    }
    outcome: dict[str, BaseException] = {}

    def _execute() -> None:
        try:
            exec(compile(code, "<generated>", "exec"), {"__builtins__": SAFE_BUILTINS}, namespace)
        except BaseException as exc:  # noqa: BLE001 - 需要把任何异常回传给调用方
            outcome["error"] = exc

    worker = threading.Thread(target=_execute, daemon=True)
    worker.start()
    worker.join(timeout)

    if worker.is_alive():
        raise CodeTimeoutError(f"代码执行超过 {timeout:.0f} 秒，已停止等待。请把问题拆得更具体。")
    if "error" in outcome:
        raise CodeExecutionError(_friendly_error(outcome["error"])) from outcome["error"]

    result = namespace.get("result")
    if result is None:
        raise CodeExecutionError("生成的代码没有把答案赋给变量 result。")
    return result
