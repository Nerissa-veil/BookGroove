"""BookGroove Streamlit app: bookshelf, DNA editing, BGM generation, and player."""

import os, time, tempfile
import streamlit as st
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

from core.strings import STRINGS
if "app_lang" not in st.session_state:
    st.session_state["app_lang"] = os.getenv("APP_LANG", "en")
T = STRINGS.get(st.session_state["app_lang"], STRINGS["en"])

from core.analyzer import analyze_book_dna, generate_suite_sections
from core.bgm_workflow import check_audio_deps, generate_bgm_suite, show_bgm_error
from core.cache import (
    save_book_dna, load_book_dna,
    get_book_bgm, list_book_bgm_versions,
    save_session, list_books_with_titles, delete_book,
)
from core.book_reader import read_file_for_dna

st.set_page_config(page_title="BookGroove", page_icon="bookmark", layout="wide")

if st.session_state.get("app_lang") == "cn":
    import streamlit.components.v1 as _c
    _c.html("<script>window.parent.document.documentElement.lang='zh-CN';</script>", height=0)

try:
    from core.scene import get_scene_html
    _SCENE_OK = True
except ImportError:
    _SCENE_OK = False

st.markdown("""
<style>
  @import url("https://fonts.bunny.net/css?family=cinzel:400,600,700&display=swap");
  @import url("https://fonts.loli.net/css2?family=Noto+Serif+SC:wght@400;600;700&display=swap");
  .stApp { background-color: #1a1a2e; color: #e0d7c6; font-family: 'Microsoft YaHei', '微软雅黑', 'Noto Serif SC', 'Cinzel', 'Palatino Linotype', Georgia, sans-serif; }
  [data-testid="stHtml"] { padding: 0 !important; margin: 0 !important; width: 100% !important; }
  [data-testid="stHtml"] iframe { display: block; border: none; width: 100% !important; }
  .stComponentV1Container { width: 100% !important; padding: 0 !important; }
  .stComponentV1Container iframe { width: 100% !important; display: block; border: none; }
  [data-testid="stCustomComponentV1"] { width: 100% !important; }
  [data-testid="stCustomComponentV1"] iframe { width: 100% !important; }
  .element-container:has(iframe) { padding: 0 !important; }
  .block-container { padding-top: 0 !important; padding-left: 1rem !important; padding-right: 1rem !important; max-width: 100% !important; }
  h1, h2, h3 { color: #c9b99a; font-family: 'Cinzel', 'Palatino Linotype', Georgia, serif; letter-spacing: 0.04em; font-weight: 600; }
  label { color: #b8a888 !important; font-size: 0.78rem !important; letter-spacing: 0.06em !important; }
  .mood-card { background: #16213e; border-left: 3px solid rgba(201,185,154,0.6); padding: 16px 20px; border-radius: 8px; margin: 12px 0; }
  [data-baseweb="select"] > div { background-color: #16213e !important; border-color: rgba(201,185,154,0.3) !important; border-radius: 6px !important; }
  [data-baseweb="select"] span { color: #e0d7c6 !important; }
  [data-baseweb="option"] { background-color: #16213e !important; color: #e0d7c6 !important; }
  [data-baseweb="option"]:hover { background-color: #1e2d50 !important; }
  [data-baseweb="popover"] { background-color: #16213e !important; }
  [data-baseweb="input"] { background-color: #16213e !important; border-color: rgba(201,185,154,0.3) !important; }
  [data-baseweb="input"] input { color: #e0d7c6 !important; }
  .stButton > button {
    background: rgba(201,185,154,0.05); color: #c9b99a;
    border: 1px solid rgba(201,185,154,0.38); border-radius: 20px;
    padding: 7px 22px; font-family: 'Cinzel', Georgia, serif;
    font-size: 12px; letter-spacing: 0.1em; transition: all 0.25s ease;
  }
  .stButton > button:hover {
    background: rgba(201,185,154,0.12);
    box-shadow: 0 0 12px rgba(201,185,154,0.22);
    border-color: rgba(201,185,154,0.65); color: #e0d7c6;
  }
  .stButton > button[kind="primary"] {
    background: linear-gradient(135deg, rgba(201,185,154,0.18), rgba(201,185,154,0.07));
    border: 1px solid rgba(201,185,154,0.55); border-radius: 4px;
    color: #e0d7c6; font-size: 13px; letter-spacing: 0.14em; padding: 11px 36px;
  }
  .stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, rgba(201,185,154,0.28), rgba(201,185,154,0.14));
    box-shadow: 0 0 18px rgba(201,185,154,0.32); border-color: rgba(201,185,154,0.75);
  }
  [data-testid="stSidebar"] { background-color: #16213e !important; border-right: 1px solid rgba(201,185,154,0.12); }
  [data-testid="stSidebar"] h1,
  [data-testid="stSidebar"] h2,
  [data-testid="stSidebar"] h3 { color: #c9b99a !important; font-family: 'Cinzel', Georgia, serif !important; }
  [data-testid="stSidebar"] label { color: #b8a888 !important; }
  [data-testid="stSidebar"] p { color: #e0d7c6 !important; }
  [data-testid="stSidebar"] hr { border-color: rgba(201,185,154,0.2) !important; }
  [data-testid="stSidebar"] [data-baseweb="select"] > div { background-color: #1a1a2e !important; border-color: rgba(201,185,154,0.35) !important; }
  [data-testid="stSidebar"] [data-testid="stFileUploadDropzone"] { background-color: #1a1a2e !important; border-color: rgba(201,185,154,0.28) !important; }
  [data-testid="stSidebar"] small { color: rgba(201,185,154,0.48) !important; }
</style>
""", unsafe_allow_html=True)

