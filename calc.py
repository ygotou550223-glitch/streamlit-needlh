import csv as txt

SHIFT_HOURS = 7.5       # 1人の実働（h）
SAFETY_FACTOR = 1.10    # 安全係数（+10%）

# 1) マスタ読み込み
processes = []
with open("master.txt", encoding="utf-8") as f:
    reader = txt.DictReader(f)
    for row in reader:
        processes.append({
            "name": row["name"],
            "rate_uph": float(row["rate_uph"]),
            "util": float(row["util"]),
            "indirect_pct": float(row["indirect_pct"]),
        })

# 2) 当日の処理必要数を工程ごとに入力（例：同じ数を一括で入れる）
base_volume = int(input("今日の処理必要数（同じ数を全工程に入れる）: "))
for p in processes:
    p["volume"] = base_volume

# 3) 計算
total_lh = 0.0
for p in processes:
    direct_lh = (p["volume"] / p["rate_uph"]) / p["util"]
    indirect_lh = direct_lh * p["indirect_pct"]
    need_lh = (direct_lh + indirect_lh)
    total_lh += need_lh
    print(f"{p['name']}: 直{direct_lh:.2f}h / 間{indirect_lh:.2f}h / 小計{need_lh:.2f}h")

total_lh *= SAFETY_FACTOR
heads = total_lh / SHIFT_HOURS

print("-" * 32)
print(f"合計LH(安全係数込): {total_lh:.2f} h")
print(f"必要人数({SHIFT_HOURS}h/人): {heads:.1f} 人")

import math
from datetime import datetime

SHIFT_HOURS_LIST = [8.0, 7.5, 6.0, 4.0]  # 複数シフトで計算
SAFETY_FACTOR = 1.10
FIXED_HEADS = 2  # 最低固定人員（リード等）

# 2) 工程別の処理必要数を入力
print("=== 工程別の処理必要数を入力してください ===")
for p in processes:
    while True:
        try:
            v = int(input(f"{p['name']} の処理必要数: "))
            if v < 0:
                print("0以上で入力してください。")
                continue
            p["volume"] = v
            break
        except ValueError:
            print("整数で入力してください。")

# 3) 工程別のLHを計算・表示
total_lh = 0.0
print("\n--- 工程別 計算結果 ---")
for p in processes:
    direct_lh = (p["volume"] / p["rate_uph"]) / p["util"]
    indirect_lh = direct_lh * p["indirect_pct"]
    need_lh = direct_lh + indirect_lh
    total_lh += need_lh
    print(f"{p['name']}: 直{direct_lh:.2f}h / 間{indirect_lh:.2f}h / 小計{need_lh:.2f}h")

# 4) 安全係数を適用
total_lh *= SAFETY_FACTOR

print("\n--- 合計 ---")
print(f"合計LH(安全係数込): {total_lh:.2f} h")

# 5) シフト別必要人数を表示（切り上げ+固定人員）
print("\n--- シフト別 必要人数 ---")
for sh in SHIFT_HOURS_LIST:
    heads = total_lh / sh
    heads_up = math.ceil(heads) + FIXED_HEADS
    print(f"{sh:.1f}h/人: 端数切上げ {math.ceil(heads)} 人 + 固定{FIXED_HEADS}人 → 合計 {heads_up} 人")

# 6) ログCSVに保存（任意）
log_name = "need_lh_log.csv"
try:
    import os
    is_new = not os.path.exists(log_name)
    with open(log_name, "a", encoding="utf-8") as f:
        if is_new:
            f.write("date,total_lh," + ",".join([f"heads_{int(s*10)}" for s in SHIFT_HOURS_LIST]) + "\n")
        row = [datetime.now().strftime("%Y-%m-%d %H:%M"), f"{total_lh:.2f}"]
        for sh in SHIFT_HOURS_LIST:
            row.append(str(math.ceil(total_lh / sh) + FIXED_HEADS))
        f.write(",".join(row) + "\n")
    print(f"\nログを {log_name} に追記しました。")
except Exception as e:
    print(f"\nログ保存はスキップしました（理由: {e}）")
