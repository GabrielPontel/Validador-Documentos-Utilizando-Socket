using System;
using System.Collections.Generic;
using System.Net.Sockets; // TcpClient
using System.Text; // ASCII

namespace ClienteGB
{
    class Program
    {
        const string host = "127.0.0.1"; // IP do servidor
        const int porta_tcp = 4851; // Porta
        const int tempo_maximo_espera = 10000;
        const char fim_mensagem = '\n'; // toda mensagem do GBProtocol termina com \n
        const char separador_pares = '&'; // separa um par do outro
        const char separador_campo = '+'; // separa o campo da resposta

        static void Main()
        {
            string tipo_doc;
            string doc;
            bool executando = true;
            string requisicao;
            string resposta;

            Console.WriteLine("*************** GBProtocol (CPF / CNPJ) ***************");

            while (executando)
            {
                Console.Write("\nTipo do documento (CPF/CNPJ) (Somente aperte enter para sair): ");
                tipo_doc = Console.ReadLine() ?? "";
                if (tipo_doc == "")
                    executando = false;
                if (executando)
                {
                    Console.Write("Numero do documento (somente digitos): ");
                    doc = Console.ReadLine() ?? "";

                    // Requisição do protocolo: campo+resposta&campo+resposta
                    requisicao = $"tipo_doc{separador_campo}{tipo_doc}{separador_pares}doc{separador_campo}{doc}";

                    resposta = EnviarRequisicao(requisicao);
                    Console.Write("\nREQUISICAO:\n" + requisicao);
                    if (resposta != null)
                    {
                        Console.Write("\n\nRESPOSTA:\n" + resposta);
                        Console.Write("\n\nRESULTADO:\n" + TraduzirResposta(resposta, tipo_doc, doc) + "\n");
                    }
                    else
                        executando = false;
                }
            }

            Console.WriteLine("Cliente encerrado.");
        }


        static string EnviarRequisicao(string requisicao)
        {
            string resposta = null;
            byte[] saida;
            byte[] buffer = new byte[256];
            NetworkStream fluxo;
            StringBuilder texto = new StringBuilder();
            int lidos;
            bool lendo = true;

            try
            {
                // 'using' garante que o socket seja fechado no final
                using (TcpClient cliente = new TcpClient())
                {
                    cliente.ReceiveTimeout = tempo_maximo_espera;
                    cliente.SendTimeout = tempo_maximo_espera;

                    // Conecta ao servidor (handshake TCP)
                    cliente.Connect(host, porta_tcp);
                    fluxo = cliente.GetStream();

                    // Envia os bytes da requisição em ASCII, terminando com \n
                    saida = Encoding.ASCII.GetBytes(requisicao + fim_mensagem);
                    fluxo.Write(saida, 0, saida.Length);

                    // TCP é um fluxo de bytes: um Read() pode trazer só uma parte da mensagem
                    // A resposta termina quando chegar o \n
                    while (!texto.ToString().Contains(fim_mensagem) && lendo)
                    {
                        lidos = fluxo.Read(buffer, 0, buffer.Length);
                        if (lidos == 0)
                            lendo = false;
                        else
                            texto.Append(Encoding.ASCII.GetString(buffer, 0, lidos));
                    }

                    resposta = texto.ToString().Trim();
                    if (resposta.Length == 0)
                    {
                        Console.WriteLine(">> Servidor recusou a conexao (limite de conexoes ativas).");
                        resposta = null;
                    }
                }
            }
            catch (SocketException erro)
            {
                Console.WriteLine($">> Nao foi possivel falar com o servidor: {erro.Message}");
            }
            catch (System.IO.IOException erro)
            {
                Console.WriteLine($">> Falha na comunicacao: {erro.Message}");
            }
            return resposta;
        }


        static Dictionary<string, string> SepararCampos(string resposta)
        {
            // Separa os pares por & e cada par por +
            Dictionary<string, string> campos = new Dictionary<string, string>();
            string[] pares = resposta.Split(separador_pares);
            string[] partes;

            foreach (string par in pares)
            {
                partes = par.Split(separador_campo, 2);
                if (partes.Length == 2)
                    campos[partes[0]] = partes[1];
            }
            return campos;
        }


        static string TraduzirResposta(string resposta, string tipo_doc, string doc)
        {
            // O servidor manda apenas códigos; o texto é montado aqui no cliente
            Dictionary<string, string> campos = SepararCampos(resposta);
            string valido = campos.GetValueOrDefault("valido", "");
            string erro = campos.GetValueOrDefault("erro", "");
            int ideal = tipo_doc == "CPF" ? 11 : 14;
            string mensagem;

            if (valido == "1")
                mensagem = "Documento valido";
            else if (erro == "0")
                mensagem = "Documento invalido";
            else if (erro == "1.1")
                mensagem = "Estrutura da requisicao invalida";
            else if (erro == "1.2")
                mensagem = "O campo tipo_doc nao foi informado ou esta vazio";
            else if (erro == "1.3")
                mensagem = "O campo doc nao foi informado ou esta vazio";
            else if (erro == "2.1")
                mensagem = $"O tipo {tipo_doc} nao e processado pelo GBProtocol";
            else if (erro == "3.1")
                mensagem = $"A quantidade ideal para {tipo_doc} e de {ideal} digitos e seu documento possui {doc.Length}, portanto faltam {ideal - doc.Length} digitos";
            else if (erro == "3.2")
                mensagem = $"A quantidade ideal para {tipo_doc} e de {ideal} digitos e seu documento possui {doc.Length}, portanto existem {doc.Length - ideal} digitos a mais";
            else if (erro == "4.1")
                mensagem = MensagemCaracteres(doc);
            else
                mensagem = "Resposta desconhecida do servidor";
            return mensagem;
        }


        static string MensagemCaracteres(string doc)
        {
            // Lista os caracteres que não são dígitos, sem repetir
            List<char> invalidos = new List<char>();
            string mensagem;

            foreach (char c in doc)
                if ((c < '0' || c > '9') && !invalidos.Contains(c))
                    invalidos.Add(c);

            if (invalidos.Count == 1)
                mensagem = $"O campo doc so aceita digitos e o caractere {invalidos[0]} nao e permitido";
            else
                mensagem = $"O campo doc so aceita digitos e os caracteres {string.Join(", ", invalidos.GetRange(0, invalidos.Count - 1))} e {invalidos[invalidos.Count - 1]} nao sao permitidos";
            return mensagem;
        }
    }
}
