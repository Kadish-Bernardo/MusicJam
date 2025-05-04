# Importando as bibliotecas necessárias
import socket
import pickle
import struct
import zlib
import sounddevice as sd
import numpy as np
import threading

# Configuração do cliente
SERVER_IP = '127.0.0.1'  # Endereço do servidor (localhost para teste no mesmo PC)
PORT = 5050              # Porta deve ser igual à do servidor

# Conecta ao servidor
client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.connect((SERVER_IP, PORT))
print("[Cliente] Conectado ao servidor!")

# Recebe o sample rate (frequência de amostragem)
sample_rate_data = client_socket.recv(4)
sample_rate = struct.unpack('I', sample_rate_data)[0]
print(f"[Cliente] Sample rate: {sample_rate}")

# Variáveis de controle
buffer = []        # Onde os dados de áudio ficam enquanto não são reproduzidos
play_flag = True   # Se está tocando ou pausado
stop_flag = False  # Se deve encerrar

# Função para capturar comandos do usuário (pausar, retomar, parar)
def command_input():
    global play_flag, stop_flag
    while True:
        cmd = input("Comando (p=pause, r=resume, s=stop): ").strip().lower()
        if cmd == 'p':
            play_flag = False
        elif cmd == 'r':
            play_flag = True
        elif cmd == 's':
            stop_flag = True
            break

# Função chamada automaticamente para enviar os dados ao alto-falante
def audio_callback(outdata, frames, time_info, status):
    if not play_flag or len(buffer) < frames:
        # Se está pausado ou não tem dados suficientes → envia silêncio
        outdata[:] = np.zeros((frames, 1))
    else:
        # Envia dados reais do áudio
        outdata[:] = np.array(buffer[:frames]).reshape(-1, 1)
        del buffer[:frames]  # Remove os dados já enviados

# Inicia o áudio
stream = sd.OutputStream(channels=1, samplerate=sample_rate, callback=audio_callback)
stream.start()

# Inicia a thread para capturar comandos do usuário
threading.Thread(target=command_input, daemon=True).start()

try:
    while not stop_flag:
        # Primeiro recebe o tamanho do bloco
        size_data = client_socket.recv(4)
        if not size_data:
            break
        block_size = struct.unpack('I', size_data)[0]

        # Recebe os dados do bloco
        block_data = b''
        while len(block_data) < block_size:
            packet = client_socket.recv(block_size - len(block_data))
            if not packet:
                break
            block_data += packet

        # Descomprime e reconstrói os dados
        decompressed = zlib.decompress(block_data)
        chunk = pickle.loads(decompressed)

        # Adiciona ao buffer para reprodução
        buffer.extend(chunk.tolist())
except Exception as e:
    print(f"[Cliente] Problema: {e}")
finally:
    # Encerra tudo ao final
    stream.stop()
    client_socket.close()
    print("[Cliente] Encerrado.")