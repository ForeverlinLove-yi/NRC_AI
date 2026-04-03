"""
技能数据库 - 从 SQLite 加载并解析技能效果
"""
import os
import re
import sqlite3
from typing import Optional, Dict, List

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.models import Skill, Type, SkillCategory, TYPE_NAME_MAP, CATEGORY_NAME_MAP

# 魔攻属性类型
SPECIAL_TYPES = {Type.FIRE, Type.WATER, Type.GRASS, Type.ELECTRIC, Type.ICE,
                 Type.PSYCHIC, Type.DRAGON, Type.DARK, Type.FAIRY}

_conn: Optional[sqlite3.Connection] = None
_skill_db: dict = {}
_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "nrc.db")

# 属性中文名→Type (包含短名)
_TYPE_MAP = {
    "普通": Type.NORMAL, "火": Type.FIRE, "水": Type.WATER, "草": Type.GRASS,
    "电": Type.ELECTRIC, "冰": Type.ICE, "武": Type.FIGHTING, "毒": Type.POISON,
    "地": Type.GROUND, "翼": Type.FLYING, "幻": Type.PSYCHIC, "虫": Type.BUG,
    "岩": Type.ROCK, "幽": Type.GHOST, "龙": Type.DRAGON, "恶": Type.DARK,
    "机械": Type.STEEL, "萌": Type.FAIRY, "光": Type.PSYCHIC,
    "未知": Type.NORMAL, "—": Type.NORMAL,
}
_TYPE_MAP.update(TYPE_NAME_MAP)

# 分类中文名→SkillCategory (含 wiki 用语)
_CAT_MAP = {
    "物理": SkillCategory.PHYSICAL, "魔法": SkillCategory.MAGICAL,
    "防御": SkillCategory.DEFENSE, "状态": SkillCategory.STATUS,
    "物攻": SkillCategory.PHYSICAL, "魔攻": SkillCategory.MAGICAL,
    "变化": SkillCategory.STATUS, "—": SkillCategory.STATUS,
}
_CAT_MAP.update(CATEGORY_NAME_MAP)


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        if not os.path.exists(_DB_PATH):
            raise FileNotFoundError(f"Database not found: {_DB_PATH}")
        _conn = sqlite3.connect(_DB_PATH)
        _conn.row_factory = sqlite3.Row
    return _conn


def parse_effect(skill: Skill, desc: str) -> Skill:
    """从效果描述文本解析技能效果"""
    d = desc.replace("，", ",").replace("。", "").replace("：", ":")

    # 连击数
    m = re.search(r'(\d+)连击', d)
    if m:
        skill.hit_count = int(m.group(1))

    # 吸血
    m = re.search(r'吸血(\d+)%', d)
    if m:
        skill.life_drain = int(m.group(1)) / 100.0

    # 减伤
    m = re.search(r'减伤(\d+)%', d)
    if m:
        skill.damage_reduction = int(m.group(1)) / 100.0

    # 自身回血
    for pattern in [r'回复(\d+)%生命', r'自己回复(\d+)%生命']:
        m = re.search(pattern, d)
        if m:
            skill.self_heal_hp = int(m.group(1)) / 100.0

    # 回复能量
    m = re.search(r'回复(\d+)能量', d)
    if m:
        skill.self_heal_energy = int(m.group(1))

    # 偷取能量
    m = re.search(r'偷取敌方?(\d+)能量', d)
    if m:
        skill.steal_energy = int(m.group(1))

    # 敌方失去能量
    m = re.search(r'敌方失去(\d+)能量', d)
    if m:
        skill.enemy_lose_energy = int(m.group(1))

    # 先手
    m = re.search(r'先手\+(\d+)', d)
    if m:
        skill.priority_mod = int(m.group(1))
    m = re.search(r'先手-(\d+)', d)
    if m:
        skill.priority_mod = -int(m.group(1))

    # 折返/脱离
    if '折返' in d or '脱离' in d:
        skill.force_switch = True

    # 迅捷
    if '迅捷' in d:
        skill.agility = True

    # 蓄力
    if '蓄力' in d:
        skill.charge = True

    # 寄生
    m = re.search(r'(\d+)层寄生', d)
    if m:
        skill.leech_stacks = int(m.group(1))
    elif '寄生' in d:
        skill.leech_stacks = 1

    # 星陨
    m = re.search(r'(\d+)层星陨', d)
    if m:
        skill.meteor_stacks = int(m.group(1))
    elif '星陨' in d:
        skill.meteor_stacks = 1

    # 印记/场效
    if '印记' in d or '场地' in d or '全队' in d:
        skill.is_mark = True

    # 自身属性增益
    def parse_self_stat(pattern, field):
        m = re.search(pattern, d)
        if m:
            setattr(skill, field, int(m.group(1)) / 100.0)

    parse_self_stat(r'获得物攻\+(\d+)%', 'self_atk')
    parse_self_stat(r'获得魔攻\+(\d+)%', 'self_spatk')
    parse_self_stat(r'获得物防\+(\d+)%', 'self_def')
    parse_self_stat(r'获得魔防\+(\d+)%', 'self_spdef')

    m = re.search(r'获得速度\+(\d+)', d)
    if m:
        skill.self_speed = int(m.group(1)) / 100.0
    m = re.search(r'获得速度-(\d+)', d)
    if m:
        skill.self_speed = -int(m.group(1)) / 100.0

    # 双攻/双防
    m = re.search(r'双攻\+(\d+)%', d)
    if m:
        v = int(m.group(1)) / 100.0
        skill.self_atk += v
        skill.self_spatk += v
    m = re.search(r'双防\+(\d+)%', d)
    if m:
        v = int(m.group(1)) / 100.0
        skill.self_def += v
        skill.self_spdef += v

    # 敌方属性减益
    def parse_enemy_stat(pattern, field):
        m = re.search(pattern, d)
        if m:
            setattr(skill, field, int(m.group(1)) / 100.0)

    parse_enemy_stat(r'敌方获得物攻-(\d+)%', 'enemy_atk')
    parse_enemy_stat(r'敌方获得魔攻-(\d+)%', 'enemy_spatk')
    parse_enemy_stat(r'敌方获得物防-(\d+)%', 'enemy_def')
    parse_enemy_stat(r'敌方获得魔防-(\d+)%', 'enemy_spdef')
    parse_enemy_stat(r'敌方获得双攻-(\d+)%', 'enemy_all_atk')
    parse_enemy_stat(r'敌方获得双防-(\d+)%', 'enemy_all_def')

    # 状态层数
    m = re.search(r'(\d+)层中毒', d)
    if m:
        skill.poison_stacks = int(m.group(1))
    m = re.search(r'(\d+)层灼烧', d)
    if m:
        skill.burn_stacks = int(m.group(1))
    m = re.search(r'(\d+)层冻结', d)
    if m:
        skill.freeze_stacks = int(m.group(1))

    # 敌方技能能耗+X
    m = re.search(r'敌方获得全技能能耗\+(\d+)', d)
    if m:
        skill.enemy_energy_cost_up = int(m.group(1))
    m = re.search(r'技能能耗\+(\d+)', d)
    if m and skill.enemy_energy_cost_up == 0:
        skill.enemy_energy_cost_up = int(m.group(1))

    # 应对攻击
    if '应对攻击' in d:
        m = re.search(r'应对攻击.*?吸血(\d+)%', d)
        if m:
            skill.counter_physical_drain = int(m.group(1)) / 100.0
        m = re.search(r'应对攻击.*?失去(\d+)能量', d)
        if m:
            skill.counter_physical_energy_drain = int(m.group(1))

    # 应对状态
    if '应对状态' in d:
        m = re.search(r'应对状态.*?威力.*?(\d+)倍', d)
        if m:
            skill.counter_status_power_mult = int(m.group(1))
        m = re.search(r'应对状态.*?翻倍', d)
        if m and skill.counter_status_power_mult == 0:
            skill.counter_status_power_mult = 2

    # 应对防御
    if '应对防御' in d:
        m = re.search(r'应对防御.*?物攻\+(\d+)%', d)
        if m:
            skill.counter_defense_self_atk = int(m.group(1)) / 100.0

    return skill


