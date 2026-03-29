"""
MCTS AI + 经验学习系统

核心改进：
1. 支持新战斗机制（应对、连击、吸血、减伤、层数）
2. 经验学习：每场对战记录决策，后续对战参考历史胜率
3. 先验引导：用经验数据作为UCB1的先验概率
"""

import sys
import os
import math
import random
import copy
from typing import List, Tuple, Optional, Dict
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.models import BattleState, StatusType, StatType
from src.battle import (
    get_actions, execute_full_turn, check_winner, auto_switch, Action
)


# ============================================================
# 经验记忆 - 跨对战学习
# ============================================================
class ExperienceMemory:
    """
    经验记忆系统
    记录 (状态签名, 动作) -> (胜利次数, 总使用次数)
    下次遇到类似状态时，作为MCTS的先验概率
    """

    def __init__(self, decay: float = 0.95):
        # key: (state_key, action_tuple) -> [wins, total]
        self._memory: Dict[Tuple, List[float]] = defaultdict(lambda: [0.0, 0.0])
        self._decay = decay
        self._battle_count = 0

    def state_key(self, state: BattleState, team: str) -> str:
        """生成状态签名（简化，便于泛化）"""
        p = state.get_current(team)
        enemy_team = "b" if team == "a" else "a"
        e = state.get_current(enemy_team)
        # 签名 = 我方精灵+HP%+能量 | 敌方精灵+HP%+能量 | 回合数段
        my_hp_pct = p.current_hp / p.hp if p.hp > 0 else 0
        enemy_hp_pct = e.current_hp / e.hp if e.hp > 0 else 0
        round_bin = state.turn // 5  # 5回合一个区间
        return f"{p.name}|{my_hp_pct:.1f}|{p.energy}|{e.name}|{enemy_hp_pct:.1f}|{round_bin}"

    def record_action(self, state_key: str, action: Action, won: bool):
        """记录一次动作的结果"""
        key = (state_key, action)
        self._memory[key][1] += 1.0
        if won:
            self._memory[key][0] += 1.0

    def get_prior(self, state_key: str, action: Action) -> Tuple[float, int]:
        """获取先验概率和样本量"""
        key = (state_key, action)
        w, t = self._memory[key]
        if t < 1:
            return 0.5, 0
        return w / t, int(t)

    def decay(self):
        """衰减旧经验（模拟遗忘）"""
        for key in self._memory:
            self._memory[key][0] *= self._decay
            self._memory[key][1] *= self._decay

    def record_battle(self, state_log: List[Tuple[str, Action]], won: bool):
        """记录一整场对战的动作序列"""
        self._battle_count += 1
        for state_key, action in state_log:
            self.record_action(state_key, action, won)
        # 每10场衰减一次
        if self._battle_count % 10 == 0:
            self.decay()

    @property
    def size(self) -> int:
        return len(self._memory)

    def save(self):
        return {
            "battle_count": self._battle_count,
            "memory_size": self.size,
        }

    def save_to_file(self, filepath: str):
        """保存经验到MD文件"""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        lines = [
            f"# Experience Memory",
            f"",
            f"- **Battle Count**: {self._battle_count}",
            f"- **Memory Size**: {self.size}",
            f"- **Decay**: {self._decay}",
            f"",
            f"```",
        ]
        for (state_key, action), (wins, total) in self._memory.items():
            if total >= 0.1:
                # 用 TAB 分隔，避免和MD冲突
                lines.append(f"{state_key}\t{action}\t{wins:.4f}\t{total:.4f}")
        lines.append("```")
        lines.append("")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def load_from_file(self, filepath: str):
        """从MD文件加载经验"""
        if not os.path.exists(filepath):
            return
        with open(filepath, "r", encoding="utf-8") as f:
            in_code_block = False
            for line in f:
                stripped = line.rstrip("\n").rstrip("\r")
                if stripped.strip() == "```":
                    in_code_block = not in_code_block
                    continue
                if not in_code_block:
                    continue
                parts = stripped.split("\t")
                if len(parts) < 4:
                    continue
                state_key = parts[0]
                action_str = parts[1]
                try:
                    wins = float(parts[2])
                    total = float(parts[3])
                    action = eval(action_str)
                    self._memory[(state_key, action)] = [wins, total]
                except Exception:
                    continue

    def summary(self) -> str:
        """生成经验摘要文本"""
        return f"battles={self._battle_count}, records={self.size}"


# 全局经验库（A队和B队各一个）
EXPERIENCE_A = ExperienceMemory()
EXPERIENCE_B = ExperienceMemory()


# ============================================================
# MCTS 节点
# ============================================================
class MCTSNode:
    __slots__ = ('state', 'parent', 'action', 'children', 'wins', 'visits',
                 'untried', 'team')

    def __init__(self, state: BattleState, parent=None, action=None, team="a"):
        self.state = state
        self.parent = parent
        self.action = action
        self.children: List['MCTSNode'] = []
        self.wins = 0.0
        self.visits = 0
        self.untried: List[Action] = []
        self.team = team

    @property
    def ucb1(self):
        if self.visits == 0:
            return float('inf')
        return self.wins / self.visits + math.sqrt(2 * math.log(self.parent.visits) / self.visits)

    @property
    def fully_expanded(self):
        return len(self.untried) == 0


