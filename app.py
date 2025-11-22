import math
from datetime import datetime
import pandas as pd
import streamlit as st

st.set_page_config(page_title="NeedLH", page_icon="🧮", layout="wide")

# ===== サイドバー：設定 =====
st.sidebar.header("設定")
uploaded = st.sidebar.file_uploader("master.csv（または.csv/.txt）をアップロード", type=["csv", "txt"])
default_safety = st.sidebar.number_input("安全係数（例: 1.10 は +10%）", min_value=1.00, max_value=1.50, value=1.10, step=0.01)
fixed_heads = st.sidebar.number_input("固定人員（班長/QC など）", min_value=0, max_value=20, value=2, step=1)
shift_hours_list = st.sidebar.multiselect(
    "シフト実働（h/人）※複数選択可",
    options=[8.0, 7.5, 6.0, 4.0],
    default=[8.0, 7.5, 6.0, 4.0]
)
log_on = st.sidebar.checkbox("計算結果をCSVに追記（need_lh_log.csv）", value=True)

# ===== マスタ読込 =====
def load_master(file_like) -> pd.DataFrame:
    df = pd.read_csv(file_like)
    # 必須列の存在チェック
    required = {"name", "rate_uph", "util", "indirect_pct"}
    if not required.issubset(set(df.columns)):
        raise ValueError(f"master に必要な列が不足しています: {sorted(list(required))}")
    # 型を明示
    df = df.copy()
    df["rate_uph"] = df["rate_uph"].astype(float)
    df["util"] = df["util"].astype(float)
    df["indirect_pct"] = df["indirect_pct"].astype(float)
    return df

if uploaded is not None:
    df_master = load_master(uploaded)
else:
    # ローカルの master.csv を読む（同フォルダ）
    try:
        df_master = load_master("master.csv")
    except Exception as e:
        st.warning("master.csv をアップロードするか、同フォルダに配置してください。")
        st.stop()

st.title("🧮 必要レイバーアワー計算（工程別入力）")
st.caption("CSVの列: name, rate_uph, util, indirect_pct")

# ===== 入力フォーム（工程別の処理必要数）=====
with st.form("vol_input"):
    st.subheader("工程別の処理必要数（Units）")
    cols = st.columns([2,1,1,1,1])
    cols[0].markdown("**工程名**")
    cols[1].markdown("**UPH**")
    cols[2].markdown("**稼働率**")
    cols[3].markdown("**間接率**")
    cols[4].markdown("**処理必要数**")

    volumes = []
    for i, row in df_master.iterrows():
        c = st.columns([2,1,1,1,1])
        c[0].write(row["name"])
        c[1].write(f'{row["rate_uph"]:.0f}')
        c[2].write(f'{row["util"]:.2f}')
        c[3].write(f'{row["indirect_pct"]:.2f}')
        v = c[4].number_input(
            " ", key=f"vol_{i}", min_value=0, value=0, step=100,
            help="この工程の当日/対象期間の処理必要数（Units）"
        )
        volumes.append(v)

    submitted = st.form_submit_button("計算する")

# ===== 計算ロジック =====
def calc_rows(df: pd.DataFrame, vols, safety_factor: float):
    df = df.copy()
    df["volume"] = vols
    # 直LH = (量 / UPH) / 稼働率
    df["direct_lh"] = (df["volume"] / df["rate_uph"]) / df["util"]
    # 間接LH = 直LH × 間接率
    df["indirect_lh"] = df["direct_lh"] * df["indirect_pct"]
    df["need_lh"] = df["direct_lh"] + df["indirect_lh"]
    total_lh = df["need_lh"].sum() * safety_factor
    return df, total_lh

if submitted:
    df_calc, total_lh = calc_rows(df_master, volumes, default_safety)

    st.subheader("工程別 計算結果")
    df_view = df_calc[["name", "volume", "rate_uph", "util", "indirect_pct", "direct_lh", "indirect_lh", "need_lh"]].copy()
    df_view.rename(columns={
        "name":"工程",
        "volume":"処理必要数",
        "rate_uph":"UPH",
        "util":"稼働率",
        "indirect_pct":"間接率",
        "direct_lh":"直LH(h)",
        "indirect_lh":"間LH(h)",
        "need_lh":"小計LH(h)",
    }, inplace=True)
    st.dataframe(df_view.style.format({
        "処理必要数":"{:,.0f}", "UPH":"{:,.0f}", "稼働率":"{:.2f}",
        "間接率":"{:.2f}", "直LH(h)":"{:.2f}", "間LH(h)":"{:.2f}", "小計LH(h)":"{:.2f}"
    }), use_container_width=True)

    st.markdown("---")
    c1, c2 = st.columns(2)
    c1.metric(label="合計LH（安全係数込み）", value=f"{total_lh:,.2f} h")
    c2.write(f"安全係数: **{default_safety:.2f}** / 固定人員: **{fixed_heads} 人**")

    # シフト別人数
    st.subheader("シフト別 必要人数（端数切上げ + 固定人員）")
    result_rows = []
    for sh in shift_hours_list:
        heads = total_lh / sh
        heads_up = math.ceil(heads)
        final_heads = heads_up + fixed_heads
        result_rows.append({
            "シフト(h/人)": sh,
            "必要人数(切上げ前)": heads,
            "必要人数(切上げ後)": heads_up,
            "固定人員": fixed_heads,
            "合計必要人数": final_heads
        })
    df_heads = pd.DataFrame(result_rows)
    st.dataframe(df_heads.style.format({
        "必要人数(切上げ前)":"{:.2f}",
        "必要人数(切上げ後)":"{:,.0f}",
        "固定人員":"{:,.0f}",
        "合計必要人数":"{:,.0f}",
    }), use_container_width=True)

    # ログ保存（任意）
    if log_on:
        try:
            log_name = "need_lh_log.csv"
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            row = {
                "date": now,
                "total_lh": round(total_lh, 2),
                "safety": default_safety,
                "fixed_heads": fixed_heads
            }
            for sh in shift_hours_list:
                row[f"heads_{str(sh).replace('.','_')}h"] = math.ceil(total_lh / sh) + fixed_heads
            pd.DataFrame([row]).to_csv(log_name, mode="a", index=False, header=not pd.io.common.file_exists(log_name), encoding="utf-8-sig")
            st.success(f"ログを {log_name} に追記しました。")
        except Exception as e:
            st.info(f"ログ保存はスキップしました（理由: {e}）")

else:
    st.info("サイドバーで master.csv を用意し、処理必要数を入れて「計算する」を押してください。")
