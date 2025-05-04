# Importando as bibliotecas necessárias
import socket        # Para comunicação entre computadores
import threading     # Para permitir vários clientes ao mesmo tempo
import librosa       # Para ler o arquivo de áudio
import pickle        # Para transformar os dados do áudio em um formato que possa ser enviado
import struct        # Para enviar dados de tamanho fixo (como o tamanho do bloco)
import zlib          # Para comprimir os dados
import time          # Para controlar o tempo de envio (respeitar velocidade de áudio)

# Configurações do servidor
HOST = '0.0.0.0'      # Aceita conexões de qualquer computador na rede
PORT = 5050         # Porta usada para conexão (pode ser qualquer número acima de 1024)
CHUNK_SIZE = 2048    # Quantidade de pedaços de áudio enviados por vez

# Carrega o arquivo de áudio
audio_data, sample_rate = librosa.load('musica.mp3', sr=None)  # sr=None = mantém a qualidade original
print(f"[Servidor] Música carregada! Duração: {len(audio_data) / sample_rate:.2f} segundos.")

# Função para lidar com cada cliente
def handle_client(connection, address):
    print(f"[Servidor] Cliente conectado: {address}")
    try:
        # Envia para o cliente o sample rate (frequência de amostragem)
        connection.sendall(struct.pack('I', sample_rate))

        total_samples = len(audio_data)  # Quantidade total de amostras (pontos de áudio)
        index = 0  # Começa do início da música

        # Envia blocos de áudio enquanto ainda houver dados
        while index < total_samples:
            # Seleciona um pedaço (bloco) da música
            end = min(index + CHUNK_SIZE, total_samples)
            chunk = audio_data[index:end]

            # Transforma o bloco em bytes (serialização)
            serialized = pickle.dumps(chunk)

            # Comprime os dados
            compressed = zlib.compress(serialized)

            # Envia o tamanho do bloco primeiro (para o cliente saber quanto receber)
            connection.sendall(struct.pack('I', len(compressed)))

            # Envia o bloco comprimido
            connection.sendall(compressed)

            # Avança para o próximo bloco
            index = end

            # Espera um pouquinho para respeitar a velocidade da música
            time.sleep(CHUNK_SIZE / sample_rate)
    except Exception as e:
        print(f"[Servidor] Problema com cliente {address}: {e}")
    finally:
        # Fecha a conexão quando terminar
        connection.close()
        print(f"[Servidor] Cliente {address} desconectado.")

# Prepara o servidor para aceitar conexões
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((HOST, PORT))  # Liga o servidor ao IP e à porta escolhida
server_socket.listen(5)  # Permite até 5 clientes esperando ao mesmo tempo
print(f"[Servidor] Aguardando conexões em {HOST}:{PORT}...")

try:
    while True:
        # Quando um cliente se conecta:
        connection, address = server_socket.accept()

        # Cria uma nova thread (processo paralelo) para lidar com ele
        client_thread = threading.Thread(target=handle_client, args=(connection, address))
        client_thread.start()
except KeyboardInterrupt:
    print("\n[Servidor] Encerrando servidor...")
finally:
    server_socket.close()