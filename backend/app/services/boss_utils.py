"""
Boss 直聘工具函数

包含：
1. parse_salary —— 薪资字符串解析（"20-40K·15薪" → {min, max, months, ...}）
2. normalize_city —— 城市名归一化（"北京市"/"上海 "/"beijing" → "北京"/"上海"）
3. CITY_CODES —— 完整城市编码表（含三线城市，从 boss_search 迁移）
4. decode_degree —— 学历代码解码

这些工具独立于 boss_search.py 的搜索逻辑，便于复用与单元测试。
"""

import re
import logging
import unicodedata
from typing import Dict, Any, Optional

logger = logging.getLogger("offerclaw.boss_utils")


# ============================================================================
# 城市编码表（含三线城市，参考 chan9yu/bosszpider 的 city_code.json）
# ============================================================================

CITY_CODES: Dict[str, str] = {
    "全国": "100010000",
    # 一线
    "北京": "101010100", "上海": "101020100", "广州": "101280100",
    "深圳": "101280600", "杭州": "101210100",
    # 新一线
    "成都": "101270100", "南京": "101190100", "武汉": "101200100",
    "西安": "101110100", "苏州": "101190400", "长沙": "101250100",
    "天津": "101030100", "重庆": "101040100", "郑州": "101180100",
    "东莞": "101281600", "佛山": "101280800", "合肥": "101220100",
    "青岛": "101120200", "宁波": "101210400", "沈阳": "101070100",
    "昆明": "101290100", "大连": "101070200", "厦门": "101230200",
    "珠海": "101280700", "无锡": "101190200", "福州": "101230100",
    "济南": "101120100", "哈尔滨": "101050100", "长春": "101060100",
    "南昌": "101240100", "贵阳": "101260100", "南宁": "101300100",
    "石家庄": "101090100", "太原": "101100100", "兰州": "101160100",
    "海口": "101310100", "常州": "101191100", "温州": "101210700",
    "嘉兴": "101210300", "徐州": "101190800", "香港": "101320100",
    # 二三线（部分）
    "烟台": "101120300", "潍坊": "101120600", "保定": "101090200",
    "唐山": "101090300", "临沂": "101120900", "洛阳": "101180700",
    "汕头": "101280400", "邯郸": "101091000", "淄博": "101120400",
    "盐城": "101190700", "台州": "101210600", "绍兴": "101210500",
    "惠州": "101280300", "呼和浩特": "101080100", "镇江": "101190300",
    "桂林": "101300500", "赣州": "101240700", "银川": "101170100",
    "中山": "101281700", "湖州": "101210200", "南通": "101190600",
    "连云港": "101191000", "扬州": "101190500", "湛江": "101281000",
    "大庆": "101050900", "株洲": "101250300", "绵阳": "101270400",
    "芜湖": "101220300", "秦皇岛": "101091100", "遵义": "101260300",
    "襄樊": "101200600", "宜昌": "101200900",
}

# 城市别名（去掉"市"/"地区"等行政后缀）
_CITY_ALIASES = {
    "北京市": "北京", "上海市": "上海", "广州市": "广州", "深圳市": "深圳",
    "杭州市": "杭州", "成都市": "成都", "南京市": "南京", "武汉市": "武汉",
    "西安市": "西安", "苏州市": "苏州", "长沙市": "长沙", "天津市": "天津",
    "重庆市": "重庆", "郑州市": "郑州", "东莞市": "东莞", "佛山市": "佛山",
    "合肥市": "合肥", "青岛市": "青岛", "宁波市": "宁波", "沈阳市": "沈阳",
    "昆明市": "昆明", "大连市": "大连", "厦门市": "厦门", "珠海市": "珠海",
    "无锡市": "无锡", "福州市": "福州", "济南市": "济南", "哈尔滨市": "哈尔滨",
    "长春市": "长春", "南昌市": "南昌", "贵阳市": "贵阳", "南宁市": "南宁",
    "石家庄市": "石家庄", "太原市": "太原", "兰州市": "兰州", "海口市": "海口",
    "常州市": "常州", "温州市": "温州", "嘉兴市": "嘉兴", "徐州市": "徐州",
    "香港特别行政区": "香港",
}

# 拼音 → 中文（常见一线城市）
_PINYIN_MAP = {
    "beijing": "北京", "shanghai": "上海", "guangzhou": "广州",
    "shenzhen": "深圳", "hangzhou": "杭州", "chengdu": "成都",
    "nanjing": "南京", "wuhan": "武汉", "xian": "西安", "suzhou": "苏州",
    "changsha": "长沙", "tianjin": "天津", "chongqing": "重庆",
    "zhengzhou": "郑州", "dongguan": "东莞", "foshan": "佛山",
    "hefei": "合肥", "qingdao": "青岛", "ningbo": "宁波", "shenyang": "沈阳",
    "kunming": "昆明", "dalian": "大连", "xiamen": "厦门", "zhuhai": "珠海",
    "wuxi": "无锡", "fuzhou": "福州", "jinan": "济南",
    "harbin": "哈尔滨", "changchun": "长春", "nanchang": "南昌",
    "guiyang": "贵阳", "nanning": "南宁", "shijiazhuang": "石家庄",
    "taiyuan": "太原", "lanzhou": "兰州", "haikou": "海口",
}


