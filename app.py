# app.py (VERSÃO MELHORADA E COM NOVAS FUNCIONALIDADES)

# Imports necessários
from flask import Flask, jsonify, request
from flask_cors import CORS
import google.generativeai as genai
import os
from dotenv import load_dotenv
import json
import requests  # NOVO: Para fazer chamadas à API da Last.fm
import random    # NOVO: Para embaralhar a playlist
from ytmusicapi import YTMusic # NOVO: Para a integração com YouTube Music

# Carregar variáveis de ambiente
load_dotenv()
app = Flask(__name__)
CORS(app) # Permite que seu front-end na Vercel chame este back-end

# --- Configuração das APIs ---
# Chave da API do Gemini (Google AI)
GENAI_API_KEY = os.getenv("GENAI_APIKEY")
if GENAI_API_KEY:
    genai.configure(api_key=GENAI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
else:
    print("AVISO: GENAI_APIKEY não encontrada. As funções da IA estão desabilitadas.")
    model = None

# Chave da API da Last.fm
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_API_URL = "http://ws.audioscrobbler.com/2.0/"


# --- FUNÇÕES AUXILIARES ---

# MANTIDO: Função para gerar o conteúdo criativo da playlist (título/descrição)
def gerar_conteudo_criativo_playlist(genero, artistas):
    if not model:
        return {
            "titulo_playlist": f"Playlist de {genero}",
            "descricao_playlist": f"Uma seleção de músicas baseada nos artistas: {', '.join(artistas)}.",
            "aviso_conteudo": "A geração criativa de nomes está desabilitada (API Key não configurada)."
        }
    
    prompt = f"""
    Sua tarefa é ser um DJ criativo. Baseado no gênero musical "{genero}" e nos artistas de referência "{', '.join(artistas)}", 
    crie um nome e uma breve descrição para uma playlist.
    
    Instruções:
    1.  Sugira um título criativo para a playlist que reflita o gênero e os artistas.
    2.  Inclua uma breve descrição (1-2 frases) sobre a vibe da playlist.
    3.  Se o gênero ou os artistas forem inadequados ou não relacionados à música, retorne um aviso.

    Retorne APENAS o JSON com a seguinte estrutura:
    {{
        "titulo_playlist": "Seu Título Criativo Aqui",
        "descricao_playlist": "Sua descrição da vibe da playlist aqui.",
        "aviso_conteudo": null
    }}
    Se houver um aviso, o campo "aviso_conteudo" deve explicar o motivo.
    """
    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                response_mime_type="application/json"
            )
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Erro ao gerar conteúdo criativo com Gemini: {e}")
        return {
            "titulo_playlist": f"Playlist de {genero}",
            "descricao_playlist": f"Uma seleção de músicas com {', '.join(artistas)}.",
            "aviso_conteudo": "Falha na geração criativa do título."
        }


# --- ROTAS DA API ---

