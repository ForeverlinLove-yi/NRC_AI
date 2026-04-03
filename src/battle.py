"""
洛克王国战斗模拟系统 - 战斗引擎 + 队伍构建
"""

import sys
import os
import random
from typing import Tuple, Optional, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.models import (
    Pokemon, Skill, BattleState, Type, SkillCategory,
    StatusType, StatType, get_type_effectiveness
)
from src.skill_db import get_skill, SPECIAL_TYPES
from src.effect_models import E, Timing
from src.effect_engine import EffectExecutor


# ============================================================
# 伤害计算
# ============================================================
class DamageCalculator:

    @staticmethod
    def calculate(attacker: Pokemon, defender: Pokemon, skill: Skill,
                  power_override: int = 0) -> int:
        power = power_override or skill.power
        if power <= 0:
            return 0

        if skill.skill_type in SPECIAL_TYPES:
            atk = attacker.effective_spatk()
            dfn = defender.effective_spdef()
        else:
            atk = attacker.effective_atk()
            dfn = defender.effective_def()

        if dfn < 1:
            dfn = 1

        # 基础伤害 = 攻击/防御 * 威力 * 0.9
        base = (atk / dfn) * power * 0.9

        # 属性克制
        eff = get_type_effectiveness(skill.skill_type, defender.pokemon_type)

        # 本系加成
        stab = 1.5 if skill.skill_type == attacker.pokemon_type else 1.0

        # 连击
        hits = skill.hit_count

        damage = base * eff * stab * hits
        return max(1, int(damage))


# ============================================================
# 技能执行
# ============================================================
def apply_skill(attacker: Pokemon, defender: Pokemon, skill: Skill,
                is_counter: bool = False, counter_category: SkillCategory = None) -> int:
    """执行技能，返回造成的伤害"""

    # --- 自身增益 ---
    attacker.apply_self_buff(skill)

    # --- 敌方减益 ---
    defender.apply_enemy_debuff(skill)

    # --- 回复HP ---
    if skill.self_heal_hp > 0:
        heal = int(attacker.hp * skill.self_heal_hp)
        attacker.current_hp = min(attacker.hp, attacker.current_hp + heal)

    # --- 回复/偷取能量 ---
    if skill.self_heal_energy > 0:
        attacker.gain_energy(skill.self_heal_energy)
    if skill.steal_energy > 0:
        attacker.gain_energy(skill.steal_energy)
        defender.energy = max(0, defender.energy - skill.steal_energy)
    if skill.enemy_lose_energy > 0:
        defender.energy = max(0, defender.energy - skill.enemy_lose_energy)

    # --- 状态附加 ---
    if skill.poison_stacks > 0:
        defender.poison_stacks += skill.poison_stacks
    if skill.burn_stacks > 0:
        defender.burn_stacks += skill.burn_stacks
    if skill.freeze_stacks > 0:
        defender.freeze_stacks += skill.freeze_stacks
    if skill.leech_stacks > 0:
        defender.leech_stacks += skill.leech_stacks
    if skill.meteor_stacks > 0:
        defender.meteor_stacks += skill.meteor_stacks
        if defender.meteor_countdown <= 0:
            defender.meteor_countdown = 3

    # --- 伤害计算 ---
    power = skill.power

    # 应对效果：威力倍率
    if is_counter and counter_category:
        if counter_category in (SkillCategory.PHYSICAL, SkillCategory.MAGICAL):
            # 对方用攻击，我的应对效果
            pass  # 防御技能主要减伤，攻击技能看应对状态
        if counter_category == SkillCategory.STATUS:
            if skill.counter_status_power_mult > 1:
                power = int(power * skill.counter_status_power_mult)
        if counter_category == SkillCategory.DEFENSE:
            if skill.counter_defense_power_mult > 1:
                power = int(power * skill.counter_defense_power_mult)

    if power <= 0 and skill.counter_physical_power_mult > 0:
        return 0

    damage = DamageCalculator.calculate(attacker, defender, skill, power_override=power)

    # --- 防御减伤 ---
    if skill.damage_reduction > 0:
        # 如果这是防御技能且对方在攻击，减少受到的伤害
        pass  # 减伤在execute_turn中处理

    # 吸血在 _execute_with_counter 中统一处理，此处不做

    return damage