def normalize_city(city: Optional[str]) -> str:
    """
    城市名归一化

    支持以下输入，统一返回 CITY_CODES 中的标准城市名：
    - "北京市" / "北京 " / "北京巿"（繁体）→ "北京"
    - "beijing" / "BEIJING" → "北京"
    - "上海地区" → "上海"
    - 模糊匹配（"杭州湾" → "杭州"，但分数 < 85 时不匹配）

    无法识别时返回 "全国"。
    """
    if not city or not city.strip():
        return "全国"

    # NFKC 归一化：全角→半角，繁体→简体（部分）
    c = unicodedata.normalize("NFKC", city.strip())
    c = c.replace(" ", "").replace("\t", "").replace("市", "").replace("地区", "")

    # 1. 精确匹配
    if c in CITY_CODES:
        return c

    # 2. 别名匹配
    if c in _CITY_ALIASES:
        return _CITY_ALIASES[c]

    # 3. 拼音匹配
    lower = c.lower()
    if lower in _PINYIN_MAP:
        return _PINYIN_MAP[lower]

    # 4. 模糊匹配（rapidfuzz 可选，未安装时退回 substring）
    try:
        from rapidfuzz import process
        match = process.extractOne(c, list(CITY_CODES.keys()), score_cutoff=85)
        if match:
            return match[0]
    except ImportError:
        # 退回：包含匹配（"杭州湾" 包含 "杭州"）
        for std_city in CITY_CODES:
            if std_city in c or c in std_city:
                return std_city

    logger.debug(f"无法识别的城市名: {city!r}，回退到全国")
    return "全国"


def get_city_code(city: Optional[str]) -> str:
    """城市名 → 城市编码（未识别返回全国编码）"""
    normalized = normalize_city(city)
    return CITY_CODES.get(normalized, "100010000")


# ============================================================================
# 薪资解析
# ============================================================================

def parse_salary(s: Optional[str]) -> Dict[str, Any]:
    """
    解析 Boss 薪资字符串

    支持格式：
    - "20-40K·15薪" → {min: 20000, max: 40000, unit: "K", months: 15}
    - "15-30K·14薪" → {min: 15000, max: 30000, unit: "K", months: 14}
    - "200-300元/天" → {min: 200, max: 300, unit: "元/天", months: 12}
    - "20-40W" → {min: 200000, max: 400000, unit: "W", months: 12}
    - "面议" → {min: None, max: None, unit: "面议", months: None}
    - "时薪50-100" → {min: 50, max: 100, unit: "时薪", months: 12}

    Returns:
        dict: {
            "min": Optional[int],       # 月薪下限（元）
            "max": Optional[int],       # 月薪上限（元）
            "unit": str,                # 原始单位描述
            "months": Optional[int],    # 薪资月数（默认 12）
            "annual_min": Optional[int], # 年薪下限 = min × months
            "annual_max": Optional[int], # 年薪上限 = max × months
            "raw": str,                 # 原始字符串
        }
    """
    if not s or not s.strip():
        return _empty_salary(s or "")

    s = s.strip()

    # 面议 / 薪资面议
    if "面议" in s or "negotiable" in s.lower():
        return _empty_salary(s, unit="面议")

    # 日薪：200-300元/天
    m = re.match(r"(\d+)\s*[-~]\s*(\d+)\s*元?/?天", s)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return {
            "min": lo, "max": hi, "unit": "元/天", "months": 12,
            "annual_min": lo * 22,  # 按每月 22 工作日估算
            "annual_max": hi * 22,
            "raw": s,
        }

    # 时薪：50-100元/小时 / 时薪50-100
    m = re.match(r"(?:时薪)?(\d+)\s*[-~]\s*(\d+)\s*元?/?小时?", s)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return {
            "min": lo, "max": hi, "unit": "元/小时", "months": 12,
            "annual_min": lo * 8 * 22,
            "annual_max": hi * 8 * 22,
            "raw": s,
        }

    # 月薪：20-40K·15薪 / 15-30K·14薪 / 20-40K
    m = re.match(
        r"(\d+)\s*[-~]\s*(\d+)\s*([Kk万千Ww])?(?:\s*[·•.]\s*(\d+)\s*薪)?",
        s,
    )
    if m:
        lo_str, hi_str, unit_str, months_str = m.groups()
        lo, hi = int(lo_str), int(hi_str)

        # 单位换算到元
        unit_norm = (unit_str or "").upper()
        if unit_norm in ("K", "W"):
            multiplier = 1000 if unit_norm == "K" else 10000
            lo *= multiplier
            hi *= multiplier
            unit_label = unit_str.upper()
        elif unit_str in ("万",):
            multiplier = 10000
            lo *= multiplier
            hi *= multiplier
            unit_label = "万"
        elif unit_str in ("千",):
            multiplier = 1000
            lo *= multiplier
            hi *= multiplier
            unit_label = "千"
        else:
            unit_label = "元"

        months = int(months_str) if months_str else 12

        return {
            "min": lo, "max": hi, "unit": unit_label, "months": months,
            "annual_min": lo * months,
            "annual_max": hi * months,
            "raw": s,
        }

    # 无法解析
    logger.debug(f"无法解析薪资字符串: {s!r}")
    return _empty_salary(s, unit=s)


def _empty_salary(raw: str, unit: str = "未知") -> Dict[str, Any]:
    return {
        "min": None, "max": None, "unit": unit, "months": None,
        "annual_min": None, "annual_max": None, "raw": raw,
    }


# ============================================================================
# 学历代码解码
# ============================================================================

_DEGREE_MAP = {
    0: "不限",
    209: "初中及以下",
    208: "中专/中技",
    206: "高中",
    202: "大专",
    203: "本科",
    204: "硕士",
    205: "博士",
}


def decode_degree(degree: Any) -> str:
    """解码 Boss 学历代码（数字 → 中文字符串）"""
    if not degree:
        return ""
    if isinstance(degree, str):
        return degree
    return _DEGREE_MAP.get(degree, str(degree))
