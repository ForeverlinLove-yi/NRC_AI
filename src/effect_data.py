"""
效果数据 — 35个技能 + 12个特性的结构化 EffectTag 配置

每个技能/特性的效果描述已拆解为有序的 EffectTag 列表。
只有在此配置中的技能才走新引擎，其余仍走旧的 parse_effect 正则。
"""

from src.effect_models import E, EffectTag, Timing, AbilityEffect


# ============================================================
#  技能效果配置: Dict[技能名, List[EffectTag]]
# ============================================================
SKILL_EFFECTS = {

    # ──────────── A队 (毒队) 技能 ────────────

    # 毒雾 (毒/状态/7/0): 将敌方所有增益，转化成中毒。
    "毒雾": [
        EffectTag(E.CONVERT_BUFF_TO_POISON),
    ],

    # 泡沫幻影 (水/状态/2/0): 减伤70%，应对攻击：自己脱离。
    "泡沫幻影": [
        EffectTag(E.DAMAGE_REDUCTION, {"pct": 0.7}),
        EffectTag(E.COUNTER_ATTACK, sub_effects=[
            EffectTag(E.FORCE_SWITCH),
        ]),
    ],

    # 疫病吐息 (毒/状态/3/0): 敌方获得1层中毒印记。
    "疫病吐息": [
        EffectTag(E.POISON_MARK, {"stacks": 1}),
    ],

    # 打湿 (水/变化/4/0): 自己获得1层湿润印记。
    "打湿": [
        EffectTag(E.MOISTURE_MARK, {"stacks": 1, "target": "self"}),
    ],

    # 嘲弄 (幽/状态/2/0): 自己获得魔攻+70%，若敌方本回合替换精灵，自己获得速度+70。
    "嘲弄": [
        EffectTag(E.SELF_BUFF, {"spatk": 0.7}),
        EffectTag(E.CONDITIONAL_BUFF, {
            "condition": "enemy_switch",
            "buff": {"speed": 0.7},
        }),
    ],

    # 恶意逃离 (恶/状态/1/0): 脱离，应对防御：额外使敌方攻击技能能耗+6。
    "恶意逃离": [
        EffectTag(E.FORCE_SWITCH),
        EffectTag(E.COUNTER_DEFENSE, sub_effects=[
            EffectTag(E.ENEMY_ENERGY_COST_UP, {"amount": 6, "filter": "attack"}),
        ]),
    ],

    # 毒液渗透 (毒/魔法/5/120): 造成魔伤，敌方每有1层中毒效果，本技能能耗-1，敌方获得1层中毒。
    "毒液渗透": [
        EffectTag(E.ENERGY_COST_DYNAMIC, {"per": "enemy_poison", "reduce": 1}),
        EffectTag(E.DAMAGE),
        EffectTag(E.POISON, {"stacks": 1}),
    ],

    # 感染病 (毒/魔法/4/85): 造成魔伤，若击败敌方则将中毒转化为印记。
    "感染病": [
        EffectTag(E.DAMAGE),
        EffectTag(E.CONVERT_POISON_TO_MARK, {"on": "kill"}),
    ],

    # 阻断 (普通/魔法/2/70): 造成魔伤，应对状态：额外打断被应对技能。
    "阻断": [
        EffectTag(E.DAMAGE),
        EffectTag(E.COUNTER_STATUS, sub_effects=[
            EffectTag(E.INTERRUPT),
        ]),
    ],

    # 崩拳 (武/物理/2/60): 造成物伤，应对状态：自己获得物攻+100%。
    "崩拳": [
        EffectTag(E.DAMAGE),
        EffectTag(E.COUNTER_STATUS, sub_effects=[
            EffectTag(E.SELF_BUFF, {"atk": 1.0}),
        ]),
    ],

    # 毒囊 (毒/物理/2/20): 造成物伤，敌方获得2层中毒，应对状态：改为获得6层。
    "毒囊": [
        EffectTag(E.DAMAGE),
        EffectTag(E.POISON, {"stacks": 2}),
        EffectTag(E.COUNTER_STATUS, sub_effects=[
            EffectTag(E.COUNTER_OVERRIDE, {"replace": "poison", "from": 2, "to": 6}),
        ]),
    ],

    # 防御 (普通/状态/1/0): 减伤70%，应对攻击。
    "防御": [
        EffectTag(E.DAMAGE_REDUCTION, {"pct": 0.7}),
        EffectTag(E.COUNTER_ATTACK),
    ],

    # 甩水 (水/魔法/0/30): 造成魔伤，自己回复1能量。
    "甩水": [
        EffectTag(E.DAMAGE),
        EffectTag(E.HEAL_ENERGY, {"amount": 1}),
    ],

    # 天洪 (水/魔法/7/140): 造成魔伤，应对状态：本技能能耗永久-6。
    "天洪": [
        EffectTag(E.DAMAGE),
        EffectTag(E.COUNTER_STATUS, sub_effects=[
            EffectTag(E.PERMANENT_MOD, {"target": "cost", "delta": -6}),
        ]),
    ],

    # 以毒攻毒 (毒/状态/1/0): 敌方每有1层中毒，自己获得魔攻+30%。
    "以毒攻毒": [
        EffectTag(E.CONDITIONAL_BUFF, {
            "condition": "per_enemy_poison",
            "buff": {"spatk": 0.3},
        }),
    ],

    # ──────────── B队 (翼王队) 技能 ────────────

    # 风墙 (翼/状态/2/0): 减伤50%，迅捷，应对攻击。
    "风墙": [
        EffectTag(E.DAMAGE_REDUCTION, {"pct": 0.5}),
        EffectTag(E.AGILITY),
        EffectTag(E.COUNTER_ATTACK),
    ],

    # 啮合传递 (机械/状态/1/0): 自己获得速度+80，
    #   本技能位于1号位或3号位时额外获得物攻+100%，传动1。
    "啮合传递": [
        EffectTag(E.SELF_BUFF, {"speed": 0.8}),
        EffectTag(E.POSITION_BUFF, {
            "positions": [0, 2],
            "buff": {"atk": 1.0},
        }),
        EffectTag(E.DRIVE, {"value": 1}),
    ],

    # 双星 (幻/物理/3/100): 造成物伤。
    "双星": [
        EffectTag(E.DAMAGE),
    ],

    # 偷袭 (普通/物理/3/85): 造成物伤，应对状态：威力变为3倍。
    "偷袭": [
        EffectTag(E.DAMAGE),
        EffectTag(E.COUNTER_STATUS, sub_effects=[
            EffectTag(E.POWER_DYNAMIC, {"condition": "counter", "multiplier": 3.0}),
        ]),
    ],

    # 力量增效 (普通/状态/1/0): 自己获得物攻+100%。
    "力量增效": [
        EffectTag(E.SELF_BUFF, {"atk": 1.0}),
    ],

    # 水刃 (水/物理/4/115): 造成物伤，应对状态：本技能能耗永久-4。
    "水刃": [
        EffectTag(E.DAMAGE),
        EffectTag(E.COUNTER_STATUS, sub_effects=[
            EffectTag(E.PERMANENT_MOD, {"target": "cost", "delta": -4}),
        ]),
    ],

    # 斩断 (武/物理/2/70): 造成物伤，应对状态：额外打断被应对技能。
    "斩断": [
        EffectTag(E.DAMAGE),
        EffectTag(E.COUNTER_STATUS, sub_effects=[
            EffectTag(E.INTERRUPT),
        ]),
    ],

    # 听桥 (武/状态/4/0): 减伤60%，应对攻击：对敌方造成伤害，威力与被应对技能相等。
    "听桥": [
        EffectTag(E.DAMAGE_REDUCTION, {"pct": 0.6}),
        EffectTag(E.COUNTER_ATTACK, sub_effects=[
            EffectTag(E.MIRROR_DAMAGE, {"source": "countered_skill"}),
        ]),
    ],

    # 火焰护盾 (火/状态/2/0): 减伤70%，应对攻击：敌方获得4层灼烧。
    "火焰护盾": [
        EffectTag(E.DAMAGE_REDUCTION, {"pct": 0.7}),
        EffectTag(E.COUNTER_ATTACK, sub_effects=[
            EffectTag(E.BURN, {"stacks": 4}),
        ]),
    ],

    # 引燃 (火/状态/2/0): 敌方获得10层灼烧效果。
    "引燃": [
        EffectTag(E.BURN, {"stacks": 10}),
    ],

    # 倾泻 (普通/魔法/3/60): 造成魔伤，若未被防御或应对则驱散双方所有印记。
    "倾泻": [
        EffectTag(E.DAMAGE),
        EffectTag(E.DISPEL_MARKS, {"condition": "not_blocked"}),
    ],

    # 抽枝 (草/物理/4/85): 造成物伤，应对状态：自己回复50%生命和5能量。
    "抽枝": [
        EffectTag(E.DAMAGE),
        EffectTag(E.COUNTER_STATUS, sub_effects=[
            EffectTag(E.HEAL_HP, {"pct": 0.5}),
            EffectTag(E.HEAL_ENERGY, {"amount": 5}),
        ]),
    ],

    # 水环 (水/状态/2/0): 减伤70%，应对攻击：自己获得全技能能耗-2。
    "水环": [
        EffectTag(E.DAMAGE_REDUCTION, {"pct": 0.7}),
        EffectTag(E.COUNTER_ATTACK, sub_effects=[
            EffectTag(E.PASSIVE_ENERGY_REDUCE, {"reduce": 2, "range": "all"}),
        ]),
    ],

    # 疾风连袭 (翼/状态/0/0): 释放自己释放过的迅捷技能，
    #   其能耗之和的二分之一加至本技能能耗，每次使用后能耗+1。
    "疾风连袭": [
        EffectTag(E.REPLAY_AGILITY),
        EffectTag(E.AGILITY_COST_SHARE, {"divisor": 2}),
        EffectTag(E.ENERGY_COST_ACCUMULATE, {"delta": 1}),
    ],

    # 扇风 (翼/物理/3/70): 造成物伤，若先于敌方攻击，本次技能威力+50%。
    "扇风": [
        EffectTag(E.POWER_DYNAMIC, {"condition": "first_strike", "bonus_pct": 0.5}),
        EffectTag(E.DAMAGE),
    ],

    # 能量刃 (普通/物理/3/70): 造成物伤，每应对成功1次本技能威力永久+90。
    "能量刃": [
        EffectTag(E.DAMAGE),
        EffectTag(E.PERMANENT_MOD, {
            "target": "power", "delta": 90,
            "trigger": "per_counter",
        }),
    ],

    # 轴承支撑 (机械/状态/3/0): 主动：本技能；被动：额外-1能耗，被动两侧技能能耗-1，传动。
    "轴承支撑": [
        EffectTag(E.PASSIVE_ENERGY_REDUCE, {"reduce": 1, "range": "self"}),
        EffectTag(E.PASSIVE_ENERGY_REDUCE, {"reduce": 1, "range": "adjacent"}),
        EffectTag(E.DRIVE, {"value": 1}),
    ],

    # 齿轮扭矩 (机械/物理/3/60): 造成物伤，每变化1次位置本技能威力永久+20。
    "齿轮扭矩": [
        EffectTag(E.DAMAGE),
        EffectTag(E.PERMANENT_MOD, {
            "target": "power", "delta": 20,
            "trigger": "per_position_change",
        }),
    ],

    # 地刺 (地/物理/3/95): 造成物伤，应对状态：额外打断被应对技能。
    "地刺": [
        EffectTag(E.DAMAGE),
        EffectTag(E.COUNTER_STATUS, sub_effects=[
            EffectTag(E.INTERRUPT),
        ]),
    ],

    # 吓退 (普通/状态/2/0): 减伤70%，应对攻击：敌方脱离。
    "吓退": [
        EffectTag(E.DAMAGE_REDUCTION, {"pct": 0.7}),
        EffectTag(E.COUNTER_ATTACK, sub_effects=[
            EffectTag(E.FORCE_ENEMY_SWITCH),
        ]),
    ],
}


