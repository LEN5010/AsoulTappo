"""Curated catalog for the asset pipeline.

Everything that ends up in the repository is selected by an explicit allowlist
in this file (by card id, emote file stem, theme directory, ...).  Anything that
is not listed here is never read, converted or committed.

The catalog covers exactly five characters: 嘉然, 乃琳, 贝拉, 心宜, 思诺.
"""
from __future__ import annotations

# ---------------------------------------------------------------- characters
# id, display name (also the wire value of `character`), accent colour
CHARACTERS = [
    {"id": "jiaran", "name": "嘉然", "color": "#e799b0"},
    {"id": "nailin", "name": "乃琳", "color": "#576690"},
    {"id": "beila", "name": "贝拉", "color": "#bd7d74"},
    {"id": "xinyi", "name": "心宜", "color": "#f27ba9"},
    {"id": "sinuo", "name": "思诺", "color": "#3f5fa8"},
]
CHAR_BY_NAME = {c["name"]: c for c in CHARACTERS}

# ------------------------------------------------------------------- themes
# Source directories live under <assets>/主题.  Several directories may be
# merged into one theme (the first directory that has a part wins).
# Spaced duplicates ("… 2.0") are ignored on purpose: they are strict subsets.
DEFAULT_THEME = "jiaran-eat"
THEMES = [
    # id, display name, characters, source dirs
    ("jiaran-eat", "嘉然今天吃什么", ["嘉然"], ["嘉然今天吃什么"]),
    ("jiaran-album-2025", "2025 嘉然的画册", ["嘉然"], ["2025嘉然的画册"]),
    ("jiaran-album-2026", "2026 嘉然的画册", ["嘉然"], ["嘉然的画册2026", "2026嘉然的画册"]),
    ("jiaran-2-0", "嘉然个性装扮 2.0", ["嘉然"], ["嘉然个性装扮2.0"]),
    ("jiaran-garden", "糖糖与小然熊的游园会", ["嘉然"], ["糖糖与小然熊的游园会"]),
    ("jiaran-naodong", "脑洞波 · 嘉然", ["嘉然"], ["脑洞波系列主题装扮-嘉然"]),
    ("nailin-tavern-2025", "2025 乃琳的酒馆", ["乃琳"], ["2025乃琳的酒馆"]),
    ("nailin-queen", "乃琳 Queen", ["乃琳"], ["乃琳Queen"]),
    ("nailin-2-0", "乃琳个性装扮 2.0", ["乃琳"], ["乃琳个性装扮2.0"]),
    ("nailin-raccoon", "奶淇琳浣熊", ["乃琳"], ["奶淇琳浣熊"]),
    ("nailin-naodong", "脑洞波 · 乃琳", ["乃琳"], ["脑洞波系列主题装扮-乃琳"]),
    ("beila-adventure-2025", "2025 贝拉的冒险", ["贝拉"], ["2025贝拉的冒险"]),
    ("beila-kira", "贝拉 kira", ["贝拉"], ["贝拉kira"]),
    ("beila-2-0", "贝拉个性装扮 2.0", ["贝拉"], ["贝拉个性装扮2.0"]),
    ("beila-rabbit", "贝拉兔与贝极星的日常", ["贝拉"], ["贝拉兔与贝极星的日常"]),
    ("beila-naodong", "脑洞波 · 贝拉", ["贝拉"], ["脑洞波系列主题装扮-贝拉"]),
    ("symphony", "心宜和思诺的交响乐谱", ["心宜", "思诺"], ["心宜和思诺的交响乐谱"]),
]