st.divider()

# ---- Sidebar -------------------------------------------------------------------
with st.sidebar:
    _lang_options = {"English": "en", "中文": "cn"}
    _lang_display = [k for k,v in _lang_options.items() if v == st.session_state.get("app_lang","en")]
    _lang_sel = st.selectbox(T["lang_label"], list(_lang_options.keys()),
        index=list(_lang_options.keys()).index(_lang_display[0]), key="lang_sel")
    if _lang_options[_lang_sel] != st.session_state.get("app_lang","en"):
        st.session_state["app_lang"] = _lang_options[_lang_sel]
        st.rerun()
    T = STRINGS.get(st.session_state["app_lang"], STRINGS["en"])
    st.header(T["bookshelf"])
    _books_info = list_books_with_titles()
    _book_dir_map = {disp: d for d, disp in _books_info}
    _book_displays = [disp for _, disp in _books_info]
    selected_display = st.selectbox(T["choose_book"], [""] + _book_displays) if _books_info else ""
    selected_book = _book_dir_map.get(selected_display, "") if selected_display else ""
    if not _books_info:
        st.info(T["no_books"])

    if selected_book:
        if st.checkbox(T["remove_book"].format(book=selected_display or selected_book), key="del_check"):
            st.warning(T["remove_warning"].format(book=selected_display or selected_book))
            if st.button(T["confirm_delete"], key="del_btn"):
                delete_book(selected_book)
                st.session_state.clear()
                st.rerun()

    st.caption(T["storage_hint"])

    st.divider()
    st.header(T["upload_header"])
    uploaded = st.file_uploader(T["upload_label"], type=["epub", "pdf", "txt"])
    if uploaded and st.button(T["analyse_btn"]):
        suffix = Path(uploaded.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded.read())
            tmp_path = tmp.name
        try:
            with st.spinner(T["reading_epub"]):
                title, content = read_file_for_dna(tmp_path)
                if Path(uploaded.name).suffix.lower() == ".pdf" and len(content.strip()) < 100:
                    os.unlink(tmp_path)
                    st.error(T["err_scanned_pdf"])
                    st.stop()
            os.unlink(tmp_path)
            with st.spinner(T["analysing_dna"]):
                dna = analyze_book_dna(title, content)
            save_book_dna(title, dna)
            st.toast(T["done_ready"].format(title=title), icon="✅")
            st.rerun()
        except Exception as e:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            _msg = str(e)
            if "401" in _msg or "unauthorized" in _msg.lower() or "invalid token" in _msg.lower():
                st.error(T["err_sf_401"])
            elif "429" in _msg:
                st.error(T["err_sf_429"])
            elif "503" in _msg or "50508" in _msg or "too busy" in _msg.lower():
                st.error(T["err_sf_503"])
            elif "connect" in _msg.lower() or "timeout" in _msg.lower():
                st.error(T["err_network"])
            else:
                st.error(T["err_analysis"].format(msg=_msg))
            st.stop()
    st.divider()
    _env_path = Path(__file__).parent / ".env"
    _sf_set   = bool(os.getenv("OPENAI_API_KEY"))
    _rep_set  = bool(os.getenv("REPLICATE_API_TOKEN"))
    with st.expander(T["api_keys_title"], expanded=(not _sf_set or not _rep_set)):
        st.caption(T["keys_hint"])

        _sf_cur = os.getenv("OPENAI_API_KEY", "")
        _sf_hint = (f"{_sf_cur[:6]}...{_sf_cur[-4:]}" if len(_sf_cur) > 10
                    else (T["key_set"] if _sf_cur else T["key_not_set"]))
        st.caption(f"SiliconFlow: {_sf_hint}  |  [Get API Key](https://cloud.siliconflow.cn/account/ak)")
        _sf_input = st.text_input(
            T["sf_label"], type="password",
            placeholder="sk-...", key="sf_key_input"
        )

        _rep_cur = os.getenv("REPLICATE_API_TOKEN", "")
        _rep_hint = (f"{_rep_cur[:4]}...{_rep_cur[-4:]}" if len(_rep_cur) > 8
                     else (T["key_set"] if _rep_cur else T["key_not_set"]))
        st.caption(f"Replicate: {_rep_hint}  |  [Get API Token](https://replicate.com/account/api-tokens)")
        _rep_input = st.text_input(
            T["rep_label"], type="password",
            placeholder="r8_...", key="rep_key_input"
        )

        if st.button(T["save_keys"], use_container_width=True):
            from dotenv import set_key as _set_key
            _changed = False
            if _sf_input.strip():
                _set_key(str(_env_path), "OPENAI_API_KEY", _sf_input.strip())
                os.environ["OPENAI_API_KEY"] = _sf_input.strip()
                _changed = True
            if _rep_input.strip():
                _set_key(str(_env_path), "REPLICATE_API_TOKEN", _rep_input.strip())
                os.environ["REPLICATE_API_TOKEN"] = _rep_input.strip()
                _changed = True
            if _changed:
                st.toast(T["keys_ok"], icon="✅")
                st.rerun()
            else:
                st.warning(T["keys_one"])


