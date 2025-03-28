import streamlit as st
import streamlit.components.v1 as components
import requests
import json
import os
from dotenv import load_dotenv
from datetime import datetime
import time

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

EMAIL = os.getenv("FIREBASE_EMAIL")
SENHA = os.getenv("FIREBASE_SENHA")
API_KEY = os.getenv("FIREBASE_API_KEY")
FIREBASE_URL = os.getenv("FIREBASE_DB_URL", "https://batalha-musical-default-rtdb.firebaseio.com")

# Configuração para auto-rerun da seção tocando_agora
if 'last_update_time' not in st.session_state:
    st.session_state.last_update_time = time.time()
    st.session_state.update_interval = 5  # segundos
    st.session_state.auto_rerun = True

# Inicializa ou obtém dados de batalha (apenas uma vez por sessão)
if 'dados_batalha' not in st.session_state:
    st.session_state.dados_batalha = None

# Exibir informações de configuração (apenas para debug)
st.sidebar.write("### Configuração:")
st.sidebar.write(f"Firebase URL: {FIREBASE_URL[:20]}..." if FIREBASE_URL else "❌ Firebase URL não configurada")
st.sidebar.write(f"Email: {EMAIL[:3]}...{EMAIL[-8:]}" if EMAIL else "❌ Email não configurado")
st.sidebar.write(f"API Key: {API_KEY[:5]}..." if API_KEY else "❌ API Key não configurada")

# Verificar se as credenciais foram fornecidas
if not all([EMAIL, SENHA, API_KEY]):
    st.error("⚠️ Credenciais do Firebase não configuradas. Configure as variáveis de ambiente FIREBASE_EMAIL, FIREBASE_SENHA e FIREBASE_API_KEY no arquivo .env")

playlist_id = "PLCcM9n2mu2uHA6fuInzsrEOhiTq7Dsd97"

@st.cache_data
def autenticar():
    auth_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={API_KEY}"
    st.write(f"Tentando autenticar com email: {EMAIL[:3]}...{EMAIL[-8:]}")
    
    try:
        res = requests.post(auth_url, json={"email": EMAIL, "password": SENHA, "returnSecureToken": True})
        res.raise_for_status()
        token = res.json()["idToken"]
        st.write(f"Token obtido: {token[:10]}...")
        return token
    except Exception as e:
        st.write(f"Erro detalhado na autenticação: {str(e)}")
        if hasattr(e, 'response') and e.response:
            st.write(f"Status: {e.response.status_code}")
            st.write(f"Resposta: {e.response.text}")
        raise e

def buscar_status_atual(token):
    url = f"{FIREBASE_URL}/status_atual.json?auth={token}"
    try:
        st.sidebar.write(f"Buscando status em: {url[:50]}...")
        res = requests.get(url)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        st.sidebar.error(f"Erro ao buscar status atual: {str(e)}")
        if hasattr(e, 'response') and e.response:
            st.sidebar.write(f"Status: {e.response.status_code}")
            st.sidebar.write(f"Resposta: {e.response.text}")
        return None

def sinalizar_batalha(token):
    url = f"{FIREBASE_URL}/batalha_estado.json?auth={token}"
    st.write(f"Enviando requisição para: {url[:50]}...")
    
    try:
        res = requests.patch(url, json={"nova_batalha": True})
        st.write(f"Status da resposta: {res.status_code}")
        st.write(f"Resposta: {res.text}")
        return res.status_code == 200
    except Exception as e:
        st.write(f"Erro detalhado no envio: {str(e)}")
        if hasattr(e, 'response') and e.response:
            st.write(f"Status: {e.response.status_code}")
            st.write(f"Resposta: {e.response.text}")
        raise e

# Obter token de autenticação no início
try:
    auth_token = autenticar()
except Exception as e:
    st.error(f"Erro ao autenticar: {e}")
    auth_token = ""