# -------------------------------------------------------------------- emotes
# Source directories live under <assets>/表情包 (AI高清 preferred, else 原图).
# id, display name, character, source dir  (whole sets by a single character)
EMOTE_SETS = [
    ("jiaran-eat", "嘉然今天吃什么", "嘉然", "嘉然今天吃什么"),
    ("jiaran-album-2025", "2025 嘉然的画册", "嘉然", "2025嘉然的画册"),
    ("jiaran-album-2026", "2026 嘉然的画册", "嘉然", "2026嘉然的画册"),
    ("jiaran-2-0", "嘉然个性装扮 2.0", "嘉然", "嘉然个性装扮2.0"),
    ("jiaran-garden", "糖糖与小然熊的游园会", "嘉然", "糖糖与小然熊的游园会"),
    ("jiaran-naodong", "脑洞波 · 嘉然", "嘉然", "脑洞波系列主题装扮-嘉然"),
    ("nailin-tavern-2025", "2025 乃琳的酒馆", "乃琳", "2025乃琳的酒馆"),
    ("nailin-queen", "乃琳 Queen", "乃琳", "乃琳Queen"),
    ("nailin-2-0", "乃琳个性装扮 2.0", "乃琳", "乃琳个性装扮2.0"),
    ("nailin-raccoon", "奶淇琳浣熊", "乃琳", "奶淇琳浣熊"),
    ("nailin-naodong", "脑洞波 · 乃琳", "乃琳", "脑洞波系列主题装扮-乃琳"),
    ("beila-adventure-2025", "2025 贝拉的冒险", "贝拉", "2025贝拉的冒险"),
    ("beila-kira", "贝拉 kira", "贝拉", "贝拉kira"),
    ("beila-2-0", "贝拉个性装扮 2.0", "贝拉", "贝拉个性装扮2.0"),
    ("beila-rabbit", "贝拉兔与贝极星的日常", "贝拉", "贝拉兔与贝极星的日常"),
    ("beila-naodong", "脑洞波 · 贝拉", "贝拉", "脑洞波系列主题装扮-贝拉"),
]

# Mixed sets: (source dir, [(set id, set name, character, [file stems])])
MIXED_EMOTE_SETS = [
    (
        "A-SOUL 绽放收藏集",
        [
            ("bloom-jiaran", "绽放收藏集 · 嘉然", "嘉然", ["嘉心糖", "嘉然", "懂你意思", "笑晕了", "超喜欢"]),
            ("bloom-nailin", "绽放收藏集 · 乃琳", "乃琳", ["乃琳", "奶淇琳", "摸摸头", "晚安", "约定"]),
            ("bloom-beila", "绽放收藏集 · 贝拉", "贝拉", ["抱抱", "接好运", "毫无头绪", "贝拉", "贝极星"]),
        ],
    ),
    (
        "心宜和思诺的交响乐谱",
        [
            ("symphony-xinyi", "交响乐谱 · 心宜", "心宜",
             ["为你打call", "呆", "哭哭", "喝一杯", "欸嘿", "生气", "睡觉", "谢谢款待", "阿？", "飞踢"]),
            ("symphony-sinuo", "交响乐谱 · 思诺", "思诺",
             ["为你应援", "举高高", "亲亲", "吃饭", "帅！", "急了急了", "打你", "抱抱", "晚安喵", "飞飞飞"]),
        ],
    ),
]

# --------------------------------------------------------------------- cards
# series id -> (display name, source dir under <assets>/收藏集卡牌)
CARD_SERIES = {
    "bloom": ("A-SOUL 绽放收藏集", "A-SOUL绽放收藏集"),
    "brilliant": ("嘉然的画册 · 绚烂心迹", "嘉然的画册-绚烂心迹"),
    "moon": ("嘉然的画册 · 此间为爱", "嘉然的画册-此间为爱"),
    "tavern": ("乃琳的酒馆 · 沉沦醉与爱", "乃琳的酒馆-沉沦醉与爱"),
    "voyage": ("贝拉的冒险 · 时空旅人", "贝拉的冒险-时空旅人"),
    "symphony": ("心宜和思诺的交响乐谱 · 双声巡梦", "心宜和思诺的交响乐谱-双声巡梦"),
}

