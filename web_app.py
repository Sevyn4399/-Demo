from __future__ import annotations

import html
import json
import math
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 8765))


LEGAL_KEYWORDS = {
    "直播带货": ["直播", "带货", "主播", "达人", "直播间", "短视频"],
    "虚假宣传": ["虚假宣传", "夸大宣传", "误导", "不实", "绝对化用语", "功效宣传"],
    "消费者权益": ["消费者", "购买", "退货", "赔偿", "欺诈", "三倍赔偿"],
    "产品责任": ["质量问题", "缺陷", "食品安全", "药品", "保健品", "瑕疵"],
    "网络平台责任": ["平台", "电商平台", "审核", "下架", "店铺", "入驻"],
    "广告代言": ["代言", "推荐", "证明", "广告", "背书"],
    "合同纠纷": ["合同", "订单", "价款", "违约", "退款"],
    "侵权责任": ["侵权", "损害", "损失", "过错", "因果关系"],
    "连带责任": ["连带责任", "共同责任", "共同侵权", "补充责任"],
    "明知应知": ["明知", "应知", "未核实", "审查义务", "注意义务"],
    "获利分成": ["佣金", "分成", "收益", "坑位费", "推广费", "返佣"],
}


ISSUE_TEMPLATES = [
    ("是否构成虚假宣传", ["虚假宣传", "夸大宣传", "不实", "误导", "绝对化用语", "功效宣传"]),
    ("主播是否参与商品宣传并形成交易影响", ["主播", "直播", "带货", "推荐", "证明", "背书"]),
    ("主播是否明知或应知宣传内容不实", ["明知", "应知", "未核实", "审查义务", "注意义务"]),
    ("主播、商家、平台之间如何分配责任", ["连带责任", "平台", "商家", "责任分配", "共同侵权"]),
    ("消费者是否因宣传产生错误认识并购买", ["消费者", "购买", "误导", "错误认识", "因果关系"]),
    ("主播获利或合作模式是否影响责任认定", ["佣金", "分成", "合作", "坑位费", "推广费"]),
    ("平台是否尽到审核、提示和处置义务", ["平台", "审核", "下架", "入驻", "投诉"]),
]


QUESTION_BANK = {
    "主播": "主播是否承担责任，通常取决于其是否实际参与宣传、是否以推荐或证明方式影响交易、是否尽到合理审查义务，以及是否存在佣金、坑位费等获利安排。",
    "连带": "连带责任不是当然成立。若主播与商家共同实施误导宣传，或明知、应知商品信息不实仍作推荐证明，法院更可能支持相应连带或共同责任。",
    "为什么": "裁判逻辑一般会从行为、过错、因果关系和损害四个层面展开：宣传是否不实，用户是否因该宣传购买，主体是否有审查能力与注意义务，损失是否可归责。",
    "平台": "平台责任通常看是否履行入驻审核、广告标识、投诉处置、下架整改等义务。平台若仅提供技术服务且及时处置，责任会明显减轻。",
    "原告": "支持消费者一方时，重点组织宣传截图、直播话术、购买链路、主播收益、商品检测或官方说明，以证明误导宣传和交易决定之间的因果关系。",
    "被告": "支持主播一方时，可强调主播仅作一般展示、未作专业保证、已核验合理资料、无实际销售分成，或者消费者损失与宣传内容之间缺少因果关系。",
}


@dataclass
class Case:
    title: str
    docket: str
    court: str
    date: str
    cause: str
    side: str
    facts: str
    holding: str
    reasoning: str
    result: str
    tags: list[str]
    support_for: str
    quote: str


@dataclass
class ParsedInput:
    raw: str
    behaviors: list[str] = field(default_factory=list)
    subjects: list[str] = field(default_factory=list)
    liabilities: list[str] = field(default_factory=list)
    legal_elements: dict[str, list[str]] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    query_terms: list[str] = field(default_factory=list)
    cause: str = "消费者权益保护纠纷 / 网络服务合同相关争议"


