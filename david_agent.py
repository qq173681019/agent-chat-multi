"""
David - 炒股高手 Agent
=================
专门处理金融/股票话题,会在说话前去调真实金融数据(Tushare)。
不相关的对话直接静默,不应答。

设计要点:
1. topic_relevant(): 纯关键词判定(0 成本,快)
2. Tushare 工具: 实时行情、K 线、资金流、行业板块
3. ReAct 文本标记: LLM 输出 <<TOOL: name, args>> 即可触发工具
4. 两阶段 LLM:
   - Phase 1: 让 LLM 决定"要不要查 + 查什么"(基于话题+性格)
   - Phase 2: 把数据塞回去,让 LLM 写最终回复
"""
import os
import re
import json
import time
import logging

log = logging.getLogger("david")

# ---------------------------------------------------------------------------
# 话题相关性(关键词门控,0 成本)
# ---------------------------------------------------------------------------
FINANCE_KEYWORDS = {
    # 股票/交易
    "股票", "股", "涨停", "跌停", "收盘", "开盘", "高开", "低开", "拉升", "跳水",
    "盘", "大盘", "指数", "上证", "深证", "创业板", "科创板", "北证", "北交所",
    "牛市", "熊市", "震荡", "回调", "反弹", "突破", "支撑", "压力", "阻力",
    "主力", "散户", "游资", "机构", "北向", "南向", "融资", "融券", "配股",
    "做空", "做多", "建仓", "加仓", "减仓", "清仓", "止损", "止盈", "被套", "解套",
    # 金融品种
    "etf", "基金", "债券", "国债", "逆回购", "可转债", "期货", "期权", "商品", "黄金", "白银",
    "原油", "比特币", "btc", "eth", "加密", "数字货币", "虚拟货币", "美股", "港股", "a股",
    "纳斯达克", "道琼斯", "标普", "恒生", "恒指", "日经", "韩股",
    # 公司/财报/行业
    "营收", "净利润", "业绩", "财报", "季报", "年报", "中报", "公告", "披露", "预增", "预减",
    "分红", "派息", "回购", "增持", "减持", "解禁", "ipo", "上市", "退市", "st", "*st",
    "板块", "概念", "题材", "龙头", "妖股", "蓝筹", "白马", "成长股", "价值股",
    "新能源", "半导体", "芯片", "ai算力", "机器人", "医药", "白酒", "银行", "地产", "汽车",
    "光伏", "锂电", "储能", "军工", "消费", "传媒", "游戏", "教育", "券商", "保险",
    # 高频股票名(避免漏判含具体股票名的提问)
    "茅台", "五粮液", "宁德", "比亚迪", "平安", "招行", "工行", "建行", "中行", "农行",
    "美的", "格力", "海康", "讯飞", "恒瑞", "迈瑞", "片仔癀", "京东方", "中信", "中免",
    "伊利", "海螺", "神华", "万科", "长城", "上汽", "复星", "长春高新", "智飞", "紫金", "汾酒",
    "贵州", "隆基", "立讯", "科大", "爱尔", "中石化", "中石油", "联通", "电信", "浦发", "潍柴",
    "苹果", "微软", "特斯拉", "英伟达", "谷歌", "亚马逊", "meta", "奈飞", "amd", "台积电",
    "腾讯", "阿里", "美团", "拼多多", "京东", "网易", "百度", "小米", "华为", "字节",
    # 指标/术语
    "pe", "pb", "roe", "估值", "市盈率", "市净率", "股息率", "换手率", "成交量", "成交额",
    "macd", "kdj", "rsi", "均线", "ma", "boll", "布林", "形态", "k线", "k线图",
    "技术面", "基本面", "消息面", "政策面", "资金面", "情绪面",
    # 宏观/政策
    "央行", "降息", "降准", "加息", "lpr", "mlf", "逆回购", "汇率", "美元", "人民币", "离岸",
    "cpi", "ppi", "gdp", "pmi", "通胀", "通缩", "宽松", "紧缩", "刺激",
    "美联储", "fed", "鲍威尔", "议息", "非农", "pce",
}

