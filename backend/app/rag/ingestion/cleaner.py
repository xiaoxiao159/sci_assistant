"""数据清洗:解析后、切片前,分三级清洗。

规则顺序即设计:字符级 → 行级 → 结构级;后面的规则依赖前面的规范化
(标题识别依赖行首尾 strip,页眉统计依赖抠数字归一)。

  - 字符级:英文断词 join / 隐形字符删除 / 连字定向归一(不用 NFKC,保护 10⁻³ 等科学计数)
  - 行级:独立页码行改逐行判断(修掉 v1 正则连续页码行漏删一个的 bug);目录点导引行去除
  - 结构级:参考文献列表去除(标题行锚定 + 60% 位置门槛,切到文末;书籍"每章末参考文献"
    会误删后续章节,V1 面向论文可接受);页眉页脚跨页重复统计(仅本地路线 blocks=每页一个;
    MinerU 路线整篇单 block 无页边界,但其版面模型在上游已丢弃页眉页脚,无需此规则)

明确不清洗(防误伤):行内引用 [12] / 图表标题 caption / 公式 LaTeX / DOI / URL / 致谢。

注意:clean_parsed 为一次性语义(摄入管线只调用一次);页眉统计规则无状态,
重复调用时若各页正文首/末行也高度重复,存在过度删除风险。
"""
import re
from collections import Counter

from app.rag.ingestion.parser import ParsedDocument

# ─────────────── 字符级 ───────────────

# 英文断词:aug-\nmented -> augmented。仅当换行后是小写字母才去掉连字符
# (人名 Wu-\nYi、区间 5-\n10 断行不碰;复合词断行如 state-of-\nthe-art 罕见,接受误差)
_DEHYPHEN = re.compile(r"(\w)-[ \t]*\n(?=[a-z])")
# 零宽/软连字符等隐形杂质:零宽空格/连接符/不可断字符/BOM/软连字符,没有正当理由留在正文里
_INVISIBLE = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff\u00ad]")
# 连字定向归一(不用 NFKC:会把 10⁻³ 变 10-3)
_LIGATURES = str.maketrans({
    "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl",
})


def _clean_chars(text: str) -> str:
    """字符级:断词 join、隐形字符、连字。"""
    text = _DEHYPHEN.sub(r"\1", text)
    text = _INVISIBLE.sub("", text)
    return text.translate(_LIGATURES)


# ─────────────── 行级 ───────────────

_SPACES = re.compile(r"[ \t]{2,}")
# 整行只有 1-3 位数字:PDF 独立页码行(页脚最常见形态)
_PAGE_NUM_LINE = re.compile(r"^\d{1,3}$")
# 目录点导引行:行内出现 >=3 个点/句号(或 >=2 个省略号)且以 1-4 位数字结尾。
# 只认点导引符,不认"标题+数字"——后者会把"精度达到 95"这类正文行误杀
_TOC_LINE = re.compile(r"(?:[.。．]{3,}|…{2,})\s*\d{1,4}$")
_TOC_LINE_MAX_LEN = 200  # 目录行不会太长;长行是正文,即使形态命中也保留


def _clean_lines(text: str) -> str:
    """行级:空格压缩、行首尾空白、独立页码行、目录行、空行压缩。"""
    out: list[str] = []
    for line in text.split("\n"):
        line = _SPACES.sub(" ", line).strip()
        if not line:  # 空行保留,末尾统一压缩
            out.append("")
            continue
        if _PAGE_NUM_LINE.match(line):
            # 前一行以连字符结尾:是跨行数字区间(如 5-\n10)的后半段,不是页码
            if not (out and out[-1].endswith(("-", "–", "—"))):
                continue
        if len(line) < _TOC_LINE_MAX_LEN and _TOC_LINE.search(line):
            continue
        out.append(line)
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ─────────────── 结构级(跨 block 视野) ───────────────