# (series, numeric id, card name, characters).  Only cards listed here exist.
CARDS = [
    ("tavern", "1762331462002", "蝶影共醉", ["乃琳"]),
    ('moon', '1781070981009', '珍馐派对', ['嘉然']),
    ('moon', '1781070981002', '午睡时间', ['嘉然']),
    ('moon', '1781070981003', '倚凭栏', ['嘉然']),
    ('moon', '1781070981004', 'SUPER IDOL', ['嘉然']),
    ('moon', '1781070981005', '安可time', ['嘉然']),
    ('moon', '1781070981006', '非请勿入', ['嘉然']),
    ('moon', '1781070981007', '噔噔噔！灯会', ['嘉然']),
    ('moon', '1781070981008', '金币至上', ['嘉然']),
    ('tavern', '1762331462009', '绮梦妖狐', ['乃琳']),
    ('tavern', '1762331462003', '四季的心动', ['乃琳']),
    ('tavern', '1762331462004', '罗兰紫嫣', ['乃琳']),
    ('tavern', '1762331462005', '欢迎光琳', ['乃琳']),
    ('tavern', '1762331462006', '酒意半酣', ['乃琳']),
    ('tavern', '1762331462007', '女王法典', ['乃琳']),
    ('tavern', '1762331462008', '镜界对影', ['乃琳']),
    ("bloom", "1700742793002", "睡衣系列-贝拉", ["贝拉"]),
    ("bloom", "1700742793004", "睡衣系列-乃琳", ["乃琳"]),
    ("bloom", "1700742793005", "睡衣系列-嘉然", ["嘉然"]),
    ("bloom", "1700742793007", "潮流系列-贝拉", ["贝拉"]),
    ("bloom", "1700742793008", "潮流系列-嘉然", ["嘉然"]),
    ("bloom", "1700742793010", "《绽放》舞蹈-嘉然", ["嘉然"]),
    ("bloom", "1700742793012", "Q版系列-贝拉", ["贝拉"]),
    ("bloom", "1700742793013", "Q版系列-嘉然", ["嘉然"]),
    ("bloom", "1700742793014", "潮流系列-乃琳", ["乃琳"]),
    ("bloom", "1700742793015", "都市系列-贝拉", ["贝拉"]),
    ("bloom", "1700742793016", "Q版系列-乃琳", ["乃琳"]),
    ("bloom", "1700742793017", "《绽放》舞蹈-乃琳", ["乃琳"]),
    ("bloom", "1700742793018", "《绽放》舞蹈-贝拉", ["贝拉"]),
    ("bloom", "1700742793020", "都市系列-乃琳", ["乃琳"]),
    ("bloom", "1700742793021", "都市系列-嘉然", ["嘉然"]),
    ("bloom", "1700742793022", "舞台系列-贝拉", ["贝拉"]),
    ("bloom", "1700742793023", "舞台系列-嘉然", ["嘉然"]),
    ("bloom", "1700742793026", "舞台系列-乃琳", ["乃琳"]),
    ("bloom", "1700742793031", "时序系列-嘉然", ["嘉然"]),
    ("bloom", "1700742793032", "时序系列-贝拉", ["贝拉"]),
    ("bloom", "1700742793033", "时序系列-乃琳", ["乃琳"]),
    ("bloom", "1700799218001", "《Shiny Dancer》", ["贝拉"]),
    ("bloom", "1700799218003", "《Sweet Counter》", ["乃琳"]),
    ("bloom", "1700799218004", "《Hopeful Dreamer》", ["嘉然"]),
    ("tavern", "1762331702001", "临阶倩影", ["乃琳"]),
    ("moon", "1781070981010", "月纱花信", ["嘉然"]),
    ("brilliant", "1745315724002", "绘心物语", ["嘉然"]),
    ("brilliant", "1745315724003", "甜蜜时刻", ["嘉然"]),
    ("brilliant", "1745315724004", "春日暖阳", ["嘉然"]),
    ("brilliant", "1745315724005", "草莓甜心", ["嘉然"]),
    ("brilliant", "1745315724006", "电玩高手", ["嘉然"]),
    ("brilliant", "1745315724007", "喵喵出击", ["嘉然"]),
    ("brilliant", "1745315724008", "天使奇遇", ["嘉然"]),
    ("brilliant", "1745315724009", "星夜私语", ["嘉然"]),
    ("brilliant", "1745398468001", "请快乐！", ["嘉然"]),
    ("symphony", "1748345610002", "海中密语", ["思诺"]),
    ("symphony", "1748345610003", "与你相依", ["心宜", "思诺"]),
    ("symphony", "1748345610004", "闪耀时刻", ["思诺"]),
    ("symphony", "1748345610005", "缤纷光影", ["心宜"]),
    ("symphony", "1748345610006", "花见邂逅", ["思诺"]),
    ("symphony", "1748345610007", "遇见幸运", ["心宜"]),
    ("symphony", "1748345610008", "初智齿", ["思诺"]),
    ("symphony", "1748345610009", "相信光", ["心宜"]),
    ("symphony", "1748345610010", "巡梦漫游", ["心宜", "思诺"]),
    ("symphony", "1748345610011", "魔女契约", ["心宜", "思诺"]),
    ("voyage", "1756378523002", "时空行者", ["贝拉"]),
    ("voyage", "1756378523003", "拉龙入侵", ["贝拉"]),
    ("voyage", "1756378523004", "一起跳起来！", ["贝拉"]),
    ("voyage", "1756378523005", "决定性电话瞬间", ["贝拉"]),
    ("voyage", "1756378523006", "灯塔之约", ["贝拉"]),
    ("voyage", "1756378523007", "西部女武神", ["贝拉"]),
    ("voyage", "1756378523008", "末路狂花", ["贝拉"]),
    ("voyage", "1756378523009", "星贝传说", ["贝拉"]),
    ("voyage", "1756378523010", "引爆枝江大楼", ["贝拉"]),
]