def load_skills(csv_path: str = None) -> dict:
    """从 SQLite 加载技能数据库（兼容旧接口）"""
    global _skill_db
    if _skill_db:
        return _skill_db

    # 加载效果数据配置 (新引擎)
    try:
        from src.effect_data import SKILL_EFFECTS
    except ImportError:
        SKILL_EFFECTS = {}

    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM skill")

    new_count = 0
    for row in c.fetchall():
        name = row["name"]
        element = _TYPE_MAP.get(row["element"], Type.NORMAL)
        category = _CAT_MAP.get(row["category"], SkillCategory.STATUS)
        power = row["power"] or 0
        energy = row["energy_cost"] or 0
        desc = row["description"] or ""

        skill = Skill(
            name=name, skill_type=element, category=category,
            power=power, energy_cost=energy,
        )

        # 优先使用新引擎的效果数据
        if name in SKILL_EFFECTS:
            skill.effects = SKILL_EFFECTS[name]
            new_count += 1
        elif desc:
            # 旧技能仍走正则解析
            parse_effect(skill, desc)

        _skill_db[name] = skill

    print(f"[OK] Loaded {len(_skill_db)} skills from DB ({new_count} with new effect engine)")
    return _skill_db


def get_skill(name: str) -> Skill:
    """获取技能（返回副本）"""
    load_skills()
    if name in _skill_db:
        return _skill_db[name].copy()
    return Skill(name=name, skill_type=Type.NORMAL, category=SkillCategory.PHYSICAL,
                power=40, energy_cost=2)


def get_all_skills() -> dict:
    """获取所有技能"""
    load_skills()
    return dict(_skill_db)


def get_skill_learners(skill_name: str) -> List[str]:
    """获取能学习某技能的精灵列表"""
    conn = _get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT p.name FROM pokemon p
        JOIN pokemon_skill ps ON ps.pokemon_id = p.id
        JOIN skill s ON ps.skill_id = s.id
        WHERE s.name = ?
    """, (skill_name,))
    return [r[0] for r in c.fetchall()]


def load_ability_effects(ability_str: str) -> list:
    """
    根据精灵的特性字符串 (格式: '特性名:描述') 返回 AbilityEffect 列表。
    如果特性在 ABILITY_EFFECTS 中有配置则返回配置, 否则返回空列表。
    """
    try:
        from src.effect_data import ABILITY_EFFECTS
    except ImportError:
        return []

    # 提取特性名
    if ":" in ability_str:
        name = ability_str.split(":")[0]
    elif "：" in ability_str:
        name = ability_str.split("：")[0]
    else:
        name = ability_str

    return ABILITY_EFFECTS.get(name, [])
