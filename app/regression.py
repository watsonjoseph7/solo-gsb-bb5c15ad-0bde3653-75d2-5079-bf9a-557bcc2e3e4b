"""规则变更回归检查：旧版 / 新版两套规则分别解析，对同一批路径各自模拟。

- 以最终状态码、最终 URL、Location、结束原因四项作为结果指纹，逐条路径标记是否变化；
- 对发生变化的路径，进一步比对两侧**命中的**改写 / 重定向动作序列：
  比较时只看动作类型与输入输出（REWRITE 的路径前后值、REDIRECT 的输入路径、
  状态码与 Location），**跳过未命中步骤与源码行号**；行号与规则原文仅在展示
  「首次分叉」时给出；
- 若两侧命中动作序列完全一致而最终结果不同（例如一侧在未命中步骤上耗尽步数上限，
  或一侧先触发循环检测），则展示终止差异（四字段中具体不同的项）；
- 两侧规则的语法错误分别收集、分别提示，互不覆盖。
"""

from __future__ import annotations

from .engine import parse_rules
from .minimizer import SIGNATURE_FIELDS, MinimizeValidationError, normalize_paths
from .simulator import simulate

# 新旧两套规则各自允许的有效规则条数上限（与规则精简保持一致）
MAX_RULE_LINES = 400

# 命中动作比较键：不含 line / rule 原文 —— 源码行号与书写风格差异不算分叉
_ACTION_KEY = ("kind", "input", "output", "status")


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


def _hit_actions(trace: list[dict]) -> list[dict]:
    """从执行轨迹中抽取命中的改写 / 重定向动作（跳过 start/test/end/loop/limit）。"""
    actions: list[dict] = []
    for step in trace:
        kind = step["type"]
        if kind == "rewrite":
            actions.append(
                {
                    "kind": "rewrite",
                    "line": step["line"],
                    "rule": step["rule"],
                    "input": step["path"],
                    "output": step["new_path"],
                    "status": None,
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
                    "status": step["status"],
                }
            )
    return actions


def _action_key(action: dict) -> tuple:
    return tuple(action[key] for key in _ACTION_KEY)


def _fork_reason(index: int, old: dict | None, new: dict | None) -> str:
    """生成首次分叉的人类可读原因（行号不参与比较，故不在此出现）。"""
    if old is None:
        return f"新版执行到第 {index} 个命中动作时，旧版已没有更多命中动作（旧版可能已提前终止或放行）"
    if new is None:
        return f"旧版执行到第 {index} 个命中动作后仍有动作，新版已没有更多命中动作（新版可能提前终止或放行）"

    diffs: list[str] = []
    if old["kind"] != new["kind"]:
        diffs.append("动作类型不同（REWRITE / REDIRECT）")
    if old["input"] != new["input"]:
        diffs.append("动作的输入路径不同")
    if old["status"] != new["status"]:
        diffs.append("重定向状态码不同")
    if old["output"] != new["output"]:
        diffs.append("动作的输出目标不同")
    return "、".join(diffs) if diffs else "命中动作不一致"


def _divergence(
    old_actions: list[dict],
    new_actions: list[dict],
    old_result: dict,
    new_result: dict,
) -> dict:
    """定位两侧命中动作序列的首次分叉；动作序列全等时返回终止差异。"""
    count = max(len(old_actions), len(new_actions))
    for i in range(count):
        old = old_actions[i] if i < len(old_actions) else None
        new = new_actions[i] if i < len(new_actions) else None
        if old is None or new is None or _action_key(old) != _action_key(new):
            return {
                "type": "action",
                "index": i + 1,
                "reason": _fork_reason(i + 1, old, new),
                "old_action": old,
                "new_action": new,
            }

    # 命中动作（类型 / 输入 / 输出 / 状态码）逐个一致，结果却不同：
    # 差异只能来自终止方式（如步数上限耗在未命中步骤上、循环检测先后不同）
    terminal_diff = [
        {"field": field, "old": old_result[field], "new": new_result[field]}
        for field in SIGNATURE_FIELDS
        if old_result[field] != new_result[field]
    ]
    return {
        "type": "terminal",
        "index": None,
        "reason": "两侧命中动作序列完全一致，差异仅来自终止方式",
        "old_action": None,
        "new_action": None,
        "terminal_diff": terminal_diff,
    }


def _signature(result: dict) -> tuple:
    return tuple(result[key] for key in SIGNATURE_FIELDS)


def regression_check(
    old_source: str,
    new_source: str,
    paths: list[str],
    max_steps: int = 100,
    follow_redirects: bool = False,
) -> dict:
    """执行规则变更回归检查，返回可直接序列化的结果字典。

    任一侧规则文本有语法错误时返回
    ``{"ok": False, "errors": {"old": [...], "new": [...]}}``；
    路径列表不合法时抛出 :class:`MinimizeValidationError`。
    """
    paths = normalize_paths(paths)

    old_rules, old_errors = parse_rules(old_source)
    new_rules, new_errors = parse_rules(new_source)
    if old_errors or new_errors:
        return {
            "ok": False,
            "errors": {
                "old": _error_dicts(old_errors),
                "new": _error_dicts(new_errors),
            },
            "old_rule_count": len(old_rules),
            "new_rule_count": len(new_rules),
        }

    if len(old_rules) > MAX_RULE_LINES or len(new_rules) > MAX_RULE_LINES:
        raise MinimizeValidationError(
            f"新旧两套规则各自的有效规则不能超过 {MAX_RULE_LINES} 条"
            f"（当前旧版 {len(old_rules)} 条、新版 {len(new_rules)} 条），"
            "请缩小规则文本范围后重试"
        )

    outcomes: list[dict] = []
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
        old_result, new_result = old_sim["result"], new_sim["result"]
        changed = _signature(old_result) != _signature(new_result)

        old_actions = _hit_actions(old_sim["trace"])
        new_actions = _hit_actions(new_sim["trace"])
        field_changes: list[dict] = []
        divergence: dict | None = None
        if changed:
            changed_count += 1
            field_changes = [
                {"field": field, "old": old_result[field], "new": new_result[field]}
                for field in SIGNATURE_FIELDS
                if old_result[field] != new_result[field]
            ]
            divergence = _divergence(old_actions, new_actions, old_result, new_result)

        outcomes.append(
            {
                "path": path,
                "changed": changed,
                "old": old_result,
                "new": new_result,
                "field_changes": field_changes,
                "divergence": divergence,
                "old_hit_count": len(old_actions),
                "new_hit_count": len(new_actions),
            }
        )

    return {
        "ok": True,
        "paths": outcomes,
        "total": len(outcomes),
        "changed_count": changed_count,
        "old_rule_count": len(old_rules),
        "new_rule_count": len(new_rules),
    }