CASES = [
    Case(
        title="教学示例一：消费者诉某直播主播、食品公司网络购物合同纠纷案",
        docket="示例案号 JX-2023-001",
        court="教学示例案例库",
        date="2023-09-18",
        cause="网络购物合同纠纷",
        side="消费者",
        facts="主播在直播间宣称涉案食品具有明显调理功效，并引导消费者通过直播链接购买。商品页面和检测资料未能证明相应功效。",
        holding="主播深度参与商品卖点介绍并获取推广收益，未对核心宣传内容尽合理审查义务，应与经营者承担相应赔偿责任。",
        reasoning="法院重点审查直播话术、主播身份、推广收益、消费者下单路径与商品真实信息之间的差距，认为宣传内容足以影响购买决定。",
        result="支持消费者部分赔偿请求，主播与商家在误导宣传范围内承担责任。",
        tags=["直播带货", "虚假宣传", "主播", "明知应知", "获利分成", "消费者权益", "连带责任"],
        support_for="消费者",
        quote="主播并非当然免责，是否担责取决于其参与程度、获利情况和审查义务履行情况。",
    ),
    Case(
        title="教学示例二：消费者诉某文化传媒公司、化妆品店产品宣传责任纠纷案",
        docket="示例案号 JX-2022-002",
        court="教学示例案例库",
        date="2022-12-06",
        cause="产品责任纠纷",
        side="消费者",
        facts="MCN机构安排达人直播推广化妆品，直播中使用绝对化用语并暗示医疗美容效果，消费者购买后认为效果与宣传不符。",
        holding="直播推广构成商业宣传，达人及其所属机构对明显夸大的功效表述负有审查和更正义务。",
        reasoning="法院认为普通消费者容易基于达人信任作出交易决定，MCN机构组织策划脚本并获得推广利益，应承担更高注意义务。",
        result="判令商家退款并赔偿，传媒公司在其参与宣传过错范围内承担补充赔偿责任。",
        tags=["直播带货", "虚假宣传", "广告代言", "MCN", "明知应知", "产品责任", "消费者权益"],
        support_for="消费者",
        quote="达人营销不应以流量信任替代事实核验。",
    ),
    Case(
        title="教学示例三：消费者诉某电商平台、保健品经营者信息网络买卖合同纠纷案",
        docket="示例案号 JX-2021-003",
        court="教学示例案例库",
        date="2021-10-22",
        cause="信息网络买卖合同纠纷",
        side="平台",
        facts="消费者主张平台应对入驻商家保健品功效虚假宣传承担连带赔偿责任，但平台在接到投诉后及时下架并提供经营者真实信息。",
        holding="平台已履行必要审核、提示和协助义务，现有证据不足以证明其参与虚假宣传或明知违法信息。",
        reasoning="平台责任应与其控制能力和过错程度相匹配，不能因平台提供交易空间而当然承担商家全部责任。",
        result="商家承担主要赔偿责任，驳回消费者要求平台连带赔偿的请求。",
        tags=["网络平台责任", "虚假宣传", "平台", "审核", "下架", "消费者权益"],
        support_for="平台或被告",
        quote="平台是否担责，应回到通知处置、审核能力和实际参与程度。",
    ),
    Case(
        title="教学示例四：消费者诉某主播网络直播购物损害赔偿纠纷案",
        docket="示例案号 JX-2024-004",
        court="教学示例案例库",
        date="2024-05-11",
        cause="网络直播购物损害赔偿纠纷",
        side="主播",
        facts="主播在直播中展示某品牌家电优惠信息，但未自行编辑产品参数，也未收取销售佣金。消费者主张参数误导导致损失。",
        holding="主播仅作一般商品展示，未作专业保证或核心性能承诺，且无证据证明其明知参数错误，不宜直接认定连带责任。",
        reasoning="法院区分普通展示与广告代言式推荐，认为消费者仍需证明主播过错与损害之间的因果关系。",
        result="商家承担退赔责任，消费者对主播的连带责任请求未获支持。",
        tags=["直播带货", "主播", "连带责任", "明知应知", "合同纠纷", "被告抗辩"],
        support_for="主播或被告",
        quote="主播责任不能脱离具体话术、收益关系和主观过错单独判断。",
    ),
    Case(
        title="教学示例五：消费者诉某珠宝直播间欺诈销售纠纷案",
        docket="示例案号 JX-2023-005",
        court="教学示例案例库",
        date="2023-11-29",
        cause="买卖合同纠纷",
        side="消费者",
        facts="直播间宣称珠宝为天然高等级材质并限时保真，主播多次以个人信誉作保证。鉴定结果显示商品等级与宣传明显不符。",
        holding="主播以个人信用对商品品质作保证，足以增强消费者信赖，应对未尽核验义务承担相应责任。",
        reasoning="法院将保真承诺、鉴定结论、直播成交链路和佣金收益作为相似要素，认定宣传行为与购买决定存在关联。",
        result="支持退货退款和惩罚性赔偿，主播与商家承担连带赔偿责任。",
        tags=["直播带货", "虚假宣传", "主播", "连带责任", "获利分成", "消费者权益", "欺诈"],
        support_for="消费者",
        quote="以个人信誉作商品品质保证，会显著提高主播注意义务。",
    ),
    Case(
        title="教学示例六：消费者诉某短视频达人广告代言责任纠纷案",
        docket="示例案号 JX-2022-006",
        court="教学示例案例库",
        date="2022-08-15",
        cause="广告责任纠纷",
        side="消费者",
        facts="短视频达人发布种草视频，称某减肥产品安全有效并附购买链接。后监管部门认定该产品广告含有违法功效宣传。",
        holding="达人以自身体验名义推荐商品，实质属于广告代言，应对未使用或未核验的推荐内容承担责任。",
        reasoning="法院强调广告代言与普通信息分享的边界，认为购买链接、佣金和商业合作标识是判断商业推广的重要事实。",
        result="判令经营者赔偿，达人在广告代言过错范围内承担连带责任。",
        tags=["广告代言", "虚假宣传", "短视频", "达人", "明知应知", "获利分成", "连带责任"],
        support_for="消费者",
        quote="种草内容一旦进入商业推广链条，即需接受广告责任规则评价。",
    ),
]