def _reset_reading_session():
    st.session_state.pop("session_started", None)
    st.session_state.pop("bgm_path", None)
    st.session_state.pop("regen_pending", None)
    st.session_state.pop("regen_exec_choice", None)


# End reading session when the selected book changes (sidebar switch or new upload)
if st.session_state.get("active_book") != selected_book:
    _reset_reading_session()
    st.session_state["active_book"] = selected_book or None


# ---- Hero scene ----------------------------------------------------------------
_hero_dna = load_book_dna(selected_book) if selected_book else None
if _SCENE_OK and _hero_dna:
    st.components.v1.html(get_scene_html(_hero_dna, st.session_state["app_lang"]), height=290, scrolling=False)
else:
    st.title("BookGroove")
    st.caption(T["app_caption"])
    st.divider()

# ---- Guard ---------------------------------------------------------------------
if not selected_book:
    st.markdown(T["select_hint"])
    st.stop()

dna = _hero_dna or load_book_dna(selected_book)
if not dna:
    st.error(T["book_not_found"])
    st.stop()

# ---- Book DNA display ----------------------------------------------------------
st.subheader(dna.get("title", selected_book))
col1, col2, col3, col4 = st.columns(4)
col1.metric(T["mood_label"], dna.get("overall_mood", "-"))
col2.metric(T["emotional_range_label"], dna.get("emotional_range", "-"))
col3.metric(T["rhythm_label"], dna.get("rhythm", "-"))
col4.metric(T["direction_label"], str(dna.get("music_direction", "-")))
st.divider()

_dna_expanded = st.session_state.pop("dna_expander_open", False)
with st.expander(T["edit_dna"], expanded=_dna_expanded):
    _e_mood      = st.text_input(T["dna_mood"], value=dna.get("overall_mood", ""), key="e_mood")
    _e_emotion   = st.text_input(T["dna_emotional_range"], value=dna.get("emotional_range", ""), key="e_emotion")
    _e_setting   = st.text_input(T["dna_setting"], value=dna.get("setting", ""), key="e_setting")
    _e_themes    = st.text_input(T["dna_themes"], value=", ".join(dna.get("themes", [])), key="e_themes")
    _e_rhythm    = st.text_input(T["dna_rhythm"], value=dna.get("rhythm", ""), key="e_rhythm")
    _e_direction = st.text_input(T["dna_direction"], value=str(dna.get("music_direction", "")), key="e_direction")
    if st.button(T["save_changes"], key="save_dna"):
        dna["overall_mood"]    = _e_mood.strip()
        dna["emotional_range"] = _e_emotion.strip()
        dna["setting"]         = _e_setting.strip()
        dna["themes"]          = [t.strip() for t in _e_themes.split(",") if t.strip()]
        dna["rhythm"]          = _e_rhythm.strip()
        dna["music_direction"] = _e_direction.strip()
        dna.pop("suite_sections", None)
        save_book_dna(selected_book, dna)
        st.toast(T["dna_saved"], icon="✅")
        st.rerun()

