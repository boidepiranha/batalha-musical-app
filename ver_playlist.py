import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh
import requests
import os
from dotenv import load_dotenv
import time
from datetime import datetime, UTC
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
    # Use timezone-aware UTC datetime object (modern approach)
    hoje = datetime.now(UTC).strftime("%Y-%m-%d")
    url = f"{FIREBASE_URL}/batalha_estado/contador_diario/{hoje}.json?auth={token}"
    try:
        res = requests.get(url)
        res.raise_for_status() # Check for HTTP errors
        # Handle case where node exists but is null, or doesn't exist (res.json() might be None or raise error on 404 if raise_for_status isn't hit)
        return res.json() or 0
    except requests.exceptions.RequestException as e:
        # If the node doesn't exist (404), return 0. Otherwise log warning.
        if e.response is not None and e.response.status_code == 404:
            return 0
        else:
            st.warning(f"Aviso: Não foi possível buscar contador diário: {e}")
            return 0 # Fallback to 0 on other errors
    except ValueError:
        # Handle cases where response is not valid JSON
        st.warning("Aviso: Resposta inválida ao buscar contador diário (não JSON).")
        return 0

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
        console.log("Index 2 detected. Attempting to increment counter and signal battle...");
        const hoje = new Date().toISOString().split('T')[0];
        const contadorUrl = "{FIREBASE_URL}/batalha_estado/contador_diario/" + hoje + ".json?auth={auth_token}";
        console.log("Counter URL:", contadorUrl);

        fetch(contadorUrl)
          .then(response => {{
            console.log("Counter GET Response Status:", response.status);
            if (!response.ok) {{
              if (response.status === 404) {{
                console.log("Counter node not found (404), assuming 0.");
                return 0;
              }}
              throw new Error(`Erro HTTP ao buscar contador: ${{response.status}}`);
            }}
            return response.json();
          }})
          .then(valorAtual => {{
            console.log("Valor Atual recebido:", valorAtual);
            const atual = parseInt(valorAtual) || 0;
            const novoValor = atual + 1;
            console.log(`Calculado: Atual=${{atual}}, Novo=${{novoValor}}`);
            console.log("Enviando PUT para atualizar contador...");
            return fetch(contadorUrl, {{
              method: 'PUT',
              headers: {{ 'Content-Type': 'application/json' }},
              body: JSON.stringify(novoValor)
            }});
          }})
          .then(putResponse => {{
            console.log("Counter PUT Response Status:", putResponse.status);
            if (!putResponse.ok) {{
              throw new Error(`Erro HTTP ao atualizar contador (PUT): ${{putResponse.status}}`);
            }}
            console.log("Contador atualizado. Enviando PATCH para sinalizar batalha...");
            return fetch("{FIREBASE_URL}/batalha_estado.json?auth={auth_token}", {{
              method: 'PATCH',
              headers: {{ 'Content-Type': 'application/json' }},
              body: JSON.stringify({{ nova_batalha: true }})
            }});
          }})
          .then(patchResponse => {{
             console.log("Battle Signal PATCH Response Status:", patchResponse.status);
             if (!patchResponse.ok) {{
               throw new Error(`Erro HTTP ao sinalizar batalha (PATCH): ${{patchResponse.status}}`);
             }}
             console.log("Batalha sinalizada com sucesso!");
          }})
          .catch(error => {{
             console.error("ERRO na cadeia de incremento/sinalização:", error);
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

col1 = st.columns(1)[0]
st.session_state.auto_update = col1.checkbox("🔄 Auto-atualizar", value=st.session_state.auto_update)