def tokenize(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text.strip())
    tokens: list[str] = []
    for concept, words in LEGAL_KEYWORDS.items():
        if any(word in text for word in words):
            tokens.append(concept)
            tokens.extend([word for word in words if word in text])
    tokens.extend(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]+", text))
    return sorted(set(tokens), key=tokens.index)


def parse_case_input(text: str) -> ParsedInput:
    tokens = tokenize(text)
    parsed = ParsedInput(raw=text)

    parsed.behaviors = [key for key in ["直播带货", "虚假宣传", "广告代言", "产品责任"] if key in tokens]
    parsed.subjects = [word for word in ["主播", "达人", "商家", "平台", "MCN", "消费者"] if word in text]
    parsed.liabilities = [key for key in ["连带责任", "侵权责任", "消费者权益", "网络平台责任"] if key in tokens]

    parsed.legal_elements = {
        "行为性质": parsed.behaviors or ["网络交易宣传行为"],
        "责任主体": parsed.subjects or ["经营者", "推广者"],
        "责任类型": parsed.liabilities or ["赔偿责任", "审查义务"],
        "损害类型": [key for key in ["消费者权益", "产品责任", "合同纠纷"] if key in tokens] or ["交易决策受误导"],
    }

    issues = []
    for issue, markers in ISSUE_TEMPLATES:
        if any(marker in text or marker in tokens for marker in markers):
            issues.append(issue)
    if not issues:
        issues = ["案涉行为的法律性质如何认定", "相关主体是否存在过错及因果关系", "责任承担方式如何分配"]
    parsed.issues = issues[:5]

    if "平台" in text:
        parsed.cause = "网络服务合同纠纷 / 消费者权益保护纠纷"
    elif "主播" in text or "直播" in text:
        parsed.cause = "网络直播购物损害赔偿纠纷 / 网络购物合同纠纷"

    parsed.query_terms = sorted(set(tokens + parsed.behaviors + parsed.subjects + parsed.liabilities), key=(tokens + parsed.behaviors + parsed.subjects + parsed.liabilities).index)
    return parsed


def score_case(parsed: ParsedInput, case: Case) -> tuple[float, list[str], list[str]]:
    query_terms = set(parsed.query_terms)
    tag_hits = sorted(query_terms.intersection(case.tags))
    issue_hits = []
    case_text = " ".join([case.facts, case.holding, case.reasoning, " ".join(case.tags)])
    for issue in parsed.issues:
        markers = next((m for name, m in ISSUE_TEMPLATES if name == issue), [])
        if any(marker in case_text for marker in markers):
            issue_hits.append(issue)

    query_vector = set(tokenize(parsed.raw))
    case_vector = set(tokenize(case_text))
    lexical = len(query_vector.intersection(case_vector)) / max(1, len(query_vector.union(case_vector)))
    tag_score = len(tag_hits) / max(1, len(query_terms))
    issue_score = len(issue_hits) / max(1, len(parsed.issues))
    recency = (datetime.fromisoformat(case.date).year - 2020) / 6

    score = 0.45 * tag_score + 0.35 * issue_score + 0.15 * lexical + 0.05 * max(0, min(recency, 1))
    if "连带责任" in parsed.query_terms and "连带责任" in case.tags:
        score += 0.08
    if ("主播" in parsed.subjects or "直播" in parsed.raw) and "主播" in case.tags:
        score += 0.06
    return min(score, 1.0), tag_hits, issue_hits