# ============================================================
#  特性效果配置: Dict[特性名, List[AbilityEffect]]
# ============================================================
ABILITY_EFFECTS = {

    # ── A队特性 ──

    # 千棘盔 — 溶解扩散: 每携带1个毒系技能进入战斗，水系技能使敌方获得1层中毒。
    "溶解扩散": [
        AbilityEffect(
            timing=Timing.ON_BATTLE_START,
            effects=[],  # 计算毒系技能数量, 存入 ability_state
            filter={"compute": "count_poison_skills"},
        ),
        AbilityEffect(
            timing=Timing.ON_USE_SKILL,
            effects=[
                EffectTag(E.POISON, {"stacks_per_poison_skill": True}),
            ],
            filter={"element": "水"},
        ),
    ],

    # 影狸 — 下黑手: 敌方精灵离场后，更换入场的精灵获得5层中毒。
    "下黑手": [
        AbilityEffect(
            timing=Timing.ON_ENEMY_SWITCH,
            effects=[
                EffectTag(E.POISON, {"stacks": 5, "target": "enemy_new"}),
            ],
        ),
    ],

    # 裘卡 — 蚀刻: 回合结束时，敌方每2层中毒转化为1层中毒印记。
    "蚀刻": [
        AbilityEffect(
            timing=Timing.ON_TURN_END,
            effects=[
                EffectTag(E.CONVERT_POISON_TO_MARK, {
                    "ratio": 2,  # 每2层中毒→1层印记
                }),
            ],
        ),
    ],

    # 琉璃水母 — 扩散侵蚀: 使用水系技能后，敌方获得中毒，获得层数等于中毒印记层数的2倍。
    "扩散侵蚀": [
        AbilityEffect(
            timing=Timing.ON_USE_SKILL,
            effects=[
                EffectTag(E.POISON, {"stacks_per_mark": 2}),
                # stacks = enemy_poison_mark_stacks * 2
            ],
            filter={"element": "水"},
        ),
    ],

    # 迷迷箱怪 — 虚假宝箱: 自己力竭时，敌方获得攻防+20%。
    "虚假宝箱": [
        AbilityEffect(
            timing=Timing.ON_FAINT,
            effects=[
                EffectTag(E.ENEMY_DEBUFF, {
                    "atk": -0.2, "def": -0.2,
                    "invert": True,  # 给敌方加正向buff而非debuff
                }),
            ],
        ),
    ],

    # 海豹船长 — 身经百练: 己方精灵每应对1次，自己入场时水系和武系技能威力+20%。
    "身经百练": [
        AbilityEffect(
            timing=Timing.ON_ALLY_COUNTER,
            effects=[],  # 计数器+1, 实际效果在入场时应用
            filter={"action": "increment_counter"},
        ),
        AbilityEffect(
            timing=Timing.ON_ENTER,
            effects=[
                EffectTag(E.PERMANENT_MOD, {
                    "target": "power_pct",
                    "per_counter": 0.2,  # 每次应对+20%威力
                    "skill_filter": {"element": ["水", "武"]},
                }),
            ],
        ),
    ],

    # ── B队特性 ──

    # 燃薪虫 — 煤渣草: 在场时，所有灼烧的衰减变为增长。
    "煤渣草": [
        AbilityEffect(
            timing=Timing.PASSIVE,
            effects=[],
            filter={"modify": "burn_no_decay"},
            # 特殊处理: turn_end_effects 中灼烧不衰减反而增长
        ),
    ],

    # 圣羽翼王 — 飓风: 对本精灵的技能，若其他翼系精灵携带相同技能，则获得迅捷。
    #   被敌方精灵击败时，自己额外损失1点魔力。
    "飓风": [
        AbilityEffect(
            timing=Timing.ON_BATTLE_START,
            effects=[],
            filter={"compute": "shared_wing_skills"},
            # 计算哪些技能与其他翼系精灵共享, 给这些技能加迅捷
        ),
        AbilityEffect(
            timing=Timing.ON_BE_KILLED,
            effects=[
                EffectTag(E.ENEMY_LOSE_ENERGY, {"amount": 1, "target": "self_mp"}),
                # 特殊: 扣除己方MP而非能量
            ],
        ),
    ],

    # 翠顶夫人 — 洁癖: 离场后，自己的增益和减益会被更换入场的精灵继承。
    "洁癖": [
        AbilityEffect(
            timing=Timing.ON_LEAVE,
            effects=[],
            filter={"action": "transfer_mods"},
            # 特殊处理: on_switch_out 时不清除 mods, 而是传递给下一只
        ),
    ],

    # 秩序鱿墨 — 绝对秩序: 受到非敌方系别的技能攻击时伤害-50%。
    "绝对秩序": [
        AbilityEffect(
            timing=Timing.ON_TAKE_HIT,
            effects=[
                EffectTag(E.DAMAGE_REDUCTION, {"pct": 0.5}),
            ],
            filter={"condition": "skill_element_not_enemy_type"},
            # 当攻击技能属性 ≠ 敌方精灵属性时, 减伤50%
        ),
    ],

    # 声波缇塔 — 向心力: 1号位和2号位技能获得传动1和威力+30。
    "向心力": [
        AbilityEffect(
            timing=Timing.PASSIVE,
            effects=[
                EffectTag(E.DRIVE, {"value": 1}),
                EffectTag(E.PERMANENT_MOD, {"target": "power", "delta": 30}),
            ],
            filter={"positions": [0, 1]},
            # 仅1号位和2号位技能
        ),
    ],
}
