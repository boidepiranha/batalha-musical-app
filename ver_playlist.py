import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh
import requests
import os
from dotenv import load_dotenv
import time
from datetime import datetime, timedelta

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

# Funções auxiliares

# Autenticação - Removido o cache e retorna token + expiração
def autenticar():
    """Autentica no Firebase e retorna idToken e tempo de expiração em segundos."""
    auth_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={API_KEY}"
    payload = {"email": EMAIL, "password": SENHA, "returnSecureToken": True}
    res = requests.post(auth_url, json=payload)
    res.raise_for_status()
    data = res.json()
    # Retorna o idToken e o expiresIn (convertido para int)
    return data["idToken"], int(data["expiresIn"])

def _is_token_expired(margin_seconds=60):
    """Verifica se o token na session_state expirou ou está prestes a expirar."""
    if "firebase_token_expires_at" not in st.session_state:
        return True
    return datetime.now() >= (st.session_state.firebase_token_expires_at - timedelta(seconds=margin_seconds))

def gerenciar_token_firebase():
    """Obtém um token válido, autenticando se necessário."""
    if 'firebase_token' not in st.session_state or _is_token_expired():
        try:
            st.session_state.firebase_token, expires_in = autenticar()
            st.session_state.firebase_token_expires_at = datetime.now() + timedelta(seconds=expires_in)
            st.sidebar.success("✅ Token Firebase renovado!") # Feedback visual
        except Exception as e:
            st.sidebar.error(f"Erro crítico ao autenticar/renovar token: {e}")
            st.stop() # Impede a execução se não conseguir autenticar
    return st.session_state.firebase_token

def buscar_status_atual(token):
    url = f"{FIREBASE_URL}/status_atual.json?auth={token}"
    res = requests.get(url)
    res.raise_for_status()
    return res.json()

def sinalizar_batalha(token):
    url = f"{FIREBASE_URL}/batalha_estado.json?auth={token}"
    res = requests.patch(url, json={"nova_batalha": True})
    return res.status_code == 200

# --- FLUXO PRINCIPAL ---

# Gerencia e obtém o token atual
auth_token = gerenciar_token_firebase()

# Buscar status com o token gerenciado
try:
    status = buscar_status_atual(auth_token)
except Exception as e:
    st.sidebar.error(f"Erro ao buscar status: {e}")
    # Decide se quer parar ou continuar com status vazio
    status = {} # Permite que a interface tente renderizar mesmo com erro

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

current_index = tocando.get("index", -1) # Usar -1 se não houver índice
for i, v in enumerate(status.get("videos_playlist", [])):
    prefixo = "🔊 " if i == current_index else ""
    marcador = "**" if i == current_index else ""
    st.sidebar.markdown(f"- {prefixo}{marcador}[{v['title']}](https://youtu.be/{v['videoId']}){marcador}")

st.sidebar.caption(f"🕒 Última batalha: {status.get('timestamp', '---')}")

# Player YouTube
playlist_id = "PLCcM9n2mu2uHA6fuInzsrEOhiTq7Dsd97"

# **Importante**: Passar o token atual para o JavaScript
# Note que o token pode mudar, então a string HTML precisa ser gerada a cada execução
player_html = f"""
<div id="player"></div>
<script>
  var tag = document.createElement('script');
  tag.src = "https://www.youtube.com/iframe_api";
  var firstScriptTag = document.getElementsByTagName('script')[0];
  firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);

  var player;
  // Passar o token ATUALIZADO para o JavaScript
  const currentAuthToken = "{auth_token}";

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

      // Usa o token atualizado passado do Python
      fetch("{FIREBASE_URL}/status_atual/tocando_agora.json?auth=" + currentAuthToken, {{
        method: 'PUT',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(videoData)
      }});

      if (index === 2) {{
        fetch("{FIREBASE_URL}/batalha_estado.json?auth=" + currentAuthToken, {{
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
    # Usa o token gerenciado aqui também
    if sinalizar_batalha(auth_token):
        st.success("✅ Batalha sinalizada com sucesso!")
        st.rerun()
    else:
        st.error("❌ Falha ao sinalizar batalha")

# Controle de atualização automática
st.session_state.auto_update = col2.checkbox("🔄 Auto-atualizar", value=st.session_state.auto_update)
