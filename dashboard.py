import os, sqlite3, time
import streamlit as st
from rapidfuzz import fuzz
from googleapiclient.discovery import build
from google.oauth2 import service_account

DB_PATH = os.getenv("DB_PATH", "drive_telebot.db")
st.set_page_config(page_title="Drive ↔ Telegram Bot • Dashboard", layout="wide")

def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def get_counts():
    with conn() as c:
        n_alias = c.execute("SELECT COUNT(*) FROM alias").fetchone()[0]
        n_cache = c.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        n_cached_tg = c.execute("SELECT COUNT(*) FROM cache WHERE tg_file_id IS NOT NULL").fetchone()[0]
    return n_alias, n_cache, n_cached_tg

def table_alias():
    with conn() as c:
        rows = c.execute("""
            SELECT a.code, a.drive_id, IFNULL(cache.name,'?') AS name, cache.tg_file_id
            FROM alias a LEFT JOIN cache ON a.drive_id = cache.drive_id
            ORDER BY a.code
        """).fetchall()
    return rows

def table_cache():
    with conn() as c:
        rows = c.execute("""
            SELECT drive_id, name, size, modified, 
                   CASE WHEN tg_file_id IS NULL THEN 'no' ELSE 'yes' END AS cached
            FROM cache ORDER BY name
        """).fetchall()
    return rows

def local_search(term):
    with conn() as c:
        rows = c.execute("SELECT drive_id, name FROM cache").fetchall()
    scored = [(fuzz.WRatio(term, r["name"]), r["drive_id"], r["name"]) for r in rows]
    scored.sort(reverse=True)
    return scored[:10]

def build_drive():
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not cred_path:
        return None
    creds = service_account.Credentials.from_service_account_file(
        cred_path, scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build("drive", "v3", credentials=creds)

def drive_query(term, page_size=10):
    drv = build_drive()
    if drv is None:
        return []
    # Corrigido: evita erro de aspas no f-string
    safe_term = (term or "").replace("'", " ")
    q = f"name contains '{safe_term}' and mimeType='application/pdf' and trashed=false"
    res = drv.files().list(
        q=q,
        fields="files(id,name,webViewLink,webContentLink,modifiedTime,size)",
        pageSize=page_size,
        orderBy="modifiedTime desc"
    ).execute()
    return res.get("files", [])

# ---- INTERFACE ----
st.title("📄 Drive → 🤖 Telegram • Dashboard")

col1, col2, col3 = st.columns(3)
n_alias, n_cache, n_cached_tg = get_counts()
col1.metric("Aliases", n_alias)
col2.metric("Cache (arquivos)", n_cache)
col3.metric("Instantâneos (tg_file_id)", n_cached_tg)

st.divider()

st.subheader("🔎 Testar busca")
term = st.text_input("Digite um termo (nome ou parte do nome):")
opt_col1, opt_col2 = st.columns(2)
with opt_col1:
    use_drive = st.checkbox("Buscar também no Google Drive", value=True)
with opt_col2:
    st.caption("Desmarque se quiser testar apenas o cache local.")

if term:
    left, right = st.columns(2)
    with left:
        st.write("**Resultados no cache local:**")
        for score, did, name in local_search(term):
            st.write(f"• {name} — score {score}  \n`{did}`")
    with right:
        if use_drive:
            st.write("**Resultados no Google Drive:**")
            files = drive_query(term)
            if not files:
                st.info("Nenhum resultado encontrado no Drive.")
            for f in files:
                st.write(f"• {f['name']}  \nID: `{f['id']}`  \n[Ver no Drive]({f['webViewLink']})")

st.divider()
tab1, tab2 = st.tabs(["Aliases", "Cache"])
with tab1:
    rows = table_alias()
    st.dataframe([dict(r) for r in rows], use_container_width=True)
with tab2:
    rows = table_cache()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["modified"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(d["modified"]))
        except Exception:
            pass
        out.append(d)
    st.dataframe(out, use_container_width=True)

st.caption("Use /reindex no bot para atualizar o cache local.")