# 6 位数字的股票代码也算金融相关
CODE_RE = re.compile(r"\b[036]\d{5}\b")


def topic_relevant(text: str) -> bool:
    """粗判:文本里是否包含金融关键词或股票代码"""
    if not text:
        return False
    t = text.lower()
    if CODE_RE.search(t):
        return True
    # 关键词(中文直接用,英文/小写都查)
    for kw in FINANCE_KEYWORDS:
        if kw in t:
            return True
    return False


# ---------------------------------------------------------------------------
# Tushare 工具(延迟 import,避免本机没装 tushare 时 david_agent 整个 import 失败)
# ---------------------------------------------------------------------------
_TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN", "4a1bd8dea786a5525663fafcf729a2b081f9f66145a0671c8adf2f28")
_pro = None
_tushare_import_error = None

def _get_pro():
    """懒加载 tushare。失败一次后每次都直接 raise(避免重复尝试)"""
    global _pro, _tushare_import_error
    if _pro is not None:
        return _pro
    if _tushare_import_error is not None:
        raise _tushare_import_error
    try:
        import tushare as ts
        ts.set_token(_TUSHARE_TOKEN)
        _pro = ts.pro_api()
        return _pro
    except Exception as e:
        _tushare_import_error = e
        raise


def _to_ts_code(code: str) -> str:
    """600519 -> 600519.SH; 000001 -> 000001.SZ; 带后缀的保持"""
    code = code.strip().upper()
    if "." in code:
        return code
    if code.startswith(("6", "9", "5")):
        return f"{code}.SH"
    if code.startswith(("0", "3", "2")):
        return f"{code}.SZ"
    if code.startswith(("4", "8")):
        return f"{code}.BJ"
    return code


# 简单代码→名称映射(高频股,Tushare stock_basic 太慢,先硬编码)
_CODE_NAME_HINTS = {
    "600519": "贵州茅台", "000858": "五粮液", "000001": "平安银行",
    "600036": "招商银行", "601318": "中国平安", "000333": "美的集团",
    "600276": "恒瑞医药", "300750": "宁德时代", "002594": "比亚迪",
    "601012": "隆基绿能", "300059": "东方财富", "600030": "中信证券",
    "601398": "工商银行", "601939": "建设银行", "600900": "长江电力",
    "601888": "中国中免", "600887": "伊利股份", "000568": "泸州老窖",
    "002475": "立讯精密", "300760": "迈瑞医疗", "600028": "中国石化",
    "601857": "中国石油", "600050": "中国联通", "601728": "中国电信",
    "601988": "中国银行", "601288": "农业银行", "600000": "浦发银行",
    "000651": "格力电器", "000063": "中兴通讯", "002415": "海康威视",
    "000725": "京东方A", "600585": "海螺水泥",
    "601628": "中国人寿", "601088": "中国神华",
    "002230": "科大讯飞", "300015": "爱尔眼科", "600436": "片仔癀",
    "601899": "紫金矿业", "600809": "山西汾酒", "000002": "万科A",
    "601633": "长城汽车", "600104": "上汽集团", "000338": "潍柴动力",
    "600196": "复星医药", "000661": "长春高新", "300122": "智飞生物",
}


# ---------------------------------------------------------------------------
# 工具实现
# ---------------------------------------------------------------------------
def _safe_call(fn, *args, **kwargs):
    """统一异常包装,确保工具调用不会炸 poller"""
    try:
        result = fn(*args, **kwargs)
        return {"ok": True, "data": result}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}


def tool_quote(code: str) -> dict:
    """获取某只股票最新行情(日线最新一根)"""
    pro = _get_pro()
    ts_code = _to_ts_code(code)
    end = time.strftime("%Y%m%d")
    start_dt = time.time() - 5 * 86400
    start = time.strftime("%Y%m%d", time.localtime(start_dt))
    df = pro.daily(ts_code=ts_code, start_date=start, end_date=end)
    if df is None or df.empty:
        return {"error": f"未找到 {ts_code} 的行情数据(代码可能不存在)"}
    row = df.iloc[0].to_dict()
    name = _CODE_NAME_HINTS.get(code, ts_code)
    return {
        "code": ts_code,
        "name": name,
        "trade_date": str(row.get("trade_date", "")),
        "open": float(row.get("open", 0)),
        "high": float(row.get("high", 0)),
        "low": float(row.get("low", 0)),
        "close": float(row.get("close", 0)),
        "pre_close": float(row.get("pre_close", 0)),
        "pct_chg": float(row.get("pct_chg", 0)),
        "vol_k": float(row.get("vol", 0)),        # 单位:手
        "amount_kk": float(row.get("amount", 0)),  # 单位:千元
    }


