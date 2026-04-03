"""
效果执行引擎 — 根据 EffectTag 列表驱动战斗效果

核心类 EffectExecutor 提供:
  - execute_skill()          执行技能的全部效果
  - execute_counter()        执行应对效果
  - execute_ability()        在指定时机触发特性
  - execute_agility_entry()  入场时执行迅捷技能

所有子系统(印记/传动/打断/永久修改/条件触发)都在本文件实现。
"""

import random
from typing import List, Optional, Dict, Tuple, TYPE_CHECKING

from src.effect_models import E, EffectTag, Timing, AbilityEffect

if TYPE_CHECKING:
    from src.models import Pokemon, Skill, BattleState, SkillCategory


# ============================================================
#  辅助函数
# ============================================================

def _get_ability_name(pokemon: "Pokemon") -> str:
    """从 '特性名:描述' 格式中提取特性名"""
    if ":" in pokemon.ability:
        return pokemon.ability.split(":")[0]
    if "：" in pokemon.ability:
        return pokemon.ability.split("：")[0]
    return pokemon.ability


def _find_skill_index(pokemon: "Pokemon", skill: "Skill") -> int:
    """找到技能在精灵技能列表中的索引"""
    for i, s in enumerate(pokemon.skills):
        if s.name == skill.name:
            return i
    return -1


# ============================================================
#  效果执行引擎
# ============================================================

