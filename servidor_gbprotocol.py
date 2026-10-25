import socket  # API de sockets
import threading  # Criação de threads

MAXIMO_CONEXOES = 10
TIMEOUT_CLIENTE = 10  # em segundos
HOST = "0.0.0.0"
PORTA = 4851
TAMANHO_MAXIMO_REQUISICAO = 300
FIM_MENSAGEM = "\n"  # toda mensagem do GBProtocol termina com \n
SEPARADOR_PARES = "&"  # separa um par do outro
SEPARADOR_CAMPO = "+"  # separa o campo da resposta
CAMPOS = ["tipo_doc", "doc"]
QUANTIDADE_DIGITOS_DOCS = {"CPF": 11, "CNPJ": 14}  # tipo -> quantidade

# Estrutura de dados com as conexões abertas
conexoes_ativas = []

# Ideia de mutex
trava = threading.Lock()


def validar_cpf(cpf: str) -> bool:
    # Confere os dois dígitos verificadores do CPF
    digitos_corretos = True
    soma = 0
    digito_calculado = 0

    if cpf == cpf[0] * 11:  # 000..., 111... são inválidos
        digitos_corretos = False
    else:
        for posicao_digito in (9, 10):
            soma = 0
            for indice in range(posicao_digito):
                soma += int(cpf[indice]) * (posicao_digito + 1 - indice)
            digito_calculado = (soma * 10) % 11 % 10
            if digito_calculado != int(cpf[posicao_digito]):
                digitos_corretos = False
    return digitos_corretos


def validar_cnpj(cnpj: str) -> bool:
    # Confere os dois dígitos verificadores do CNPJ
    pesos_primeiro_digito = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos_segundo_digito = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    digitos_corretos = True
    soma = 0
    resto = 0
    digito_calculado = 0

    if cnpj == cnpj[0] * 14:
        digitos_corretos = False
    else:
        for pesos, posicao_digito in ((pesos_primeiro_digito, 12), (pesos_segundo_digito, 13)):
            soma = 0
            for indice in range(posicao_digito):
                soma += int(cnpj[indice]) * pesos[indice]
            resto = soma % 11
            if resto < 2:
                digito_calculado = 0
            else:
                digito_calculado = 11 - resto
            if digito_calculado != int(cnpj[posicao_digito]):
                digitos_corretos = False
    return digitos_corretos


def montar_resposta(valido: bool, erro: str) -> bytes:
    # Formato GBProtocol: valido+X&erro+Y\n, em ASCII
    texto = f"valido{SEPARADOR_CAMPO}{int(valido)}{SEPARADOR_PARES}erro{SEPARADOR_CAMPO}{erro}{FIM_MENSAGEM}"
    resposta = texto.encode("ascii", errors="replace")
    return resposta


def receber_requisicao(sock: socket.socket) -> str:
    # TCP é um fluxo de bytes: lê até chegar o \n que fecha a mensagem
    dados = ""
    pedaco = ""
    lendo = True

    while FIM_MENSAGEM not in dados and lendo:
        pedaco = sock.recv(100).decode("ascii", errors="replace")
        if not pedaco:
            lendo = False
        else:
            dados += pedaco
        if len(dados) > TAMANHO_MAXIMO_REQUISICAO:
            lendo = False
    dados = dados.split(FIM_MENSAGEM)[0].strip("\r")
    return dados


def separar_campos(texto: str):
    # Separa os pares por & e cada par por +. Retorna (estrutura_ok, campos)
    campos = {}
    estrutura_ok = len(texto) > 0
    pares = []
    nome = ""
    valor = ""

    if estrutura_ok:
        pares = texto.split(SEPARADOR_PARES)
    for par in pares:
        if SEPARADOR_CAMPO not in par:
            estrutura_ok = False
        else:
            nome, valor = par.split(SEPARADOR_CAMPO, 1)
            if nome not in CAMPOS or nome in campos:
                estrutura_ok = False
            else:
                campos[nome] = valor
    return estrutura_ok, campos


def processar(texto: str) -> bytes:
    valido = False
    erro = "0"
    estrutura_ok = False
    campos = {}
    tipo = ""
    documento = ""
    ideal = 0

    estrutura_ok, campos = separar_campos(texto)
    tipo = campos.get("tipo_doc", "")
    documento = campos.get("doc", "")
    ideal = QUANTIDADE_DIGITOS_DOCS.get(tipo, 0)

    if not estrutura_ok:
        erro = "1.1"
    elif tipo == "":  # ausente ou vazio
        erro = "1.2"
    elif documento == "":  # ausente ou vazio
        erro = "1.3"
    elif tipo not in QUANTIDADE_DIGITOS_DOCS:  # CPF ou CNPJ (somente maiúsculo)
        erro = "2.1"
    elif not documento.isdigit() or not documento.isascii():
        erro = "4.1"
    elif len(documento) < ideal:
        erro = "3.1"
    elif len(documento) > ideal:
        erro = "3.2"
    elif tipo == "CPF":
        valido = validar_cpf(documento)
    else:
        valido = validar_cnpj(documento)

    return montar_resposta(valido, erro)


def atender_cliente(sock: socket.socket, endereco):
    texto = ""
    resposta = b""
    ativos = 0

    try:
        sock.settimeout(TIMEOUT_CLIENTE)
        texto = receber_requisicao(sock)
        print(f"[{endereco}] <- {texto}")
        resposta = processar(texto)
        sock.sendall(resposta)  # sendall garante envio total
        print(f"[{endereco}] -> {resposta.decode('ascii').strip()}")
    except socket.timeout:
        sock.sendall(montar_resposta(False, "1.1"))
    except OSError as erro:
        print(f"[{endereco}] erro: {erro}")
    finally:
        # Remove da lista de conexões e fecha
        with trava:
            if sock in conexoes_ativas:
                conexoes_ativas.remove(sock)
            ativos = len(conexoes_ativas)
        sock.close()
        print(f"[{endereco}] desconectado. Ativas: {ativos}/{MAXIMO_CONEXOES}")


def main():
    servidor = None
    cliente = None
    endereco = None
    ativo = False
    thread = None

    # AF_INET = IPv4 e SOCK_STREAM = TCP
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # permite reiniciar o servidor
    servidor.bind((HOST, PORTA))  # associa o socket a IP:porta
    servidor.listen()  # escutando
    print(f"GBProtocol ouvindo em {HOST}:{PORTA} (max. {MAXIMO_CONEXOES} conexoes)")

    try:
        while True:
            ativo = False
            cliente, endereco = servidor.accept()  # bloqueia até chegar um

            # Trava para ver quantos estão conectados no momento
            with trava:
                if len(conexoes_ativas) < MAXIMO_CONEXOES:
                    conexoes_ativas.append(cliente)
                    ativo = True
            if not ativo:
                # Cheio: fecha a conexão sem resposta
                print(f"[{endereco}] recusado: o servidor ja esta com a quantidade maxima de conexoes")
                cliente.close()
            else:
                print(f"[{endereco}] conectado. Ativas: {len(conexoes_ativas)}/{MAXIMO_CONEXOES}")
                thread = threading.Thread(target=atender_cliente, args=(cliente, endereco), daemon=True)
                thread.start()
    except KeyboardInterrupt:
        print("\nEncerrando servidor...")
    finally:
        servidor.close()


if __name__ == "__main__":
    main()