def summarize_match(parsed: ParsedInput, case: Case, tag_hits: list[str], issue_hits: list[str]) -> dict[str, Any]:
    differences = []
    if "获利分成" in parsed.query_terms and "获利分成" not in case.tags:
        differences.append("该案未突出主播实际获利或销售分成。")
    if "平台" in parsed.subjects and "平台" not in case.tags:
        differences.append("该案主要讨论主播或商家责任，平台责任部分较弱。")
    if "连带责任" in parsed.query_terms and "连带责任" not in case.tags:
        differences.append("该案没有直接支持连带责任，更适合用于责任边界分析。")
    if not differences:
        differences.append("核心事实与当前问题较接近，可直接比较宣传参与程度、审查义务和责任承担。")

    angle = "可用于论证消费者请求" if "消费者" in case.support_for else "可用于区分或支持被告抗辩"
    if "主播" in case.support_for:
        angle = "可用于论证主播并非当然承担连带责任"

    return {
        "title": case.title,
        "docket": case.docket,
        "court": case.court,
        "date": case.date,
        "cause": case.cause,
        "score": round(score_case(parsed, case)[0] * 100),
        "similarities": [
            f"命中要素：{('、'.join(tag_hits) if tag_hits else '宣传行为、交易损害、责任主体')}",
            f"对应争议：{('；'.join(issue_hits) if issue_hits else '行为性质与责任分配')}",
        ],
        "differences": differences,
        "holding": case.holding,
        "summary": [
            f"案情概括：{case.facts}",
            f"争议焦点：{('；'.join(issue_hits) if issue_hits else '推广主体是否应对宣传内容承担责任')}。",
            f"法院观点：{case.reasoning}",
            f"裁判结果：{case.result}",
            f"可引用要旨：{case.quote}",
        ],
        "angle": angle,
        "support_for": case.support_for,
    }


def search_cases(text: str) -> dict[str, Any]:
    parsed = parse_case_input(text)
    ranked = []
    for case in CASES:
        score, tag_hits, issue_hits = score_case(parsed, case)
        ranked.append((score, case, tag_hits, issue_hits))
    ranked.sort(key=lambda item: (-item[0], item[1].date), reverse=False)
    cards = [summarize_match(parsed, case, tag_hits, issue_hits) for _, case, tag_hits, issue_hits in ranked[:3]]
    return {
        "parsed": {
            "cause": parsed.cause,
            "behaviors": parsed.behaviors,
            "subjects": parsed.subjects,
            "liabilities": parsed.liabilities,
            "legal_elements": parsed.legal_elements,
            "issues": parsed.issues,
            "query_terms": parsed.query_terms,
        },
        "cards": cards,
        "study_tips": build_study_tips(parsed, cards),
    }


def build_study_tips(parsed: ParsedInput, cards: list[dict[str, Any]]) -> list[str]:
    tips = [
        "先用争议焦点检索，再用事实要素筛选，避免只搜零散关键词。",
        "比较主播话术、是否获利、是否核验、消费者购买链路四类事实。",
        "同时保留支持与不支持责任的案例，模拟法庭论证会更完整。",
    ]
    if "连带责任" in parsed.query_terms:
        tips.append("论证连带责任时，要特别补强共同宣传、共同获利或明知应知的证据。")
    if cards and "主播" in cards[0]["support_for"]:
        tips.append("首位案例偏向主播抗辩，可作为区分不利案例的训练素材。")
    return tips[:4]


def answer_question(question: str, context: str) -> dict[str, str]:
    merged = question + " " + context
    for key, answer in QUESTION_BANK.items():
        if key in merged:
            return {"answer": answer}
    return {
        "answer": "可以按“行为性质、主体过错、因果关系、责任范围”四步分析。先判断宣传是否足以误导消费者，再看主播或平台是否实际参与、是否获利、是否能核验，最后比较类案中的裁判要旨是否支持你的立场。"
    }


