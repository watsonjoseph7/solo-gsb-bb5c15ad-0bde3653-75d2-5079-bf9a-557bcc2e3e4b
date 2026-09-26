"""规则变更回归检查：解析旧 / 新两套规则，对多条请求路径分别模拟并定位分叉。

比较口径：

- 先按**最终状态码、最终 URL、Location、结束原因**四项判断每条路径是否发生变化；
- 对发生变化的路径，逐动作比对两侧**命中的** REWRITE / REDIRECT：
  跳过未命中步骤（test）与源码行号，按动作的「类型 + 输入路径 + 输出 +
  重定向状态码」对齐，报告首次分叉的两侧原行号与动作；
- 若动作序列完全一致（含输入输出）而最终结果不同（典型为循环 / 步数上限等
  终止差异），报告终止差异。
"""

from __future__ import annotations

from .engine import parse_rules
from .minimizer import (
    MAX_PATHS,
    MAX_RULE_LINES,
    MinimizeValidationError,
    SIGNATURE_FIELDS,
    normalize_paths,
)
from .simulator import simulate

__all__ = ["MAX_PATHS", "MinimizeValidationError", "regression_check"]

# 参与动作比对的字段（刻意不含行号 / 规则原文 / 捕获组明细）：
# 动作类型、命中时输入路径、动作输出（改写后的路径或 Location）、重定向状态码
_ACTION_KEY_FIELDS = ("kind", "input", "output", "status")

_TERMINAL_FIELDS = (
    "status",
    "final_url",
    "location",
    "finish_reason",
    "steps",
    "hops",
)


def _error_dicts(errors) -> list[dict]:
    return [
        {
            "line": e.line,
            "col": e.col,
            "length": e.length,
            "message": e.message,
            "source": e.source,
        }
        for e in errors
    ]


def _terminal(result: dict) -> dict:
    """提取一次模拟的终局信息（四要素 + 步数 / 跳数）。"""
    return {key: result[key] for key in _TERMINAL_FIELDS}


def _hit_actions(trace: list[dict]) -> list[dict]:
    """从轨迹中提取命中的改写 / 重定向动作。

    未命中步骤（test）、start / end / loop / limit 等节点一律跳过，
    行号仅用于展示，不参与一致性比较。
    """
    actions: list[dict] = []
    for step in trace:
        kind = step.get("type")
        if kind == "rewrite":
            actions.append(
                {
                    "kind": "rewrite",
                    "line": step["line"],
                    "rule": step["rule"],
                    "input": step["path"],
                    "output": step["new_path"],
                    "status": None,
                    "flow": "last" if str(step.get("flow", "")).startswith("last") else "next",
                }
            )
        elif kind == "redirect":
            actions.append(
                {
                    "kind": "redirect",
                    "line": step["line"],
                    "rule": step["rule"],
                    "input": step["path"],
                    "output": step["location"],
                    "status": step.get("status"),
                    "flow": step.get("flow"),
                }
            )
    return actions


def _action_key(action: dict) -> tuple:
    return tuple(action[key] for key in _ACTION_KEY_FIELDS)


def _diff_one_path(old_sim: dict, new_sim: dict) -> dict:
    """比较单条路径在两套规则下的模拟结果。"""
    old_result = old_sim["result"]
    new_result = new_sim["result"]

    changed_fields = [
        key for key in SIGNATURE_FIELDS if old_result[key] != new_result[key]
    ]
    old_terminal = _terminal(old_result)
    new_terminal = _terminal(new_result)
    old_actions = _hit_actions(old_sim["trace"])
    new_actions = _hit_actions(new_sim["trace"])

    base = {
        "old": {"terminal": old_terminal, "action_count": len(old_actions)},
        "new": {"terminal": new_terminal, "action_count": len(new_actions)},
    }

    if not changed_fields:
        return {"changed": False, "changed_fields": [], "divergence": None, **base}

    # 按动作序号对齐（已跳过未命中步骤），找首个输入输出不一致的位置
    divergence: dict | None = None
    paired = min(len(old_actions), len(new_actions))
    for index in range(paired):
        if _action_key(old_actions[index]) != _action_key(new_actions[index]):
            divergence = {
                "kind": "action",
                "index": index,
                "old_action": old_actions[index],
                "new_action": new_actions[index],
                "old_terminal": old_terminal,
                "new_terminal": new_terminal,
            }
            break

    # 成对动作全部一致但一侧动作更多：多出的首个动作即分叉点，
    # 另一侧动作序列在该位置已经结束
    if divergence is None and len(old_actions) != len(new_actions):
        divergence = {
            "kind": "action",
            "index": paired,
            "old_action": old_actions[paired] if paired < len(old_actions) else None,
            "new_action": new_actions[paired] if paired < len(new_actions) else None,
            "old_terminal": old_terminal,
            "new_terminal": new_terminal,
        }

    # 动作（类型 / 输入 / 输出 / 状态码）逐条一致而终局不同：终止差异
    if divergence is None:
        divergence = {
            "kind": "terminal",
            "changed_fields": changed_fields,
            "old_terminal": old_terminal,
            "new_terminal": new_terminal,
        }

    return {
        "changed": True,
        "changed_fields": changed_fields,
        "divergence": divergence,
        **base,
    }


def regression_check(
    old_source: str,
    new_source: str,
    paths: list[str],
    max_steps: int = 100,
    follow_redirects: bool = False,
) -> dict:
    """对两套规则执行多路径回归比较，返回可直接序列化的结果字典。

    任一侧规则文本存在语法错误时返回
    ``{"ok": False, "old_errors": [...], "new_errors": [...]}``，
    两侧错误分别列出、互不覆盖；路径列表不合法时抛出
    :class:`MinimizeValidationError`。
    """
    paths = normalize_paths(paths)

    old_rules, old_errors = parse_rules(old_source)
    new_rules, new_errors = parse_rules(new_source)

    if old_errors or new_errors:
        return {
            "ok": False,
            "old_errors": _error_dicts(old_errors),
            "new_errors": _error_dicts(new_errors),
        }

    for label, rule_list in (("旧版", old_rules), ("新版", new_rules)):
        if len(rule_list) > MAX_RULE_LINES:
            raise MinimizeValidationError(
                f"{label}规则的有效规则不能超过 {MAX_RULE_LINES} 条"
                f"（当前 {len(rule_list)} 条），请缩小规则文本范围后重试"
            )

    results: list[dict] = []
    changed_count = 0
    for path in paths:
        old_sim = simulate(
            old_rules,
            path,
            max_steps=max_steps,
            follow_redirects=follow_redirects,
        )
        new_sim = simulate(
            new_rules,
            path,
            max_steps=max_steps,
            follow_redirects=follow_redirects,
        )
        diff = _diff_one_path(old_sim, new_sim)
        results.append({"path": path, **diff})
        if diff["changed"]:
            changed_count += 1

    return {
        "ok": True,
        "paths": paths,
        "old_rule_count": len(old_rules),
        "new_rule_count": len(new_rules),
        "changed_count": changed_count,
        "unchanged_count": len(paths) - changed_count,
        "results": results,
    }