# 参考文献标题行:必须独立成行(正文句不匹配),兼容编号前缀与 markdown # 前缀
_REF_HEADING = re.compile(
    r"^#*\s*(?:\d+[.、]?\s*)?(?:参考文献|引用文献|references|bibliography"
    r"|works\s+cited|literature\s+cited)\s*$",
    re.IGNORECASE,
)
_REFERENCES_POSITION = 0.6  # 标题须落在全文后 60% 区间,防文前话题误杀

_EDGE_NOISE = re.compile(r"[\s\d|\uff5c]+")  # 页眉页脚归一:抠掉数字/空白/竖线(全半角)再比
_EDGE_MIN_PAGES = 5                          # 页数太少,统计不可靠
_EDGE_THRESHOLD = 0.6                       # 出现率门槛


def _strip_references(parsed: ParsedDocument) -> None:
    """参考文献列表去除:首个位于全文后 40% 区间的标题行处截断,其后 block 全部丢弃。

    MinerU(整篇单 block)在 block 内截断;本地路线跨 block 截断。
    seen/total 为近似计数(block 间距按 \n 计),60% 门槛是启发式,近似无碍。
    """
    total = sum(len(b.text) for b in parsed.blocks)
    if total == 0:
        return
    seen = 0
    for i, block in enumerate(parsed.blocks):
        lines = block.text.split("\n")
        for j, line in enumerate(lines):
            if seen / total >= _REFERENCES_POSITION and _REF_HEADING.match(line.strip()):
                block.text = "\n".join(lines[:j]).rstrip()
                del parsed.blocks[i + 1 :]
                return
            seen += len(line) + 1
        seen += 1


def _norm_edge(line: str) -> str:
    return _EDGE_NOISE.sub(" ", line).strip()


def _strip_page_edges(parsed: ParsedDocument) -> None:
    """页眉页脚去除:仅本地路线(blocks=每页一个且带页码)。

    统计首页以外各页的首/末行(归一化后),出现率 >= 60% 的判为页眉/页脚并从各页删除。
    护栏:首页豁免(首页顶部是标题,不参与统计也不删);页数 < 5 不统计;
    归一化抠数字(页眉常带页码,如 "Nature Mach. Intell. | 3")。
    """
    blocks = parsed.blocks
    if len(blocks) < _EDGE_MIN_PAGES or not all(b.page is not None for b in blocks):
        return
    body = blocks[1:]
    if not body:
        return

    def _frequent(vals: list[str]) -> set[str]:
        counts = Counter(v for v in vals if v)
        return {v for v, c in counts.items() if c / len(vals) >= _EDGE_THRESHOLD}

    bad_first = _frequent([_norm_edge(b.text.split("\n", 1)[0]) for b in body])
    bad_last = _frequent([_norm_edge(b.text.rsplit("\n", 1)[-1]) for b in body])
    if not bad_first and not bad_last:
        return
    for b in body:
        lines = b.text.split("\n")
        if lines and _norm_edge(lines[0]) in bad_first:
            del lines[0]
        if lines and _norm_edge(lines[-1]) in bad_last:
            del lines[-1]
        # 删行后首尾可能残留空行:直接 strip,保证幂等(重复清洗不再改变文本)
        b.text = "\n".join(lines).strip()


# ─────────────── 入口 ───────────────

def clean_text(text: str) -> str:
    """单字符串清洗(字符级 + 行级,纯函数;结构级见 clean_parsed)。"""
    return _clean_lines(_clean_chars(text))


def clean_parsed(parsed: ParsedDocument) -> ParsedDocument:
    """三级清洗(原地改):字符/行级逐 block,结构级跨 block,最后丢空 block。"""
    for block in parsed.blocks:
        block.text = clean_text(block.text)
    _strip_references(parsed)
    _strip_page_edges(parsed)
    parsed.blocks = [b for b in parsed.blocks if b.text and b.text.strip()]
    return parsed