@app.route('/playlist', methods=['POST'])
def make_playlist():
    dados = request.get_json()
    if not dados:
        return jsonify({'error': 'Requisição JSON inválida.'}), 400

    genero = dados.get('genero')
    artistas_input = dados.get('artistas', [])

    # Validação de entrada (mantida e melhorada)
    if not genero or not isinstance(genero, str) or not genero.strip():
        return jsonify({'error': 'O campo "genero" é obrigatório e deve ser uma string não vazia.'}), 400
    if not artistas_input or not isinstance(artistas_input, list) or len(artistas_input) == 0:
        return jsonify({'error': 'O campo "artistas" é obrigatório e deve ser uma lista com pelo menos um artista.'}), 400

    # ----- LÓGICA REFEITA: ABORDAGEM HÍBRIDA -----
    
    # Passo 1: Usar a IA para gerar apenas o título e a descrição (parte criativa)
    conteudo_criativo = gerar_conteudo_criativo_playlist(genero, artistas_input)

    # Passo 2: Usar a API da Last.fm para buscar músicas REAIS (parte factual)
    if not LASTFM_API_KEY:
        return jsonify({
            **conteudo_criativo,
            "musicas": [],
            "aviso_conteudo": "API da Last.fm não configurada. Não é possível buscar músicas."
        }), 500

    playlist_musicas = []
    musicas_por_artista = 15 // len(artistas_input) + 1 # Divide o total de músicas desejado pelo nº de artistas

    for artista_nome in artistas_input:
        params = {
            'method': 'artist.gettoptracks',
            'artist': artista_nome,
            'api_key': LASTFM_API_KEY,
            'format': 'json',
            'limit': musicas_por_artista
        }
        try:
            response = requests.get(LASTFM_API_URL, params=params)
            response.raise_for_status()
            top_tracks_data = response.json()
            
            if 'track' in top_tracks_data.get('toptracks', {}):
                for track in top_tracks_data['toptracks']['track']:
                    playlist_musicas.append({
                        'titulo_musica': track['name'],
                        'artista_musica': track['artist']['name'] # Usar o nome que a API retorna para consistência
                    })
        except requests.exceptions.RequestException as e:
            print(f"Erro ao buscar faixas para {artista_nome} na Last.fm: {e}")
            continue # Pula para o próximo artista se este falhar
        except KeyError:
            print(f"Artista '{artista_nome}' não encontrado na Last.fm.")
            if not conteudo_criativo.get("aviso_conteudo"):
                 conteudo_criativo["aviso_conteudo"] = ""
            conteudo_criativo["aviso_conteudo"] += f" O artista '{artista_nome}' não foi encontrado. "
            continue

    if not playlist_musicas:
         return jsonify({
            **conteudo_criativo,
            "musicas": [],
            "aviso_conteudo": "Nenhuma música encontrada para os artistas fornecidos. Tente outros nomes."
        }), 200

    # Passo 3: Embaralhar e limitar a playlist final
    random.shuffle(playlist_musicas)
    playlist_final = playlist_musicas[:15] # Garante no máximo 15 músicas

    # Passo 4: Montar a resposta final
    response_data = {
        **conteudo_criativo,
        "musicas": playlist_final
    }
    
    return jsonify(response_data), 200


@app.route('/create-yt-playlist', methods=['POST'])
def create_yt_playlist():
    # NOVO: Esta rota inteira é para a funcionalidade do YouTube Music

    # Passo 1: Autenticar. Requer o arquivo 'oauth.json' no mesmo diretório no servidor.
    # AVISO: A Vercel tem um sistema de arquivos efêmero. A melhor abordagem para produção
    # seria passar o CONTEÚDO do oauth.json como uma variável de ambiente e criar o arquivo em /tmp.
    # Para simplificar, vamos assumir que o 'oauth.json' está presente.
    try:
        # Se você colocar o conteúdo do seu oauth.json em uma variável de ambiente chamada YT_OAUTH_JSON:
        # with open("/tmp/oauth.json", "w") as f:
        #     f.write(os.getenv("YT_OAUTH_JSON"))
        # ytmusic = YTMusic("/tmp/oauth.json")
        
        # Para desenvolvimento local e simplicidade na Vercel (se funcionar):
        ytmusic = YTMusic('oauth.json')
    except Exception as e:
        print(f"Erro ao inicializar YTMusicAPI: {e}")
        return jsonify({"error": "Falha na autenticação com o YouTube Music. Verifique a configuração do servidor."}), 500

    data = request.get_json()
    playlist_name = data.get('titulo_playlist', 'Playlist Gerada por IA')
    playlist_description = data.get('descricao_playlist', 'Criada por PlaylistGen AI')
    musicas = data.get('musicas', [])

    if not musicas:
        return jsonify({"error": "Nenhuma música fornecida."}), 400

    # Passo 2: Encontrar os videoIds para cada música
    video_ids = []
    for musica in musicas:
        query = f"{musica['artista_musica']} {musica['titulo_musica']}"
        search_results = ytmusic.search(query, filter='songs', limit=1)
        if search_results and 'videoId' in search_results[0]:
            video_ids.append(search_results[0]['videoId'])
        else:
            print(f"Não encontrado videoId para: {query}")

    if not video_ids:
        return jsonify({"error": "Nenhuma das músicas foi encontrada no YouTube Music."}), 404

    # Passo 3: Criar a playlist e adicionar as músicas
    try:
        playlist_id = ytmusic.create_playlist(playlist_name, playlist_description)
        ytmusic.add_playlist_items(playlist_id, video_ids)
        playlist_url = f"https://music.youtube.com/playlist?list={playlist_id}"
        
        return jsonify({
            "message": "Playlist criada com sucesso!",
            "playlist_url": playlist_url
        })
    except Exception as e:
        print(f"Erro ao criar playlist no YouTube Music: {e}")
        return jsonify({"error": f"Erro interno ao criar a playlist no YouTube: {e}"}), 500


if __name__ == '__main__':
    app.run(debug=True)