BIG_HIDDEN_IDS = {'1700742793031', '1700742793032', '1748345610010', '1745315724002', '1781070981009', '1762331462002', '1756378523002', '1700742793033'}
SMALL_HIDDEN_IDS = {'1762331462009', '1700742793026', '1756378523010', '1700742793022', '1781070981010', '1745315724008', '1700742793023', '1748345610011'}
RARITIES = ["common", "rare", "epic", "legendary"]


def card_tier(card_id: str) -> str:
    return "big" if card_id in BIG_HIDDEN_IDS else "small" if card_id in SMALL_HIDDEN_IDS else "normal"


def card_rarity(card_id: str, name: str, has_video: bool) -> str:
    return {"big": "legendary", "small": "epic", "normal": "common"}[card_tier(card_id)]


def card_subseries(series: str, name: str) -> str | None:
    if series == "bloom" and "-" in name:
        return name.split("-")[0]
    return None


# ------------------------------------------------------------------ economy
# Emote sets are common, except the bloom collection sets.  Non-default themes are rare.
RARE_EMOTE_SETS = {"bloom-jiaran", "bloom-nailin", "bloom-beila"}
THEME_RARITY = "rare"
# Every player owns the five characters, the default theme and the first
# STARTER_EMOTES emotes of each character's first emote set.
STARTER_EMOTES = 4
# Duplicates turn into shards; shards craft a chosen missing item.
DUP_SHARDS = {"common": 1, "rare": 3, "epic": 8, "legendary": 20}
CRAFT_COST = {"common": 10, "rare": 30, "epic": 80, "legendary": 200}


# -------------------------------------------------------- frames and badges
# id, kind, display name, source file (relative to <assets>/杂项), series, min cards
# frame unlock: own >= min(5, series size) distinct cards; badge: own >= 1 card.
FRAMES_BADGES = [
    ("frame-brilliant", "frame", "绚烂心迹 头像挂件", "绚烂心迹/嘉然头像挂件-1743597003001_other.png", "brilliant"),
    ("badge-brilliant", "badge", "绚烂心迹 LV1", "绚烂心迹.LV1/绚烂心迹.LV1-1745315724002_other.png", "brilliant"),
    ("frame-moon", "frame", "此间为爱 头像挂件", "此间为爱/嘉然头像挂件-1780993181001_other.png", "moon"),
    ("frame-tavern", "frame", "沉沦醉与爱 头像挂件", "沉沦醉与爱/乃琳头像挂件-1755580227001_other.png", "tavern"),
    ("badge-tavern", "badge", "2025 乃琳的酒馆 LV1", "2025乃琳的酒馆.LV1/2025乃琳的酒馆.LV1-1762331462002_other.png", "tavern"),
    ("frame-voyage", "frame", "时空旅人 头像挂件", "时空旅人/贝拉头像挂件-1755607041001_other.png", "voyage"),
    ("badge-voyage", "badge", "2025 贝拉的冒险 LV1", "2025贝拉的冒险.LV1/2025贝拉的冒险.LV1-1756378523002_other.png", "voyage"),
    ("frame-symphony", "frame", "双声巡梦 头像框", "双声巡梦/心宜思诺头像框-1748246876001_other.png", "symphony"),
    ("badge-symphony", "badge", "交响乐谱 LV1", "心宜和思诺的交响乐谱.LV1/心宜和思诺的交响乐谱.LV1-1748345610010_other.png", "symphony"),
]
