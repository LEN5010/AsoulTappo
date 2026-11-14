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
    {"id": "beila", "name": "贝拉", "color": "#db7d74"},
    {"id": "xinyi", "name": "心宜", "color": "#c93773"},
    {"id": "sinuo", "name": "思诺", "color": "#7252c0"},
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

# Additional sets in the member/collection layout. Keep the original GIF animation.
# id, title, member, collection directory, source folder
COLLECTION_EMOTE_SETS = [
    ("nailin-reverie", "绮梦漫游 · 乃琳", "乃琳", "乃琳的酒馆-绮梦漫游", "表情包AI高清"),
    ("beila-casket", "匣中惊鸿 · 贝拉", "贝拉", "贝拉的冒险-匣中惊鸿", "表情包AI高清"),
    ("jiaran-moon-motion", "此间为爱 · 嘉然（动态）", "嘉然", "嘉然的画册-此间为爱", "动态表情包"),
    ("nailin-reverie-motion", "绮梦漫游 · 乃琳（动态）", "乃琳", "乃琳的酒馆-绮梦漫游", "动态表情包"),
    ("beila-casket-motion", "匣中惊鸿 · 贝拉（动态）", "贝拉", "贝拉的冒险-匣中惊鸿", "动态表情包"),
]

# 阿草's stickers: won from scratch cards only, never in the resonance pool and never crafted.
# id, title, owner, sticker names in emote order. The pictures (表情包/阿草和TA的朋友们/AI高清, trimmed and scaled
# to 320px) are kept in client/public/assets/emotes/achao/<nn>.webp; the pipeline only lists them.
SCRATCH_EMOTE_SET = ("achao", "阿草和TA的朋友们", "阿草", [
    "兜风", "安慰", "对不起", "微笑", "惊恐", "才八点", "打call", "拒绝", "招商", "收到",
    "晚安", "欢呼", "比心", "流汗", "生无可恋", "看直播", "索嗨嗨", "肯定", "观察", "谢谢观看",
])

# --------------------------------------------------------------------- cards
# series id -> (display name, source dir under <assets>/收藏集卡牌)
CARD_SERIES = {
    "bloom": ("A-SOUL 绽放收藏集", "A-SOUL绽放收藏集"),
    "brilliant": ("嘉然的画册 · 绚烂心迹", "嘉然的画册-绚烂心迹"),
    "moon": ("嘉然的画册 · 此间为爱", "嘉然的画册-此间为爱"),
    "tavern": ("乃琳的酒馆 · 沉沦醉与爱", "乃琳的酒馆-沉沦醉与爱"),
    "voyage": ("贝拉的冒险 · 时空旅人", "贝拉的冒险-时空旅人"),
    "symphony": ("心宜和思诺的交响乐谱 · 双声巡梦", "心宜和思诺的交响乐谱-双声巡梦"),
    "reverie": ("乃琳的酒馆 · 绮梦漫游", "乃琳的酒馆-绮梦漫游"),
    "casket": ("贝拉的冒险 · 匣中惊鸿", "贝拉的冒险-匣中惊鸿"),
}

# Member-first layout used by the newer downloadable collection archive.
CARD_SOURCE_DIRS = {
    "bloom": "A-SOUL/A-SOUL 绽放收藏集/收藏集",
    "brilliant": "嘉然/嘉然的画册-绚烂心迹/收藏集",
    "moon": "嘉然/嘉然的画册-此间为爱/收藏集",
    "tavern": "乃琳/乃琳的酒馆-沉沦罪与爱/收藏集",
    "voyage": "贝拉/贝拉的冒险-时空旅人/收藏集",
    "symphony": "心宜和思诺/心宜和思诺的交响乐谱-双声巡梦/收藏集",
    "reverie": "乃琳/乃琳的酒馆-绮梦漫游/收藏集",
    "casket": "贝拉/贝拉的冒险-匣中惊鸿/收藏集",
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
    ("reverie", "1787896765002", "晨间一刻", ["乃琳"]),
    ("reverie", "1787896765003", "歌剧之星", ["乃琳"]),
    ("reverie", "1787896765004", "软绵绵时光", ["乃琳"]),
    ("reverie", "1787896765005", "Shining！", ["乃琳"]),
    ("reverie", "1787896765006", "采购日", ["乃琳"]),
    ("reverie", "1787896765007", "晚风微醺", ["乃琳"]),
    ("reverie", "1787896765008", "甜蜜便当", ["乃琳"]),
    ("reverie", "1787896765009", "危险邀约", ["乃琳"]),
    ("reverie", "1787896765010", "纯白誓约", ["乃琳"]),
    ("casket", "1785126321002", "月下童话", ["贝拉"]),
    ("casket", "1785126321003", "浮生若梦", ["贝拉"]),
    ("casket", "1785126321004", "Shopping Time", ["贝拉"]),
    ("casket", "1785126321005", "公路旅行", ["贝拉"]),
    ("casket", "1785126321006", "海风之恋", ["贝拉"]),
    ("casket", "1785126321007", "一起去滑雪", ["贝拉"]),
    ("casket", "1785126321008", "新的邀请", ["贝拉"]),
    ("casket", "1785126321009", "在你身边", ["贝拉"]),
    ("casket", "1785126321010", "夜的终章", ["贝拉"]),
]