def export_markdown(payload: dict[str, Any]) -> str:
    result = search_cases(payload.get("query", ""))
    lines = ["# 类案检索速配报告", ""]
    lines.append(f"检索问题：{payload.get('query', '')}")
    lines.append(f"建议案由：{result['parsed']['cause']}")
    lines.append("")
    lines.append("## 争议焦点")
    for issue in result["parsed"]["issues"]:
        lines.append(f"- {issue}")
    lines.append("")
    lines.append("## Top 3 类案卡片")
    for idx, card in enumerate(result["cards"], 1):
        lines.append(f"### {idx}. {card['title']}")
        lines.append(f"- 案号：{card['docket']}")
        lines.append(f"- 法院/日期：{card['court']}，{card['date']}")
        lines.append(f"- 匹配度：{card['score']}%")
        lines.append(f"- 裁判要旨：{card['holding']}")
        lines.append(f"- 可借鉴角度：{card['angle']}")
        lines.append("- 学习型摘要：")
        for sentence in card["summary"]:
            lines.append(f"  - {sentence}")
        lines.append("")
    return "\n".join(lines)


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>类案检索速配智能体</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #172033;
      --muted: #5d6a7c;
      --line: #d9e0ea;
      --bg: #f6f8fb;
      --panel: #ffffff;
      --accent: #1d6f8f;
      --accent-2: #8a4f1d;
      --soft: #eaf5f7;
      --good: #28724f;
      --warn: #ad5a11;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }
    header {
      background: #ffffff;
      border-bottom: 1px solid var(--line);
      padding: 18px clamp(18px, 5vw, 52px);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
    }
    h1 { margin: 0; font-size: clamp(22px, 3vw, 32px); letter-spacing: 0; }
    header p { margin: 4px 0 0; color: var(--muted); font-size: 14px; }
    main {
      width: min(1280px, 100%);
      margin: 0 auto;
      padding: 22px clamp(14px, 3vw, 34px) 40px;
      display: grid;
      grid-template-columns: minmax(320px, 430px) 1fr;
      gap: 18px;
    }
    section, aside, .card, dialog {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .input-panel { padding: 18px; align-self: start; position: sticky; top: 14px; }
    label { display: block; font-size: 13px; color: var(--muted); margin-bottom: 8px; }
    textarea {
      width: 100%;
      min-height: 168px;
      resize: vertical;
      border: 1px solid #c8d3df;
      border-radius: 8px;
      padding: 12px;
      font: inherit;
      line-height: 1.55;
      color: var(--ink);
      background: #fbfcfe;
    }
    .button-row { display: flex; gap: 10px; margin-top: 12px; flex-wrap: wrap; }
    button {
      border: 1px solid transparent;
      border-radius: 7px;
      min-height: 38px;
      padding: 0 14px;
      font: inherit;
      cursor: pointer;
      background: #edf2f7;
      color: var(--ink);
    }
    button.primary { background: var(--accent); color: white; }
    button.ghost { border-color: var(--line); background: white; }
    button:focus-visible, textarea:focus, input:focus { outline: 3px solid #c8e6ef; outline-offset: 1px; }
    .chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
    .chip {
      display: inline-flex;
      align-items: center;
      min-height: 26px;
      padding: 3px 9px;
      border-radius: 999px;
      background: var(--soft);
      color: #155467;
      font-size: 12px;
      border: 1px solid #c8e3e9;
    }
    .workspace { display: grid; gap: 14px; }
    .analysis-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .mini { padding: 14px; }
    .mini h2, .results h2, .qa h2 { margin: 0 0 10px; font-size: 17px; }
    .mini dl { margin: 0; display: grid; gap: 8px; }
    .mini dt { color: var(--muted); font-size: 12px; }
    .mini dd { margin: 2px 0 0; line-height: 1.5; }
    .results { padding: 16px; }
    .cards { display: grid; gap: 12px; }
    .case-card { padding: 15px; }
    .case-head {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      align-items: start;
    }
    .case-card h3 { margin: 0; font-size: 18px; line-height: 1.35; }
    .meta { margin-top: 5px; color: var(--muted); font-size: 13px; line-height: 1.5; }
    .score {
      width: 64px;
      height: 64px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      background: #f2f7e9;
      color: var(--good);
      border: 1px solid #d5e7bd;
      font-weight: 700;
    }
    .two-col { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 12px; }
    .note { background: #fbfcfe; border: 1px solid #e3e8ef; border-radius: 8px; padding: 10px; line-height: 1.55; }
    .note b { color: var(--accent-2); }
    details { margin-top: 10px; }
    summary { cursor: pointer; color: var(--accent); font-weight: 650; }
    ul { padding-left: 19px; margin: 8px 0; }
    li { margin: 5px 0; line-height: 1.55; }
    mark { background: #fff1b8; padding: 0 2px; border-radius: 3px; }
    .qa { padding: 16px; display: grid; gap: 10px; }
    .qa-row { display: grid; grid-template-columns: 1fr auto; gap: 10px; }
    input {
      min-height: 38px;
      border: 1px solid #c8d3df;
      border-radius: 8px;
      padding: 0 12px;
      font: inherit;
    }
    .answer { min-height: 44px; color: var(--ink); line-height: 1.6; background: #fbfcfe; border: 1px solid #e3e8ef; border-radius: 8px; padding: 10px; }
    .empty {
      border: 1px dashed #b9c5d3;
      background: #ffffff;
      color: var(--muted);
      border-radius: 8px;
      padding: 32px;
      text-align: center;
      line-height: 1.7;
    }
    @media (max-width: 920px) {
      main { grid-template-columns: 1fr; }
      .input-panel { position: static; }
    }
    @media (max-width: 640px) {
      header { align-items: flex-start; flex-direction: column; }
      .analysis-grid, .two-col, .qa-row { grid-template-columns: 1fr; }
      .case-head { grid-template-columns: 1fr; }
      .score { width: auto; height: 38px; border-radius: 8px; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>类案检索速配智能体</h1>
      <p>把自然语言案情转换为争议焦点、法律要素和 Top 3 学习型类案卡片。内置数据为教学示例。</p>
    </div>
    <button class="ghost" id="loadExample">填入示例</button>
  </header>
  <main>
    <aside class="input-panel">
      <label for="caseInput">输入案情或检索问题</label>
      <textarea id="caseInput">直播带货虚假宣传，主播是否承担连带责任？消费者因主播推荐购买保健品，后来发现功效宣传不实，主播收取佣金但称自己只是介绍商品。</textarea>
      <div class="button-row">
        <button class="primary" id="searchBtn">速配类案</button>
        <button id="exportBtn">导出报告</button>
      </div>
      <div class="chips" id="quickChips">
        <span class="chip">虚假宣传</span>
        <span class="chip">主播责任</span>
        <span class="chip">连带责任</span>
        <span class="chip">明知应知</span>
      </div>
    </aside>
    <div class="workspace">
      <div id="analysis" class="empty">点击“速配类案”后，这里会显示案由、法律要素、争议焦点和检索关键词。</div>
      <section class="results">
        <h2>Top 3 类案卡片</h2>
        <div id="cards" class="cards">
          <div class="empty">暂无结果。</div>
        </div>
      </section>
      <section class="qa">
        <h2>智能问答与模拟法庭辅助</h2>
        <div class="qa-row">
          <input id="question" placeholder="例如：为什么主播需要承担责任？或：我代表消费者如何论证？" />
          <button id="askBtn">提问</button>
        </div>
        <div id="answer" class="answer">检索后可围绕判例摘要继续追问。</div>
      </section>
    </div>
  </main>
  <script>
    const $ = (id) => document.getElementById(id);
    let lastResult = null;

    const highlight = (text, terms = []) => {
      let escaped = String(text).replace(/[&<>"']/g, (m) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
      terms.filter(Boolean).sort((a, b) => b.length - a.length).slice(0, 12).forEach((term) => {
        const safe = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        escaped = escaped.replace(new RegExp(safe, "g"), `<mark>${term}</mark>`);
      });
      return escaped;
    };

    async function runSearch() {
      const query = $("caseInput").value.trim();
      if (!query) return;
      $("cards").innerHTML = '<div class="empty">正在解析案情并匹配类案...</div>';
      const res = await fetch("/api/search", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({query})
      });
      lastResult = await res.json();
      renderAnalysis(lastResult.parsed);
      renderCards(lastResult.cards, lastResult.parsed.query_terms);
    }

    function renderAnalysis(parsed) {
      const legal = parsed.legal_elements;
      $("analysis").className = "analysis-grid";
      $("analysis").innerHTML = `
        <section class="mini">
          <h2>案情解析</h2>
          <dl>
            <div><dt>建议案由</dt><dd>${parsed.cause}</dd></div>
            <div><dt>行为</dt><dd>${(parsed.behaviors.length ? parsed.behaviors : ["网络交易宣传"]).join("、")}</dd></div>
            <div><dt>主体</dt><dd>${(parsed.subjects.length ? parsed.subjects : ["经营者", "推广者"]).join("、")}</dd></div>
            <div><dt>责任类型</dt><dd>${(parsed.liabilities.length ? parsed.liabilities : ["赔偿责任"]).join("、")}</dd></div>
          </dl>
        </section>
        <section class="mini">
          <h2>争议焦点</h2>
          <ul>${parsed.issues.map((item) => `<li>${item}</li>`).join("")}</ul>
          <div class="chips">${parsed.query_terms.slice(0, 12).map((item) => `<span class="chip">${item}</span>`).join("")}</div>
        </section>
        <section class="mini">
          <h2>法律要素</h2>
          <dl>${Object.entries(legal).map(([key, val]) => `<div><dt>${key}</dt><dd>${val.join("、")}</dd></div>`).join("")}</dl>
        </section>
        <section class="mini">
          <h2>学习提示</h2>
          <ul>${lastResult.study_tips.map((item) => `<li>${item}</li>`).join("")}</ul>
        </section>
      `;
    }

    function renderCards(cards, terms) {
      $("cards").innerHTML = cards.map((card, index) => `
        <article class="case-card card">
          <div class="case-head">
            <div>
              <h3>${index + 1}. ${card.title}</h3>
              <div class="meta">${card.docket} · ${card.court} · ${card.date} · ${card.cause}</div>
            </div>
            <div class="score">${card.score}%</div>
          </div>
          <div class="two-col">
            <div class="note"><b>相似点</b><ul>${card.similarities.map((item) => `<li>${highlight(item, terms)}</li>`).join("")}</ul></div>
            <div class="note"><b>差异点</b><ul>${card.differences.map((item) => `<li>${highlight(item, terms)}</li>`).join("")}</ul></div>
          </div>
          <p class="note"><b>裁判要旨：</b>${highlight(card.holding, terms)}</p>
          <p class="note"><b>可借鉴角度：</b>${card.angle}</p>
          <details>
            <summary>展开学习型摘要</summary>
            <ul>${card.summary.map((item) => `<li>${highlight(item, terms)}</li>`).join("")}</ul>
          </details>
        </article>
      `).join("");
    }

    async function ask() {
      const question = $("question").value.trim();
      if (!question) return;
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({question, context: JSON.stringify(lastResult || {})})
      });
      const data = await res.json();
      $("answer").textContent = data.answer;
    }

    async function exportReport() {
      const query = $("caseInput").value.trim();
      if (!query) return;
      const res = await fetch("/api/export", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({query})
      });
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "类案检索速配报告.md";
      a.click();
      URL.revokeObjectURL(url);
    }

    $("searchBtn").addEventListener("click", runSearch);
    $("askBtn").addEventListener("click", ask);
    $("exportBtn").addEventListener("click", exportReport);
    $("loadExample").addEventListener("click", () => {
      $("caseInput").value = "我代表消费者，想主张主播承担责任。直播间宣传某珠宝为天然高等级材质，消费者因主播保真承诺购买，鉴定后发现等级不符。主播收取佣金，商家称责任只在店铺。";
      runSearch();
    });
    runSearch();
  </script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data: Any, status: int = 200) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:
    path = urlparse(self.path).path

    if path in ["/", "/index.html"]:
        self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
    elif path == "/favicon.ico":
        self._send(204, b"", "image/x-icon")
    else:
        self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
        

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {key: value[0] for key, value in parse_qs(raw).items()}

        path = urlparse(self.path).path
        if path == "/api/search":
            query = str(payload.get("query", "")).strip()
            self._json(search_cases(query))
        elif path == "/api/ask":
            self._json(answer_question(str(payload.get("question", "")), str(payload.get("context", ""))))
        elif path == "/api/export":
            content = export_markdown(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="case_match_report.md"')
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self._json({"error": "not found"}, 404)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"类案检索速配智能体已启动：http://127.0.0.1:{PORT}")
    print(f"同一局域网设备可使用本机 IP 访问，例如：http://你的电脑IP:{PORT}")
    print("按 Ctrl+C 停止服务。")
    server.serve_forever()


if __name__ == "__main__":
    main()