class EffectExecutor:
    """
    无状态的效果执行器。所有方法均为 @staticmethod，
    通过传入 BattleState + 双方精灵来执行效果。
    """

    # ────────────────────────────────────────
    #  主入口: 执行技能
    # ────────────────────────────────────────

    @staticmethod
    def execute_skill(
        state: "BattleState",
        user: "Pokemon",
        target: "Pokemon",
        skill: "Skill",
        effects: List[EffectTag],
        is_first: bool = False,
        enemy_skill: Optional["Skill"] = None,
        team: str = "a",
    ) -> Dict:
        """
        执行技能的全部效果 (非应对部分)。

        Args:
            state:       当前战斗状态
            user:        使用者
            target:      目标 (对手)
            skill:       使用的技能
            effects:     技能的 EffectTag 列表
            is_first:    是否先于敌方行动
            enemy_skill: 对方本回合使用的技能 (用于应对判定)
            team:        使用者所属队伍 "a"/"b"

        Returns:
            result dict: {"damage": int, "interrupted": bool, "countered": bool,
                          "force_switch": bool, "counter_effects": [...]}
        """
        result = {
            "damage": 0,
            "interrupted": False,
            "countered": False,
            "force_switch": False,
            "force_enemy_switch": False,
            "counter_effects": [],
        }

        # 动态威力修正 (在伤害计算前)
        power_mult = 1.0
        dynamic_power_bonus = 0

        for tag in effects:
            # 跳过应对容器, 这些在 execute_counter 中处理
            if tag.type in (E.COUNTER_ATTACK, E.COUNTER_STATUS, E.COUNTER_DEFENSE):
                result["counter_effects"].append(tag)
                continue

            EffectExecutor._execute_one(
                tag, state, user, target, skill, result,
                is_first=is_first, team=team,
            )

        return result

    # ────────────────────────────────────────
    #  应对效果执行
    # ────────────────────────────────────────

    @staticmethod
    def execute_counter(
        state: "BattleState",
        user: "Pokemon",
        target: "Pokemon",
        skill: "Skill",
        counter_tag: EffectTag,
        enemy_skill: "Skill",
        damage: int,
        team: str = "a",
    ) -> Dict:
        """
        执行应对效果。

        Args:
            user:        技能使用者 (拥有应对效果的一方)
            target:      对手
            skill:       使用者的技能
            counter_tag: 应对容器 EffectTag
            enemy_skill: 对方的技能
            damage:      对方技能造成的原始伤害

        Returns:
            {"final_damage": int, "interrupted": bool, "force_switch": bool, ...}
        """
        from src.models import SkillCategory

        result = {
            "final_damage": damage,
            "interrupted": False,
            "force_switch": False,
            "force_enemy_switch": False,
        }

        # 检查应对类型是否匹配
        matched = False
        if counter_tag.type == E.COUNTER_ATTACK:
            matched = enemy_skill.category in (SkillCategory.PHYSICAL, SkillCategory.MAGICAL)
        elif counter_tag.type == E.COUNTER_STATUS:
            matched = enemy_skill.category == SkillCategory.STATUS
        elif counter_tag.type == E.COUNTER_DEFENSE:
            matched = enemy_skill.category == SkillCategory.DEFENSE

        if not matched:
            return result

        # 应对成功: 更新计数
        if not hasattr(state, "counter_count_a"):
            state.counter_count_a = 0
            state.counter_count_b = 0
        if team == "a":
            state.counter_count_a += 1
        else:
            state.counter_count_b += 1

        # 执行子效果
        for sub in counter_tag.sub_effects:
            if sub.type == E.INTERRUPT:
                result["interrupted"] = True

            elif sub.type == E.FORCE_SWITCH:
                result["force_switch"] = True

            elif sub.type == E.FORCE_ENEMY_SWITCH:
                result["force_enemy_switch"] = True

            elif sub.type == E.SELF_BUFF:
                _apply_buff(user, sub.params)

            elif sub.type == E.ENEMY_DEBUFF:
                _apply_debuff(target, sub.params)

            elif sub.type == E.POISON:
                target.poison_stacks += sub.params.get("stacks", 1)

            elif sub.type == E.BURN:
                target.burn_stacks += sub.params.get("stacks", 1)

            elif sub.type == E.HEAL_HP:
                pct = sub.params.get("pct", 0)
                heal = int(user.hp * pct)
                user.current_hp = min(user.hp, user.current_hp + heal)

            elif sub.type == E.HEAL_ENERGY:
                user.gain_energy(sub.params.get("amount", 1))

            elif sub.type == E.PERMANENT_MOD:
                _apply_permanent_mod(user, skill, sub.params)

            elif sub.type == E.POWER_DYNAMIC:
                # 应对时威力倍率 (偷袭3倍)
                if sub.params.get("condition") == "counter":
                    mult = sub.params.get("multiplier", 1.0)
                    # 重算伤害
                    from src.battle import DamageCalculator
                    new_power = int(skill.power * mult)
                    result["final_damage"] = DamageCalculator.calculate(
                        user, target, skill, power_override=new_power
                    )

            elif sub.type == E.MIRROR_DAMAGE:
                # 反弹伤害: 用被应对技能的威力反击
                from src.battle import DamageCalculator
                mirror_power = enemy_skill.power
                if mirror_power > 0:
                    mirror_dmg = DamageCalculator.calculate(user, target, skill,
                                                           power_override=mirror_power)
                    target.current_hp -= mirror_dmg

            elif sub.type == E.COUNTER_OVERRIDE:
                # 应对时替换效果 (毒囊: 中毒2→6)
                replace_type = sub.params.get("replace", "")
                from_val = sub.params.get("from", 0)
                to_val = sub.params.get("to", 0)
                if replace_type == "poison":
                    # 先撤回之前给的, 再给新的
                    target.poison_stacks -= from_val
                    target.poison_stacks += to_val

            elif sub.type == E.ENEMY_ENERGY_COST_UP:
                # 敌方攻击技能能耗+N
                amount = sub.params.get("amount", 0)
                filt = sub.params.get("filter", "all")
                from src.models import SkillCategory as SC
                for s in target.skills:
                    if filt == "attack" and s.category in (SC.PHYSICAL, SC.MAGICAL):
                        s.energy_cost += amount
                    elif filt == "all":
                        s.energy_cost += amount

            elif sub.type == E.PASSIVE_ENERGY_REDUCE:
                # 全技能能耗-N (水环)
                reduce = sub.params.get("reduce", 0)
                rng = sub.params.get("range", "all")
                if rng == "all":
                    for s in user.skills:
                        s.energy_cost = max(0, s.energy_cost - reduce)

        return result

    # ────────────────────────────────────────
    #  特性触发
    # ────────────────────────────────────────

    @staticmethod
    def execute_ability(
        state: "BattleState",
        pokemon: "Pokemon",
        enemy: "Pokemon",
        timing: Timing,
        ability_effects: List[AbilityEffect],
        team: str = "a",
        context: Optional[Dict] = None,
    ) -> Dict:
        """
        在指定时机触发特性效果。

        Args:
            pokemon:          特性拥有者
            enemy:            对手
            timing:           当前时机
            ability_effects:  特性的 AbilityEffect 列表
            context:          额外上下文 {"skill": ..., "damage": ..., ...}

        Returns:
            result dict
        """
        result = {"triggered": False, "damage_reduction": 0}
        context = context or {}

        for ae in ability_effects:
            if ae.timing != timing:
                continue

            # 过滤条件检查
            if not EffectExecutor._check_ability_filter(ae, pokemon, enemy, state, team, context):
                continue

            result["triggered"] = True

            # 特殊处理的特性
            special = ae.filter.get("compute") or ae.filter.get("action") or ae.filter.get("modify")
            if special:
                EffectExecutor._handle_special_ability(
                    special, ae, pokemon, enemy, state, team, context
                )
                continue

            # 执行通用效果
            for tag in ae.effects:
                EffectExecutor._execute_ability_tag(
                    tag, pokemon, enemy, state, team, context
                )

                # 收集减伤信息
                if tag.type == E.DAMAGE_REDUCTION:
                    result["damage_reduction"] = tag.params.get("pct", 0)

        return result

    # ────────────────────────────────────────
    #  迅捷入场
    # ────────────────────────────────────────

    @staticmethod
    def execute_agility_entry(
        state: "BattleState",
        pokemon: "Pokemon",
        enemy: "Pokemon",
        team: str = "a",
    ) -> None:
        """入场时执行带迅捷标记的技能"""
        for i, skill in enumerate(pokemon.skills):
            if not hasattr(skill, "effects") or not skill.effects:
                # 旧技能走旧逻辑
                if skill.agility and pokemon.energy >= skill.energy_cost:
                    _execute_agility_old(pokemon, enemy, skill)
                continue

            has_agility = any(e.type == E.AGILITY for e in skill.effects)
            if has_agility and pokemon.energy >= skill.energy_cost:
                pokemon.energy -= skill.energy_cost
                EffectExecutor.execute_skill(
                    state, pokemon, enemy, skill, skill.effects,
                    is_first=True, team=team,
                )
                break  # 只触发第一个迅捷技能

    # ────────────────────────────────────────
    #  传动系统
    # ────────────────────────────────────────

    @staticmethod
    def execute_drive(
        state: "BattleState",
        user: "Pokemon",
        target: "Pokemon",
        skill: "Skill",
        drive_value: int,
        team: str = "a",
    ) -> None:
        """
        执行传动: 使用技能后, 按传动值触发后方N位技能的被动效果。
        传动循环: 位置 = (当前位置 + drive_value) % 4
        """
        skill_idx = _find_skill_index(user, skill)
        if skill_idx < 0:
            return

        n_skills = len(user.skills)
        if n_skills == 0:
            return

        target_idx = (skill_idx + drive_value) % n_skills
        target_skill = user.skills[target_idx]

        if not hasattr(target_skill, "effects") or not target_skill.effects:
            return

        # 触发目标技能的被动效果
        for tag in target_skill.effects:
            if tag.type == E.PASSIVE_ENERGY_REDUCE:
                reduce = tag.params.get("reduce", 0)
                rng = tag.params.get("range", "self")
                if rng == "self":
                    target_skill.energy_cost = max(0, target_skill.energy_cost - reduce)
                elif rng == "adjacent":
                    # 两侧技能能耗-N
                    for offset in [-1, 1]:
                        adj_idx = (target_idx + offset) % n_skills
                        user.skills[adj_idx].energy_cost = max(
                            0, user.skills[adj_idx].energy_cost - reduce
                        )

        # 传动也触发齿轮扭矩的位置变化计数
        for tag in target_skill.effects:
            if tag.type == E.PERMANENT_MOD:
                if tag.params.get("trigger") == "per_position_change":
                    target_skill.power += tag.params.get("delta", 0)

    # ────────────────────────────────────────
    #  内部: 执行单个效果
    # ────────────────────────────────────────

    @staticmethod
    def _execute_one(
        tag: EffectTag,
        state: "BattleState",
        user: "Pokemon",
        target: "Pokemon",
        skill: "Skill",
        result: Dict,
        is_first: bool = False,
        team: str = "a",
    ) -> None:
        """执行一个非应对类 EffectTag"""

        if tag.type == E.DAMAGE:
            from src.battle import DamageCalculator
            power = skill.power + result.get("_power_bonus", 0)
            power_mult = result.get("_power_mult", 1.0)
            if power_mult != 1.0:
                power = int(power * power_mult)
            if power > 0 and not target.is_fainted:
                dmg = DamageCalculator.calculate(user, target, skill, power_override=power)
                result["damage"] += dmg

        elif tag.type == E.SELF_BUFF:
            _apply_buff(user, tag.params)

        elif tag.type == E.ENEMY_DEBUFF:
            if tag.params.get("invert"):
                _apply_buff(target, tag.params)
            else:
                _apply_debuff(target, tag.params)

        elif tag.type == E.HEAL_HP:
            pct = tag.params.get("pct", 0)
            heal = int(user.hp * pct)
            user.current_hp = min(user.hp, user.current_hp + heal)

        elif tag.type == E.HEAL_ENERGY:
            user.gain_energy(tag.params.get("amount", 1))

        elif tag.type == E.STEAL_ENERGY:
            amt = tag.params.get("amount", 1)
            user.gain_energy(amt)
            target.energy = max(0, target.energy - amt)

        elif tag.type == E.ENEMY_LOSE_ENERGY:
            target.energy = max(0, target.energy - tag.params.get("amount", 1))

        elif tag.type == E.LIFE_DRAIN:
            # 吸血在伤害计算后执行
            pct = tag.params.get("pct", 0)
            heal = int(result["damage"] * pct)
            user.current_hp = min(user.hp, user.current_hp + heal)

        elif tag.type == E.POISON:
            stacks = tag.params.get("stacks", 1)
            target.poison_stacks += stacks

        elif tag.type == E.BURN:
            target.burn_stacks += tag.params.get("stacks", 1)

        elif tag.type == E.FREEZE:
            target.freeze_stacks += tag.params.get("stacks", 1)

        elif tag.type == E.LEECH:
            target.leech_stacks += tag.params.get("stacks", 1)

        elif tag.type == E.METEOR:
            target.meteor_stacks += tag.params.get("stacks", 1)
            if target.meteor_countdown <= 0:
                target.meteor_countdown = 3

        elif tag.type == E.POISON_MARK:
            marks = state.marks_b if team == "a" else state.marks_a
            marks["poison_mark"] = marks.get("poison_mark", 0) + tag.params.get("stacks", 1)

        elif tag.type == E.MOISTURE_MARK:
            tgt = tag.params.get("target", "enemy")
            if tgt == "self":
                marks = state.marks_a if team == "a" else state.marks_b
            else:
                marks = state.marks_b if team == "a" else state.marks_a
            marks["moisture_mark"] = marks.get("moisture_mark", 0) + tag.params.get("stacks", 1)

        elif tag.type == E.DAMAGE_REDUCTION:
            result["_damage_reduction"] = tag.params.get("pct", 0)

        elif tag.type == E.FORCE_SWITCH:
            result["force_switch"] = True

        elif tag.type == E.FORCE_ENEMY_SWITCH:
            result["force_enemy_switch"] = True

        elif tag.type == E.AGILITY:
            # 标记, 实际效果在入场时由 execute_agility_entry 处理
            pass

        elif tag.type == E.CONVERT_BUFF_TO_POISON:
            # 将敌方所有正向修正转化为中毒层数
            total_buff = 0
            for attr in ["atk_mod", "def_mod", "spatk_mod", "spdef_mod", "speed_mod"]:
                v = getattr(target, attr, 0)
                if v > 0:
                    # 每10%=1层
                    total_buff += int(v * 10)
                    setattr(target, attr, 0)
            if total_buff > 0:
                target.poison_stacks += total_buff

        elif tag.type == E.CONVERT_POISON_TO_MARK:
            on = tag.params.get("on", "")
            ratio = tag.params.get("ratio", 0)
            if on == "kill" and target.is_fainted:
                # 击败时: 敌方所有中毒层数→中毒印记
                stacks = target.poison_stacks
                marks = state.marks_b if team == "a" else state.marks_a
                marks["poison_mark"] = marks.get("poison_mark", 0) + stacks
                target.poison_stacks = 0
            elif ratio > 0:
                # 蚀刻: 每N层中毒→1层印记
                stacks = target.poison_stacks
                converted = stacks // ratio
                if converted > 0:
                    target.poison_stacks -= converted * ratio
                    marks = state.marks_b if team == "a" else state.marks_a
                    marks["poison_mark"] = marks.get("poison_mark", 0) + converted

        elif tag.type == E.DISPEL_MARKS:
            cond = tag.params.get("condition", "")
            if cond == "not_blocked":
                result["_dispel_if_not_blocked"] = True
            else:
                state.marks_a.clear()
                state.marks_b.clear()

        elif tag.type == E.CONDITIONAL_BUFF:
            condition = tag.params.get("condition", "")
            buff = tag.params.get("buff", {})

            if condition == "enemy_switch":
                # 这需要在回合结束时检查, 暂存到 result
                result["_conditional_enemy_switch_buff"] = buff

            elif condition == "per_enemy_poison":
                stacks = target.poison_stacks
                if stacks > 0:
                    scaled_buff = {k: v * stacks for k, v in buff.items()}
                    _apply_buff(user, scaled_buff)

        elif tag.type == E.ENERGY_COST_DYNAMIC:
            per = tag.params.get("per", "")
            reduce = tag.params.get("reduce", 0)
            if per == "enemy_poison":
                stacks = target.poison_stacks
                actual_reduce = stacks * reduce
                # 动态降低能耗 (已扣费前调用, 需要退还差额)
                result["_energy_refund"] = actual_reduce

        elif tag.type == E.POWER_DYNAMIC:
            condition = tag.params.get("condition", "")
            if condition == "first_strike" and is_first:
                bonus_pct = tag.params.get("bonus_pct", 0)
                result["_power_mult"] = result.get("_power_mult", 1.0) + bonus_pct
            elif condition == "per_poison":
                stacks = target.poison_stacks
                bonus = tag.params.get("bonus_per_stack", 0) * stacks
                result["_power_bonus"] = result.get("_power_bonus", 0) + bonus

        elif tag.type == E.PERMANENT_MOD:
            _apply_permanent_mod(user, skill, tag.params)

        elif tag.type == E.POSITION_BUFF:
            positions = tag.params.get("positions", [])
            buff = tag.params.get("buff", {})
            skill_idx = _find_skill_index(user, skill)
            if skill_idx in positions:
                _apply_buff(user, buff)

        elif tag.type == E.DRIVE:
            # 传动在主效果执行完后由 battle.py 调用 execute_drive
            result["_drive_value"] = tag.params.get("value", 1)

        elif tag.type == E.PASSIVE_ENERGY_REDUCE:
            # 被动能耗减少 (轴承支撑的被动效果, 由传动触发)
            pass  # 已在 execute_drive 中处理

        elif tag.type == E.REPLAY_AGILITY:
            # 疾风连袭: 释放之前释放过的迅捷技能
            result["_replay_agility"] = True

        elif tag.type == E.AGILITY_COST_SHARE:
            # 迅捷技能能耗之和的 1/divisor 加到本技能
            result["_agility_cost_share"] = tag.params.get("divisor", 2)

        elif tag.type == E.ENERGY_COST_ACCUMULATE:
            # 每次使用后能耗+N
            delta = tag.params.get("delta", 1)
            skill.energy_cost += delta

        elif tag.type == E.ENEMY_ENERGY_COST_UP:
            from src.models import SkillCategory as SC
            amount = tag.params.get("amount", 0)
            filt = tag.params.get("filter", "all")
            for s in target.skills:
                if filt == "attack" and s.category in (SC.PHYSICAL, SC.MAGICAL):
                    s.energy_cost += amount
                elif filt == "all":
                    s.energy_cost += amount

    # ────────────────────────────────────────
    #  内部: 特性效果标签执行
    # ────────────────────────────────────────

    @staticmethod
    def _execute_ability_tag(
        tag: EffectTag,
        pokemon: "Pokemon",
        enemy: "Pokemon",
        state: "BattleState",
        team: str,
        context: Dict,
    ) -> None:
        """执行特性中的单个 EffectTag"""

        if tag.type == E.POISON:
            stacks = tag.params.get("stacks", 0)
            # 特殊: stacks_per_poison_skill (溶解扩散)
            if tag.params.get("stacks_per_poison_skill"):
                ability_state = getattr(pokemon, "ability_state", {})
                n = ability_state.get("poison_skill_count", 0)
                stacks = n
            # 特殊: stacks_per_mark (扩散侵蚀)
            if tag.params.get("stacks_per_mark"):
                mult = tag.params["stacks_per_mark"]
                enemy_marks = state.marks_b if team == "a" else state.marks_a
                mark_stacks = enemy_marks.get("poison_mark", 0)
                stacks = mark_stacks * mult
            # 目标
            tgt = tag.params.get("target", "enemy")
            if tgt == "enemy" or tgt == "enemy_new":
                enemy.poison_stacks += stacks
            else:
                pokemon.poison_stacks += stacks

        elif tag.type == E.BURN:
            enemy.burn_stacks += tag.params.get("stacks", 1)

        elif tag.type == E.SELF_BUFF:
            _apply_buff(pokemon, tag.params)

        elif tag.type == E.ENEMY_DEBUFF:
            if tag.params.get("invert"):
                # 虚假宝箱: 给敌方正向buff
                _apply_buff(enemy, {k: abs(v) for k, v in tag.params.items() if k != "invert"})
            else:
                _apply_debuff(enemy, tag.params)

        elif tag.type == E.CONVERT_POISON_TO_MARK:
            ratio = tag.params.get("ratio", 2)
            stacks = enemy.poison_stacks
            converted = stacks // ratio
            if converted > 0:
                enemy.poison_stacks -= converted * ratio
                enemy_marks = state.marks_b if team == "a" else state.marks_a
                enemy_marks["poison_mark"] = enemy_marks.get("poison_mark", 0) + converted

        elif tag.type == E.ENEMY_LOSE_ENERGY:
            tgt = tag.params.get("target", "enemy")
            if tgt == "self_mp":
                # 飓风: 扣己方MP
                if team == "a":
                    state.mp_a -= tag.params.get("amount", 1)
                else:
                    state.mp_b -= tag.params.get("amount", 1)
            else:
                enemy.energy = max(0, enemy.energy - tag.params.get("amount", 1))

        elif tag.type == E.DAMAGE_REDUCTION:
            context["ability_damage_reduction"] = tag.params.get("pct", 0)

        elif tag.type == E.PERMANENT_MOD:
            # 身经百练: 入场时根据应对计数给水系/武系技能加威力
            per_counter = tag.params.get("per_counter", 0)
            if per_counter > 0:
                counter_count = getattr(state, "counter_count_a" if team == "a" else "counter_count_b", 0)
                bonus_pct = per_counter * counter_count
                skill_filter = tag.params.get("skill_filter", {})
                elements = skill_filter.get("element", [])
                from src.skill_db import _TYPE_MAP
                for s in pokemon.skills:
                    if elements:
                        type_matched = any(
                            _TYPE_MAP.get(el) == s.skill_type for el in elements
                        )
                        if type_matched:
                            s.power = int(s.power * (1.0 + bonus_pct))

        elif tag.type == E.DRIVE:
            # 向心力: 被动给1号位和2号位技能加传动
            # 实际生效在技能执行时
            pass

    # ────────────────────────────────────────
    #  内部: 特性过滤
    # ────────────────────────────────────────

    @staticmethod
    def _check_ability_filter(
        ae: AbilityEffect,
        pokemon: "Pokemon",
        enemy: "Pokemon",
        state: "BattleState",
        team: str,
        context: Dict,
    ) -> bool:
        """检查特性触发条件是否满足"""

        f = ae.filter
        if not f:
            return True

        # 按系别过滤 (使用技能后触发)
        if "element" in f:
            skill = context.get("skill")
            if skill:
                from src.skill_db import _TYPE_MAP
                expected_type = _TYPE_MAP.get(f["element"])
                if expected_type and skill.skill_type != expected_type:
                    return False
            else:
                return False

        # 按攻击系别过滤 (绝对秩序: 非敌方系别)
        if f.get("condition") == "skill_element_not_enemy_type":
            skill = context.get("skill")
            if skill and skill.skill_type != enemy.pokemon_type:
                return True
            return False

        # 位置过滤 (向心力: 1号位和2号位)
        if "positions" in f:
            skill = context.get("skill")
            if skill:
                idx = _find_skill_index(pokemon, skill)
                if idx not in f["positions"]:
                    return False
            else:
                return False

        return True

    # ────────────────────────────────────────
    #  内部: 特殊特性处理
    # ────────────────────────────────────────

    @staticmethod
    def _handle_special_ability(
        action: str,
        ae: AbilityEffect,
        pokemon: "Pokemon",
        enemy: "Pokemon",
        state: "BattleState",
        team: str,
        context: Dict,
    ) -> None:
        """处理需要特殊逻辑的特性"""

        if action == "count_poison_skills":
            # 千棘盔溶解扩散: 计算携带的毒系技能数量
            from src.skill_db import _TYPE_MAP
            from src.models import Type
            count = sum(1 for s in pokemon.skills if s.skill_type == Type.POISON)
            if not hasattr(pokemon, "ability_state"):
                pokemon.ability_state = {}
            pokemon.ability_state["poison_skill_count"] = count

        elif action == "shared_wing_skills":
            # 圣羽翼王飓风: 检查其他翼系精灵携带的相同技能, 给它们加迅捷
            from src.models import Type
            team_list = state.team_a if team == "a" else state.team_b
            my_skills = {s.name for s in pokemon.skills}
            shared = set()
            for p in team_list:
                if p.name == pokemon.name:
                    continue
                if p.pokemon_type == Type.FLYING:
                    for s in p.skills:
                        if s.name in my_skills:
                            shared.add(s.name)
            # 给共享技能加迅捷
            for s in pokemon.skills:
                if s.name in shared:
                    s.agility = True
                    if hasattr(s, "effects") and s.effects:
                        if not any(e.type == E.AGILITY for e in s.effects):
                            s.effects.insert(0, EffectTag(E.AGILITY))

        elif action == "increment_counter":
            # 海豹船长: 应对计数+1
            if not hasattr(state, "counter_count_a"):
                state.counter_count_a = 0
                state.counter_count_b = 0
            if team == "a":
                state.counter_count_a += 1
            else:
                state.counter_count_b += 1

        elif action == "transfer_mods":
            # 翠顶夫人洁癖: 离场时保存 mods, 传给下一只
            context["transfer_mods"] = {
                "atk_mod": pokemon.atk_mod,
                "def_mod": pokemon.def_mod,
                "spatk_mod": pokemon.spatk_mod,
                "spdef_mod": pokemon.spdef_mod,
                "speed_mod": pokemon.speed_mod,
            }
            # 注: 实际传递在 battle.py 的换人逻辑中完成

        elif action == "burn_no_decay":
            # 燃薪虫煤渣草: 标记灼烧不衰减
            context["burn_no_decay"] = True


