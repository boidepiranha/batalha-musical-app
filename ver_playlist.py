import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh
import requests
import os
from dotenv import load_dotenv
import time

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

EMAIL = os.getenv("FIREBASE_EMAIL")
SENHA = os.getenv("FIREBASE_SENHA")
API_KEY = os.getenv("FIREBASE_API_KEY")
FIREBASE_URL = os.getenv("FIREBASE_DB_URL", "https://batalha-musical-default-rtdb.firebaseio.com")

# Controle de atualização automática
if 'auto_update' not in st.session_state:
    st.session_state.auto_update = True

if 'update_interval' not in st.session_state:
    st.session_state.update_interval = 5  # segundos

if st.session_state.auto_update:
    st_autorefresh(interval=st.session_state.update_interval * 1000, key="autorefresh")

# Funções auxiliares
@st.cache_data
def autenticar():
    auth_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={API_KEY}"
    res = requests.post(auth_url, json={"email": EMAIL, "password": SENHA, "returnSecureToken": True})
    res.raise_for_status()
    return res.json()["idToken"]

def buscar_status_atual(token):
    url = f"{FIREBASE_URL}/status_atual.json?auth={token}"
    res = requests.get(url)
    res.raise_for_status()
    return res.json()

def sinalizar_batalha(token):
    url = f"{FIREBASE_URL}/batalha_estado.json?auth={token}"
    res = requests.patch(url, json={"nova_batalha": True})
    return res.status_code == 200

# Autenticar
try:
    auth_token = autenticar()
    st.sidebar.success("✅ Autenticado com sucesso")
except Exception as e:
    st.sidebar.error(f"Erro ao autenticar: {e}")
    st.stop()

# Buscar status
try:
    status = buscar_status_atual(auth_token)
except Exception as e:
    st.sidebar.error(f"Erro ao buscar status: {e}")
    st.stop()

tocando = status.get("tocando_agora", {})

# Sidebar
st.sidebar.markdown("### 🎬 Tocando agora")
if tocando:
    st.sidebar.write(f"**{tocando.get('title', '?')}**")
    st.sidebar.caption(f"🎥 ID: `{tocando.get('videoId')}` | 🎞️ Índice: `{tocando.get('index')}`")
    st.sidebar.caption(f"⏱️ Detectado: {tocando.get('timestamp')}")
else:
    st.sidebar.info("Nenhum vídeo detectado no momento")

st.sidebar.markdown("---")
st.sidebar.markdown("### 🥊 Batalha")
st.sidebar.write(f"**Arena:** {status.get('arena', ['?', '?'])[0]} vs {status.get('arena', ['?', '?'])[1]}")
st.sidebar.write(f"**Reserva:** {status.get('reserva', '?')}")
st.sidebar.write(f"**Vencedora anterior:** {status.get('vencedora_ultima_batalha', '?')}")
st.sidebar.write("**Todos os vídeos:**")

for i, v in enumerate(status.get("videos_playlist", [])):
    prefixo = "🔊 " if i == tocando.get("index") else ""
    marcador = "**" if i == tocando.get("index") else ""
    st.sidebar.markdown(f"- {prefixo}{marcador}[{v['title']}](https://youtu.be/{v['videoId']}){marcador}")

st.sidebar.caption(f"🕒 Última batalha: {status.get('timestamp', '---')}")

# Player YouTube
playlist_id = "PLCcM9n2mu2uHA6fuInzsrEOhiTq7Dsd97"

player_html = f"""
<div id=\"player\"></div>
<script>
  var tag = document.createElement('script');
  tag.src = \"https://www.youtube.com/iframe_api\";
  var firstScriptTag = document.getElementsByTagName('script')[0];
  firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);

  var player;
  function onYouTubeIframeAPIReady() {{
    player = new YT.Player('player', {{
      height: '394',
      width: '700',
      playerVars: {{
        listType: 'playlist',
        list: '{playlist_id}',
        autoplay: 1,
        controls: 1
      }},
      events: {{
        'onStateChange': onPlayerStateChange
      }}
    }});
  }}

  function onPlayerStateChange(event) {{
    if (event.data === YT.PlayerState.PLAYING) {{
      const index = player.getPlaylistIndex();
      const videoData = {{
        index: index,
        videoId: player.getVideoData().video_id,
        title: player.getVideoData().title,
        timestamp: new Date().toISOString()
      }};

      fetch("{FIREBASE_URL}/status_atual/tocando_agora.json?auth={auth_token}", {{
        method: 'PUT',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(videoData)
      }});
    }}
  }}
</script>
"""

st.title("🎵 Playlist da Batalha")
components.html(player_html, height=420)

col1, col2 = st.columns([1, 1])

if col1.button("🔥 Iniciar nova batalha"):
    if sinalizar_batalha(auth_token):
        st.success("✅ Batalha sinalizada com sucesso!")
        st.rerun()
    else:
        st.error("❌ Falha ao sinalizar batalha")

# Controle de atualização automática
st.session_state.auto_update = col2.checkbox("🔄 Auto-atualizar", value=st.session_state.auto_update)
