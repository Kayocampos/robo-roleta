import telebot
import sqlite3
import requests
import time
import threading
from bs4 import BeautifulSoup
from datetime import datetime

# Seu Token do Telegram configurado
TOKEN = "8872976531:AAGeot87CMe2y76KJt4SSLbAiu_MGXCKqe0"
bot = telebot.TeleBot(TOKEN)

# URL da roleta Immersive no TipMiner para o robô monitorar
URL_ROBÔ = "https://www.tipminer.com/br/cassinos/evolution/immersive-roulette?limit=3000&subject=filter&isLoadMore=true&t=1782948000121"

# Definição das matrizes idênticas ao painel (REGIAO.jpeg)
fracoes = {
    'f23': [2, 11, 20, 14, 21, 25, 30, 36],
    'f65': [6, 15, 24, 33, 16, 27, 32],
    'f76': [7, 18, 25, 34, 6, 17, 28, 29],
    'f83': [8, 26, 35, 0, 3, 12, 30],
    'f94': [9, 18, 27, 36, 13, 31, 22, 29],
    'f5':  [5, 10, 23, 14, 16, 27, 32]
}

# Variável para controlar o último número que o robô já processou (evita repetir o mesmo número)
ultimo_numero_gravado = None
# ID do chat que vai receber os sinais automáticos (o bot enviará para quem der /start)
CHAT_ID_DESTINO = None