_suite_expanded = st.session_state.pop("suite_expander_open", False)
with st.expander(T["edit_suite"], expanded=_suite_expanded):
    _sections = list(dna.get("suite_sections") or [])
    if not _sections:
        st.info(T["suite_empty"])
        if st.button(T["compose_suite_btn"], key="compose_suite"):
            try:
                with st.spinner(T["composing"]):
                    _sections = generate_suite_sections(dna)
                    if not _sections:
                        st.error(T["err_no_suite"])
                    else:
                        dna["suite_sections"] = _sections
                        save_book_dna(selected_book, dna)
                        st.toast(T["suite_saved"], icon="✅")
                        st.rerun()
            except Exception as e:
                _msg = str(e)
                if "401" in _msg or "unauthorized" in _msg.lower():
                    st.error(T["err_sf_401"])
                elif "429" in _msg:
                    st.error(T["err_sf_429"])
                elif "503" in _msg or "50508" in _msg or "too busy" in _msg.lower():
                    st.error(T["err_sf_503"])
                elif "connect" in _msg.lower() or "timeout" in _msg.lower():
                    st.error(T["err_network"])
                else:
                    st.error(T["err_analysis"].format(msg=_msg))
    else:
        _edited_sections = []
        for _si, _sec in enumerate(_sections[:3]):
            st.markdown(f"**{T['suite_movement'].format(i=_si + 1)}**")
            _s_name = st.text_input(
                T["suite_name"], value=_sec.get("name", ""), key=f"s_name_{_si}"
            )
            _s_atm = st.text_input(
                T["suite_atmosphere"], value=_sec.get("atmosphere", ""), key=f"s_atm_{_si}"
            )
            _s_prompt = st.text_area(
                T["suite_prompt"], value=_sec.get("music_prompt", ""), key=f"s_prompt_{_si}", height=80
            )
            _edited_sections.append({
                "name": _s_name.strip(),
                "atmosphere": _s_atm.strip(),
                "music_prompt": _s_prompt.strip(),
            })
        if st.button(T["save_suite"], key="save_suite"):
            dna["suite_sections"] = _edited_sections
            save_book_dna(selected_book, dna)
            st.toast(T["suite_saved"], icon="✅")
            st.rerun()

# ---- BGM status ----------------------------------------------------------------
_cached_bgm = get_book_bgm(selected_book)


def _enter_session():
    st.session_state["session_started"] = True
    st.session_state["active_book"] = selected_book
    st.session_state["bgm_path"] = get_book_bgm(selected_book)

_in_reading_session = (
    st.session_state.get("session_started")
    and st.session_state.get("active_book") == selected_book
)

if not _in_reading_session:
    st.subheader(T["start_reading"])
    if _cached_bgm:
        st.caption(T["bgm_cached"])
        if st.button(T["enter_session"], type="primary", use_container_width=True):
            _enter_session()
            st.rerun()
    else:
        st.info(T["no_bgm"])
        if st.button(T["generate_btn"], type="primary", use_container_width=True):
            check_audio_deps(T)
            try:
                generate_bgm_suite(
                    dna, selected_book, T,
                    composing_text=T["composing"],
                    stitching_text=T["stitching"],
                )
                _enter_session()
                st.rerun()
            except Exception as e:
                show_bgm_error(e, T)

