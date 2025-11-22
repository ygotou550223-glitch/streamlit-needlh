import math
from datetime import datetime
import pandas as pd
import streamlit as st

st.set_page_config(page_title="必要レイバーアワー計算", page_icon="🧮", layout="wide")
st.title("🧮 必要レイバーアワー計算（工程別入力／CSV不要モード対応）")

# ====== サイドバー：設定 ======
st.sidebar.header("設定")
master_mode = st.sidebar.radio("マスタ入力方法", ["Webで入力", "CSVアップロード"], index=0)
default_safety = st.sidebar.number_input("安全係数（1.00=上乗せ無し）", min_value=1.00, max_value=1.50, value=1.10, step=0.01)
fixed_heads = st.sidebar.number_input("固定人員（班長/QCなど）", min_value=0, max_value=50, value=2, step=1)
shift_hours_list = st.sidebar.multiselect("シフト実働（h/人）", options=[8.0, 7.5, 6.0, 4.0], default=[8.0, 7.5, 6.0, 4.0])
log_on = st.sidebar.checkbox("計算結果をCSVに追記（need_lh_log.csv）", value=True)

# ====== マスタ入力（Web or CSV） ======
def init_default_master():
    return pd.DataFrame([
        {"name": "搬入(2)",  "rate_uph": 160.0, "util": 0.85, "indirect_pct": 0.10},
        {"name": "受領(1)",  "rate_uph": 120.0, "util": 0.88, "indirect_pct": 0.05},
        {"name": "棚入れ(1)","rate_uph": 100.0, "util": 0.90, "indirect_pct": 0.05},
    ])

