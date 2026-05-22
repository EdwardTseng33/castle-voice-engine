# castle-voice-engine - castle/dispatch/castle_members.py
# (c) 2026 Edward / BeyondPath
#
# 城堡 7 同事定義 (Voice Path v2.0 Phase 2 後半段)
#
# 來源：user-level CLAUDE.md 7 人架構 + agents/{name}.md
# 這份在 voice engine 用作 dispatch routing reference、不是 SSOT
# (SSOT 在 castle-ai-system repo agents/{name}.md)

from __future__ import annotations

from typing import TypedDict


class CastleMember(TypedDict):
    key: str               # function calling name (英文、不含中文)
    display_name: str      # 中文顯示名
    role: str              # 1 句話定位
    capabilities: list[str]  # 能做的事 (給 Sophie 判斷該派誰)
    model_for_simulation: str  # Claude model 跑模擬時用的 (PoC 階段 stub)
    icon: str              # emoji
    when_to_dispatch: str  # 一句話 Sophie 用來判斷時機


CASTLE_MEMBERS: list[CastleMember] = [
    {
        "key": "howl",
        "display_name": "霍爾",
        "role": "CPO · 產品策略 / 品牌 / 競品 / 願景校準",
        "capabilities": [
            "product_strategy",
            "competitive_analysis",
            "brand_positioning",
            "pmf_validation",
            "roadmap_planning",
        ],
        "model_for_simulation": "claude-haiku-4-5",
        "icon": "🧙",
        "when_to_dispatch": "Edward 問產品方向 / 競品 / 品牌敘事 / Roadmap 取捨",
    },
    {
        "key": "calcifer",
        "display_name": "卡西法",
        "role": "CTO · 技術架構 / 程式碼 / 部署 / 工時估算",
        "capabilities": [
            "code_review",
            "tech_architecture",
            "deployment",
            "smoke_testing",
            "agent_mcp_integration",
        ],
        "model_for_simulation": "claude-haiku-4-5",
        "icon": "🔥",
        "when_to_dispatch": "Edward 問技術方案 / bug / 部署 / 程式架構決策",
    },
    {
        "key": "witch",
        "display_name": "女巫",
        "role": "Creative Director · UI / 視覺 / 設計系統 / Figma",
        "capabilities": [
            "visual_design",
            "design_system",
            "ui_critique",
            "figma_handoff",
            "design_dna_check",
        ],
        "model_for_simulation": "claude-haiku-4-5",
        "icon": "🔮",
        "when_to_dispatch": "Edward 問畫面 / 色彩 / 字型 / 設計系統 / 美感判斷",
    },
    {
        "key": "turnip",
        "display_name": "蕪菁頭",
        "role": "用戶意圖 / 行為分析 / UX 研究 / A/B 測試",
        "capabilities": [
            "user_research",
            "behavioral_analysis",
            "persona_design",
            "funnel_analysis",
            "retention_check",
        ],
        "model_for_simulation": "claude-haiku-4-5",
        "icon": "🥕",
        "when_to_dispatch": "Edward 問用戶真的要不要 / 數據怎麼說 / 漏斗",
    },
    {
        "key": "markl",
        "display_name": "馬魯克",
        "role": "PM / QA Lead · 任務拆解 / 版控 / 品質 / 交付前巡檢",
        "capabilities": [
            "task_breakdown",
            "sprint_planning",
            "qa_regression",
            "diff_report",
            "release_checklist",
        ],
        "model_for_simulation": "claude-haiku-4-5",
        "icon": "🌿",
        "when_to_dispatch": "Edward 問任務怎麼拆 / 版號 / 品質檢查 / 退版",
    },
    {
        "key": "sophie",
        "display_name": "蘇菲",
        "role": "COO / CFO · 營運 / 財務 / 客戶 / BD / 文案 / 定價",
        "capabilities": [
            "ops_coordination",
            "financial_estimation",
            "customer_relations",
            "pricing_strategy",
            "copy_writing",
        ],
        "model_for_simulation": "claude-haiku-4-5",
        "icon": "🌸",
        "when_to_dispatch": "Edward 問營運 / 財務 / 客戶 / 文案 / 定價 (此 voice 蘇菲自己就是、實際 dispatch 用於深度任務)",
    },
    {
        "key": "suliman",
        "display_name": "沙利曼",
        "role": "Head of Trust · 資安 / 合規 / 法務 / DevOps / Gate 5",
        "capabilities": [
            "security_review",
            "compliance_check",
            "legal_redline",
            "devops_pipeline",
            "incident_response",
        ],
        "model_for_simulation": "claude-haiku-4-5",
        "icon": "🧙‍♀️",
        "when_to_dispatch": "Edward 問資安 / 合規 / 合約 / 部署風險 / 信任檢查",
    },
]


def get_member(key: str) -> CastleMember | None:
    """Lookup castle member by key (case-insensitive)."""
    key_lower = key.lower().strip()
    for m in CASTLE_MEMBERS:
        if m["key"] == key_lower:
            return m
    return None