def apply_defense_response(defender: Pokemon, attacker: Pokemon,
                           def_skill: Skill, atk_skill: Skill,
                           damage: int) -> Tuple[int, bool]:
    """处理防御技能的应对效果，返回(最终伤害, 是否完全防御)"""
    final_damage = damage

    # 减伤
    if def_skill.damage_reduction > 0:
        final_damage = int(damage * (1.0 - def_skill.damage_reduction))

    # 应对攻击的额外效果
    if def_skill.counter_physical_drain > 0:
        heal = int(final_damage * def_skill.counter_physical_drain)
        defender.current_hp = min(defender.hp, defender.current_hp + heal)
    if def_skill.counter_physical_energy_drain > 0:
        attacker.energy = max(0, attacker.energy - def_skill.counter_physical_energy_drain)
    if def_skill.counter_physical_self_atk > 0:
        defender.atk_mod += def_skill.counter_physical_self_atk
    if def_skill.counter_physical_enemy_def > 0:
        attacker.def_mod -= def_skill.counter_physical_enemy_def
    if def_skill.counter_physical_enemy_atk > 0:
        attacker.atk_mod -= def_skill.counter_physical_enemy_atk

    # 应对反伤
    if def_skill.counter_damage_reflect > 0:
        reflect = int(final_damage * def_skill.counter_damage_reflect)
        attacker.current_hp -= reflect

    return max(0, final_damage), def_skill.damage_reduction >= 1.0


def apply_counter_status(attacker: Pokemon, defender: Pokemon,
                         atk_skill: Skill, def_skill: Skill) -> int:
    """攻击技能应对状态技能的额外效果"""
    extra = 0
    if def_skill.category == SkillCategory.STATUS:
        if atk_skill.counter_status_enemy_lose_energy > 0:
            defender.energy = max(0, defender.energy - atk_skill.counter_status_enemy_lose_energy)
            extra += atk_skill.counter_status_enemy_lose_energy
        if atk_skill.counter_physical_self_atk > 0:
            attacker.atk_mod += atk_skill.counter_physical_self_atk
        if atk_skill.counter_status_poison_stacks > 0:
            defender.poison_stacks += atk_skill.counter_status_poison_stacks
    return extra


# ============================================================
# 回合执行
# ============================================================
Action = Tuple[int, ...]  # (skill_idx,) | (-1,) 汇合聚能 | (-2, switch_idx) 换人


def get_actions(state: BattleState, team: str) -> List[Action]:
    """获取合法动作"""
    actions = []
    team_list = state.team_a if team == "a" else state.team_b
    idx = state.current_a if team == "a" else state.current_b
    current = team_list[idx]

    if current.is_fainted:
        for i, p in enumerate(team_list):
            if i != idx and not p.is_fainted:
                actions.append((-2, i))
        return actions if actions else [(-1,)]

    actions.append((-1,))  # 汇合聚能

    for i, skill in enumerate(current.skills):
        cd = current.cooldowns.get(i, 0)
        if current.energy >= skill.energy_cost and cd <= 0:
            actions.append((i,))

    return actions if actions else [(-1,)]


def apply_action(state: BattleState, team: str, action: Action) -> Optional[str]:
    """执行动作，返回技能名(用于日志)"""
    team_list = state.team_a if team == "a" else state.team_b
    idx = state.current_a if team == "a" else state.current_b
    enemy_list = state.team_b if team == "a" else state.team_a
    eidx = state.current_b if team == "a" else state.current_a
    current = team_list[idx]
    defender = enemy_list[eidx]

    if action[0] == -2:
        if team == "a":
            state.current_a = action[1]
        else:
            state.current_b = action[1]
        return f"换人->{team_list[action[1]].name}"

    if action[0] == -1:
        current.gain_energy(5)
        return "汇合聚能"

    skill = current.skills[action[0]]
    current.energy -= skill.energy_cost

    if skill.force_switch:
        # 脱离
        alive = [i for i, p in enumerate(team_list) if not p.is_fainted and i != idx]
        if alive:
            current.on_switch_out()
            new_idx = random.choice(alive)
            if team == "a":
                state.current_a = new_idx
            else:
                state.current_b = new_idx

    if skill.category == SkillCategory.DEFENSE:
        # 防御技能不造成直接伤害，效果在应对时处理
        return skill.name

    if skill.power > 0 and not defender.is_fainted:
        damage = apply_skill(current, defender, skill)
        defender.current_hp -= damage
        if defender.current_hp <= 0:
            defender.current_hp = 0
            defender.status = StatusType.FAINTED

    return skill.name


def auto_switch(state: BattleState, switch_cb_a=None, switch_cb_b=None) -> None:
    """
    被动换人：精灵倒下后选择下一只上场精灵，不占用行动回合。
    
    switch_cb_a/b: 可选的回调函数 (state, team_list, alive_indices) -> int
      返回要换上的精灵索引。若为 None 则默认选第一个存活精灵。
    """
    if state.team_a[state.current_a].is_fainted:
        alive = [i for i, p in enumerate(state.team_a) if not p.is_fainted]
        if alive:
            state.team_a[state.current_a].on_switch_out()
            if switch_cb_a and len(alive) > 1:
                chosen = switch_cb_a(state, state.team_a, alive)
                state.current_a = chosen if chosen in alive else alive[0]
            else:
                state.current_a = alive[0]
    if state.team_b[state.current_b].is_fainted:
        alive = [i for i, p in enumerate(state.team_b) if not p.is_fainted]
        if alive:
            state.team_b[state.current_b].on_switch_out()
            if switch_cb_b and len(alive) > 1:
                chosen = switch_cb_b(state, state.team_b, alive)
                state.current_b = chosen if chosen in alive else alive[0]
            else:
                state.current_b = alive[0]


