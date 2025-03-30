import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh
import requests
import os
from dotenv import load_dotenv
import time
from datetime import datetime
import logging
import json
import random

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
ARTISTAS = ["vlada", "yulia", "roma"]
# Detalhes do vídeo de contagem regressiva
VIDEO_CONTAGEM_ID = "FUKmyRLOlAA"
VIDEO_CONTAGEM_TITLE = "10 Seconds Countdown Timer"

# --- Auto Refresh Setup ---
if 'auto_update' not in st.session_state:
    st.session_state.auto_update = True
if 'update_interval' not in st.session_state:
    st.session_state.update_interval = 10 # Aumentar intervalo? Para dar tempo do player acabar
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

def buscar_dados_firebase(token, path):
    """Busca dados de um caminho específico no Firebase."""
    url = f"{FIREBASE_URL}/{path}.json?auth={token}"
    try:
        res = requests.get(url)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        st.error(f"Erro ao buscar dados de '{path}': {e}")
        return None

def atualizar_dados_firebase(token, path, data):
    """Atualiza dados em um caminho específico usando PUT."""
    url = f"{FIREBASE_URL}/{path}.json?auth={token}"
    try:
        res = requests.put(url, json=data)
        res.raise_for_status()
        return True
    except Exception as e:
        st.error(f"Erro ao atualizar dados em '{path}': {e}")
        return False

# --- Cache para Carregar Playlists JSON ---
@st.cache_data
def carregar_playlists_artistas():
    playlists = {}
    for artista in ARTISTAS:
        try:
            with open(f"{artista}_playlist.json", 'r', encoding='utf-8') as f:
                playlists[artista] = json.load(f)
        except FileNotFoundError:
            st.warning(f"Arquivo {artista}_playlist.json não encontrado.")
            playlists[artista] = []
        except json.JSONDecodeError:
            st.error(f"Erro ao decodificar {artista}_playlist.json.")
            playlists[artista] = []
    return playlists

try:
    auth_token = gerenciar_token_firebase()
    st.sidebar.success("✅ Autenticado com sucesso")
except Exception as e:
    st.sidebar.error(f"Erro ao autenticar: {e}")
    st.stop()

# Carrega as playlists dos artistas (cacheado)
playlists_artistas = carregar_playlists_artistas()

# Busca estado atual da batalha
estado_batalha = buscar_dados_firebase(auth_token, "batalha_estado")
estado_atual = buscar_dados_firebase(auth_token, "status_atual")

if estado_batalha is None or estado_atual is None:
    st.error("Não foi possível carregar o estado inicial da batalha do Firebase.")
    st.stop()

hoje = datetime.now().strftime("%Y-%m-%d")
batalhas_hoje = estado_batalha.get("contador_diario", {}).get(hoje, 0)

incumbente = estado_atual.get("arena", [None, None])[0]
desafiadora = estado_atual.get("arena", [None, None])[1]
reserva = estado_atual.get("reserva")

# Pega os vídeos JÁ SELECIONADOS para a batalha atual
videos_batalha_atual = estado_atual.get("videos_batalha_atual", [])
tocando = estado_atual.get("tocando_agora", {})

# --- Sidebar --- (Exibe o estado atual lido)
st.sidebar.markdown("### 🎬 Tocando agora")
if tocando:
    st.sidebar.write(f"**{tocando.get('title', '?')}**")
    st.sidebar.caption(f"🎥 ID: `{tocando.get('videoId')}` | 🎞️ Índice: `{tocando.get('index')}`")
    st.sidebar.caption(f"⏱️ Detectado: {tocando.get('timestamp')}")
else:
    st.sidebar.info("Nenhum vídeo detectado no momento (aguardando início da batalha)")

st.sidebar.markdown("---")
st.sidebar.markdown("### 🥊 Batalha Atual")
st.sidebar.write(f"**Incumbente:** {incumbente or '?'}")
st.sidebar.write(f"**Desafiadora:** {desafiadora or '?'}")
st.sidebar.write(f"**Reserva:** {reserva or '?'}")
st.sidebar.write(f"**Vencedora anterior:** {estado_atual.get('vencedora_ultima_batalha', '?')}")
st.sidebar.write("**Vídeos da Batalha:**")

# Ajusta a exibição para mostrar os vídeos da batalha atual
for i, v in enumerate(videos_batalha_atual):
    prefixo = "🔊 " if i == tocando.get("index") else ""
    marcador = "**" if i == tocando.get("index") else ""
    st.sidebar.markdown(f"- {prefixo}{marcador}[{v['title']}](https://youtu.be/{v['videoId']}){marcador}")

st.sidebar.caption(f"🕒 Última atualização Firebase: {estado_atual.get('timestamp', '---')}")
st.sidebar.caption(f"📊 Batalhas hoje: {batalhas_hoje} de 50")