# ---- Player --------------------------------------------------------------------
if _in_reading_session:
    bgm_path = st.session_state.get("bgm_path") or get_book_bgm(selected_book)

    st.divider()
    st.subheader(T["now_reading"])

    _themes = dna.get("themes", [])
    _themes_str = "  ".join(_themes) if _themes else "-"
    st.markdown(
        f'<div class="mood-card">'
        f'<b>{T["atmosphere"]}:</b> {dna.get("overall_mood","")}<br>'
        f'<b>{T["bg_setting"]}:</b> {dna.get("setting","")}<br>'
        f'<b>{T["themes"]}:</b> {_themes_str}'
        f'</div>',
        unsafe_allow_html=True
    )

    _versions = list_book_bgm_versions(selected_book)
    if len(_versions) > 1:
        _ver_labels = [v[0] for v in _versions]
        _cur_idx = next((i for i,(lbl,p) in enumerate(_versions) if p == bgm_path), len(_versions)-1)
        _sel = st.radio(T["bgm_version"], _ver_labels, index=_cur_idx, horizontal=True, key="bgm_ver")
        bgm_path = next(p for lbl,p in _versions if lbl == _sel)
        st.session_state["bgm_path"] = bgm_path
        _, _dvcol, _ = st.columns([3, 2, 3])
        with _dvcol:
            if st.button(T["delete_version"], key="del_ver", use_container_width=True):
                st.session_state.pop(f"_b64_{bgm_path}", None)
                os.remove(bgm_path)
                st.session_state["bgm_path"] = None
                st.rerun()

    if bgm_path and os.path.exists(bgm_path):
        import base64 as _b64
        _b64_key = f"_b64_{bgm_path}"
        if _b64_key not in st.session_state:
            with open(bgm_path, "rb") as _f:
                st.session_state[_b64_key] = _b64.b64encode(_f.read()).decode()
        _b64_audio = st.session_state[_b64_key]

        _css = (
            '@import url("https://fonts.bunny.net/css?family=cinzel:400,600,700|noto-serif-sc:400,600,700&display=swap");' 
            '*{margin:0;padding:0;box-sizing:border-box}'
            "body{background:transparent;font-family:'Cinzel',Georgia,serif;color:#e0d7c6}"
            '#pw{background:rgba(22,33,62,0.92);border:1px solid rgba(201,185,154,0.2);'
            'border-radius:12px;padding:18px 22px}'
            '.title{text-align:center;font-size:12px;color:rgba(201,185,154,0.55);'
            'letter-spacing:0.1em;margin-bottom:10px}'
            '.pbw{height:4px;background:rgba(201,185,154,0.12);border-radius:2px;'
            'margin:0 0 4px;cursor:pointer}'
            '.pb{height:100%;background:linear-gradient(90deg,rgba(201,185,154,0.85),'
            'rgba(201,185,154,0.4));border-radius:2px;width:0%;transition:width 0.3s linear}'
            '.tr{display:flex;justify-content:space-between;font-size:10px;'
            'color:rgba(201,185,154,0.38);margin-bottom:14px}'
            '.ctrl{display:flex;justify-content:center;align-items:center;gap:22px}'
            '.btn{background:none;border:none;cursor:pointer;color:rgba(201,185,154,0.65);'
            'font-size:20px;transition:color 0.2s;line-height:1;padding:2px}'
            '.btn:hover{color:#e0d7c6}'
            '.pbtn{width:42px;height:42px;border:1.5px solid rgba(201,185,154,0.35)!important;'
            'border-radius:50%!important;font-size:15px!important;display:flex;'
            'align-items:center;justify-content:center;background:rgba(201,185,154,0.06)!important}'
            '.pbtn:hover{background:rgba(201,185,154,0.15)!important;'
            'border-color:rgba(201,185,154,0.65)!important}'
            '.vrow{display:flex;align-items:center;justify-content:center;gap:8px;margin-top:12px}'
            '#vol{-webkit-appearance:none;width:130px;height:3px;background:rgba(201,185,154,0.18);border-radius:2px;outline:none;cursor:pointer}'
            '#vol::-webkit-slider-thumb{-webkit-appearance:none;width:11px;height:11px;border-radius:50%;background:rgba(201,185,154,0.7)}'
            '.vlbl{font-size:11px;color:rgba(201,185,154,0.4)}'
        )

        _body = (
            '<div id="pw">'
            '<div class="title" id="ti">' + T["player_bgm_label"] + ' &mdash; ' + dna.get("title", selected_book) + '</div>'
            '<div class="pbw" id="pbw"><div class="pb" id="pb"></div></div>'
            '<div class="tr"><span id="ct">0:00</span><span id="dt">--:--</span></div>'
            '<div class="ctrl">'
            '<button class="btn" onclick="sk(-15)" title="-15s">\u21ba</button>'
            '<button class="btn pbtn" id="pp" onclick="tog()">\u25b6</button>'
            '<button class="btn" onclick="sk(15)" title="+15s">\u21bb</button>'
            '</div>'
            '<div class="vrow"><span class="vlbl">🔈</span><input type="range" id="vol" min="0" max="1" step="0.05" value="0.8"><span class="vlbl">🔊</span></div>'
            '</div>'
            '<audio id="au"></audio>'
        )

        _ext = os.path.splitext(bgm_path)[1].lower()
        _mime = 'audio/wav' if _ext == '.wav' else 'audio/mpeg'
        _js = (
            "const T='___TRACK___';"
            "const au=document.getElementById('au'),"
            "pb=document.getElementById('pb'),ct=document.getElementById('ct'),"
            "dt=document.getElementById('dt'),pp=document.getElementById('pp'),"
            "pbw=document.getElementById('pbw');"
            "function ft(s){s=Math.floor(s);return Math.floor(s/60)+':'+(''+(s%60)).padStart(2,'0')}"
            "const _b=atob(T),_ba=new Uint8Array(_b.length);"
            "for(let i=0;i<_b.length;i++)_ba[i]=_b.charCodeAt(i);"
            "au.src=URL.createObjectURL(new Blob([_ba],{type:'___MIME___'}));"
            "au.loop=true;"
            
            
            "au.addEventListener('timeupdate',function(){"
            "if(au.duration){pb.style.width=(au.currentTime/au.duration*100)+'%';"
            "ct.textContent=ft(au.currentTime);dt.textContent=ft(au.duration);}});"
            "function tog(){if(au.paused){au.play();pp.textContent='\u23f8';}"
            "else{au.pause();pp.textContent='\u25b6';}}"
            "function sk(s){au.currentTime=Math.max(0,Math.min(au.currentTime+s,au.duration||0));}"
            "pbw.addEventListener('click',function(e){"
            "if(au.duration){au.currentTime=(e.offsetX/this.offsetWidth)*au.duration;}});"
            "var vol=document.getElementById('vol');au.volume=0.8;"
            "vol.addEventListener('input',function(){au.volume=parseFloat(this.value);});"
        )

        _html = (
            "<!DOCTYPE html><html><head><style>" + _css + "</style></head><body>"
            + _body
            + "<script>" + _js.replace("___TRACK___", _b64_audio).replace("___MIME___", _mime) + "</script></body></html>"
        )
        st.components.v1.html(_html, height=200)
        with open(bgm_path, "rb") as _dlf:
            st.download_button(
                T["download_bgm"],
                data=_dlf.read(),
                file_name=f"{selected_book}_{Path(bgm_path).stem}.mp3",
                mime="audio/mpeg",
                use_container_width=True,
            )
    else:
        st.warning(T["bgm_not_found"])


    _, _rc, _ = st.columns([3, 2, 3])
    with _rc:
        if st.button(T["regenerate"], use_container_width=True):
            st.session_state["regen_pending"] = True

    if st.session_state.get("regen_pending"):
        st.divider()
        st.caption(T["regen_how"])
        _regen_choice = st.radio(
            T["regen_how"],
            [T["regen_opt_same"], T["regen_opt_edit"], T["regen_opt_ai"]],
            key="regen_choice_radio",
            label_visibility="collapsed",
        )
        _col_cancel, _col_confirm = st.columns(2)
        with _col_cancel:
            if st.button(T["regen_cancel"], use_container_width=True, key="regen_cancel_btn"):
                st.session_state.pop("regen_pending", None)
                st.rerun()
        with _col_confirm:
            if st.button(T["regen_confirm"], use_container_width=True, key="regen_confirm_btn", type="primary"):
                st.session_state["regen_exec_choice"] = st.session_state.get("regen_choice_radio", T["regen_opt_same"])
                st.rerun()
    if st.session_state.get("regen_exec_choice"):
        _choice = st.session_state.pop("regen_exec_choice")
        st.session_state.pop("regen_pending", None)
        if _choice == T["regen_opt_edit"]:
            st.session_state["dna_expander_open"] = True
            st.session_state["suite_expander_open"] = True
            st.toast(T["regen_edit_hint"], icon="✏️")
            st.rerun()
        else:
            check_audio_deps(T)
            try:
                _redesign = _choice == T["regen_opt_ai"]
                bgm_path, _ = generate_bgm_suite(
                    dna, selected_book, T,
                    redesign_sections=_redesign,
                    composing_text=T["composing_new"] if _redesign else T["composing"],
                    stitching_text=T["stitching_short"],
                )
                st.session_state["bgm_path"] = bgm_path
                st.rerun()
            except Exception as e:
                show_bgm_error(e, T)
    st.divider()
    _, col_end, _ = st.columns([2, 1, 2])
    with col_end:
        if st.button(T["end_session"], use_container_width=True):
            save_session(selected_book, {
                "timestamp": time.strftime("%Y-%m-%d %H:%M")
            })
            _reset_reading_session()
            st.toast(T["session_saved"], icon="✅")
            st.rerun()