def turn_end_effects(state: BattleState) -> None:
    """回合结束：状态伤害结算 + 特性触发 (规则 v0.2)"""

    # 先触发回合结束特性
    pairs_ability = [
        (state.team_a, state.current_a, state.team_b, state.current_b, "a"),
        (state.team_b, state.current_b, state.team_a, state.current_a, "b"),
    ]
    burn_no_decay = set()  # 记录哪方灼烧不衰减
    for my_team, my_idx, enemy_team, enemy_idx, team_id in pairs_ability:
        p = my_team[my_idx]
        if p.is_fainted:
            continue
        if p.ability_effects:
            ctx = {}
            EffectExecutor.execute_ability(
                state, p, enemy_team[enemy_idx], Timing.ON_TURN_END,
                p.ability_effects, team_id, ctx,
            )
            if ctx.get("burn_no_decay"):
                burn_no_decay.add(team_id)

            # 燃薪虫煤渣草: PASSIVE 也检查
            EffectExecutor.execute_ability(
                state, p, enemy_team[enemy_idx], Timing.PASSIVE,
                p.ability_effects, team_id, ctx,
            )
            if ctx.get("burn_no_decay"):
                burn_no_decay.add(team_id)

    pairs = [
        (state.team_a, state.current_a, state.team_b, state.current_b, "a"),
        (state.team_b, state.current_b, state.team_a, state.current_a, "b"),
    ]
    for my_team, my_idx, enemy_team_list, enemy_idx, team_id in pairs:
        p = my_team[my_idx]
        if p.is_fainted:
            continue

        # 中毒: 3% × 层数 (不衰减)
        if p.poison_stacks > 0:
            dmg = int(p.hp * 0.03 * p.poison_stacks)
            p.current_hp -= max(1, dmg)

        # 燃烧: 4% × 层数, 然后层数减半(最少减1层)
        # 燃薪虫煤渣草: 灼烧不衰减反而增长
        if p.burn_stacks > 0:
            dmg = int(p.hp * 0.04 * p.burn_stacks)
            p.current_hp -= max(1, dmg)
            # 判断对手是否有煤渣草特性 (对手的在场精灵)
            enemy_team_id = "b" if team_id == "a" else "a"
            if enemy_team_id in burn_no_decay:
                # 灼烧增长 (增加与衰减等量)
                growth = max(1, p.burn_stacks // 2)
                p.burn_stacks += growth
            else:
                decay = max(1, p.burn_stacks // 2)
                p.burn_stacks = max(0, p.burn_stacks - decay)

        # 冻伤: 每回合累加 hp//12 不可恢复伤害
        if p.frostbite_damage > 0 or p.freeze_stacks > 0:
            frost_tick = p.hp // 12
            p.frostbite_damage += frost_tick
            if p.current_hp <= p.frostbite_damage:
                p.current_hp = 0
            else:
                effective_max = p.effective_max_hp
                if p.current_hp > effective_max:
                    p.current_hp = effective_max

        # 寄生: 每层8%最大HP, 吸取给对手
        if p.leech_stacks > 0:
            leech_dmg = int(p.hp * 0.08 * p.leech_stacks)
            p.current_hp -= max(1, leech_dmg)
            enemy = enemy_team_list[enemy_idx]
            if not enemy.is_fainted:
                enemy.current_hp = min(enemy.hp, enemy.current_hp + leech_dmg)

        # 星陨: 倒计时-1, 到0时引爆
        if p.meteor_countdown > 0:
            p.meteor_countdown -= 1
            if p.meteor_countdown <= 0 and p.meteor_stacks > 0:
                enemy = enemy_team_list[enemy_idx]
                meteor_power = 30 * p.meteor_stacks
                if not enemy.is_fainted:
                    e_spatk = enemy.effective_spatk()
                    p_spdef = max(1.0, p.effective_spdef())
                    meteor_dmg = max(1, int((e_spatk / p_spdef) * meteor_power * 0.9))
                else:
                    meteor_dmg = max(1, meteor_power)
                p.current_hp -= meteor_dmg
                p.meteor_stacks = 0

        # 判定倒下
        if p.current_hp <= 0:
            p.current_hp = 0
            p.status = StatusType.FAINTED

    # 减少冷却
    for p in state.team_a + state.team_b:
        for k in list(p.cooldowns.keys()):
            if p.cooldowns[k] > 0:
                p.cooldowns[k] -= 1


def resolve_counter(attacker: Pokemon, defender: Pokemon,
                    atk_skill: Skill, def_skill: Skill, damage: int) -> int:
    """解析应对交互，返回最终伤害"""
    if def_skill.category == SkillCategory.DEFENSE:
        if atk_skill.category in (SkillCategory.PHYSICAL, SkillCategory.MAGICAL):
            # 攻击 vs 防御 → 防御减伤+应对效果
            final_dmg, _ = apply_defense_response(defender, attacker, def_skill, atk_skill, damage)
            return final_dmg
        # 防御 vs 状态 → 状态的应对防御效果
        if def_skill.counter_defense_self_atk > 0:
            defender.atk_mod += def_skill.counter_defense_self_atk
        if def_skill.counter_defense_enemy_def > 0:
            attacker.def_mod -= def_skill.counter_defense_enemy_def

    elif def_skill.category == SkillCategory.STATUS:
        if atk_skill.category in (SkillCategory.PHYSICAL, SkillCategory.MAGICAL):
            # 攻击 vs 状态 → 攻击的应对状态效果
            apply_counter_status(attacker, defender, atk_skill, def_skill)
        elif atk_skill.category == SkillCategory.DEFENSE:
            # 防御 vs 状态 → 状态的应对防御效果
            if def_skill.counter_defense_enemy_def > 0:
                attacker.def_mod -= def_skill.counter_defense_enemy_def

    elif def_skill.category in (SkillCategory.PHYSICAL, SkillCategory.MAGICAL):
        if atk_skill.category == SkillCategory.STATUS:
            # 状态 vs 攻击 → 状态无特殊效果
            pass

    return damage


def _check_fainted_and_deduct_mp(state: BattleState) -> None:
    """检查倒地精灵，扣除MP"""
    pa = state.team_a[state.current_a]
    pb = state.team_b[state.current_b]
    if pa.is_fainted:
        state.mp_a -= 1
    if pb.is_fainted:
        state.mp_b -= 1


def execute_full_turn(state: BattleState, action_a: Action, action_b: Action,
                      switch_cb_a=None, switch_cb_b=None) -> None:
    """
    执行完整回合。
    
    switch_cb_a/b: 被动换人回调 (state, team_list, alive_indices) -> int
      精灵倒下后让玩家/AI选择下一只上场精灵。
    """
    p_a = state.team_a[state.current_a]
    p_b = state.team_b[state.current_b]

    # 重置本回合换人标记
    state.switch_this_turn_a = False
    state.switch_this_turn_b = False

    # 速度判定
    spd_a = p_a.effective_speed() * (1.0 + get_priority(state, "a", action_a))
    spd_b = p_b.effective_speed() * (1.0 + get_priority(state, "b", action_b))

    if spd_a >= spd_b:
        first_team, second_team = "a", "b"
        first_act, second_act = action_a, action_b
    else:
        first_team, second_team = "b", "a"
        first_act, second_act = action_b, action_a

    # 先手行动
    _execute_with_counter(state, first_team, first_act, second_team, second_act)
    _check_fainted_and_deduct_mp(state)
    auto_switch(state, switch_cb_a, switch_cb_b)

    if check_winner(state):
        return

    # 后手行动
    _execute_with_counter(state, second_team, second_act, first_team, first_act)
    _check_fainted_and_deduct_mp(state)
    auto_switch(state, switch_cb_a, switch_cb_b)

    if check_winner(state):
        return

    turn_end_effects(state)
    _check_fainted_and_deduct_mp(state)
    auto_switch(state, switch_cb_a, switch_cb_b)
    state.turn += 1


def _execute_with_counter(state: BattleState, team: str, action: Action,
                          enemy_team: str, enemy_action: Action) -> None:
    """执行行动+应对解析 (兼容新旧引擎)"""
    team_list = state.team_a if team == "a" else state.team_b
    idx = state.current_a if team == "a" else state.current_b
    enemy_list = state.team_b if team == "a" else state.team_a
    eidx = state.current_b if team == "a" else state.current_a
    current = team_list[idx]
    enemy = enemy_list[eidx]

    # 换人
    if action[0] == -2:
        old_pokemon = current
        current.on_switch_out()

        # 特性: 离场触发 (翠顶夫人洁癖)
        transfer_ctx = {}
        if old_pokemon.ability_effects:
            EffectExecutor.execute_ability(
                state, old_pokemon, enemy, Timing.ON_LEAVE,
                old_pokemon.ability_effects, team, transfer_ctx,
            )

        if team == "a":
            state.current_a = action[1]
            state.switch_this_turn_a = True
        else:
            state.current_b = action[1]
            state.switch_this_turn_b = True

        new_pokemon = team_list[action[1]]

        # 洁癖: 传递属性修正
        if "transfer_mods" in transfer_ctx:
            mods = transfer_ctx["transfer_mods"]
            new_pokemon.atk_mod += mods.get("atk_mod", 0)
            new_pokemon.def_mod += mods.get("def_mod", 0)
            new_pokemon.spatk_mod += mods.get("spatk_mod", 0)
            new_pokemon.spdef_mod += mods.get("spdef_mod", 0)
            new_pokemon.speed_mod += mods.get("speed_mod", 0)

        # 特性: 入场触发
        if new_pokemon.ability_effects:
            EffectExecutor.execute_ability(
                state, new_pokemon, enemy, Timing.ON_ENTER,
                new_pokemon.ability_effects, team,
            )

        # 迅捷：入场时自动释放带 agility 标记的技能
        EffectExecutor.execute_agility_entry(state, new_pokemon, enemy, team)

        # 敌方特性: 对手换人时触发 (影狸下黑手)
        if enemy.ability_effects:
            EffectExecutor.execute_ability(
                state, enemy, new_pokemon, Timing.ON_ENEMY_SWITCH,
                enemy.ability_effects, enemy_team,
            )
        return

    # 汇合聚能
    if action[0] == -1:
        current.gain_energy(5)
        return

    skill = current.skills[action[0]]

    # 蓄力逻辑
    if skill.charge:
        if current.charging_skill_idx != action[0]:
            current.charging_skill_idx = action[0]
            return
        else:
            current.charging_skill_idx = -1

    if current.energy < skill.energy_cost:
        current.gain_energy(5)
        return
    current.energy -= skill.energy_cost

    # ═══════════════════════════════════════
    #  新引擎路径: 有 effects 的技能
    # ═══════════════════════════════════════
    if skill.effects:
        _execute_new_engine(state, team, enemy_team, current, enemy, skill,
                            action, enemy_action, team_list, idx)
        return

    # ═══════════════════════════════════════
    #  旧引擎路径: 无 effects 的技能 (保持不变)
    # ═══════════════════════════════════════

    if skill.force_switch:
        alive = [i for i, p in enumerate(team_list) if not p.is_fainted and i != idx]
        if alive:
            current.on_switch_out()
            new_idx = random.choice(alive)
            if team == "a":
                state.current_a = new_idx
            else:
                state.current_b = new_idx
        return

    enemy_skill = None
    if enemy_action[0] >= 0 and not enemy.is_fainted:
        enemy_skill = enemy.skills[enemy_action[0]]

    if skill.category == SkillCategory.DEFENSE:
        current.apply_self_buff(skill)
        if skill.self_heal_hp > 0:
            heal = int(current.hp * skill.self_heal_hp)
            current.current_hp = min(current.hp, current.current_hp + heal)
        if skill.self_heal_energy > 0:
            current.gain_energy(skill.self_heal_energy)
        return

    if skill.category == SkillCategory.STATUS:
        current.apply_self_buff(skill)
        enemy.apply_enemy_debuff(skill)
        if skill.self_heal_hp > 0:
            heal = int(current.hp * skill.self_heal_hp)
            current.current_hp = min(current.hp, current.current_hp + heal)
        if skill.self_heal_energy > 0:
            current.gain_energy(skill.self_heal_energy)
        if skill.steal_energy > 0:
            current.gain_energy(skill.steal_energy)
            enemy.energy = max(0, enemy.energy - skill.steal_energy)
        if skill.enemy_lose_energy > 0:
            enemy.energy = max(0, enemy.energy - skill.enemy_lose_energy)
        if skill.poison_stacks > 0:
            enemy.poison_stacks += skill.poison_stacks
        if skill.burn_stacks > 0:
            enemy.burn_stacks += skill.burn_stacks
        if skill.freeze_stacks > 0:
            enemy.freeze_stacks += skill.freeze_stacks
        if skill.leech_stacks > 0:
            enemy.leech_stacks += skill.leech_stacks
        if skill.meteor_stacks > 0:
            enemy.meteor_stacks += skill.meteor_stacks
            if enemy.meteor_countdown <= 0:
                enemy.meteor_countdown = 3
        if skill.force_switch:
            alive = [i for i, p in enumerate(team_list) if not p.is_fainted and i != idx]
            if alive:
                current.on_switch_out()
                new_idx = random.choice(alive)
                if team == "a":
                    state.current_a = new_idx
                else:
                    state.current_b = new_idx
        return

    # 攻击技能（旧路径）
    current.apply_self_buff(skill)
    enemy.apply_enemy_debuff(skill)
    if skill.poison_stacks > 0:
        enemy.poison_stacks += skill.poison_stacks
    if skill.burn_stacks > 0:
        enemy.burn_stacks += skill.burn_stacks
    if skill.freeze_stacks > 0:
        enemy.freeze_stacks += skill.freeze_stacks
    if skill.leech_stacks > 0:
        enemy.leech_stacks += skill.leech_stacks
    if skill.meteor_stacks > 0:
        enemy.meteor_stacks += skill.meteor_stacks
        if enemy.meteor_countdown <= 0:
            enemy.meteor_countdown = 3
    if skill.steal_energy > 0:
        current.gain_energy(skill.steal_energy)
        enemy.energy = max(0, enemy.energy - skill.steal_energy)
    if skill.enemy_lose_energy > 0:
        enemy.energy = max(0, enemy.energy - skill.enemy_lose_energy)
    if skill.power <= 0 or enemy.is_fainted:
        if skill.self_heal_hp > 0:
            heal = int(current.hp * skill.self_heal_hp)
            current.current_hp = min(current.hp, current.current_hp + heal)
        if skill.self_heal_energy > 0:
            current.gain_energy(skill.self_heal_energy)
        return
    damage = DamageCalculator.calculate(current, enemy, skill)
    if enemy_skill and not enemy.is_fainted:
        damage = resolve_counter(current, enemy, skill, enemy_skill, damage)
    enemy.current_hp -= damage
    if enemy.current_hp <= 0:
        enemy.current_hp = 0
        enemy.status = StatusType.FAINTED
    if skill.life_drain > 0:
        heal = int(damage * skill.life_drain)
        current.current_hp = min(current.hp, current.current_hp + heal)
    if skill.self_heal_hp > 0:
        heal = int(current.hp * skill.self_heal_hp)
        current.current_hp = min(current.hp, current.current_hp + heal)
    if skill.self_heal_energy > 0:
        current.gain_energy(skill.self_heal_energy)


def _execute_new_engine(state: BattleState, team: str, enemy_team: str,
                        current: Pokemon, enemy: Pokemon, skill: Skill,
                        action: Action, enemy_action: Action,
                        team_list: list, idx: int) -> None:
    """新引擎路径: 用 EffectExecutor 执行有 effects 的技能"""

    # 获取对方技能 (用于应对判定)
    enemy_skill = None
    enemy_list = state.team_b if team == "a" else state.team_a
    if enemy_action[0] >= 0 and not enemy.is_fainted:
        enemy_skill = enemy.skills[enemy_action[0]]

    # 判断先后手
    is_first = _is_first_action(state, team, action, enemy_team, enemy_action)

    # 能耗动态调整 (毒液渗透等)
    energy_refund = 0
    for tag in skill.effects:
        if tag.type == E.ENERGY_COST_DYNAMIC:
            per = tag.params.get("per", "")
            reduce = tag.params.get("reduce", 0)
            if per == "enemy_poison":
                energy_refund = enemy.poison_stacks * reduce

    if energy_refund > 0:
        current.gain_energy(min(energy_refund, skill.energy_cost))

    # 执行主效果
    result = EffectExecutor.execute_skill(
        state, current, enemy, skill, skill.effects,
        is_first=is_first, enemy_skill=enemy_skill, team=team,
    )

    damage = result["damage"]

    # 应对解析 (新引擎)
    if enemy_skill and not enemy.is_fainted and result["counter_effects"]:
        for counter_tag in result["counter_effects"]:
            counter_result = EffectExecutor.execute_counter(
                state, current, enemy, skill, counter_tag,
                enemy_skill, damage, team,
            )

            if counter_result.get("interrupted"):
                result["interrupted"] = True

            if counter_result.get("force_switch"):
                result["force_switch"] = True

            if counter_result.get("force_enemy_switch"):
                result["force_enemy_switch"] = True

    # 对方也有应对效果? (对方技能有 COUNTER_*, 且匹配我方技能类型)
    if enemy_skill and hasattr(enemy_skill, "effects") and enemy_skill.effects:
        for etag in enemy_skill.effects:
            if etag.type in (E.COUNTER_ATTACK, E.COUNTER_STATUS, E.COUNTER_DEFENSE):
                counter_result = EffectExecutor.execute_counter(
                    state, enemy, current, enemy_skill, etag,
                    skill, damage, enemy_team,
                )
                # 防御减伤
                if etag.type == E.COUNTER_ATTACK:
                    # 查找对方技能是否有减伤
                    for e2 in enemy_skill.effects:
                        if e2.type == E.DAMAGE_REDUCTION:
                            pct = e2.params.get("pct", 0)
                            damage = int(damage * (1.0 - pct))

                if counter_result.get("force_enemy_switch"):
                    # 吓退: 强制我方脱离
                    alive = [i for i, p in enumerate(team_list)
                             if not p.is_fainted and i != idx]
                    if alive:
                        current.on_switch_out()
                        new_idx = random.choice(alive)
                        if team == "a":
                            state.current_a = new_idx
                        else:
                            state.current_b = new_idx

    # 秩序鱿墨特性: 受到攻击时减伤
    if enemy.ability_effects and damage > 0:
        ability_ctx = {"skill": skill, "damage": damage}
        ability_result = EffectExecutor.execute_ability(
            state, enemy, current, Timing.ON_TAKE_HIT,
            enemy.ability_effects, enemy_team, ability_ctx,
        )
        if ability_result.get("damage_reduction", 0) > 0:
            damage = int(damage * (1.0 - ability_result["damage_reduction"]))

    # 技能自带减伤 (防御类/状态类技能)
    dmg_reduction = result.get("_damage_reduction", 0)
    if dmg_reduction > 0:
        # 这是自身的减伤, 应用于对方对自己造成的伤害 (不适用于此处)
        pass

    # 造成伤害
    if damage > 0 and not enemy.is_fainted:
        enemy.current_hp -= damage
        if enemy.current_hp <= 0:
            enemy.current_hp = 0
            enemy.status = StatusType.FAINTED

    # 击败检查 & 击败时效果
    if enemy.is_fainted:
        # 感染病: 击败时中毒转印记
        for tag in skill.effects:
            if tag.type == E.CONVERT_POISON_TO_MARK and tag.params.get("on") == "kill":
                marks = state.marks_b if team == "a" else state.marks_a
                marks["poison_mark"] = marks.get("poison_mark", 0) + enemy.poison_stacks
                enemy.poison_stacks = 0

        # 特性: 被击败时 (圣羽翼王飓风)
        if enemy.ability_effects:
            EffectExecutor.execute_ability(
                state, enemy, current, Timing.ON_BE_KILLED,
                enemy.ability_effects, enemy_team,
            )

        # 特性: 力竭时 (迷迷箱怪虚假宝箱)
        if enemy.ability_effects:
            EffectExecutor.execute_ability(
                state, enemy, current, Timing.ON_FAINT,
                enemy.ability_effects, enemy_team,
            )

    # 脱离
    if result.get("force_switch"):
        alive = [i for i, p in enumerate(team_list) if not p.is_fainted and i != idx]
        if alive:
            current.on_switch_out()
            new_idx = random.choice(alive)
            if team == "a":
                state.current_a = new_idx
            else:
                state.current_b = new_idx

    # 强制敌方脱离 (吓退)
    if result.get("force_enemy_switch"):
        eidx = state.current_b if team == "a" else state.current_a
        enemy_list_ref = state.team_b if team == "a" else state.team_a
        alive = [i for i, p in enumerate(enemy_list_ref) if not p.is_fainted and i != eidx]
        if alive:
            enemy.on_switch_out()
            new_idx = random.choice(alive)
            if team == "a":
                state.current_b = new_idx
            else:
                state.current_a = new_idx

    # 驱散印记 (倾泻: 未被防御时)
    if result.get("_dispel_if_not_blocked"):
        # 检查对方是否使用了防御/减伤技能
        was_blocked = False
        if enemy_skill and enemy_skill.effects:
            was_blocked = any(e.type == E.DAMAGE_REDUCTION for e in enemy_skill.effects)
        elif enemy_skill and enemy_skill.damage_reduction > 0:
            was_blocked = True
        if not was_blocked:
            state.marks_a.clear()
            state.marks_b.clear()

    # 传动
    drive_value = result.get("_drive_value", 0)
    if drive_value > 0:
        EffectExecutor.execute_drive(state, current, enemy, skill, drive_value, team)

    # 特性: 使用技能后触发 (千棘盔溶解扩散/琉璃水母扩散侵蚀)
    if current.ability_effects:
        EffectExecutor.execute_ability(
            state, current, enemy, Timing.ON_USE_SKILL,
            current.ability_effects, team,
            context={"skill": skill},
        )

    # 条件增益: 嘲弄 (敌方本回合替换精灵)
    cond_buff = result.get("_conditional_enemy_switch_buff")
    if cond_buff:
        enemy_switched = (state.switch_this_turn_b if team == "a" else state.switch_this_turn_a)
        if enemy_switched:
            from src.effect_engine import _apply_buff
            _apply_buff(current, cond_buff)


def _is_first_action(state: BattleState, team: str, action: Action,
                     enemy_team: str, enemy_action: Action) -> bool:
    """判断当前行动是否先于对手"""
    if action[0] < 0 or enemy_action[0] < 0:
        return True
    p_a = state.team_a[state.current_a]
    p_b = state.team_b[state.current_b]
    spd_a = p_a.effective_speed() * (1.0 + get_priority(state, "a", action))
    spd_b = p_b.effective_speed() * (1.0 + get_priority(state, "b", enemy_action))
    if team == "a":
        return spd_a >= spd_b
    else:
        return spd_b > spd_a


def get_priority(state: BattleState, team: str, action: Action) -> float:
    """获取先手修正"""
    if action[0] < 0:
        return 0
    team_list = state.team_a if team == "a" else state.team_b
    idx = state.current_a if team == "a" else state.current_b
    skill = team_list[idx].skills[action[0]]
    return skill.priority_mod * 0.1


def check_winner(state: BattleState) -> Optional[str]:
    """检查胜负: 先失去4点MP(降到0)的玩家败北"""
    if state.mp_a <= 0:
        return "b"
    if state.mp_b <= 0:
        return "a"
    return None


# ============================================================
# 队伍构建 - 从精灵数据库+技能数据库自动获取属性
# ============================================================
class TeamBuilder:

    TYPE_MAP = {
        "普通": Type.NORMAL, "火": Type.FIRE, "水": Type.WATER, "草": Type.GRASS,
        "电": Type.ELECTRIC, "冰": Type.ICE, "格斗": Type.FIGHTING, "毒": Type.POISON,
        "地面": Type.GROUND, "飞行": Type.FLYING, "超能": Type.PSYCHIC, "虫": Type.BUG,
        "岩石": Type.ROCK, "幽灵": Type.GHOST, "龙": Type.DRAGON, "恶": Type.DARK,
        "钢": Type.STEEL, "妖精": Type.FAIRY, "机械": Type.STEEL, "萌": Type.FAIRY,
        "翼": Type.FLYING, "武": Type.FIGHTING, "幽": Type.GHOST, "幻": Type.PSYCHIC,
        "光": Type.ELECTRIC,
    }

    @staticmethod
    def _p(name: str, skill_names: list) -> Pokemon:
        """根据精灵名称从数据库获取六维数据，构造Pokemon对象"""
        from src.pokemon_db import get_pokemon
        from src.skill_db import load_ability_effects

        data = get_pokemon(name)
        if data:
            ptype_str = data["属性"]
            ability = data["特性"]
            hp = int(data["生命值"])
            atk = int(data["物攻"])
            dfn = int(data["物防"])
            spatk = int(data["魔攻"])
            spdef = int(data["魔防"])
            spd = int(data["速度"])
        else:
            print(f"[WARN] 精灵 '{name}' 未在数据库中找到，使用默认属性")
            ptype_str = "普通"
            ability = "未知"
            hp, atk, dfn, spatk, spdef, spd = 500, 350, 350, 350, 350, 350

        type_enum = TeamBuilder.TYPE_MAP.get(ptype_str, Type.NORMAL)
        skills = [get_skill(n) for n in skill_names]

        # 加载特性效果
        ability_effects = load_ability_effects(ability) if ability else []

        p = Pokemon(name=name, pokemon_type=type_enum,
                    hp=hp, attack=atk, defense=dfn,
                    sp_attack=spatk, sp_defense=spdef,
                    speed=spd, ability=ability, skills=skills)
        p.ability_effects = ability_effects
        return p

    @staticmethod
    def create_toxic_team() -> List[Pokemon]:
        return [
            TeamBuilder._p("千棘盔", ["毒雾", "泡沫幻影", "疫病吐息", "打湿"]),
            TeamBuilder._p("影狸", ["嘲弄", "恶意逃离", "毒液渗透", "感染病"]),
            TeamBuilder._p("裘卡", ["阻断", "崩拳", "毒囊", "防御"]),
            TeamBuilder._p("琉璃水母", ["甩水", "天洪", "泡沫幻影", "以毒攻毒"]),
            TeamBuilder._p("迷迷箱怪", ["风墙", "啮合传递", "双星", "偷袭"]),
            TeamBuilder._p("海豹船长", ["力量增效", "水刃", "斩断", "听桥"]),
        ]

    @staticmethod
    def create_wing_team() -> List[Pokemon]:
        return [
            TeamBuilder._p("燃薪虫", ["火焰护盾", "引燃", "倾泻", "抽枝"]),
            TeamBuilder._p("圣羽翼王", ["水刃", "力量增效", "疾风连袭", "扇风"]),
            TeamBuilder._p("翠顶夫人", ["力量增效", "水刃", "水环", "泡沫幻影"]),
            TeamBuilder._p("迷迷箱怪", ["双星", "啮合传递", "偷袭", "吓退"]),
            TeamBuilder._p("秩序鱿墨", ["风墙", "能量刃", "力量增效", "倾泻"]),
            TeamBuilder._p("声波缇塔", ["轴承支撑", "齿轮扭矩", "地刺", "啮合传递"]),
        ]