# ============================================================
# MCTS 搜索器（带经验学习）
# ============================================================
class MCTS:
    def __init__(self, simulations: int = 200, team: str = "a",
                 experience: ExperienceMemory = None,
                 explore_weight: float = 1.4):
        self.simulations = simulations
        self.team = team
        self.experience = experience  # 经验记忆
        self.explore_weight = explore_weight  # 探索权重
        self._action_log: List[Tuple[str, Action]] = []  # 本场动作记录

    def get_best_action(self, state: BattleState) -> Action:
        root = MCTSNode(copy.deepcopy(state), team=self.team)
        root.untried = get_actions(state, self.team)

        if not root.untried:
            return (-1,)
        if len(root.untried) == 1:
            return root.untried[0]

        state_key = None
        if self.experience:
            state_key = self.experience.state_key(state, self.team)

        for _ in range(self.simulations):
            node = root

            # Selection - 带经验先验的UCB选择
            while node.fully_expanded and node.children:
                node = self._select_child(node, state_key)

            # Expansion
            if node.untried:
                act = node.untried.pop(random.randrange(len(node.untried)))
                new_state = copy.deepcopy(node.state)
                w = check_winner(new_state)
                if w:
                    self._backpropagate(node, w)
                    continue
                enemy = "b" if self.team == "a" else "a"
                enemy_actions = get_actions(new_state, enemy)
                if not enemy_actions:
                    self._backpropagate(node, self.team)
                    continue
                enemy_act = random.choice(enemy_actions)
                if self.team == "a":
                    execute_full_turn(new_state, act, enemy_act)
                else:
                    execute_full_turn(new_state, enemy_act, act)
                child = MCTSNode(new_state, node, act, self.team)
                child.untried = get_actions(new_state, self.team)
                node.children.append(child)
                node = child

            # Simulation
            winner = self._simulate(node.state)

            # Backpropagation
            self._backpropagate(node, winner)

        if not root.children:
            return get_actions(state, self.team)[0]

        # 记录本场选择的动作
        best = max(root.children, key=lambda x: x.visits)
        if state_key:
            self._action_log.append((state_key, best.action))

        return best.action

    def _select_child(self, node: MCTSNode, state_key: str = None) -> MCTSNode:
        """带经验先验的UCB选择"""
        best_score = -1
        best_child = None

        for child in node.children:
            # 基础UCB1
            if child.visits == 0:
                score = float('inf')
            else:
                exploit = child.wins / child.visits
                explore = math.sqrt(self.explore_weight * math.log(node.visits) / child.visits)
                score = exploit + explore

            # 经验先验加成
            if state_key and self.experience and child.action:
                prior_w, prior_n = self.experience.get_prior(state_key, child.action)
                if prior_n > 0:
                    # 用经验胜率微调exploit项
                    # 经验权重随样本量增长，但有上限
                    prior_weight = min(prior_n / 20.0, 0.3)  # 最多影响30%
                    if child.visits > 0:
                        current_rate = child.wins / child.visits
                        adjusted = current_rate * (1 - prior_weight) + prior_w * prior_weight
                        explore = math.sqrt(self.explore_weight * math.log(node.visits) / child.visits)
                        score = adjusted + explore

            if score > best_score:
                best_score = score
                best_child = child

        return best_child

    def _simulate(self, state: BattleState, max_rounds: int = 150) -> Optional[str]:
        """快速随机模拟"""
        state = copy.deepcopy(state)
        for _ in range(max_rounds):
            w = check_winner(state)
            if w:
                return w
            actions_a = get_actions(state, "a")
            actions_b = get_actions(state, "b")
            if not actions_a:
                return "b"
            if not actions_b:
                return "a"

            # 带经验偏好的随机选择
            if self.experience:
                act_a = self._biased_choice(state, "a", actions_a)
                act_b = self._biased_choice(state, "b", actions_b)
            else:
                act_a = random.choice(actions_a)
                act_b = random.choice(actions_b)

            execute_full_turn(state, act_a, act_b)
        return check_winner(state)

    def _biased_choice(self, state: BattleState, team: str,
                       actions: List[Action]) -> Action:
        """带经验偏好的随机选择（用于模拟阶段）"""
        state_key = self.experience.state_key(state, team)
        scores = []
        for act in actions:
            prior_w, prior_n = self.experience.get_prior(state_key, act)
            if prior_n > 0:
                # 胜率越高的动作被选中概率越大
                scores.append((act, prior_w, prior_n))
            else:
                scores.append((act, 0.5, 0))

        # 按加权概率选择
        total = sum(max(0.1, s[1]) * (1 + s[2] * 0.01) for s in scores)
        r = random.random() * total
        cumul = 0
        for act, w, n in scores:
            cumul += max(0.1, w) * (1 + n * 0.01)
            if cumul >= r:
                return act
        return random.choice(actions)

    def _backpropagate(self, node: MCTSNode, winner: Optional[str]) -> None:
        while node:
            node.visits += 1
            if winner == node.team:
                node.wins += 1.0
            elif winner:
                node.wins += 0.0
            else:
                node.wins += 0.5
            node = node.parent

    def get_action_log(self) -> List[Tuple[str, Action]]:
        """获取本场动作记录"""
        return self._action_log

    def clear_log(self):
        self._action_log = []
