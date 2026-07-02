import telebot
import sqlite3
from datetime import datetime

# Seu Token configurado e pronto para uso
TOKEN = "8872976531:AAGeot87CMe2y76KJt4SSLbAiu_MGXCKqe0"
bot = telebot.TeleBot(TOKEN)

# Definição das matrizes idênticas ao painel (REGIAO.jpeg)
fracoes = {
    'f23': [2, 11, 20, 14, 21, 25, 30, 36],
    'f65': [6, 15, 24, 33, 16, 27, 32],
    'f76': [7, 18, 25, 34, 6, 17, 28, 29],
    'f83': [8, 26, 35, 0, 3, 12, 30],
    'f94': [9, 18, 27, 36, 13, 31, 22, 29],
    'f5':  [5, 10, 23, 14, 16, 27, 32]
}

# Inicialização do Banco de Dados SQLite para persistência 24h
def iniciar_banco():
    conn = sqlite3.connect('roleta_dados.db')
    cursor = conn.cursor()
    # Tabela para guardar estatísticas do dia
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS estatisticas (
            id INTEGER PRIMARY KEY,
            data_atual TEXT,
            greens INTEGER,
            reds INTEGER,
            greens_seguidos INTEGER
        )
    ''')
    # Tabela para manter o histórico recente da timeline (até 14 números)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS timeline (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero INTEGER
        )
    ''')
    
    # Garante que a linha de estatísticas exista
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
    linhas = cursor.fetchall()
    historico = [r[0] for r in linhas]
    
    conn.close()
    return {
        'data_atual': dados[0],
        'greens': dados[1],
        'reds': dados[2],
        'greens_seguidos': dados[3],
        'historico': historico
    }

def salvar_dados(dados, historico_novo=None):
    conn = sqlite3.connect('roleta_dados.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE estatisticas 
        SET data_atual = ?, greens = ?, reds = ?, greens_seguidos = ? 
        WHERE id = 1
    ''', (dados['data_atual'], dados['greens'], dados['reds'], dados['greens_seguidos']))
    
    if historico_novo is not None:
        cursor.execute("DELETE FROM timeline")
        for num in reversed(historico_novo):  # Mantém a ordenação correta ao reinserir
            cursor.execute("INSERT INTO timeline (numero) VALUES (?)", (num,))
            
    conn.commit()
    conn.close()

# Variáveis voláteis de controle de sinal
operacao = {
    'em_andamento': False,
    'tentativas': 0,
    'alvos': [],
    'nome_gatilho': ""
}

def checar_e_resetar_diario(dados_atuais):
    """Verifica se a data mudou em relação à salva no banco para resetar às 00h"""
    data_hoje = datetime.now().strftime('%Y-%m-%d')
    if dados_atuais['data_atual'] != data_hoje:
        dados_atuais['data_atual'] = data_hoje
        dados_atuais['greens'] = 0
        dados_atuais['reds'] = 0
        dados_atuais['greens_seguidos'] = 0
        salvar_dados(dados_atuais)
        print(f"🔄 Meia-noite atingida! Placar diário resetado para {data_hoje}.")
    return dados_atuais

def obter_nome_fracao(chave):
    nomes = {'f23': 'Fração 2/3', 'f65': 'Fração 6/5', 'f76': 'Fração 7/6', 'f83': 'Fração 8/3', 'f94': 'Fração 9/4', 'f5': 'Fração 5'}
    return nomes.get(chave, chave)

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

@bot.message_handler(commands=['add'])
def receber_numero(message):
    try:
        partes = message.text.split()
        if len(partes) < 2:
            return bot.reply_to(message, "Digite o número. Exemplo: `/add 20`", parse_mode="Markdown")
            
        num = int(partes[1])
        if num < 0 or num > 36:
            return bot.reply_to(message, "Número inválido! Digite de 0 a 36.")
            
        processar_roleta(num, message.chat.id)
        
    except ValueError:
        bot.reply_to(message, "Por favor, insira apenas números inteiros.")

def processar_roleta(num, chat_id):
    global operacao
    
    dados = obter_dados()
    dados = checar_e_resetar_diario(dados)
    
    historico_numeros = dados['historico']
    
    # 1. Avaliação de resultado do sinal corrente (G1, G2, G3)
    if operacao['em_andamento']:
        operacao['tentativas'] += 1
        if num in operacao['alvos']:
            dados['greens'] += 1
            dados['greens_seguidos'] += 1
            salvar_dados(dados)
            bot.send_message(chat_id, f"🟢 **GREEN no G{operacao['tentativas']}** ({num})!\nSinal: {operacao['nome_gatilho']}", parse_mode="Markdown")
            operacao['em_andamento'] = False
        elif operacao['tentativas'] >= 3:
            dados['reds'] += 1
            dados['greens_seguidos'] = 0
            salvar_dados(dados)
            bot.send_message(chat_id, f"🔴 **RED após 3 giros.**\nAlvos originais: {operacao['alvos']}", parse_mode="Markdown")
            operacao['em_andamento'] = False

    # 2. Atualização sequencial da linha de tempo
    historico_numeros.insert(0, num)
    if len(historico_numeros) > 14:
        historico_numeros = historico_numeros[:14]
        
    salvar_dados(dados, historico_novo=historico_numeros)

    if len(historico_numeros) < 14 or operacao['em_andamento']:
        return

    # 3. Varredura matemática e lógica de rabeira
    contagem = {chave: sum(1 for n in historico_numeros if n in lista) for chave, lista in fracoes.items()}
    num13, num14 = historico_numeros[12], historico_numeros[13]
    
    regioes_ativadas = []
    for chave, qtd in contagem.items():
        if qtd >= 5 and (num13 in fracoes[chave] or num14 in fracoes[chave]):
            regioes_ativadas.append(chave)

    # 4. Injeção dinâmica de alvos e envio de sinal
    if regioes_ativadas:
        alvos_finais = []
        nomes_sinal = []
        ultimos_5 = historico_numeros[:5]
        
        for regiao in regioes_ativadas:
            nomes_sinal.append(obter_nome_fracao(regiao))
            alvos_finais.extend(fracoes[regiao])
            
            # Regras dinâmicas estritas retiradas da tabela DEPENDE (REGIAO.jpeg)
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
            "🎯 **SINAL DETECTADO!**\n"
            f"Setores: `{operacao['nome_gatilho']}`\n"
            f"🎰 Cobertura: {', '.join(map(str, operacao['alvos']))}\n"
            "⚠️ Limite: Até 3 Giros."
        )
        bot.send_message(chat_id, mensagem_sinal, parse_mode="Markdown")

if __name__ == "__main__":
    iniciar_banco()
    print("🤖 Robô de Frações 24h Iniciado com Sucesso!")
    bot.infinity_polling()