# Exibir informações para debug
if auth_token:
    st.sidebar.success("✅ Autenticado com sucesso")
    
    # Buscar e exibir status atual na sidebar
    status = buscar_status_atual(auth_token)
    if status:
        st.sidebar.markdown("### 🎬 Tocando agora")
        tocando = status.get("tocando_agora", {})
        if tocando:
            st.sidebar.write(f"**{tocando.get('title', '?')}**")
            st.sidebar.caption(f"🎥 ID: `{tocando.get('videoId')}` | 🎞️ Índice: `{tocando.get('index')}`")
            st.sidebar.caption(f"⏱️ Detectado: {tocando.get('timestamp')}")
        
        st.sidebar.markdown("---")
        
        # Informações da batalha
        st.sidebar.markdown("### 🥊 Batalha")
        st.sidebar.write(f"**Arena:** {status.get('arena', ['?', '?'])[0]} vs {status.get('arena', ['?', '?'])[1]}")
        st.sidebar.write(f"**Reserva:** {status.get('reserva', '?')}")
        st.sidebar.write(f"**Vencedora anterior:** {status.get('vencedora_ultima_batalha', '?')}")
        st.sidebar.write("**Todos os vídeos:**")
        
        # Obtém o índice atual
        current_index = tocando.get('index', 0) if tocando else 0
        
        for i, v in enumerate(status.get("videos_playlist", [])):
            # Destaca o vídeo atual
            if i == current_index:
                st.sidebar.markdown(f"- 🔊 **[{v['title']}](https://youtu.be/{v['videoId']})**")
            else:
                st.sidebar.markdown(f"- [{v['title']}](https://youtu.be/{v['videoId']})")
        st.sidebar.caption(f"🕒 Última batalha: {status.get('timestamp', '---')}")
    else:
        st.sidebar.warning("Não foi possível carregar o status atual.")
else:
    st.sidebar.error("❌ Falha na autenticação inicial")

# Função para atualizar o estado do vídeo atual (será chamada pelo botão de recarregar)
def atualizar_estado_video():
    # Como não podemos usar comunicação direta JS->Python, vamos apenas atualizar o timestamp
    st.session_state.last_update = time.time()

html_code = f"""
<div id="player"></div>

<script>
  // Token de autenticação Firebase
  const authToken = "{auth_token}";
  console.log("Token carregado:", authToken ? "Sim (primeiros caracteres: " + authToken.substring(0, 10) + "...)" : "Não");
  
  var tag = document.createElement('script');
  tag.src = "https://www.youtube.com/iframe_api";
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
        'onReady': onPlayerReady,
        'onStateChange': onPlayerStateChange
      }}
    }});
  }}

  function onPlayerReady(event) {{
    console.log("🎬 Player pronto");
    
    // Captura dados iniciais e atualiza o Firebase após o player carregar
    setTimeout(() => {{
      if (player && player.getPlaylistIndex() !== undefined) {{
        const index = player.getPlaylistIndex();
        const videoData = {{
          index: index,
          videoId: player.getVideoData().video_id,
          title: player.getVideoData().title,
          timestamp: new Date().toISOString()
        }};
        
        const firebaseUrl = "{FIREBASE_URL}/status_atual/tocando_agora.json?auth=" + authToken;
        fetch(firebaseUrl, {{
          method: "PUT",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(videoData)
        }})
        .then(r => console.log("Estado inicial do player atualizado:", r.ok ? "Sucesso" : "Falha"))
        .catch(e => console.error("Erro ao atualizar estado inicial:", e));
      }}
    }}, 2000);
  }}

  function onPlayerStateChange(event) {{
    // Detecta quando um novo vídeo começa a tocar
    if (event.data === YT.PlayerState.PLAYING) {{
      var index = player.getPlaylistIndex();
      console.log("🎵 Tocando vídeo índice:", index);

      // Captura dados do vídeo atual
      const videoData = {{
        index: index,
        videoId: player.getVideoData().video_id,
        title: player.getVideoData().title,
        timestamp: new Date().toISOString()
      }};

      // Atualiza status_atual com o vídeo tocando agora
      const firebaseUrl = "{FIREBASE_URL}/status_atual/tocando_agora.json?auth=" + authToken;
      console.log("Enviando status 'tocando_agora' para:", firebaseUrl);

      fetch(firebaseUrl, {{
        method: "PUT",
        headers: {{
          "Content-Type": "application/json"
        }},
        body: JSON.stringify(videoData)
      }}).then(r => {{
        if (r.ok) {{
          console.log("✅ Status 'tocando_agora' atualizado com sucesso");
          return r.json();
        }} else {{
          console.error("❌ Erro ao atualizar 'tocando_agora':", r.status);
          return r.text().then(text => {{
            console.error("Resposta de erro:", text);
            throw new Error("Falha na atualização");
          }});
        }}
      }}).catch(e => console.error("❌ Erro no envio para Firebase", e));

      // Aciona batalha se for o vídeo 2
      if (index === 2) {{
        console.log("🎬 Começou o vídeo da contagem regressiva!");

        const triggerUrl = "{FIREBASE_URL}/batalha_estado.json?auth=" + authToken;
        fetch(triggerUrl, {{
          method: "PATCH",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ nova_batalha: true }})
        }}).then(r => {{
          if (r.ok) {{
            console.log("✅ Batalha sinalizada com sucesso");
          }} else {{
            console.error("❌ Erro ao sinalizar batalha:", r.status);
          }}
        }}).catch(e => console.error("❌ Erro na sinalização de batalha", e));
      }}
    }}
    
    // Mantém a função original para recarregar quando a playlist terminar
    if (event.data === YT.PlayerState.ENDED) {{
      console.log("🎬 Playlist terminou. Recarregando...");
      setTimeout(() => location.reload(), 2000); // Espera 2 segundos e recarrega
    }}
  }}
</script>
"""

