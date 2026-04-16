import streamlit as st
from google import genai 
from gradio_client import Client
import os
import pandas as pd
import io
import re
from datetime import datetime
from dotenv import load_dotenv
from streamlit_gsheets import GSheetsConnection 

# ==========================================
# 1. 環境設定與安全金鑰讀取 (絕對要放在第一行)
# ==========================================
st.set_page_config(page_title="太魯閣族語AI翻譯平臺", layout="wide")
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

# --- 初始化 Google Sheets 連線 ---
conn = st.connection("gsheets", type=GSheetsConnection) 

# ==========================================
# 2. CSS 視覺定義 
# ==========================================
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; font-family: 'Microsoft JhengHei', sans-serif; }
    
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
    .mt-box { border: 2px solid #2e7d32 !important; background-color: #1b2e1b !important; color: #e8f5e9 !important; }
    .gemini-box { border: 2px solid #1565c0 !important; background-color: #1a237e !important; color: #e3f2fd !important; }

    div[data-testid="column"] .stButton button {
        background-color: transparent !important; 
        border: none !important;                  
        box-shadow: none !important;              
        color: #888888 !important;                
        font-size: 0.85rem !important;
        padding: 0px !important;
        min-height: 24px !important;
        height: 24px !important;
        transition: 0.2s;
    }
    div[data-testid="column"] .stButton button:hover {
        color: #ffffff !important;                
        background-color: rgba(255,255,255,0.1) !important; 
    }
    button[key*="send_"] {
        background-color: #1565c0 !important;
        color: white !important;
        border: none !important;
        height: 24px !important; 
        font-size: 0.9rem !important;
        margin-top: 10px !important;
        width: 100% !important;
    }
    div[data-testid="column"] .stButton button {
        min-height: 16px !important; 
        height: 14px !important;    
        padding: 0px 3px !important; 
        font-size: 0.7rem !important; 
        line-height: 1 !important;
        border-width: 1px !important;
        border-style: solid !important;
        background-color: #1a1c23 !important;
        transition: all 0.2s ease !important;
        border-radius: 4px !important; 
    }
    button[key*="mt1_"], button[key*="g1_"] { border-color: #a5d6a7 !important; color: #a5d6a7 !important; }
    button[key*="mt2_"], button[key*="g2_"] { border-color: #fff59d !important; color: #fff59d !important; }
    button[key*="mt3_"], button[key*="g3_"] { border-color: #ef9a9a !important; color: #ef9a9a !important; }
    .privacy-box { padding: 15px; border-radius: 8px; background-color: #262730; border-left: 5px solid #ff4b4b; margin-top: 20px; font-size: 0.9rem; color: #d1d1d1; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 3. 側邊欄與雲端統計
# ==========================================
total_suggestions = 0
try:
    # 抓取雲端資料夾計算總筆數
    existing_data = conn.read(ttl="5s") 
    if existing_data is not None:
        total_suggestions = len(existing_data)
except Exception as e:
    pass # 錯誤時保持為 0

with st.sidebar:
    st.header("📈 社群貢獻看板")
    st.markdown(f"""
        <div style="background-color: #1e1e1e; padding: 15px; border-radius: 10px; border: 1px solid #333;">
            <p style="margin:0; color: #888; font-size: 0.9rem;">📊 社群累積貢獻</p>
            <h2 style="margin:0; color: #ffbd45;">{total_suggestions} <span style="font-size: 1rem;">筆建議</span></h2>
        </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    st.header("📋 歷史管理")
    if 'translation_history' in st.session_state and st.session_state.translation_history:
        df_h = pd.DataFrame(st.session_state.translation_history)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer: df_h.to_excel(writer, index=False)
        st.download_button(label="📥 下載翻譯記錄 (.xlsx)", data=buffer.getvalue(), 
                           file_name=f"History_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx", use_container_width=True)
    if st.button("🧹清除所有記錄", use_container_width=True):
        st.session_state.translation_history, st.session_state.translation_cache, st.session_state.current_idx = [], {}, None
        st.rerun()

# ==========================================
# 4. RAG 核心與輔助函數
# ==========================================
def dehydrate(text):
    if not text: return ""
    res = re.sub(r'[^\w\u4e00-\u9fa5]', '', str(text))
    res = re.sub(r'\s+', '', res)
    return res.lower()

if 'corpus_data' not in st.session_state or st.session_state.corpus_data is None:
    if os.path.exists("corpus.xlsx"):
        try:
            df = pd.read_excel("corpus.xlsx", engine='openpyxl')
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
    if st.session_state.corpus_data is None or st.session_state.corpus_data.empty:
        return ""
    
    df = st.session_state.corpus_data
    keywords = re.findall(r'[\u4e00-\u9fa5]+|[a-zA-Z0-9]+', query_text)
    if not keywords: return ""
    
    mask = df.iloc[:, 0].astype(str).apply(lambda x: any(k in x for k in keywords))
    related = df[mask].head(3)
    
    context = "\n【參考範例】：\n"
    for _, row in related.iterrows():
        # 已修正 KeyError: 改用 iloc 抓取位置
        context += f"原文：{row.iloc[0]} -> 族語：{row.iloc[1]}\n"
    return context

@st.cache_resource
def init_engines():
    try:
        # 🔑 修正：指向原語會最新的官方主機
        mt = Client("https://ai-labs.ilrdf.org.tw/kari-seejiq-tnpusu-ai-hmjil/")
    except: 
        mt = None
    gemini = genai.Clien

MT_CLIENT, GEMINI_CLIENT = init_engines()

if 'translation_history' not in st.session_state: st.session_state.translation_history = []
if 'translation_cache' not in st.session_state: st.session_state.translation_cache = {}
if 'current_idx' not in st.session_state: st.session_state.current_idx = None
if 'last_api_mode' not in st.session_state: st.session_state.last_api_mode = None

# ==========================================
# 5. 主介面與翻譯執行邏輯
# ==========================================
st.title("🏔️ 太魯閣族語AI翻譯平臺")

choice = st.radio("翻譯方向：", ["華語 ⮕ 太魯閣語", "太魯閣語 ⮕ 華語"], horizontal=True)
current_mode = "zh_to_truku" if "華語" in choice[:2] else "truku_to_zh"
user_input = st.text_area("請輸入文字", height=150, key="main_input")

if st.button("🚀 啟動翻譯對照", use_container_width=True, type="secondary"):
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
                    except Exception as e:
                        # 💡 這一行是關鍵！我們強制把錯誤訊息印在網頁上，不讓 Streamlit 遮蔽
                        st.error(f"🚨 Gemini 發生錯誤，詳細原因：{str(e)}") 
                        res_gemini = "API 錯誤，請看上方紅框"

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
# 6. 持久渲染區：結果顯示與回饋建議
# ==========================================
if st.session_state.current_idx is not None:
    idx = st.session_state.current_idx
    data = st.session_state.translation_history[idx]
    
    col_l, col_r = st.columns(2)
    
    # --- 左側：參考翻譯一 (MT) ---
    with col_l:
        st.markdown("### 🏗️ 參考翻譯一")
        st.markdown(f'<div class="result-text mt-box">{data["參考一結果"]}</div>', unsafe_allow_html=True)
        
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

        if st.session_state.translation_history[idx].get("參考一評分") in ["普通", "不佳"]:
            if not st.session_state.get(f"submitted_mt_{idx}", False):
                s_mt = st.text_input("💡 請輸入建議的正確翻譯：", key=f"in_mt_{idx}")
                if s_mt:
                    if st.button("提交建議資料", key=f"send_mt_{idx}"):
                        try:
                            # 讀取最新表格避免覆寫
                            existing_df = conn.read(ttl=0)
                            new_row = pd.DataFrame([{
                                "時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "原文": data["原文"],
                                "參考一結果": data["參考一結果"], "參考一評分": st.session_state.translation_history[idx]["參考一評分"], "參考一建議": s_mt,
                                "參考二結果": data["參考二結果"], "參考二評分": st.session_state.translation_history[idx].get("參考二評分", ""), "參考二建議": ""
                            }])
                            updated_df = pd.concat([existing_df, new_row], ignore_index=True)
                            conn.update(data=updated_df)
                            
                            st.session_state.translation_history[idx]["參考一建議"] = s_mt
                            st.session_state[f"submitted_mt_{idx}"] = True
                            st.toast("✅ 建議已記錄並同步至雲端")
                            st.rerun()
                        except Exception as e:
                            st.error(f"同步出錯：{e}")
            else:
                st.markdown('<p style="color: #4caf50; font-weight: bold;">✅ 謝謝您的建議！已成功存入記錄。</p>', unsafe_allow_html=True)

    # --- 右側：參考翻譯二 (Gemini) ---
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

        if st.session_state.translation_history[idx].get("參考二評分") in ["普通", "不佳"]:
            if not st.session_state.get(f"submitted_gm_{idx}", False):
                s_gm = st.text_input("💡 請輸入建議的正確翻譯：", key=f"in_gm_{idx}")
                if s_gm:
                    if st.button("提交建議資料", key=f"send_gm_{idx}"):
                        try:
                            # 讀取最新表格避免覆寫
                            existing_df = conn.read(ttl=0)
                            new_row = pd.DataFrame([{
                                "時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "原文": data["原文"],
                                "參考一結果": data["參考一結果"], "參考一評分": st.session_state.translation_history[idx].get("參考一評分", ""), "參考一建議": st.session_state.translation_history[idx].get("參考一建議", ""),
                                "參考二結果": data["參考二結果"], "參考二評分": st.session_state.translation_history[idx]["參考二評分"], "參考二建議": s_gm
                            }])
                            updated_df = pd.concat([existing_df, new_row], ignore_index=True)
                            conn.update(data=updated_df)
                            
                            st.session_state.translation_history[idx]["參考二建議"] = s_gm
                            st.session_state[f"submitted_gm_{idx}"] = True
                            st.toast("✅ 建議已記錄並同步至雲端")
                            st.rerun()
                        except Exception as e:
                            st.error(f"同步出錯：{type(e).__name__} - {str(e)}")
            else:
                st.markdown('<p style="color: #4caf50; font-weight: bold;">✅ 謝謝您的寶貴建議！已成功記錄 Mhuway su balay!</p>', unsafe_allow_html=True)
