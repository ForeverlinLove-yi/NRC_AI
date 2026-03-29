"""
精灵数据库 - 从 pokemon_stats.xlsx 加载精灵属性和六维数据
"""
import os
import openpyxl

# 精灵数据缓存: name -> dict
_db = {}


def load_pokemon_db(filepath=None):
    """从Excel加载精灵数据"""
    global _db
    if not filepath:
        filepath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "data", "pokemon_stats.xlsx")
    if not os.path.exists(filepath):
        print(f"[WARN] 精灵数据库文件不存在: {filepath}")
        return

    wb = openpyxl.load_workbook(filepath, read_only=True)
    ws = wb["精灵总表"]

    for row in ws.iter_rows(min_row=2, values_only=True):
        if len(row) < 18:
            continue
        name = row[1]  # 名称
        if not name:
            continue

        # 优先使用"最终形态"，否则用第一个匹配的
        key = name
        # 如果已有同名的最终形态，跳过非最终形态
        existing = _db.get(name)
        if existing and existing.get("进化阶段") == "最终形态":
            stage = row[3] or ""
            if stage != "最终形态":
                continue

        _db[key] = {
            "编号": row[0],
            "名称": name,
            "属性": row[2] or "普通",
            "进化阶段": row[3] or "",
            "特性": row[4] or "",
            "生命种族值": row[5] or 0,
            "物攻种族值": row[6] or 0,
            "魔攻种族值": row[7] or 0,
            "物防种族值": row[8] or 0,
            "魔防种族值": row[9] or 0,
            "速度种族值": row[10] or 0,
            "种族值总和": row[11] or 0,
            "生命值": row[12] or 0,
            "物攻": row[13] or 0,
            "魔攻": row[14] or 0,
            "物防": row[15] or 0,
            "魔防": row[16] or 0,
            "速度": row[17] or 0,
        }

    wb.close()
    print(f"[OK] 精灵数据库已加载: {len(_db)} 只精灵")


def get_pokemon(name: str) -> dict:
    """
    根据名称获取精灵数据。
    支持模糊匹配：如果精确匹配失败，尝试包含匹配。
    优先选择"最终形态"。
    """
    # 精确匹配
    if name in _db:
        return _db[name]

    # 模糊匹配 - 精确包含
    candidates = []
    for key, data in _db.items():
        if name in key or key in name:
            candidates.append((key, data))

    if not candidates:
        # 最后尝试：忽略括号部分匹配
        base_name = name.split("（")[0]
        for key, data in _db.items():
            key_base = key.split("（")[0]
            if base_name == key_base:
                candidates.append((key, data))

    if candidates:
        # 优先最终形态
        for key, data in candidates:
            if data.get("进化阶段") == "最终形态":
                return data
        return candidates[0][1]

    return None


def search_pokemon(keyword: str) -> list:
    """搜索精灵"""
    results = []
    for key, data in _db.items():
        if keyword in key or keyword in str(data.get("特性", "")):
            results.append(data)
    return results[:20]