BIG_HIDDEN_IDS = {'1700742793031', '1700742793032', '1748345610010', '1745315724002', '1781070981009', '1762331462002', '1756378523002', '1700742793033'}
SMALL_HIDDEN_IDS = {'1762331462009', '1700742793026', '1756378523010', '1700742793022', '1781070981010', '1745315724008', '1700742793023', '1748345610011'}
BIG_HIDDEN_IDS.update({'1787896765003', '1785126321002'})
SMALL_HIDDEN_IDS.update({'1787896765010', '1785126321010'})
# Cards whose video holds one still picture over its sound: no dancing, only the voice track.
STILL_VIDEO_IDS = {
    '1762331462004', '1745315724003', '1748345610002', '1748345610003', '1756378523003',
    '1700742793022', '1700742793023', '1700742793026',
}
RARITIES = ["common", "uncommon", "rare", "epic", "legendary"]


def card_tier(card_id: str) -> str:
    return "big" if card_id in BIG_HIDDEN_IDS else "small" if card_id in SMALL_HIDDEN_IDS else "normal"


def card_still(card_id: str) -> bool:
    return card_id in STILL_VIDEO_IDS


def card_rarity(card_id: str, name: str, has_video: bool) -> str:
    tier = card_tier(card_id)
    if tier == "big":
        return "legendary"
    return "epic" if tier == "small" or has_video else "common"


def card_subseries(series: str, name: str) -> str | None:
    if series == "bloom" and "-" in name:
        return name.split("-")[0]
    return None


# ------------------------------------------------------------------ economy
# Animated collection emotes are rare; Bloom and Brainwave sets are uncommon.
RARE_EMOTE_SETS = {sid for sid, _, _, _, folder in COLLECTION_EMOTE_SETS if folder == "动态表情包"}
UNCOMMON_EMOTE_SETS = {"jiaran-naodong", "nailin-naodong", "beila-naodong",
                       "bloom-jiaran", "bloom-nailin", "bloom-beila"}
THEME_RARITY = "rare"
# Every player owns the five characters, the default theme and the first
# STARTER_EMOTES emotes of each character's first emote set.
STARTER_EMOTES = 4
# Resonance mixes every member; duplicates refund shards and crafting targets common/rare items.
# Pet skins. `name` is the id: the asset folder, the save's char:<name> item and the room's character field, so it
# never changes; it is the member followed by the series. `title` is what the screen shows instead, when set: the
# member followed by the skin's own name from SKIN_TITLES.
# `since` is the release (x.y.z) that ships the skin's picture: the server keeps the skin out of the resonance pool of
# clients older than it, and the skins sharing the newest `since` are the launch spotlight (client/src/stores/spotlight.ts).
SKIN_TITLES = {"嘉然山海经": "帝江", "贝拉山海经": "毕方", "乃琳山海经": "九尾狐",
               "嘉然2025生日": "小画嘉", "贝拉2025生日": "小滑板", "乃琳2025生日": "酒馆"}


def skin(member: str, series: str, since: str | None = None) -> dict:
    name = f"{member}{series}"
    out = {"name": name, "member": member}
    if name in SKIN_TITLES:
        out["title"] = f"{member}{SKIN_TITLES[name]}"
    if since:
        out["since"] = since
    return out


