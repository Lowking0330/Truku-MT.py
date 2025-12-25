import streamlit as st
from google import genai 
from gradio_client import Client
import os
import time
import pandas as pd
import io
import re
from datetime import datetime
from dotenv import load_dotenv

# --- 1. 環境設定 ---
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# 初始化頁面配置
st.set_page_config(page_title="太魯閣語工作站 v13.1", layout="wide")

# CSS 視覺強化：鎖定 1.3rem 字體、美化對照框、微型按鈕與置中比例
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; font-family: 'Microsoft JhengHei', sans-serif; }
    
    /* 1. 輸入框加大 (1.3rem) */
    .stTextArea textarea {
        font-size: 1.3rem !important; 
        line-height: 1.5 !important;
        font-family: 'Times New Roman', serif !important;
        color: #ffffff !important;
        background-color: #1a1c23 !important;
    }
    
    /* 2. 結果對照框樣式：美化並強化陰影 */
    .result-text {
        font-family: 'Times New Roman', serif !important;
        font-size: 1.4rem !important;
        line-height: 1.4;
        padding: 18px; border-radius: 12px; min-height: 70px; 
        margin-bottom: 2px !important; 
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }
    .mt-box { border: 2px solid #2e7d32; background-color: #1b2e1b; color: #e8f5e9; }
    .gemini-box { border: 2px solid #1565c0; background-color: #1a237e; color: #e3f2fd; }
    
    h3 { margin-bottom: 4px !important; color: #ffffff !important; font-size: 1.1rem !important; }
    
    /* 3. 強力微型按鈕 CSS */
    div[data-testid="column"] { gap: 0.2rem !important; } 
    
    .stButton button {
        min-height: 22px !important; 
        height: 24px !important;
        padding: 0px 4px !important; 
        font-size: 0.75rem !important; 
        line-height: 1 !important;
        border-radius: 3px !important;
        width: 100% !important;
    }
    
    /* 評價標籤微縮 */
    .score-tag {
        font-size: 0.75rem !important;
        color: #ffca28;
        font-weight: bold;
        margin-top: -2px !important;
        margin-bottom: 10px !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. 輔助函數 (關鍵：不可遺漏) ---

def dehydrate(text):
    """移除所有標點與空格，達成 0.01 秒閃現匹配的核心函數"""
    if not text: return ""
    res = re.sub(r'[^\w\u4e00-\u9fa5]', '', str(text))
    res = re.sub(r'\s+', '', res)
    return res.lower()

def get_rag_context(query_text):
    """從 Excel 語料庫檢索參考範例 (RAG)"""
    if 'corpus_data' not in st.session_state or st.session_state.corpus_data is None: 
        return ""
    df = st.session_state.corpus_data
    # 提取關鍵字
    keywords = re.findall(r'[\u4e00-\u9fa5]+|[a-zA-Z0-9]+', query_text)
    # 模糊匹配搜尋
    mask = df.iloc[:, 0].astype(str).apply(lambda x: any(k in x for k in keywords))
    related = df[mask].head(3)
    context = "\n【參考範例】：\n"
    for _, row in related.iterrows(): 
        context += f"原文：{row[0]} -> 族語：{row[1]}\n"
    return context

# --- 3. 初始化引擎與資料載入 ---

@st.cache_resource
def init_mt():
    """初始化意傳 MT Client，設定 90 秒逾時解決忙碌問題"""
    try:
        mt = Client("ithuan/formosan-translation")
        mt.timeout = 90
        return mt
    except: return None

@st.cache_resource
def init_gemini():
    """初始化 Gemini API Client"""
    return genai.Client(api_key=GOOGLE_API_KEY) if GOOGLE_API_KEY else None

MT_CLIENT = init_mt()
GEMINI_CLIENT = init_gemini()
BEST_MODEL_ID = "gemini-3-flash-preview"

# 載入 Excel 語料庫並預處理脫水索引
if 'corpus_data' not in st.session_state:
    if os.path.exists("corpus.xlsx"):
        try:
            df = pd.read_excel("corpus.xlsx")
            df['zh_dry'] = df.iloc[:, 0].astype(str).apply(dehydrate)
            df['trv_dry'] = df.iloc[:, 1].astype(str).apply(dehydrate)
            st.session_state.corpus_data = df
        except: st.session_state.corpus_data = None

# 初始化所有 Session 狀態
if 'translation_history' not in st.session_state: st.session_state.translation_history = []
if 'translation_cache' not in st.session_state: st.session_state.translation_cache = {}
if 'last_api_mode' not in st.session_state: st.session_state.last_api_mode = None
if 'current_idx' not in st.session_state: st.session_state.current_idx = None

def update_score(idx, target, score_val):
    """更新翻譯評分"""
    field = "參考一評分" if target == 1 else "參考二評分"
    st.session_state.translation_history[idx][field] = score_val
    st.toast(f"已記錄評價：{score_val}")

# --- 4. 主介面設計：側邊欄與輸入區 ---

st.title("🏔️ 太魯閣語工作站 v13.1")

with st.sidebar:
    st.header("📋 歷史管理")
    # 下載歷史記錄功能
    if st.session_state.translation_history:
        df_h = pd.DataFrame(st.session_state.translation_history)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer: 
            df_h.to_excel(writer, index=False)
        st.download_button(label="📥 下載翻譯記錄 (.xlsx)", data=buffer.getvalue(), 
                           file_name=f"History_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx", use_container_width=True)
    st.divider()
    # 清除記錄功能
    if st.button("🧹 清除所有記錄", use_container_width=True):
        st.session_state.translation_history, st.session_state.translation_cache, st.session_state.current_idx = [], {}, None
        st.rerun()

choice = st.radio("翻譯方向：", ["華語 ⮕ 太魯閣語", "太魯閣語 ⮕ 華語"], horizontal=True)
current_mode = "zh_to_truku" if "華語" in choice[:2] else "truku_to_zh"
user_input = st.text_area("請輸入文字", height=100, key=choice)

# --- 5. 核心執行邏輯：同步翻譯流程 (解決伺服器忙碌) ---

if st.button("🚀 啟動翻譯對照", use_container_width=True):
    if user_input:
        u_text = user_input.strip()
        dry_text = dehydrate(u_text)
        cache_key = f"{current_mode}_{dry_text}"
        
        # 1. 檢查脫水快取匹配
        if cache_key in st.session_state.translation_cache:
            for i, record in enumerate(st.session_state.translation_history):
                if dehydrate(record["原文"]) == dry_text:
                    st.session_state.current_idx = i
                    break
        else:
            with st.spinner("雙模型同步翻譯中，請稍候（這可能需要 15-30 秒以確保伺服器穩定連線）..."):
                # A. 處理 Gemini (強化純淨輸出指令 + RAG)
                match_success, res_gemini = False, ""
                if st.session_state.corpus_data is not None:
                    df = st.session_state.corpus_data
                    dry_col = 'zh_dry' if current_mode == "zh_to_truku" else 'trv_dry'
                    target_idx = 1 if current_mode == "zh_to_truku" else 0
                    if dry_text in df[dry_col].values:
                        res_gemini = str(df[df[dry_col] == dry_text].iloc[0, target_idx])
                        match_success = True
                
                if not match_success:
                    rag_ctx = get_rag_context(u_text)
                    prompt = f"太魯閣語專家。僅輸出結果文字，嚴禁輸出範本標籤(如『原文』『族語』)。\n範例參考：{rag_ctx}\n內容：{u_text}\n結果："
                    try:
                        resp = GEMINI_CLIENT.models.generate_content(model=BEST_MODEL_ID, contents=prompt)
                        res_gemini = resp.text.strip()
                        if current_mode == "zh_to_truku" and res_gemini: 
                            res_gemini = res_gemini[0].upper() + res_gemini[1:]
                    except: 
                        res_gemini = "Gemini 服務繁忙"

                # B. 處理意傳 MT (穩定同步連線路徑)
                try:
                    if MT_CLIENT:
                        # 切換 API 模式
                        if st.session_state.last_api_mode != current_mode:
                            api_name = "/lambda_1" if current_mode == "zh_to_truku" else "/lambda"
                            MT_CLIENT.predict(ethnicity="太魯閣", api_name=api_name)
                            st.session_state.last_api_mode = current_mode
                        # 執行翻譯
                        res_mt = MT_CLIENT.predict(u_text, "zho_Hant", "trv_Truk", 
                                                   api_name="/translate_1" if current_mode == "zh_to_truku" else "/translate")
                    else: 
                        res_mt = "意傳伺服器未連線"
                except: 
                    res_mt = "意傳伺服器忙碌，請再次點擊啟動翻譯"

                # C. 同步將結果存入 Session
                st.session_state.translation_cache[cache_key] = {'mt': res_mt, 'gemini': res_gemini}
                st.session_state.translation_history.append({
                    "時間": datetime.now().strftime("%H:%M:%S"), 
                    "原文": u_text, "參考一結果": res_mt, "參考一評分": "", 
                    "參考二結果": res_gemini, "參考二評分": ""
                })
                st.session_state.current_idx = len(st.session_state.translation_history) - 1

# --- 6. 唯一穩定渲染區：[1, 3, 3, 3, 1] 置中佈局 ---

if st.session_state.current_idx is not None:
    data = st.session_state.translation_history[st.session_state.current_idx]
    idx = st.session_state.current_idx
    
    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("### 🏗️ 參考翻譯一")
        st.markdown(f'<div class="result-text mt-box">{data["參考一結果"]}</div>', unsafe_allow_html=True)
        # 採用您指定的置中比例
        b1, b2, b3, b4, b5 = st.columns([1, 3, 3, 3, 1])
        with b2: st.button("👍 優質", key=f"mt1_{idx}", on_click=update_score, args=(idx, 1, "優質"), use_container_width=True)
        with b3: st.button("😐 普通", key=f"mt2_{idx}", on_click=update_score, args=(idx, 1, "普通"), use_container_width=True)
        with b4: st.button("❌ 不佳", key=f"mt3_{idx}", on_click=update_score, args=(idx, 1, "不佳"), use_container_width=True)
        if data["參考一評分"]: 
            st.markdown(f'<p class="score-tag">評價：{data["參考一評分"]}</p>', unsafe_allow_html=True)
            # 關鍵：如果評價不是優質，顯示修正建議框
# 判斷是否顯示輸入框
        if data["參考一評分"] in ["普通", "不佳"]:
            s_mt = st.text_input("💡 建議正確翻譯是？", key=f"sug_mt_{idx}") # 使用獨一無二的 Key
            if s_mt: st.session_state.translation_history[idx]["參考一建議"] = s_mt

    with col_r:
        st.markdown("### ✨ 參考翻譯二")
        st.markdown(f'<div class="result-text gemini-box">{data["參考二結果"]}</div>', unsafe_allow_html=True)
        # 採用您指定的置中比例
        g1, g2, g3, g4, g5 = st.columns([1, 3, 3, 3, 1])
        with g2: st.button("👍 優質", key=f"g1_{idx}", on_click=update_score, args=(idx, 2, "優質"), use_container_width=True)
        with g3: st.button("😐 普通", key=f"g2_{idx}", on_click=update_score, args=(idx, 2, "普通"), use_container_width=True)
        with g4: st.button("❌ 不佳", key=f"g3_{idx}", on_click=update_score, args=(idx, 2, "不佳"), use_container_width=True)
        if data["參考二評分"]: 
            st.markdown(f'<p class="score-tag">評價：{data["參考二評分"]}</p>', unsafe_allow_html=True)
            # 關鍵：如果評價不是優質，顯示修正建議框
# 判斷是否顯示輸入框
        if data["參考二評分"] in ["普通", "不佳"]:
            s_gm = st.text_input("💡 建議正確翻譯是？", key=f"sug_gm_{idx}") # 使用獨一無二的 Key
            if s_gm: st.session_state.translation_history[idx]["參考二建議"] = s_gm