# --- Player YouTube --- (Passa apenas os vídeos da batalha atual)
if videos_batalha_atual:
    video_ids = [v["videoId"] for v in videos_batalha_atual]
    video_titles = [v["title"] for v in videos_batalha_atual]

    player_html = f"""
    <div id="player"></div>
    <script>
      var tag = document.createElement('script');
      tag.src = "https://www.youtube.com/iframe_api";
      var firstScriptTag = document.getElementsByTagName('script')[0];
      firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);

      const videoIds = {json.dumps(video_ids)}; // Passa como JSON
      const videoTitles = {json.dumps(video_titles)}; // Passa como JSON
      let currentIndex = 0;
      var player;

      function onYouTubeIframeAPIReady() {{
        player = new YT.Player('player', {{
          height: '394',
          width: '700',
          videoId: videoIds[0],
          playerVars: {{ 'controls': 1, 'enablejsapi': 1 }},
          events: {{ 'onReady': onPlayerReady, 'onStateChange': onPlayerStateChange }}
        }});
      }}

      function onPlayerReady(event) {{
        atualizarStatusTocandoAgora(videoIds[currentIndex], videoTitles[currentIndex], currentIndex);
      }}

      function onPlayerStateChange(event) {{
        if (event.data === YT.PlayerState.PLAYING) {{
          console.log("Player state: PLAYING, currentIndex:", currentIndex);
          atualizarStatusTocandoAgora(videoIds[currentIndex], videoTitles[currentIndex], currentIndex);
        }}
        if (event.data === YT.PlayerState.ENDED) {{
          console.log("Player state: ENDED, currentIndex before increment:", currentIndex);
          currentIndex++;
          console.log("currentIndex after increment:", currentIndex);
          console.log("videoIds.length:", videoIds.length);
          
          if (currentIndex < videoIds.length) {{
            console.log("Condition met: Loading next video ID:", videoIds[currentIndex]);
            player.loadVideoById(videoIds[currentIndex]);
          }} else {{
            console.log("Condition NOT met: End of sequence.");
            // Último vídeo (contagem) terminou - NÃO FAZ NADA AUTOMATICAMENTE
            console.log("Sequência completa (Incumbente, Desafiadora, Contagem) concluída. Aguardando botão.");
          }}
        }}
      }}

      // Função APENAS para atualizar o 'tocando_agora'
      function atualizarStatusTocandoAgora(videoId, title, index) {{
        const data = {{ videoId: videoId, title: title, index: index, timestamp: new Date().toISOString() }};
        const currentAuthToken = "{auth_token}";
        fetch('{FIREBASE_URL}/status_atual/tocando_agora.json?auth=' + currentAuthToken, {{
          method: 'PUT',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(data)
        }}).catch(error => console.error("Erro ao atualizar status 'tocando_agora':", error));
      }}
    </script>
    """
    st.title("🎵 Playlist da Batalha")
    components.html(player_html, height=420)
else:
    st.warning("Aguardando configuração da batalha no Firebase (videos_batalha_atual não definido). Inicie a próxima batalha.")

# --- Controle da Próxima Batalha (Local) ---
st.markdown("---")
st.markdown("### 🎲 Próxima Batalha")

if st.button("Iniciar Próxima Batalha / Realizar Sorteio"):
    if not incumbente or not desafiadora or not reserva:
        st.error("Estado inválido. Incumbente, Desafiadora e Reserva devem estar definidos no Firebase.")
    else:
        # 1. Realizar Sorteio
        vencedora = random.choice([incumbente, desafiadora])
        perdedora = desafiadora if vencedora == incumbente else incumbente
        st.success(f"🏆 Sorteio realizado! Vencedora: {vencedora}")

        # 2. Calcular Novos Papéis
        nova_incumbente = vencedora
        nova_desafiadora = reserva
        nova_reserva = perdedora

        # 3. Selecionar Novos Vídeos Aleatórios + Contagem
        try:
            # Converte nomes para minúsculas ao acessar o dicionário
            video_incumbente = random.choice(playlists_artistas[nova_incumbente.lower()])
            video_desafiadora = random.choice(playlists_artistas[nova_desafiadora.lower()])
            # Cria a lista inicial com os 2 vídeos da batalha
            novos_videos_batalha = [video_incumbente, video_desafiadora]
            # Adiciona o vídeo de contagem regressiva como terceiro item
            novos_videos_batalha.append({
                "videoId": VIDEO_CONTAGEM_ID,
                "title": VIDEO_CONTAGEM_TITLE
            })

        except KeyError as e:
            st.error(f"Erro ao selecionar vídeo: Artista '{e}' não encontrado nas playlists carregadas (verifique o nome/case).")
            st.stop()
        except IndexError:
             # Não precisa mais da variável 'e' aqui, a mensagem é clara
             st.error(f"Erro ao selecionar vídeo: Lista de vídeos vazia para um dos artistas.")
             st.stop()

        # 4. Atualizar Firebase
        hoje = datetime.now().strftime("%Y-%m-%d")
        novo_contador = batalhas_hoje + 1

        # Prepara dados para atualizar /status_atual
        dados_status_atual = {
            "arena": [nova_incumbente, nova_desafiadora],
            "reserva": nova_reserva,
            "vencedora_ultima_batalha": vencedora,
            "videos_batalha_atual": novos_videos_batalha, # Agora contém 3 vídeos
            "timestamp": datetime.now().isoformat()
        }

        # Prepara dados para atualizar /batalha_estado (apenas contador)
        # É mais seguro ler o contador de novo antes de incrementar para evitar race conditions, mas simplificando aqui
        dados_contador = {hoje: novo_contador}

        st.info(f"Atualizando Firebase: Arena={nova_incumbente} vs {nova_desafiadora}, Reserva={nova_reserva}")

        sucesso_status = atualizar_dados_firebase(auth_token, "status_atual", dados_status_atual)
        sucesso_contador = atualizar_dados_firebase(auth_token, f"batalha_estado/contador_diario/{hoje}", novo_contador)

        if sucesso_status and sucesso_contador:
            st.success("Firebase atualizado com sucesso! Recarregando...")
            time.sleep(1) # Pequena pausa para garantir que o Firebase processe
            st.rerun()
        else:
            st.error("Falha ao atualizar o Firebase.")

# Exibe controle de auto-atualização de forma mais visível
st.markdown("---")
st.markdown("### ⚙️ Configurações")
st.session_state.auto_update = st.checkbox("🔄 Auto-atualizar", value=st.session_state.auto_update)
