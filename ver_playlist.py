import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh
import requests
import os
from dotenv import load_dotenv
import time
from datetime import datetime

# Tenta carregar variáveis do .env (caso esteja local)
load_dotenv()

def get_secret(key: str, fallback: str = None):
    if key in st.secrets:
        return st.secrets[key]
    return os.getenv(key, fallback)

# Agora use essa função para acessar segredos
EMAIL = get_secret("FIREBASE_EMAIL")
SENHA = get_secret("FIREBASE_SENHA")
API_KEY = get_secret("FIREBASE_API_KEY")
FIREBASE_URL = get_secret("FIREBASE_DB_URL", "https://batalha-musical-default-rtdb.firebaseio.com")

# Controle de atualização automática
if 'auto_update' not in st.session_state:
    st.session_state.auto_update = True

if 'update_interval' not in st.session_state:
    st.session_state.update_interval = 5  # segundos

if st.session_state.auto_update:
    st_autorefresh(interval=st.session_state.update_interval * 1000, key="autorefresh")

# Função para autenticação com gerenciamento de expiração
def gerenciar_token_firebase():
    agora = time.time()
    if "auth_token" in st.session_state and "token_expira_em" in st.session_state:
        if agora < st.session_state.token_expira_em:
            return st.session_state.auth_token

    auth_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={API_KEY}"
    res = requests.post(auth_url, json={"email": EMAIL, "password": SENHA, "returnSecureToken": True})
    res.raise_for_status()
    dados = res.json()
    st.session_state.auth_token = dados["idToken"]
    st.session_state.token_expira_em = agora + 3500  # renova antes de 1h
    return st.session_state.auth_token

def buscar_status_atual(token):
    url = f"{FIREBASE_URL}/status_atual.json?auth={token}"
    res = requests.get(url)
    res.raise_for_status()
    return res.json()

def buscar_contador_diario(token):
    hoje = datetime.now().strftime("%Y-%m-%d")
    url = f"{FIREBASE_URL}/batalha_estado/contador_diario/{hoje}.json?auth={token}"
    try:
        res = requests.get(url)
        res.raise_for_status()
        return res.json() or 0
    except:
        return 0

def sinalizar_batalha(token):
    # Atualiza o contador diário antes de sinalizar
    hoje = datetime.now().strftime("%Y-%m-%d")
    contador_url = f"{FIREBASE_URL}/batalha_estado/contador_diario/{hoje}.json?auth={token}"
    try:
        res_get = requests.get(contador_url)
        atual = res_get.json() if res_get.ok else 0
        novo_valor = (atual or 0) + 1
        requests.put(contador_url, json=novo_valor)
    except Exception as e:
        st.warning(f"Não foi possível atualizar o contador de batalhas: {e}")

    # Sinaliza a batalha
    url = f"{FIREBASE_URL}/batalha_estado.json?auth={token}"
    res = requests.patch(url, json={"nova_batalha": True})
    return res.status_code == 200

# Autenticar com controle
try:
    auth_token = gerenciar_token_firebase()
    st.sidebar.success("✅ Autenticado com sucesso")
except Exception as e:
    st.sidebar.error(f"Erro ao autenticar: {e}")
    st.stop()

# Buscar status e contador
try:
    status = buscar_status_atual(auth_token)
    batalhas_hoje = buscar_contador_diario(auth_token)
except Exception as e:
    st.sidebar.error(f"Erro ao buscar dados: {e}")
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
st.sidebar.caption(f"📊 Batalhas hoje: {batalhas_hoje} de 50")

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

      if (index === 2) {{
        fetch("{FIREBASE_URL}/batalha_estado.json?auth={auth_token}", {{
          method: 'PATCH',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ nova_batalha: true }})
        }});
      }}
    }}

    if (event.data === YT.PlayerState.ENDED) {{
      const index = player.getPlaylistIndex();
      const total = player.getPlaylist().length;
      if (index === total - 1) {{
        setTimeout(() => location.reload(), 1500);
      }}
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