def iniciar_banco():
    conn = sqlite3.connect('roleta_dados.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS estatisticas (
            id INTEGER PRIMARY KEY, data_atual TEXT, greens INTEGER, reds INTEGER, greens_seguidos INTEGER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS timeline (
            id INTEGER PRIMARY KEY AUTOINCREMENT, numero INTEGER
        )
    ''')
    cursor.execute("SELECT COUNT(*) FROM estatisticas WHERE id = 1")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO estatisticas (id, data_atual, greens, reds, greens_seguidos) VALUES (1, ?, 0, 0, 0)", (datetime.now().strftime('%Y-%m-%d'),))
    conn.commit()
    conn.close()

def obter_dados():
    conn = sqlite3.connect('roleta_dados.db')
    cursor = conn.cursor()
    cursor.execute("SELECT data_atual, greens, reds, greens_seguidos FROM estatisticas WHERE id = 1")
    dados = cursor.fetchone()
    cursor.execute("SELECT numero FROM timeline ORDER BY id DESC")
    historico = [r[0] for r in cursor.fetchall()]
    conn.close()
    return {'data_atual': dados[0], 'greens': dados[1], 'reds': dados[2], 'greens_seguidos': dados[3], 'historico': historico}

def salvar_dados(dados, historico_novo=None):
    conn = sqlite3.connect('roleta_dados.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE estatisticas SET data_atual = ?, greens = ?, reds = ?, greens_seguidos = ? WHERE id = 1', (dados['data_atual'], dados['greens'], dados['reds'], dados['greens_seguidos']))
    if historico_novo is not None:
        cursor.execute("DELETE FROM timeline")
        for num in reversed(historico_novo):
            cursor.execute("INSERT INTO timeline (numero) VALUES (?)", (num,))
    conn.commit()
    conn.close()

operacao = {'em_andamento': False, 'tentativas': 0, 'alvos': [], 'nome_gatilho': ""}

def checar_e_resetar_diario(dados_atuais):
    data_hoje = datetime.now().strftime('%Y-%m-%d')
    if dados_atuais['data_atual'] != data_hoje:
        dados_atuais['data_atual'] = data_hoje
        dados_atuais['greens'] = 0
        dados_atuais['reds'] = 0
        dados_atuais['greens_seguidos'] = 0
        salvar_dados(dados_atuais)
    return dados_atuais

def obter_nome_fracao(chave):
    nomes = {'f23': 'Fração 2/3', 'f65': 'Fração 6/5', 'f76': 'Fração 7/6', 'f83': 'Fração 8/3', 'f94': 'Fração 9/4', 'f5': 'Fração 5'}
    return nomes.get(chave, chave)

@bot.message_handler(commands=['start'])
def comando_start(message):
    global CHAT_ID_DESTINO
    CHAT_ID_DESTINO = message.chat.id
    bot.reply_to(message, "🤖 **Robô Automático Ativado!**\n\nA partir de agora, estou monitorando a roleta Immersive de forma 100% automática. Não precisa digitar nada!", parse_mode="Markdown")

@bot.message_handler(commands=['placar'])
def enviar_placar(message):
    dados = obter_dados()
    dados = checar_e_resetar_diario(dados)
    total = dados['greens'] + dados['reds']
    assertividade = (dados['greens'] / total * 100) if total > 0 else 0.0
    
    texto_placar = (
        "🚀 **Placar do dia** 🟢 {}  🔴 {}\n"
        "🎯 Acertamos {:.2f}% das vezes\n"
        "💰 Estamos com {} Greens seguidos!"
    ).format(dados['greens'], dados['reds'], assertividade, dados['greens_seguidos'])
    bot.reply_to(message, texto_placar, parse_mode="Markdown")

def processar_roleta_automatica(num):
    global operacao, CHAT_ID_DESTINO
    if CHAT_ID_DESTINO is None:
        return # Espera pelo menos um usuário dar /start para saber para onde enviar
        
    dados = obter_dados()
    dados = checar_e_resetar_diario(dados)
    historico_numeros = dados['historico']
    
    if operacao['em_andamento']:
        operacao['tentativas'] += 1
        if num in operacao['alvos']:
            dados['greens'] += 1
            dados['greens_seguidos'] += 1
            salvar_dados(dados)
            bot.send_message(CHAT_ID_DESTINO, f"🟢 **GREEN no G{operacao['tentativas']}** ({num})!\nSinal: {operacao['nome_gatilho']}", parse_mode="Markdown")
            operacao['em_andamento'] = False
        elif operacao['tentativas'] >= 3:
            dados['reds'] += 1
            dados['greens_seguidos'] = 0
            salvar_dados(dados)
            bot.send_message(CHAT_ID_DESTINO, f"🔴 **RED após 3 giros.**\nAlvos originais: {operacao['alvos']}", parse_mode="Markdown")
            operacao['em_andamento'] = False

    historico_numeros.insert(0, num)
    if len(historico_numeros) > 14:
        historico_numeros = historico_numeros[:14]
        
    salvar_dados(dados, historico_novo=historico_numeros)

    if len(historico_numeros) < 14 or operacao['em_andamento']:
        return

    contagem = {chave: sum(1 for n in historico_numeros if n in lista) for chave, lista in fracoes.items()}
    num13, num14 = historico_numeros[12], historico_numeros[13]
    
    regioes_ativadas = []
    for chave, qtd in contagem.items():
        if qtd >= 5 and (num13 in fracoes[chave] or num14 in fracoes[chave]):
            regioes_ativadas.append(chave)

    if regioes_ativadas:
        alvos_finais = []
        nomes_sinal = []
        ultimos_5 = historico_numeros[:5]
        
        for regiao in regioes_ativadas:
            nomes_sinal.append(obter_nome_fracao(regiao))
            alvos_finais.extend(fracoes[regiao])
            if regiao == 'f65' and 16 in ultimos_5: alvos_finais.append(19)
            if regiao == 'f65': alvos_finais.append(1)
            if regiao == 'f76' and any(n in [18, 19, 29, 16, 4] for n in ultimos_5): alvos_finais.append(27)
            if regiao == 'f83' and any(n in [20, 27] for n in ultimos_5): alvos_finais.extend([17, 25])
            if regiao == 'f83' and contagem['f83'] >= 6: alvos_finais.append(28)
            if regiao == 'f94' and any(n in [9, 19] for n in ultimos_5): alvos_finais.append(4)

        operacao['alvos'] = list(set(alvos_finais))
        operacao['nome_gatilho'] = " + ".join(nomes_sinal)
        operacao['em_andamento'] = True
        operacao['tentativas'] = 0

        mensagem_sinal = (
            "🎯 **SINAL DETECTADO AUTOMATICAMENTE!**\n"
            f"Setores: `{operacao['nome_gatilho']}`\n"
            f"🎰 Cobertura: {', '.join(map(str, operacao['alvos']))}\n"
            "⚠️ Limite: Até 3 Giros."
        )
        bot.send_message(CHAT_ID_DESTINO, mensagem_sinal, parse_mode="Markdown")

def loop_monitoramento_tipminer():
    """Função que roda escondida checando o site do TipMiner de tempos em tempos"""
    global ultimo_numero_gravado
    print("🔎 Monitor de tela do TipMiner Ativado...")
    
    while True:
        try:
            # Faz uma requisição simulando um navegador comum
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            resposta = requests.get(URL_ROBÔ, headers=headers, timeout=10)
            
            if resposta.status_code == 200:
                soup = BeautifulSoup(resposta.text, 'html.parser')
                
                # Busca as caixinhas de números da roleta na estrutura do TipMiner
                roleta_divs = soup.find_all('div', class_='roulette-number')
                
                if roleta_divs:
                    # Pega o primeiro número da lista (que é o mais recente que acabou de sair)
                    texto_num = roleta_divs[0].text.strip()
                    if texto_num.isdigit():
                        numero_atual = int(texto_num)
                        
                        # Se for um número novo que acabou de sair na roleta, processa!
                        if numero_atual != ultimo_numero_gravado:
                            ultimo_numero_gravado = numero_atual
                            print(f"🎲 Novo número detectado automaticamente: {numero_atual}")
                            processar_roleta_automatica(numero_atual)
                            
        except Exception as e:
            print(f"Aviso: Erro temporário ao ler site (aguardando próxima rodada)...")
            
        time.sleep(8) # Aguarda 8 segundos antes de checar a tela de novo

if __name__ == "__main__":
    iniciar_banco()
    # Inicia o leitor automático em segundo plano para não travar o Telegram
    t = threading.Thread(target=loop_monitoramento_tipminer)
    t.daemon = True
    t.start()
    
    print("🤖 Robô de Frações 100% Automático Online!")
    bot.infinity_polling()
