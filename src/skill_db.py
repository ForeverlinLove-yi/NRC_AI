"""
技能数据库 - 从CSV加载并解析技能效果
"""

import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.models import Skill, Type, SkillCategory, TYPE_NAME_MAP, CATEGORY_NAME_MAP

# 魔攻属性类型
SPECIAL_TYPES = {Type.FIRE, Type.WATER, Type.GRASS, Type.ELECTRIC, Type.ICE,
                 Type.PSYCHIC, Type.DRAGON, Type.DARK, Type.FAIRY}

_skill_db: dict = {}


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

    # 脱离
    if '脱离' in d:
        skill.force_switch = True

    # 迅捷
    if '迅捷' in d:
        skill.agility = True

    # 蓄力
    if '蓄力' in d:
        skill.charge = True

    # 自身属性增益
    def parse_self_stat(pattern, field):
        m = re.search(pattern, d)
        if m:
            setattr(skill, field, int(m.group(1)) / 100.0)

    parse_self_stat(r'获得物攻\+(\d+)%', 'self_atk')
    parse_self_stat(r'获得魔攻\+(\d+)%', 'self_spatk')
    parse_self_stat(r'获得物防\+(\d+)%', 'self_def')
    parse_self_stat(r'获得魔防\+(\d+)%', 'self_spdef')
    parse_self_stat(r'获得速度\+(\d+)', 'self_speed')
    parse_self_stat(r'获得速度-(\d+)', 'self_speed')  # speed is flat, handle below

    # 速度是固定值加减
    m = re.search(r'获得速度\+(\d+)', d)
    if m:
        # 速度+120 意味着速度修正+120/100=1.2 (相对于基础速度)
        val = int(m.group(1))
        skill.self_speed = val / 100.0
    m = re.search(r'获得速度-(\d+)', d)
    if m:
        val = int(m.group(1))
        skill.self_speed = -val / 100.0

    # 双攻/双防
    m = re.search(r'双攻\+(\d+)%', d)
    if m:
        v = int(m.group(1)) / 100.0
        skill.self_atk += v
        skill.self_spatk += v
    m = re.search(r'双攻-(\d+)%', d)
    if m:
        v = int(m.group(1)) / 100.0
        skill.self_atk -= v
        skill.self_spatk -= v
    m = re.search(r'双防\+(\d+)%', d)
    if m:
        v = int(m.group(1)) / 100.0
        skill.self_def += v
        skill.self_spdef += v
    m = re.search(r'双防-(\d+)%', d)
    if m:
        v = int(m.group(1)) / 100.0
        skill.self_def -= v
        skill.self_spdef -= v

    # 技能威力
    m = re.search(r'获得技能威力\+(\d+)', d)
    if m:
        skill.power += int(m.group(1))
    m = re.search(r'全技能威力\+(\d+)', d)
    if m:
        skill.power += int(m.group(1))

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

    # ===== 应对效果解析 =====
    # 简化：应对攻击 = 应对物攻/魔攻; 应对防御 = 对方防御; 应对状态 = 对方状态

    # 应对攻击的额外效果
    if '应对攻击' in d:
        m = re.search(r'应对攻击.*?吸血(\d+)%', d)
        if m:
            skill.counter_physical_drain = int(m.group(1)) / 100.0
        m = re.search(r'应对攻击.*?失去(\d+)能量', d)
        if m:
            skill.counter_physical_energy_drain = int(m.group(1))
        m = re.search(r'应对攻击.*?物攻\+(\d+)%', d)
        if m:
            skill.counter_physical_self_atk = int(m.group(1)) / 100.0
        m = re.search(r'应对攻击.*?物防-(\d+)%', d)
        if m:
            skill.counter_physical_enemy_def = int(m.group(1)) / 100.0
        m = re.search(r'应对攻击.*?物攻-(\d+)%', d)
        if m:
            skill.counter_physical_enemy_atk = int(m.group(1)) / 100.0

    # 应对状态的额外效果
    if '应对状态' in d:
        m = re.search(r'应对状态.*?威力.*?(\d+)倍', d)
        if m:
            skill.counter_status_power_mult = int(m.group(1))
        m = re.search(r'应对状态.*?翻倍', d)
        if m and skill.counter_status_power_mult == 0:
            skill.counter_status_power_mult = 2
        m = re.search(r'应对状态.*?失去(\d+)能量', d)
        if m:
            skill.counter_status_enemy_lose_energy = int(m.group(1))
        m = re.search(r'应对状态.*?物攻\+(\d+)%', d)
        if m:
            skill.counter_status_self_atk = int(m.group(1)) / 100.0
        m = re.search(r'应对状态.*?吸血(\d+)%', d)
        if m:
            skill.counter_physical_drain = int(m.group(1)) / 100.0

    # 应对防御的额外效果
    if '应对防御' in d:
        m = re.search(r'应对防御.*?物攻\+(\d+)%', d)
        if m:
            skill.counter_defense_self_atk = int(m.group(1)) / 100.0
        m = re.search(r'应对防御.*?物防\+(\d+)%', d)
        if m:
            skill.counter_defense_self_def = int(m.group(1)) / 100.0
        m = re.search(r'应对防御.*?物防-(\d+)%', d)
        if m:
            skill.counter_defense_enemy_def = int(m.group(1)) / 100.0
        m = re.search(r'应对防御.*?双防-(\d+)%', d)
        if m:
            v = int(m.group(1)) / 100.0
            skill.counter_defense_enemy_def += v
        m = re.search(r'应对防御.*?攻击技能能耗\+(\d+)', d)
        if m:
            skill.counter_defense_enemy_energy_cost = int(m.group(1))
        m = re.search(r'应对防御.*?失去(\d+)能量', d)
        if m:
            skill.counter_defense_enemy_energy_cost = int(m.group(1))
        m = re.search(r'应对防御.*?(\d+)层中毒', d)
        if m:
            skill.counter_status_poison_stacks = int(m.group(1))

    return skill


def _parse_csv_row(row):
    """解析CSV行"""
    name = row[0].strip()
    if not name:
        return None

    skill_type = TYPE_NAME_MAP.get(row[1].strip(), Type.NORMAL)
    category = CATEGORY_NAME_MAP.get(row[2].strip(), SkillCategory.PHYSICAL)

    power = 0
    try:
        power = int(row[3].strip())
    except (ValueError, IndexError):
        pass

    energy = 0
    try:
        energy = int(row[4].strip())
    except (ValueError, IndexError):
        pass

    desc = row[5].strip() if len(row) > 5 else ""

    skill = Skill(
        name=name, skill_type=skill_type, category=category,
        power=power, energy_cost=energy,
    )

    if desc:
        parse_effect(skill, desc)

    return skill


def load_skills(csv_path: str = None) -> dict:
    """加载技能数据库"""
    global _skill_db
    if _skill_db:
        return _skill_db

    if csv_path is None:
        csv_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "skills_all.csv"
        )

    if not os.path.exists(csv_path):
        print(f"[WARN] Skill DB not found: {csv_path}")
        return {}

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for row in reader:
            skill = _parse_csv_row(row)
            if skill:
                _skill_db[skill.name] = skill

    print(f"[OK] Loaded {len(_skill_db)} skills from DB")
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
