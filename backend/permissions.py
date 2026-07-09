"""权限点目录（RBAC 的「权限」定义集中在代码里，角色→权限的绑定存库）。

成熟后台框架（若依 RuoYi / Spring Security 等）都把「有哪些权限点」写死在代码中
（因为权限点对应真实的功能/接口，不该由用户随意增删），而把「角色拥有哪些权限点」
存数据库、由管理员勾选。本文件即权限点目录。

权限点编码统一为「模块:动作」：
  - 模块(module) 与前端菜单 data-page 一致：collect/analysis/generate/manage/logs/users/roles
  - 动作(action) 形如 view/edit/export/save
  - 每个模块的 `:view` 控制菜单是否可见；其余动作控制模块内的写/导出按钮

超级管理员用通配权限 "*"，拥有全部权限点，且不可被编辑（避免锁死系统）。
"""
from __future__ import annotations

# 通配权限：拥有它即拥有全部权限点（超级管理员）
WILDCARD = "*"

# 权限点目录：分模块组织，前端据此渲染「勾选权限」的复选树。
# module 必须与前端菜单 li.menu-item 的 data-page 一致。
PERMISSION_CATALOG = [
    {
        "module": "collect",
        "module_name": "多源数据采集",
        "actions": [
            {"code": "collect:view", "name": "查看"},
            {"code": "collect:edit", "name": "采集 / 暂存 / 入库 / 编辑"},
        ],
    },
    {
        "module": "analysis",
        "module_name": "值勤数据分析",
        "actions": [
            {"code": "analysis:view", "name": "查看"},
            {"code": "analysis:save", "name": "保存快照"},
        ],
    },
    {
        "module": "generate",
        "module_name": "报告辅助生成",
        "actions": [
            {"code": "generate:view", "name": "查看"},
            {"code": "generate:edit", "name": "上传模板 / 生成草稿"},
        ],
    },
    {
        "module": "manage",
        "module_name": "报告在线管理",
        "actions": [
            {"code": "manage:view", "name": "查看"},
            {"code": "manage:edit", "name": "新增 / 编辑 / 删除"},
            {"code": "manage:export", "name": "导出 Word/PPT"},
        ],
    },
    {
        "module": "logs",
        "module_name": "操作日志",
        "actions": [
            {"code": "logs:view", "name": "查看"},
        ],
    },
    {
        "module": "users",
        "module_name": "用户管理",
        "actions": [
            {"code": "users:view", "name": "查看"},
            {"code": "users:edit", "name": "新增 / 编辑 / 删除"},
        ],
    },
    {
        "module": "roles",
        "module_name": "角色管理",
        "actions": [
            {"code": "roles:view", "name": "查看"},
            {"code": "roles:edit", "name": "新增 / 编辑 / 删除"},
        ],
    },
]


def all_permission_codes() -> list[str]:
    """目录中全部权限点编码（顺序与目录一致）。"""
    codes = []
    for grp in PERMISSION_CATALOG:
        for act in grp["actions"]:
            codes.append(act["code"])
    return codes


_ALL_CODES = set(all_permission_codes())


def normalize_perms(codes) -> list[str]:
    """过滤出目录中合法的权限点，去重并按目录顺序返回。

    含通配 "*" 时直接返回 ["*"]（超级权限，无需逐条列出）。
    """
    if not codes:
        return []
    s = set(codes)
    if WILDCARD in s:
        return [WILDCARD]
    return [c for c in all_permission_codes() if c in s]


def expand_perms(codes) -> set[str]:
    """把角色存的权限列表展开成「实际生效的权限点集合」。

    含通配则展开为全部权限点；否则取交集（过滤掉已下线的旧权限点）。
    前端 Perm.has() 同样支持通配，这里展开主要服务后端如需校验时使用。
    """
    s = set(codes or [])
    if WILDCARD in s:
        return set(_ALL_CODES)
    return s & _ALL_CODES