SKINS = [skin(member, series) for series in ("山海经", "睡衣派对") for member in ("嘉然", "乃琳", "贝拉")] + [
    skin("贝拉", "2025生日"),
    skin("嘉然", "2025生日"),
    skin("乃琳", "2025生日"),
] + [skin(member, "冬日奇迹", "1.2.0") for member in ("嘉然", "乃琳", "贝拉")] + [
    skin(member, "2025生日", "1.2.2") for member in ("心宜", "思诺")]
# Shards come from taps only: dailyCap × (1 − e^−x) over one China day, x = a·m + b·m² + c·m³ for m thousand taps
# (curve = [a, b, c]: 10 000 taps pay 9000, 20 000 pay 13 000, 30 000 pay 16 000, nearing 18 000);
# a minute pays for its first tapsPerMinute taps.
INCOME = {"dailyCap": 18000, "curve": [0.0890449, -0.00269613, 0.0000723108], "tapsPerMinute": 120}
RESONANCE = {"cost": 160, "rates": {"legendary": 0.1, "skin": 0.2, "epic": 4.5, "rare": 3, "uncommon": 6, "common": 86.2},
             "pity": {"legendary": 400, "skin": 200}, "commonKindWeights": {"card": 45, "emote": 41.2},
             # Shards a duplicate turns into at once: emotes, and cards by tier (big hidden cards never repeat).
             "duplicateRefund": {"emote": 5, "normal": 20, "small": 360},
             # Tiers that keep their odds once everything in them is owned; their repeats turn into shards.
             "repeatTiers": ["epic"]}
CRAFT_COST = {"common": 480, "uncommon": 960, "rare": 1600}
# Daily check-in prizes by amount; weights are percentages (1.7 draws on average, the top prize 10).
# A prize pays its shards give or take `spread` (uniform), so the amounts are seldom round; the mean is unchanged.
CHECKIN = {"prizes": [{"shards": 80, "weight": 30}, {"shards": 160, "weight": 30}, {"shards": 320, "weight": 20},
                      {"shards": 480, "weight": 12}, {"shards": 800, "weight": 6}, {"shards": 1600, "weight": 2}],
           "spread": 0.1}
# Scratch cards: `price` shards each, `daily` of them a China day. Weights are percentages and what is left
# of 100 wins nothing; the shard prizes return two thirds of the price on average. The emote tier gives one emote of
# `set` the save lacks, for certain on the `pity`-th card since the last one. Once the set is whole the tier and
# its pity are gone: its weight wins nothing. The server tells the room about `announce` shards or more.
SCRATCH = {"price": 500, "daily": 20,
           "prizes": [{"shards": 200, "weight": 25}, {"shards": 500, "weight": 20}, {"shards": 1000, "weight": 8},
                      {"shards": 2500, "weight": 3}, {"shards": 30000, "weight": 0.1}],
           "emote": {"set": SCRATCH_EMOTE_SET[0], "weight": 5, "pity": 10},
           "announce": 2500}
# Rock-paper-scissors between two room members. Both pay `bet` when the invite is accepted and the winner gets
# `prize`: a sixth of the two bets is burnt. An invite waits `inviteSec`, each round `throwSec`. A save's net
# win (prizes minus bets of the duels settled that China day) stays at or below `dailyWinCap`; losses are not
# capped. Both saves need `minTaps` taps in all, so fresh guest saves cannot feed shards to another one.
DUEL = {"stakes": [{"bet": 150, "prize": 250}, {"bet": 1500, "prize": 2500}, {"bet": 15000, "prize": 25000}],
        "inviteSec": 15, "throwSec": 10, "dailyWinCap": 10000, "minTaps": 10000}