st.title("🎵 Playlist da Batalha")

# Renderiza o player do YouTube
components.html(html_code, height=420)

# Interface para controles de atualização automática
col1, col2, col3 = st.columns([1, 1, 1])

# Botão para iniciar nova batalha
if col1.button("🔥 Iniciar nova batalha"):
    try:
        if auth_token:
            st.write("Usando token existente")
            if sinalizar_batalha(auth_token):
                st.success("✅ Batalha sinalizada com sucesso!")
                # Recarrega a página para atualizar
                st.rerun()
            else:
                st.error("❌ Falha ao atualizar no Firebase.")
        else:
            st.write("Obtendo novo token")
            token = autenticar()
            if sinalizar_batalha(token):
                st.success("✅ Batalha sinalizada com sucesso!")
                # Recarrega a página para atualizar o token no JavaScript
                st.write("Recarregando página para atualizar token no JavaScript")
                st.rerun()
            else:
                st.error("❌ Falha ao atualizar no Firebase.")
    except Exception as e:
        st.error(f"Erro: {e}")

# Busca status atual (com cache)
@st.cache_data(ttl=st.session_state.update_interval)
def buscar_status_com_cache(token):
    return buscar_status_atual(token)

# Função para exibir o painel "Tocando agora"
def exibir_tocando_agora(tocando, container):
    if tocando:
        with container:
            st.markdown("### 🎬 Tocando agora")
            st.write(f"**{tocando.get('title', '?')}**")
            st.caption(f"🎥 ID: `{tocando.get('videoId')}` | 🎞️ Índice: `{tocando.get('index')}`")
            st.caption(f"⏱️ Detectado: {tocando.get('timestamp')}")
    else:
        container.info("Nenhuma informação de vídeo tocando no momento.")

# Espaço reservado para o painel "Tocando agora"
tocando_box = st.sidebar.empty()

# Botão para recarregar o status
if col2.button("🔄 Recarregar status"):
    # Atualiza apenas os dados sem recarregar o iframe
    status = buscar_status_com_cache(auth_token)
    tocando = status.get("tocando_agora", {}) if status else {}
    exibir_tocando_agora(tocando, tocando_box)

# Controle de atualização automática
auto_rerun = col3.checkbox("🔄 Auto-atualizar", value=st.session_state.auto_rerun)
if auto_rerun != st.session_state.auto_rerun:
    st.session_state.auto_rerun = auto_rerun
    st.rerun()

# Exibição do vídeo atual na sidebar
if auth_token:
    # Busca status atual (com cache)
    status = buscar_status_com_cache(auth_token)
    
    # Atualiza dados da batalha (menos frequente)
    if status and (st.session_state.dados_batalha is None):
        st.session_state.dados_batalha = {
            'arena': status.get('arena', ['?', '?']),
            'reserva': status.get('reserva', '?'),
            'vencedora': status.get('vencedora_ultima_batalha', '?'),
            'videos': status.get('videos_playlist', []),
            'timestamp': status.get('timestamp', '---')
        }
    
    # Exibe informações de "Tocando agora"
    if status:
        tocando = status.get("tocando_agora", {})
        exibir_tocando_agora(tocando, tocando_box)
        
        # Separador
        st.sidebar.markdown("---")
        
        # Informações da batalha
        st.sidebar.markdown("### 🥊 Batalha")
        
        if st.session_state.dados_batalha:
            dados = st.session_state.dados_batalha
            st.sidebar.write(f"**Arena:** {dados['arena'][0]} vs {dados['arena'][1]}")
            st.sidebar.write(f"**Reserva:** {dados['reserva']}")
            st.sidebar.write(f"**Vencedora anterior:** {dados['vencedora']}")
            st.sidebar.write("**Todos os vídeos:**")
            
            # Obtém o índice atual
            current_index = tocando.get('index', 0) if tocando else 0
            
            for i, v in enumerate(dados['videos']):
                # Destaca o vídeo atual
                if i == current_index:
                    st.sidebar.markdown(f"- 🔊 **[{v['title']}](https://youtu.be/{v['videoId']})**")
                else:
                    st.sidebar.markdown(f"- [{v['title']}](https://youtu.be/{v['videoId']})")
            st.sidebar.caption(f"🕒 Última batalha: {dados['timestamp']}")
    else:
        st.sidebar.warning("Não foi possível carregar o status atual.")
else:
    st.sidebar.error("❌ Falha na autenticação inicial")