# ============================================================
#  辅助函数
# ============================================================

def _apply_buff(pokemon: "Pokemon", params: Dict) -> None:
    """应用正向属性修改"""
    if "atk" in params:
        pokemon.atk_mod += params["atk"]
    if "def" in params:
        pokemon.def_mod += params["def"]
    if "spatk" in params:
        pokemon.spatk_mod += params["spatk"]
    if "spdef" in params:
        pokemon.spdef_mod += params["spdef"]
    if "speed" in params:
        pokemon.speed_mod += params["speed"]
    if "all_atk" in params:
        pokemon.atk_mod += params["all_atk"]
        pokemon.spatk_mod += params["all_atk"]
    if "all_def" in params:
        pokemon.def_mod += params["all_def"]
        pokemon.spdef_mod += params["all_def"]


def _apply_debuff(pokemon: "Pokemon", params: Dict) -> None:
    """应用负向属性修改 (params中的值为正, 自动取反)"""
    if "atk" in params:
        pokemon.atk_mod -= params["atk"]
    if "def" in params:
        pokemon.def_mod -= params["def"]
    if "spatk" in params:
        pokemon.spatk_mod -= params["spatk"]
    if "spdef" in params:
        pokemon.spdef_mod -= params["spdef"]
    if "speed" in params:
        pokemon.speed_mod -= params["speed"]
    if "all_atk" in params:
        pokemon.atk_mod -= params["all_atk"]
        pokemon.spatk_mod -= params["all_atk"]
    if "all_def" in params:
        pokemon.def_mod -= params["all_def"]
        pokemon.spdef_mod -= params["all_def"]


