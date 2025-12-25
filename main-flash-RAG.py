import streamlit as st
from google import genai 
from gradio_client import Client
import os
import pandas as pd
import io
import re
from datetime import datetime
from dotenv import load_dotenv
from streamlit_gsheets import GSheetsConnection  # <--- 確保這行有加

# ==========================================
# 1. 環境設定與安全金鑰讀取
# ==========================================
load_dotenv()

def get_api_key():
    try:
        if "GOOGLE_API_KEY" in st.secrets:
            return st.secrets["GOOGLE_API_KEY"]
    except:
        pass
    return os.getenv("GOOGLE_API_KEY")

GOOGLE_API_KEY = get_api_key()

# --- 初始化 Google Sheets 連線 ---
# 確保這一行在 get_api_key 之後，且有加上 type=GSheetsConnection
conn = st.connection("gsheets", type=GSheetsConnection) 

st.set_page_config(page_title="太魯閣族語AI翻譯平臺", layout="wide")

# ==========================================
# 1. 環境設定與安全金鑰讀取
# ==========================================
load_dotenv()

def get_api_key():
    # 優先嘗試讀取 Streamlit Secrets
    try:
        if hasattr(st, "secrets") and "GOOGLE_API_KEY" in st.secrets:
            return st.secrets["GOOGLE_API_KEY"]
    except Exception:
        pass
    
    # 次要嘗試環境變數 (本地測試用)
    return os.getenv("GOOGLE_API_KEY")

GOOGLE_API_KEY = get_api_key()

st.set_page_config(page_title="太魯閣族語AI翻譯平臺", layout="wide")

# ==========================================
# 2. CSS 視覺定義 (包含 1.3rem 字體與 [1,3,3,3,1] 比例)
# ==========================================
# --- 1. 視覺強化與 CSS 定義 (已整合大按鈕樣式) ---
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; font-family: 'Microsoft JhengHei', sans-serif; }
    
/* --- 1. 恢復翻譯對話框顏色 (您打勾的部分) --- */
.result-text {
    font-family: 'Times New Roman', serif !important;
    font-size: 1.4rem !important;
    line-height: 1.4;
    padding: 18px; 
    border-radius: 12px; 
    min-height: 70px; 
    margin-bottom: 5px !important; 
    box-shadow: 0 4px 15px rgba(0,0,0,0.3);
}

/* 參考翻譯一：綠色對話框 */
.mt-box { 
    border: 2px solid #2e7d32 !important; 
    background-color: #1b2e1b !important; 
    color: #e8f5e9 !important; 
}

/* 參考翻譯二：藍色對話框 */
.gemini-box { 
    border: 2px solid #1565c0 !important; 
    background-color: #1a237e !important; 
    color: #e3f2fd !important; 
}

/* --- 2. 徹底移除評分按鈕的顏色與邊框 --- */
div[data-testid="column"] .stButton button {
    background-color: transparent !important; /* 移除背景顏色 */
    border: none !important;                 /* 移除邊框 */
    box-shadow: none !important;             /* 移除陰影 */
    color: #888888 !important;               /* 平時使用低調灰色 */
    font-size: 0.85rem !important;
    padding: 0px !important;
    min-height: 24px !important;
    height: 24px !important;
    transition: 0.2s;
}

/* 評分按鈕懸停：滑鼠移上去才顯示顏色提示 */
div[data-testid="column"] .stButton button:hover {
    color: #ffffff !important;               /* 移上去變白色亮起 */
    background-color: rgba(255,255,255,0.1) !important; /* 極微量的背景感 */
}

/* --- 3. 提交建議按鈕：維持簡單線條 --- */
button[key*="send_"] {
    background-color: #333333 !important;
    color: white !important;
    border-radius: 5px !important;
    margin-top: 10px !important;
    width: 100% !important;
}

/* 下方小按鈕：極致縮小與微調 */
div[data-testid="column"] .stButton button {
    min-height: 16px !important; 
    height: 14px !important;    /* 框框高度調小 */
    padding: 0px 3px !important; /* 左右內邊距調小 */
    font-size: 0.7rem !important; /* 字體微調小 */
    line-height: 1 !important;
    border-width: 1px !important;
    border-style: solid !important;
    background-color: #1a1c23 !important;
    transition: all 0.2s ease !important;
    border-radius: 4px !important; /* 圓角也微縮，看起來更俐落 */
}

/* 1. 淺綠色 (優質) */
button[key*="mt1_"], button[key*="g1_"] {
    border-color: #a5d6a7 !important;
    color: #a5d6a7 !important;
}

/* 2. 淺黃色 (普通) */
button[key*="mt2_"], button[key*="g2_"] {
    border-color: #fff59d !important;
    color: #fff59d !important;
}

