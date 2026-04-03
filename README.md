# 洛克王国战斗 AI 模拟器 / Rokugou Battle AI Simulator

> 基于蒙特卡洛树搜索（MCTS）的洛克王国对战模拟系统，支持 AI 自战、批量统计与玩家对战模式。
> A Monte Carlo Tree Search (MCTS) based battle simulator for Rokugou (洛克王国), featuring AI vs AI, batch statistics, and Player vs AI modes.

---

## 目录 / Table of Contents

- [功能特性 / Features](#功能特性--features)
- [队伍配置 / Teams](#队伍配置--teams)
- [战斗规则 / Battle Rules](#战斗规则--battle-rules)
- [AI 原理 / AI Algorithm](#ai-原理--ai-algorithm)
- [效果标签引擎 / Effect Tag Engine](#效果标签引擎--effect-tag-engine)
- [快速开始 / Quick Start](#快速开始--quick-start)
- [项目结构 / Project Structure](#项目结构--project-structure)

---

## 功能特性 / Features

**中文：**
- 🤖 **MCTS AI**：双方均由蒙特卡洛树搜索驱动，支持可配置模拟次数，采用**对抗式 MCTS**（双方交替 UCB 选择）
- 📚 **经验学习**：AI 积累对战记录，逐步优化决策策略
- ⚔️ **玩家对战**：交互式界面，支持玩家手动控制 A 队与 AI 对战
- 📊 **批量模拟**：一键运行多场对战，统计胜率与平均回合数
- 🔬 **学习实验**：分阶段观察 AI 随经验积累的成长曲线
- 💊 **丰富技能系统**：从 CSV/Excel 数据库加载技能，支持吸血、减伤、应对、连击等复杂效果
- 🏷️ **效果标签引擎（Effect Tag System）**：全新的结构化效果系统，用 `EffectTag` 替代正则解析，已配置 35 个技能 + 12 个特性
- 🌀 **异常状态**：中毒（叠层）、灼烧（叠层）、冻结、麻痹、睡眠
- 🔄 **被动换人**：精灵倒下时选择上场精灵，不占用行动回合

**English：**
- 🤖 **MCTS AI**: Both sides driven by Monte Carlo Tree Search with configurable simulation count; uses **Adversarial MCTS** (alternating UCB selection)
- 📚 **Experience Learning**: AI accumulates battle records and progressively improves decision-making
- ⚔️ **Player vs AI**: Interactive terminal UI for manual control of Team A against the AI
- 📊 **Batch Simulation**: Run multiple battles at once and get win-rate / avg-round statistics
- 🔬 **Learning Experiment**: Stage-by-stage observation of AI growth as experience accumulates
- 💊 **Rich Skill System**: Skills loaded from CSV/Excel DB with effects like life drain, damage reduction, counters, multi-hit
- 🏷️ **Effect Tag Engine**: New structured effect system using `EffectTag` objects instead of regex parsing — 35 skills + 12 abilities configured
- 🌀 **Status Effects**: Poison (stacking), Burn (stacking), Freeze, Paralysis, Sleep
- 🔄 **Passive Switch on Faint**: Choose which Pokémon to send in when one faints — no turn cost

---

## 队伍配置 / Teams

| 队伍 / Team | 成员 / Members |
|---|---|
| **A 队（毒队）** | 千棘盔、影狸、裘卡、琉璃水母、迷迷箱怪、海豹船长 |
| **Team A (Toxic)** | Qianjikui, Yingli, Qiuka, Liulishuimu, Mimixiangguai, Haibao Chuanzhang |
| **B 队（翼王队）** | 燃薪虫、圣羽翼王、翠顶夫人、迷迷箱怪、秩序魁墨、声波缇塔 |
| **Team B (Wing King)** | Ranxinchong, Shengyu Yiwang, Cuiding Furen, Mimixiangguai, Zhixu Kuimo, Shengbo Tita |

---

## 战斗规则 / Battle Rules

**中文：**
- **能量系统**：每个技能消耗能量，能量不足时自动使用「汇合聚能」回复 5 点
- **速度判定**：按速度数值决定先后手（除非技能带有「必定先手」属性）
- **必命中**：无命中率计算，技能必然命中
- **无暴击**：不存在暴击机制
- **换人系统**：己方精灵倒下时**被动选择上场精灵**（不消耗回合）；可主动换人（消耗行动机会）
- **效果标签引擎**：已配置 `effects` 的技能走新引擎执行，未配置的保持旧正则解析（渐进式迁移）
- **特性系统**：支持入场/离场/回合结束/使用技能/被攻击/击败敌方等多时机触发

**English：**
- **Energy System**: Each skill costs energy; when insufficient, the unit uses "Assemble & Charge" to recover 5 energy
- **Speed Priority**: Action order is determined by Speed stat (unless a skill has forced priority)
- **Always Hit**: No accuracy rolls — all moves land
- **No Critical Hits**: No crit mechanic exists
- **Switching**: On faint, **passively choose replacement** (no turn cost); manual switching consumes action
- **Effect Tag Engine**: Skills with `effects` use the new engine; unconfigured skills fall back to legacy regex (gradual migration)
- **Ability System**: Supports multiple trigger timings — on enter/leave, turn end, skill use, take hit, kill, etc.

### 伤害公式 / Damage Formula

```
伤害 = 攻击/防御 × 0.9 × 技能威力 × 克制 × 本系(1.5) × 能力等级 × (1-减伤)
Damage = (ATK / DEF) × 0.9 × Skill Power × Type Multiplier × STAB(1.5) × Stat Stage × (1 − Damage Reduction)
```

---

## AI 原理 / AI Algorithm

**中文：**
双方 AI 均采用 **对抗式蒙特卡洛树搜索（Adversarial MCTS）** 进行零和博弈优化：
1. **Selection**：双方交替按 UCB1 公式选择最优子节点
2. **Expansion**：扩展未探索的动作
3. **Simulation**：随机 rollout 至终局
4. **Backpropagation**：将结果反向更新节点价值

性能优化：使用 `BattleState.deep_copy()` 替代 `deepcopy`，状态签名包含 buff 层数，避免重复探索等价节点。

经验系统（`ExperienceDB`）会记录历史对战中高胜率的动作序列，在 rollout 阶段对这些动作给予更高采样权重，使 AI 随对战场数增加逐步"学聪明"。

**English：**
Both AIs use **Adversarial Monte Carlo Tree Search (MCTS)** for zero-sum game optimization:
1. **Selection**: Both sides alternate choosing best child via UCB1 formula
2. **Expansion**: Expand unvisited actions
3. **Simulation**: Random rollout to terminal state
4. **Backpropagation**: Update node values with the result

Performance: Uses `BattleState.deep_copy()` instead of `deepcopy`; state signatures include buff layers to avoid re-exploring equivalent nodes.

The experience system (`ExperienceDB`) records high-win-rate action sequences from past battles and assigns higher sampling weights during rollouts, allowing the AI to "learn" over successive games.

### 效果标签引擎 / Effect Tag Engine

全新的结构化效果执行系统，替代原有正则解析方式：

```
effect_models.py   →  E 枚举 + Timing 枚举 + EffectTag / AbilityEffect 数据类
effect_data.py     →  35 个技能效果配置 + 12 个特性效果配置
effect_engine.py   →  EffectExecutor 统一执行器（印记/传动/打断/永久修改/条件buff）
battle.py          →  有 effects 的技能走新引擎，无 effects 的走旧逻辑（渐进式迁移）
```

**已支持的子系统：**
- 🏷️ **印记系统**（Marks）：毒印记、水印记等团队持久Buff
- ⚙️ **传动系统**（Drive）：使用技能后的被动触发效果
- ⛔ **打断系统**（Interrupt）：特定条件下中断敌方行动
- ✏️ **永久修改**（Permanent Mod）：不可被清除的属性变化
- 📊 **条件 Buff**：基于血量比例等条件的动态增益

---

## 快速开始 / Quick Start

### 环境要求 / Requirements

- Python 3.8+
- 依赖库 / Dependencies: `openpyxl`, `pandas`

```bash
pip install -r requirements.txt
```

### 运行 / Run

```bash
# 方式一 / Option 1 — 直接运行主菜单 / Launch main menu
python start.py

# 方式二 / Option 2
python src/main.py
```

### Windows 双击启动 / Windows Double-click

直接双击 `run.bat` 即可启动。
Double-click `run.bat` to launch on Windows.

### 菜单说明 / Menu Options

```
1. 单场对战（带经验）     Watch single battle (with experience)
2. 批量模拟 50 场         Batch simulation (50 games)
3. 学习实验 100 场        Learning experiment (100 games)
4. 快速测试 10 场         Quick test (10 games, no experience)
5. A vs B 20 场（无经验） A vs B: 20 games WITHOUT experience
6. A vs B 20 场（带经验） A vs B: 20 games WITH experience
7. 玩家 vs AI ★          PLAYER vs AI (with experience) ★
0. 退出并保存经验         Exit & save experience
```

---

## 项目结构 / Project Structure

```
NRC_AI/
├── src/
│   ├── main.py              # 主程序 / Main program & menu
│   ├── mcts.py              # MCTS AI + 经验系统 / MCTS AI + Experience (Adversarial)
│   ├── battle.py            # 战斗逻辑 + 效果标签集成 / Battle logic + Effect Tag integration
│   ├── models.py            # 数据模型 / Data models (Pokémon, skills, type chart, effects)
│   ├── pokemon_db.py        # 精灵数据库加载 / Pokémon DB loader
│   ├── skill_db.py          # 技能数据库加载 / Skill DB loader
│   ├── effect_models.py     # 效果类型定义 / Effect type definitions (E enum, Timing, EffectTag)
│   ├── effect_data.py       # 效果配置数据 / Effect config data (35 skills + 12 abilities)
│   └── effect_engine.py     # 效果执行引擎 / Effect execution engine (EffectExecutor)
├── data/
│   ├── skills_all.csv                # 技能数据 / Skill data
│   ├── pokemon_stats.xlsx            # 精灵属性 / Pokémon stats
│   ├── nrc.db                        # SQLite 精灵数据库 / SQLite Pokémon DB
│   └── experience/
│       ├── experience_team_a.md      # AI-A 经验记录 / AI-A experience log
│       └── experience_team_b.md      # AI-B 经验记录 / AI-B experience log
├── start.py                 # 启动脚本 / Launch script
├── run.bat                  # Windows 启动 / Windows launcher
└── requirements.txt
```

---

## License

MIT