def _apply_permanent_mod(user: "Pokemon", skill: "Skill", params: Dict) -> None:
    """应用永久修改 (能耗/威力)"""
    target = params.get("target", "")
    delta = params.get("delta", 0)
    trigger = params.get("trigger", "")

    # 有 trigger 条件的在特定时机才生效
    if trigger == "per_counter":
        # 每次应对成功时才触发, 这里直接应用
        pass
    elif trigger == "per_position_change":
        # 传动时触发, 由 execute_drive 调用
        return

    if target == "cost":
        skill.energy_cost = max(0, skill.energy_cost + delta)
    elif target == "power":
        skill.power = max(0, skill.power + delta)


def _execute_agility_old(pokemon: "Pokemon", enemy: "Pokemon", skill: "Skill") -> None:
    """旧逻辑: 执行迅捷技能 (没有 effects 字段的技能)"""
    pokemon.energy -= skill.energy_cost
    pokemon.apply_self_buff(skill)
    enemy.apply_enemy_debuff(skill)
    if skill.poison_stacks > 0:
        enemy.poison_stacks += skill.poison_stacks
    if skill.burn_stacks > 0:
        enemy.burn_stacks += skill.burn_stacks
    if skill.leech_stacks > 0:
        enemy.leech_stacks += skill.leech_stacks
    if skill.power > 0 and not enemy.is_fainted:
        from src.battle import DamageCalculator
        dmg = DamageCalculator.calculate(pokemon, enemy, skill)
        enemy.current_hp -= dmg
        if enemy.current_hp <= 0:
            enemy.current_hp = 0
            from src.models import StatusType
            enemy.status = StatusType.FAINTED