/* 3. 淺紅色 (不佳) */
button[key*="mt3_"], button[key*="g3_"] {
    border-color: #ef9a9a !important;
    color: #ef9a9a !important;
           } 

/* 4. 提交建議資料按鈕 (專屬藍色，稍微大一點方便點擊) */
button[key*="send_"] {
    background-color: #1565c0 !important;
    color: white !important;
    border: none !important;
    height: 24px !important; 
    font-size: 0.9rem !important;
    margin-top: 10px !important;
    width: 100% !important;
}
    
    .privacy-box { padding: 15px; border-radius: 8px; background-color: #262730; border-left: 5px solid #ff4b4b; margin-top: 20px; font-size: 0.9rem; color: #d1d1d1; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 3. RAG 核心與輔助函數
# ==========================================
# --- 2. RAG 核心：語料庫讀取與索引建立 ---

def dehydrate(text):
    if not text: return ""
    res = re.sub(r'[^\w\u4e00-\u9fa5]', '', str(text))
    res = re.sub(r'\s+', '', res)
    return res.lower()

# 強化讀取邏輯：增加詳細報錯與狀態標籤
if 'corpus_data' not in st.session_state or st.session_state.corpus_data is None:
    if os.path.exists("corpus.xlsx"):
        try:
            # 指定引擎為 openpyxl 確保相容性
            df = pd.read_excel("corpus.xlsx", engine='openpyxl')
            
            # 確保欄位名稱存在，避免 iloc 造成的混淆
            df['zh_dry'] = df.iloc[:, 0].astype(str).apply(dehydrate)
            df['trv_dry'] = df.iloc[:, 1].astype(str).apply(dehydrate)
            
            st.session_state.corpus_data = df
        except Exception as e:
            st.sidebar.error(f"❌ Excel 讀取錯誤: {str(e)}")
            st.session_state.corpus_data = None
    else:
        st.sidebar.warning("⚠️ 找不到 corpus.xlsx 檔案")
        st.session_state.corpus_data = None

def get_rag_context(query_text):
    """檢索邏輯"""
    if st.session_state.corpus_data is None or st.session_state.corpus_data.empty:
        return ""
    
    df = st.session_state.corpus_data
    keywords = re.findall(r'[\u4e00-\u9fa5]+|[a-zA-Z0-9]+', query_text)
    
    # 增加篩選邏輯：確保關鍵字不為空
    if not keywords: return ""
    
    mask = df.iloc[:, 0].astype(str).apply(lambda x: any(k in x for k in keywords))
    related = df[mask].head(3)
    
    context = "\n【參考範例】：\n"
    for _, row in related.iterrows():
        context += f"原文：{row[0]} -> 族語：{row[1]}\n"
    return context

# ==========================================
# 4. 引擎與 Session 狀態初始化
# ==========================================
@st.cache_resource
def init_engines():
    try:
        mt = Client("ithuan/formosan-translation")
        mt.timeout = 90
    except: mt = None
    gemini = genai.Client(api_key=GOOGLE_API_KEY) if GOOGLE_API_KEY else None
    return mt, gemini

MT_CLIENT, GEMINI_CLIENT = init_engines()

if 'translation_history' not in st.session_state: st.session_state.translation_history = []
if 'translation_cache' not in st.session_state: st.session_state.translation_cache = {}
if 'current_idx' not in st.session_state: st.session_state.current_idx = None
if 'last_api_mode' not in st.session_state: st.session_state.last_api_mode = None

def update_score(idx, target, score_val):
    field = "參考一評分" if target == 1 else "參考二評分"
    st.session_state.translation_history[idx][field] = score_val
    st.toast(f"已記錄評價：{score_val}")

# ==========================================
# 5. 主介面：側邊欄社群功能
# ==========================================
st.title("🏔️ 太魯閣族語AI翻譯平臺")

with st.sidebar:
    st.header("📈 社群貢獻看板")
    try:
        # 從雲端試算表讀取所有已有的建議
        existing_data = conn.read(ttl=0) # ttl=0 確保每次都讀取最新資料
        total_suggestions = len(existing_data)
    except:
        total_suggestions = 0
        
    st.metric(label="全社群累計建議數", value=total_suggestions)
    st.caption("這是一個永久累計的數字，感謝您的寶貴！")
    
    st.divider()
    st.header("📋 歷史管理")
    if st.session_state.translation_history:
        df_h = pd.DataFrame(st.session_state.translation_history)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer: df_h.to_excel(writer, index=False)
        st.download_button(label="📥 下載翻譯記錄 (.xlsx)", data=buffer.getvalue(), 
                           file_name=f"History_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx", use_container_width=True)
    if st.button("🧹清除所有記錄", use_container_width=True):
        st.session_state.translation_history, st.session_state.translation_cache, st.session_state.current_idx = [], {}, None
        st.rerun()

choice = st.radio("翻譯方向：", ["華語 ⮕ 太魯閣語", "太魯閣語 ⮕ 華語"], horizontal=True)
current_mode = "zh_to_truku" if "華語" in choice[:2] else "truku_to_zh"
user_input = st.text_area("請輸入文字", height=150, key=choice)

# ==========================================
# 6. 同步翻譯執行邏輯 (雙模型 + RAG)
# ==========================================
# 在您的翻譯執行邏輯處修改這一行：
if st.button("🚀 啟動翻譯對照", use_container_width=True, type="secondary"):
    # ... 原本的翻譯邏輯 ...
    if user_input:
        u_text = user_input.strip()
        dry_text = dehydrate(u_text)
        cache_key = f"{current_mode}_{dry_text}"
        
        if cache_key in st.session_state.translation_cache:
            for i, record in enumerate(st.session_state.translation_history):
                if dehydrate(record["原文"]) == dry_text:
                    st.session_state.current_idx = i
                    break
        else:
            with st.spinner("雙模型翻譯與 RAG 檢索中..."):
                # A. 處理 Gemini 與 RAG 精準匹配
                res_gemini, gemini_source, match_success = "", "AI 專家系統", False
                if st.session_state.corpus_data is not None:
                    df = st.session_state.corpus_data
                    dry_col = 'zh_dry' if current_mode == "zh_to_truku" else 'trv_dry'
                    target_idx = 1 if current_mode == "zh_to_truku" else 0
                    if dry_text in df[dry_col].values:
                        res_gemini = str(df[df[dry_col] == dry_text].iloc[0, target_idx])
                        match_success = True
                
                if not match_success:
# 強化後的 RAG 專家提示詞
                    rag_ctx = get_rag_context(u_text)

                    prompt = f"""
你現在是太魯閣語(Truku)翻譯權威。請嚴格遵守以下翻譯範例與定義。
如果範例中的詞彙定義與你的常識衝突，請以『參考範例』為準。

                        {rag_ctx}

任務：將以下內容準確翻譯為太魯閣語或華語。
輸出要求：僅回傳翻譯結果文字，嚴禁任何解釋或標籤。

待翻譯內容：              {u_text}
翻譯結果：
"""
                    try:
                        resp = GEMINI_CLIENT.models.generate_content(model="gemini-3-flash-preview", contents=prompt)
                        res_gemini = resp.text.strip()
                    except: res_gemini = "Gemini 服務繁忙"

                # B. 處理意傳 MT
                try:
                    if MT_CLIENT:
                        if st.session_state.last_api_mode != current_mode:
                            MT_CLIENT.predict(ethnicity="太魯閣", api_name="/lambda_1" if current_mode == "zh_to_truku" else "/lambda")
                            st.session_state.last_api_mode = current_mode
                        res_mt = MT_CLIENT.predict(u_text, "zho_Hant", "trv_Truk", api_name="/translate_1" if current_mode == "zh_to_truku" else "/translate")
                    else: res_mt = "未連線"
                except: res_mt = "伺服器忙碌"

                st.session_state.translation_history.append({
                    "時間": datetime.now().strftime("%H:%M:%S"), "原文": u_text, 
                    "參考一結果": res_mt, "參考一評分": "", "參考一建議": "",
                    "參考二結果": res_gemini, "參考二來源": gemini_source, "參考二評分": "", "參考二建議": ""
                })
                st.session_state.translation_cache[cache_key] = {'mt': res_mt, 'gemini': res_gemini}
                st.session_state.current_idx = len(st.session_state.translation_history) - 1

# ==========================================
# 7. 持久渲染區：結果顯示與回饋建議 (絕對完整)
# ==========================================
  # --- 5. 持久渲染區：修正後的點擊流程 ---
if st.session_state.current_idx is not None:
    idx = st.session_state.current_idx
    data = st.session_state.translation_history[idx]
    
    col_l, col_r = st.columns(2)
    
    # --- 左側：參考翻譯一 ---
    with col_l:
        st.markdown("### 🏗️ 參考翻譯一")
        st.markdown(f'<div class="result-text mt-box">{data["參考一結果"]}</div>', unsafe_allow_html=True)
        
        # 使用者點擊按鈕後，僅更新評分狀態，不直接完成整個紀錄
        b1, b2, b3, b4, b5 = st.columns([1, 3, 3, 3, 1])
        with b2: 
            if st.button("👍 優質", key=f"mt1_{idx}"):
                st.session_state.translation_history[idx]["參考一評分"] = "優質"
                st.rerun()
        with b3: 
            if st.button("😐 普通", key=f"mt2_{idx}"):
                st.session_state.translation_history[idx]["參考一評分"] = "普通"
                st.rerun()
        with b4: 
            if st.button("❌ 不佳", key=f"mt3_{idx}"):
                st.session_state.translation_history[idx]["參考一評分"] = "不佳"
                st.rerun()

        # 核心邏輯：當評分為普通或不佳，且「尚未送出建議」時，顯示輸入框
if data["參考一評分"] in ["普通", "不佳"]:
            if not st.session_state.get(f"submitted_mt_{idx}", False):
                s_mt = st.text_input("💡 請輸入建議的正確翻譯：", key=f"in_mt_{idx}")
                if s_mt:
                    if st.button("提交建議資料", key=f"send_mt_{idx}"):
                        # 這裡的 try 必須與上面的代碼保持 4 個空格的對應縮進
                        try:
                            existing_data = conn.read(ttl=0)
                            new_row = pd.DataFrame([{
                                "時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "原文": data["原文"],
                                "參考一結果": data["參考一結果"],
                                "參考一評分": data["參考一評分"],
                                "參考一建議": s_mt,
                                "參考二結果": data["參考二結果"],
                                "參考二評分": data.get("參考二評分", ""),
                                "參考二建議": data.get("參考二建議", "")
                            }])
                            updated_df = pd.concat([existing_data, new_row], ignore_index=True)
                            conn.update(data=updated_df)
                        except Exception as e:
                            st.error(f"雲端寫入失敗: {e}")

                        st.session_state.translation_history[idx]["參考一建議"] = s_mt
                        st.session_state[f"submitted_mt_{idx}"] = True
                        st.toast("✅ 建議一已同步至雲端！")
                        st.rerun()
            else:
                st.markdown('<p style="color: #4caf50; font-weight: bold;">✅ 謝謝您的建議！已成功存入記錄。</p>', unsafe_allow_html=True)

    # --- 右側：參考翻譯二 ---
with col_r:
        st.markdown("### ✨ 參考翻譯二")
        st.markdown(f'<div class="result-text gemini-box">{data["參考二結果"]}</div>', unsafe_allow_html=True)
        
        g1, g2, g3, g4, g5 = st.columns([1, 3, 3, 3, 1])
        with g2:
            if st.button("👍 優質", key=f"g1_{idx}"):
                st.session_state.translation_history[idx]["參考二評分"] = "優質"
                st.rerun()
        with g3:
            if st.button("😐 普通", key=f"g2_{idx}"):
                st.session_state.translation_history[idx]["參考二評分"] = "普通"
                st.rerun()
        with g4:
            if st.button("❌ 不佳", key=f"g3_{idx}"):
                st.session_state.translation_history[idx]["參考二評分"] = "不佳"
                st.rerun()

if data["參考二評分"] in ["普通", "不佳"]:
            if not st.session_state.get(f"submitted_gm_{idx}", False):
                s_gm = st.text_input("💡 請輸入建議的正確翻譯：", key=f"in_gm_{idx}")
                if s_gm:
                    if st.button("提交建議資料", key=f"send_gm_{idx}"):
                        try:
                            existing_data = conn.read(ttl=0)
                            new_row = pd.DataFrame([{
                                "時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "原文": data["原文"],
                                "參考一結果": data["參考一結果"],
                                "參考一評分": data.get("參考一評分", ""),
                                "參考一建議": data.get("參考一建議", ""),
                                "參考二結果": data["參考二結果"],
                                "參考二評分": data["參考二評分"],
                                "參考二建議": s_gm
                            }])
                            updated_df = pd.concat([existing_data, new_row], ignore_index=True)
                            conn.update(data=updated_df)
                        except Exception as e:
                            st.error(f"雲端寫入失敗: {e}")

                        st.session_state.translation_history[idx]["參考二建議"] = s_gm
                        st.session_state[f"submitted_gm_{idx}"] = True
                        st.toast("✅ 建議二已同步至雲端！")
                        st.rerun()
            else:
                st.markdown('<p style="color: #4caf50; font-weight: bold;">✅ 謝謝您的寶貴建議！已成功記錄。</p>', unsafe_allow_html=True)
# ==========================================
# 8. 隱私聲明宣告 (底部)
# ==========================================
st.markdown("""
    <div class="privacy-box">
        <b>📢 隱私聲明：</b> 您的翻譯請求與回饋將被記錄，僅用於太魯閣語復振與 RAG 系統提升，不會洩漏個人隱私。
    </div>

""", unsafe_allow_html=True)















