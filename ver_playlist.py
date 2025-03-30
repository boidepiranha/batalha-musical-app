import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh
import requests
import os
from dotenv import load_dotenv
import time
from datetime import datetime
import logging

# --- Logging Configuration to Suppress Secrets Warning ---
streamlit_logger = logging.getLogger('streamlit')
class SecretsWarningFilter(logging.Filter):
    def filter(self, record):
        return "No secrets found. Valid paths for a secrets.toml file" not in record.getMessage()
streamlit_logger.addFilter(SecretsWarningFilter())

# --- Load .env if running locally ---
load_dotenv()

def get_secret(key: str, fallback: str = None):
    try:
        if key in st.secrets:
            return st.secrets[key]
    except FileNotFoundError:
        pass
    return os.getenv(key, fallback)

EMAIL = get_secret("FIREBASE_EMAIL")
SENHA = get_secret("FIREBASE_SENHA")
API_KEY = get_secret("FIREBASE_API_KEY")
FIREBASE_URL = get_secret("FIREBASE_DB_URL", "https://batalha-musical-default-rtdb.firebaseio.com")

# --- Auto Refresh Setup ---
if 'auto_update' not in st.session_state:
    st.session_state.auto_update = True
if 'update_interval' not in st.session_state:
    st.session_state.update_interval = 5
if st.session_state.auto_update:
    st_autorefresh(interval=st.session_state.update_interval * 1000, key="autorefresh")

# --- Auth with Firebase, session-aware ---
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
    st.session_state.token_expira_em = agora + 3500
    return st.session_state.auth_token

def buscar_status_atual(token):
    url = f"{FIREBASE_URL}/status_atual.json?auth={token}"
    res = requests.get(url)
    res.raise_for_status()
    return res.json()

def buscar_contador_diario(token):
    hoje = datetime.now().strftime("%Y-%m-%d")
    url = f"{FIREBASE_URL}/batalha_estado/contador_diario/{hoje}.json?auth={token}"
    res = requests.get(url)
    return res.json() or 0

try:
    auth_token = gerenciar_token_firebase()
    st.sidebar.success("✅ Autenticado com sucesso")
except Exception as e:
    st.sidebar.error(f"Erro ao autenticar: {e}")
    st.stop()

try:
    status = buscar_status_atual(auth_token)
    batalhas_hoje = buscar_contador_diario(auth_token)
except Exception as e:
    st.sidebar.error(f"Erro ao buscar dados: {e}")
    st.stop()

tocando = status.get("tocando_agora", {})

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

videos = status.get("videos_playlist", [])
video_ids = [v["videoId"] for v in videos]
video_titles = [v["title"] for v in videos]

player_html = f"""
<div id="player"></div>  <!-- O DIV que a API vai usar -->

<script>
  var tag = document.createElement('script');
  tag.src = "https://www.youtube.com/iframe_api";
  var firstScriptTag = document.getElementsByTagName('script')[0];
  firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);

  const videoIds = {video_ids};
  const videoTitles = {video_titles};
  let currentIndex = 0; // Usar 'currentIndex' para evitar conflito com 'player.index' se existir
  var player; // Variável global para o objeto player

  function onYouTubeIframeAPIReady() {{
    player = new YT.Player('player', {{ // Diz à API para usar o div#player
      height: '394',
      width: '700',
      videoId: videoIds[0], // Carrega o primeiro vídeo diretamente
      playerVars: {{
        // 'autoplay': 1, // Autoplay ainda é problemático, melhor iniciar via JS se necessário
        'controls': 1,
        'enablejsapi': 1 // Essencial para controle via JS
      }},
      events: {{
        'onReady': onPlayerReady, // Adicionado evento onReady
        'onStateChange': onPlayerStateChange
      }}
    }});
  }}

  // Função chamada quando o player está pronto
  function onPlayerReady(event) {{
    // Você PODE tentar iniciar o vídeo aqui, mas pode ser bloqueado pelo navegador
    // event.target.playVideo();
    atualizarStatus(videoIds[currentIndex], videoTitles[currentIndex], currentIndex);
  }}

  // Função chamada quando o estado do player muda
  function onPlayerStateChange(event) {{
    // Quando um vídeo começa a tocar (incluindo após loadVideoById)
    if (event.data === YT.PlayerState.PLAYING) {{
      // Garante que estamos atualizando com o índice correto que ACABOU de começar
      atualizarStatus(videoIds[currentIndex], videoTitles[currentIndex], currentIndex);
    }}

    // Quando um vídeo termina
    if (event.data === YT.PlayerState.ENDED) {{
      currentIndex++;
      if (currentIndex < videoIds.length) {{
        player.loadVideoById(videoIds[currentIndex]); // Carrega o próximo vídeo
      }} else {{
        // Último vídeo terminou, recarrega a página
        currentIndex = 0; // Reseta para talvez evitar recarga imediata se algo der errado
        setTimeout(() => location.reload(), 1500);
      }}
    }}
  }}

  // Função para atualizar o Firebase (semelhante à sua)
  function atualizarStatus(videoId, title, index) {{
    const data = {{
      videoId: videoId,
      title: title,
      index: index,
      timestamp: new Date().toISOString()
    }};
    const currentAuthToken = "{auth_token}"; // Usa o token passado pelo Python

    fetch('{FIREBASE_URL}/status_atual/tocando_agora.json?auth=' + currentAuthToken, {{
      method: 'PUT',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify(data)
    }}).catch(error => console.error("Erro ao atualizar status:", error)); // Adicionado catch básico

    if (index === 2) {{
      const hoje = new Date().toISOString().split('T')[0];
      const contadorUrl = '{FIREBASE_URL}/batalha_estado/contador_diario/' + hoje + '.json?auth=' + currentAuthToken;

      fetch(contadorUrl)
        .then(response => response.ok ? response.json() : 0)
        .then(valorAtual => {{
          const novoValor = (valorAtual || 0) + 1;
          return fetch(contadorUrl, {{
            method: 'PUT',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify(novoValor)
          }});
        }})
        .then(() => {{
          return fetch('{FIREBASE_URL}/batalha_estado.json?auth=' + currentAuthToken, {{
            method: 'PATCH',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ nova_batalha: true }})
          }});
        }})
        .catch(error => console.error("Erro ao sinalizar batalha:", error));
    }}
  }}

</script>
"""

st.title("🎵 Playlist da Batalha")
components.html(player_html, height=420)

# Exibe controle de auto-atualização de forma mais visível
st.markdown("---")
st.markdown("### ⚙️ Configurações")
st.session_state.auto_update = st.checkbox("🔄 Auto-atualizar", value=st.session_state.auto_update)