# The park (clients after 1.2.1; design in docs/design/amusement-park.md). Every game there is paid in coins.
# coin: `price` shards each, as many as the shards pay for; `gift` free a day, given with the save's first status
# that day. Buying and the gift need `minTaps` taps in all. Every coin spent is a stamp; every `stampsPerCoin` stamps turn into a coin, and
# `badges` are the stamp totals that earn the three badges.
# scratch: two cards by their price in coins. `again` (a percentage, like the prize weights) hands the price back;
# the basic card keeps the old card's emote tier and pity, and once the set is whole that weight turns into `again`.
# A premium `skin` or `big` card is one the save lacks, else its `shards`. A save's first card of each kind wins
# `first` shards. Wins of `roomAt` shards are told to the room, of `serverAt` to every running pet. A `hidden` card
# is off sale: the server refuses to sell it and the client does not show it, but one already bought is still revealed
# and paid.
# race: one every `interval` seconds, bets taken for the first `betting`; with `startAt` (minute of the China day) the
# races are placed so that each starts then: one a day at 19:00, its bets open from ten minutes after the day before's
# start (the rest of the interval is the run and the podium). The dumplings of the five members start
# together on square 0 of a lap of `track` squares (the start is also the finish), roll a six-sided die for the order
# of play and move 1 to 3 squares (`dice`), carrying those stacked on them. A group must land on the finish exactly:
# what a roll carries past it walks back from it. All five are alike, so each wins with p = 1/5 (top two 2/5, last
# 1/5). Each race draws every member a popularity, a whole number in `popularity` (inclusive), its weight w in the
# opening odds (for last mirrored about the mean, so the favourite is the least backed to come last). Odds move with
# the coins staked on each kind: a member's share is (its coins + `depth` × w / Σw) / (all coins on that kind +
# `depth`), the odds `payout` / (share × places), rounded down to a tenth, at least `minOdds`; a bet keeps the odds it
# was placed at. With nothing staked win pays about 3.8 to 4.6 and top two 1.9 to 2.3; the highest stays below even
# money for the chance (p × odds at most 0.98). A save stakes at most `maxCoins`.
# A winning bet pays coins × odds in coins, each save's bets on a race summed and then rounded half up.
# lottery: `daily` tickets a save, 000 to 999, for each draw; the draw is at minute `drawAt` of the China day and
# sales close at `closeAt` before it. A lottery day runs from one draw to the next, so the next draw's tickets go on
# sale as soon as a draw is made. The top prize is the server-wide pool: it starts at `pool.seed` shards, every coin spent in the park
# (scratch, race and lottery) adds `pool.perCoin`, and it rolls over until a draw has a top winner. The second is
# `second` of the day's sales, split between winners; the third is `third` shards each.
PARK = {
    "coin": {"price": 500, "gift": 3, "minTaps": 10000, "stampsPerCoin": 30,
             "badges": [100, 1000, 5000]},
    "scratch": {
        "cards": {
            "basic": {"coins": 1, "again": 15, "first": 1000,
                      "prizes": [{"shards": 200, "weight": 20}, {"shards": 500, "weight": 18},
                                 {"shards": 1000, "weight": 9}, {"shards": 2500, "weight": 3},
                                 {"shards": 8000, "weight": 0.5}, {"shards": 50000, "weight": 0.1}],
                      "emote": {"set": SCRATCH_EMOTE_SET[0], "weight": 5, "pity": 10}},
            "premium": {"hidden": True, "coins": 5, "again": 15, "first": 5000,
                        "prizes": [{"shards": 3000, "weight": 14}, {"shards": 5000, "weight": 10},
                                   {"shards": 12500, "weight": 3}, {"shards": 40000, "weight": 0.5},
                                   {"shards": 250000, "weight": 0.02}],
                        "skin": {"weight": 0.5, "shards": 30000}, "big": {"weight": 0.5, "shards": 60000}},
        },
        "roomAt": {"basic": 8000, "premium": 40000},
        "serverAt": {"basic": 50000, "premium": 250000},
    },
    "race": {
        "interval": 86400, "betting": 85800, "startAt": 1140, "track": 24, "dice": [1, 2, 3], "payout": 0.85,
        "minOdds": 1.1, "depth": 100, "popularity": [92, 108], "maxCoins": 10, "kinds": ["win", "top2", "last"],
        # Five squares a race, all different, somewhere in `range` (inclusive): the boost and trip squares move a
        # landing group by `boost` and `trip`; the portal's two ends, `portalGap` squares apart (inclusive), take it to
        # the other end; the flip square turns its stack upside down. `roomAt` is in coins.
        "squares": {"range": [5, 20], "boost": 2, "trip": -1, "portalGap": [4, 6]},
        "roomAt": 20,
    },
    "lottery": {"daily": 10, "closeAt": 1130, "drawAt": 1135, "pool": {"seed": 30000, "perCoin": 50},
                "second": 0.20, "third": 600},
}

# --------------------------------------------------------------- name plates
# Name plates besides the big hidden cards, which are worn under their card id. Each unlocks once every emote
# of `emoteSet` is owned; the client keeps the picture and its crop (client/src/pet/plates.ts). Ids must never
# be card ids (those are "c" and digits).
PLATES = [{"id": "achao", "name": "阿草", "emoteSet": SCRATCH_EMOTE_SET[0]}]


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