def clean_master(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # 必須列が無ければ補完
    for col in ["name", "rate_uph", "util", "indirect_pct"]:
        if col not in df.columns:
            df[col] = None
    # 型・欠損処理
    df["name"] = df["name"].astype(str)
    for c in ["rate_uph", "util", "indirect_pct"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # 不正値の除外
    df = df.dropna(subset=["name", "rate_uph", "util", "indirect_pct"])
    df = df[df["rate_uph"] > 0]
    df = df[(df["util"] > 0) & (df["util"] <= 1)]
    df = df[(df["indirect_pct"] >= 0) & (df["indirect_pct"] <= 1)]
    # 重複/空行の整理
    df = df[df["name"].str.strip() != ""]
    df = df.reset_index(drop=True)
    return df

if master_mode == "CSVアップロード":
    uploaded = st.sidebar.file_uploader("master.csv / .txt（列: name,rate_uph,util,indirect_pct）", type=["csv", "txt"])
    if uploaded is not None:
        df_master = clean_master(pd.read_csv(uploaded))
    else:
        st.info("CSV未指定のため、デフォルトのマスタを使用します。")
        if "master_df" not in st.session_state:
            st.session_state.master_df = init_default_master()
        df_master = st.session_state.master_df.copy()
else:
    # Web入力（データエディタ）
    if "master_df" not in st.session_state:
        st.session_state.master_df = init_default_master()

    st.subheader("工程マスタ（Webで直接編集）")
    st.caption("列の意味：name=工程名 / rate_uph=UPH(1人1時間の処理数) / util=稼働率0-1 / indirect_pct=間接率0-1")
    df_edit = st.data_editor(
        st.session_state.master_df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "name": st.column_config.TextColumn("工程名", width="medium", required=True),
            "rate_uph": st.column_config.NumberColumn("UPH", min_value=1.0, step=1.0, required=True),
            "util": st.column_config.NumberColumn("稼働率", min_value=0.01, max_value=1.0, step=0.01, required=True),
            "indirect_pct": st.column_config.NumberColumn("間接率", min_value=0.0, max_value=1.0, step=0.01, required=True),
        },
        key="master_editor",
    )
    # クリーン＆確定
    df_master = clean_master(df_edit)
    st.session_state.master_df = df_master.copy()

    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button(
            "このマスタをCSVとしてダウンロード",
            data=df_master.to_csv(index=False).encode("utf-8-sig"),
            file_name="master.csv",
            mime="text/csv"
        )
    with c2:
        if st.button("アプリ内に master.csv として保存（実行環境ローカル）"):
            try:
                df_master.to_csv("master.csv", index=False, encoding="utf-8-sig")
                st.success("master.csv を保存しました。")
            except Exception as e:
                st.info(f"保存はスキップしました（理由: {e}）")
    with c3:
        st.write("")  # レイアウト調整

# ====== 入力フォーム（工程別 処理必要数） ======
with st.form("vol_input"):
    st.subheader("工程別の処理必要数（Units）を入力")
    if df_master.empty:
        st.warning("有効な工程マスタがありません。工程行を追加・修正してください。")
    volumes = []
    cols = st.columns([2,1,1,1,1])
    cols[0].markdown("**工程名**")
    cols[1].markdown("**UPH**")
    cols[2].markdown("**稼働率**")
    cols[3].markdown("**間接率**")
    cols[4].markdown("**処理必要数**")

    for i, row in df_master.iterrows():
        c = st.columns([2,1,1,1,1])
        c[0].write(row["name"])
        c[1].write(f'{row["rate_uph"]:.0f}')
        c[2].write(f'{row["util"]:.2f}')
        c[3].write(f'{row["indirect_pct"]:.2f}')
        v = c[4].number_input(" ", key=f"vol_{i}", min_value=0, value=0, step=100)
        volumes.append(v)

    submitted = st.form_submit_button("計算する")

# ====== 計算ロジック ======
def calc_rows(df: pd.DataFrame, vols, safety_factor: float):
    df = df.copy()
    df["volume"] = vols
    df["direct_lh"] = (df["volume"] / df["rate_uph"]) / df["util"]
    df["indirect_lh"] = df["direct_lh"] * df["indirect_pct"]
    df["need_lh"] = df["direct_lh"] + df["indirect_lh"]
    total_lh = df["need_lh"].sum() * safety_factor
    return df, total_lh

if submitted:
    if df_master.empty:
        st.error("工程マスタが空です。Web編集 or CSVで行を用意してください。")
        st.stop()

    df_calc, total_lh = calc_rows(df_master, volumes, default_safety)

    st.subheader("工程別 計算結果")
    df_view = df_calc[["name","volume","rate_uph","util","indirect_pct","direct_lh","indirect_lh","need_lh"]].copy()
    df_view.rename(columns={
        "name":"工程","volume":"処理必要数","rate_uph":"UPH","util":"稼働率","indirect_pct":"間接率",
        "direct_lh":"直LH(h)","indirect_lh":"間LH(h)","need_lh":"小計LH(h)"
    }, inplace=True)
    st.dataframe(df_view.style.format({
        "処理必要数":"{:,.0f}","UPH":"{:,.0f}","稼働率":"{:.2f}","間接率":"{:.2f}",
        "直LH(h)":"{:.2f}","間LH(h)":"{:.2f}","小計LH(h)":"{:.2f}"
    }), use_container_width=True)

    st.markdown("---")
    c1, c2 = st.columns(2)
    c1.metric(label="合計LH（安全係数込み）", value=f"{total_lh:,.2f} h")
    c2.write(f"安全係数: **{default_safety:.2f}** / 固定人員: **{fixed_heads} 人**")

    st.subheader("シフト別 必要人数（端数切上げ + 固定人員）")
    rows = []
    for sh in shift_hours_list:
        heads_raw = total_lh / sh
        heads_up = math.ceil(heads_raw)
        final_heads = heads_up + fixed_heads
        rows.append({
            "シフト(h/人)": sh,
            "必要人数(切上げ前)": heads_raw,
            "必要人数(切上げ後)": heads_up,
            "固定人員": fixed_heads,
            "合計必要人数": final_heads
        })
    st.dataframe(pd.DataFrame(rows).style.format({
        "必要人数(切上げ前)":"{:.2f}","必要人数(切上げ後)":"{:,.0f}","固定人員":"{:,.0f}","合計必要人数":"{:,.0f}"
    }), use_container_width=True)

    # ログ保存（任意）
    if log_on:
        try:
            log_name = "need_lh_log.csv"
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            row = {"date": now, "total_lh": round(total_lh, 2), "safety": default_safety, "fixed_heads": fixed_heads}
            for sh in shift_hours_list:
                row[f"heads_{str(sh).replace('.','_')}h"] = math.ceil(total_lh / sh) + fixed_heads
            pd.DataFrame([row]).to_csv(log_name, mode="a", index=False,
                                       header=not pd.io.common.file_exists(log_name), encoding="utf-8-sig")
            st.success(f"ログを {log_name} に追記しました。")
        except Exception as e:
            st.info(f"ログ保存はスキップしました（理由: {e}）")
else:
    st.info("マスタを用意し、処理必要数を入れて「計算する」を押してください。")