def tool_kline(code: str, days: int = 20) -> dict:
    """获取某只股票最近 N 个交易日的 K 线"""
    pro = _get_pro()
    ts_code = _to_ts_code(code)
    end = time.strftime("%Y%m%d")
    start_dt = time.time() - (days + 5) * 86400
    start = time.strftime("%Y%m%d", time.localtime(start_dt))
    df = pro.daily(ts_code=ts_code, start_date=start, end_date=end)
    if df is None or df.empty:
        return {"error": f"未找到 {ts_code} 的 K 线"}
    df = df.sort_values("trade_date", ascending=False).head(days)
    name = _CODE_NAME_HINTS.get(code, ts_code)
    return {
        "code": ts_code,
        "name": name,
        "rows": [
            {
                "date": str(r["trade_date"]),
                "open": float(r["open"]),
                "close": float(r["close"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "pct_chg": float(r["pct_chg"]),
                "vol": float(r["vol"]),
            }
            for _, r in df.iterrows()
        ],
    }


def tool_index_quote(index_code: str = "000001.SH") -> dict:
    """获取大盘指数行情(默认上证指数 000001.SH; 深证成指 399001.SZ; 创业板 399006.SZ)"""
    pro = _get_pro()
    end = time.strftime("%Y%m%d")
    start_dt = time.time() - 5 * 86400
    start = time.strftime("%Y%m%d", time.localtime(start_dt))
    df = pro.index_daily(ts_code=index_code, start_date=start, end_date=end)
    if df is None or df.empty:
        return {"error": f"未找到指数 {index_code}"}
    row = df.iloc[0].to_dict()
    return {
        "code": index_code,
        "trade_date": str(row.get("trade_date", "")),
        "close": float(row.get("close", 0)),
        "pct_chg": float(row.get("pct_chg", 0)),
    }


def tool_sector_perf(n: int = 10) -> dict:
    """申万一级行业涨幅榜(Tushare 限额接口,需 5000 积分以上)"""
    pro = _get_pro()
    end = time.strftime("%Y%m%d")
    start_dt = time.time() - 5 * 86400
    start = time.strftime("%Y%m%d", time.localtime(start_dt))
    try:
        df = pro.sw_daily(start_date=start, end_date=end)
    except Exception as e:
        return {"error": f"行业接口失败(可能需要更高积分): {e}"}
    if df is None or df.empty:
        return {"error": "行业数据为空"}
    latest_date = df["trade_date"].max()
    today = df[df["trade_date"] == latest_date].sort_values("pct_chg", ascending=False)
    return {
        "date": str(latest_date),
        "top": today.head(n)[["ts_code", "name", "close", "pct_chg"]].to_dict("records"),
        "bottom": today.tail(n)[["ts_code", "name", "close", "pct_chg"]].to_dict("records"),
    }


# ---------------------------------------------------------------------------
# 工具注册表
# ---------------------------------------------------------------------------
TOOL_REGISTRY = {
    "quote": {
        "fn": tool_quote,
        "desc": "查询某只股票的最新行情(代码,例如 600519)。返回: 开高低收、涨跌幅、成交量、成交额。",
    },
    "kline": {
        "fn": tool_kline,
        "desc": "查询某只股票最近 N 天的 K 线(代码,天数,默认 20)。",
    },
    "index": {
        "fn": tool_index_quote,
        "desc": "查询大盘指数行情(指数代码,默认 000001.SH 上证;399001.SZ 深证;399006.SZ 创业板)。",
    },
    "sector": {
        "fn": tool_sector_perf,
        "desc": "查询申万一级行业涨跌幅榜(N,默认 10)。返回当日的 top 和 bottom 板块。",
    },
}


def tool_descriptions() -> str:
    """给 LLM 看的工具说明"""
    lines = []
    for name, meta in TOOL_REGISTRY.items():
        lines.append(f"- {name}: {meta['desc']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 工具调用解析(LLM 输出 <<TOOL: name, args>>)
# ---------------------------------------------------------------------------
TOOL_CALL_RE = re.compile(r"<<TOOL:\s*([a-z_]+)\s*(?:,\s*([^>]+?))?\s*>>", re.IGNORECASE)


def parse_tool_call(text):
    """从 LLM 输出里抓 <<TOOL: name, arg1, arg2>>"""
    m = TOOL_CALL_RE.search(text)
    if not m:
        return None
    name = m.group(1).strip().lower()
    raw_args = (m.group(2) or "").strip()
    args = [a.strip().strip("\"'") for a in raw_args.split(",") if a.strip()] if raw_args else []
    return name, args


# ---------------------------------------------------------------------------
# David 主入口(被 agent_poller 调用)
# ---------------------------------------------------------------------------
DAVID_SYSTEM_PROMPT = """你是 David,一位资深 A 股炒股高手,金融与股票话题专家。

## 性格
- 冷静、理性、不被情绪左右
- 数据驱动:说话必有数据支撑,不凭感觉
- 直白:好就是好,烂就是烂,不说废话
- 偶尔傲娇:看到烂操作会嘲讽,但看到高手会真心认可

## 行为准则
- **只在你专业领域(金融/股票)发言**,其他话题保持沉默
- 每次回答前必须先看真实数据,然后基于数据说话
- 严格区分:陈述事实(数据/已发生) vs 表达观点(分析/预测)
- 提示风险:任何"买入"建议必须附带风险提示

## 可用工具(必须按格式使用)
{tools}

## 工具调用格式
需要数据时输出(只输出一行):
<<TOOL: 工具名, 参数1, 参数2>>

系统会自动执行工具,然后你会看到结果,你再基于结果写最终回复。

## 回复格式
- 1-3 句话为主,像群聊
- 不需要 markdown,不用 # ** 等
- 数字要具体(不要"涨了一些",要"涨了 3.2%")
- 看到数据后必须**只用数据说话**,不要瞎编
"""


def build_david_messages(prompt):
    """David 用 minimax-cn(Anthropic 兼容),所以 system 单独,user 单独"""
    return {
        "system": DAVID_SYSTEM_PROMPT.format(tools=tool_descriptions()),
        "user": prompt,
    }


def run_david(agent_poller_module, agent_config, target_msg, recent_messages):
    """
    David 的主入口。两阶段 LLM:
    1. 决定要不要查数据 + 查什么
    2. 拿到数据后写最终回复
    """
    # 1. 构建上下文 + 第一次问 LLM
    user_prompt = agent_poller_module.build_prompt(agent_config, target_msg, recent_messages)
    # 在最上面塞一段"你是 David"的强化(避免 LLM 走神)
    name = agent_config.get("name", "David")
    agent_id = agent_config.get("id", "david")
    user_prompt = (
        f"[系统提示: 你是 {name}({agent_id})。你拥有下面这些金融工具,"
        f"看到和金融/股票相关的问题,你必须先用工具拿数据再回答。其他话题保持沉默。]\n\n"
        + user_prompt
    )
    msgs = build_david_messages(user_prompt)

    # 拿第一个可用的 provider
    provider = agent_poller_module.PROVIDERS[0]
    short_model = provider["model"].split("/")[-1]

    # === Phase 1: 让 LLM 决定查什么 ===
    if provider["protocol"] == agent_poller_module.ANTHROPIC_MSGS:
        phase1 = agent_poller_module._call_anthropic_msgs(
            provider, msgs["system"], msgs["user"], max_tokens=400
        )
        text1 = agent_poller_module._extract_anthropic_text(phase1) if phase1.get("type") != "error" else ""
        if not text1 and phase1.get("type") == "error":
            err = phase1.get("error", {})
            log.warning("david phase1 anthropic error: %s", err)
            return None
    else:
        phase1 = agent_poller_module._call_openai_chat(
            provider,
            [{"role": "system", "content": msgs["system"]},
             {"role": "user", "content": msgs["user"]}],
            max_tokens=400,
        )
        text1 = ""
        if phase1.get("choices"):
            text1 = phase1["choices"][0].get("message", {}).get("content", "")

    if not text1:
        log.warning("david phase1 got empty: %s", phase1)
        return None
    log.info("david phase1: %s", text1[:200])

    # 2. 解析工具调用
    tool_call = parse_tool_call(text1)
    if not tool_call:
        # LLM 决定不需要查数据 → 直接返回 phase1 的话(剥掉残留的 <<TOOL:...>> 标记)
        cleaned = re.sub(r"<<TOOL:[^>]*>>", "", text1).strip()
        return _postprocess(cleaned) if cleaned else None

    tool_name, tool_args = tool_call
    tool_meta = TOOL_REGISTRY.get(tool_name)
    if not tool_meta:
        log.warning("david unknown tool: %s", tool_name)
        return _postprocess(re.sub(r"<<TOOL:[^>]*>>", "", text1).strip()) or None

    # 3. 调工具
    try:
        if tool_name == "quote":
            code = tool_args[0] if tool_args else "600519"
            tool_result = _safe_call(tool_meta["fn"], code)
        elif tool_name == "kline":
            code = tool_args[0] if tool_args else "600519"
            days = int(tool_args[1]) if len(tool_args) > 1 else 20
            tool_result = _safe_call(tool_meta["fn"], code, days)
        elif tool_name == "index":
            idx = tool_args[0] if tool_args else "000001.SH"
            tool_result = _safe_call(tool_meta["fn"], idx)
        elif tool_name == "sector":
            n = int(tool_args[0]) if tool_args else 10
            tool_result = _safe_call(tool_meta["fn"], n)
        else:
            tool_result = {"ok": False, "error": "unknown"}
    except Exception as e:
        tool_result = {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}

    log.info("david tool %s(%s) → %s", tool_name, tool_args, str(tool_result)[:300])

    # 4. === Phase 2: 把工具结果 + 原始问题给 LLM,让它写最终回复 ===
    tool_str = json.dumps(tool_result, ensure_ascii=False, indent=2)[:2000]
    phase2_user = (
        f"{user_prompt}\n\n"
        f"--- 工具调用 ---\n"
        f"工具: {tool_name}\n"
        f"参数: {tool_args}\n"
        f"原始LLM意图: {text1[:300]}\n\n"
        f"--- 工具结果 ---\n"
        f"{tool_str}\n\n"
        f"请基于以上真实数据,用 David 的口吻写出最终回复(1-3句话,群聊风格,不要 markdown,不要重复工具调用标记)。"
    )
    if provider["protocol"] == agent_poller_module.ANTHROPIC_MSGS:
        phase2 = agent_poller_module._call_anthropic_msgs(
            provider, msgs["system"], phase2_user, max_tokens=300
        )
        text2 = agent_poller_module._extract_anthropic_text(phase2) if phase2.get("type") != "error" else ""
    else:
        phase2 = agent_poller_module._call_openai_chat(
            provider,
            [{"role": "system", "content": msgs["system"]},
             {"role": "user", "content": phase2_user}],
            max_tokens=300,
        )
        text2 = ""
        if phase2.get("choices"):
            text2 = phase2["choices"][0].get("message", {}).get("content", "")

    if not text2:
        log.warning("david phase2 got empty: %s", phase2)
        return _postprocess(re.sub(r"<<TOOL:[^>]*>>", "", text1).strip()) or None
    return _postprocess(text2)


def _postprocess(text):
    """群聊后处理:剥 markdown、去引号、单行化"""
    if not text:
        return text
    text = re.sub(r"[*#`]", "", text)
    text = text.strip("\"'\u201c\u201d\u2018\u2019")
    text = text.replace("\n", " ")
    return text.strip() or None
