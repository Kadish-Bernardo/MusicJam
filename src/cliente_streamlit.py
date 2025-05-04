import socket
import pickle
import struct
import zlib
import sounddevice as sd
import numpy as np
import threading
import streamlit as st

# Variáveis de controle
buffer = []
play_flag = threading.Event()
stop_flag = threading.Event()
play_flag.set()  # Começa tocando

# Streamlit interface
st.set_page_config(page_title="Music Jam Player", layout="centered")
st.title("🎵 Music Jam - Player Cliente")

# Botões de controle
col1, col2, col3 = st.columns(3)
if col1.button("⏸️ Pausar"):
    play_flag.clear()
if col2.button("▶️ Retomar"):
    play_flag.set()
if col3.button("⏹️ Parar"):
    stop_flag.set()

# Conecta ao servidor
@st.cache_resource
def connect_to_server():
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect(('127.0.0.1', 5050))
        st.success("✅ Conectado ao servidor!")
        return client_socket
    except Exception as e:
        st.error(f"❌ Erro ao conectar: {e}")
        st.stop()

client_socket = connect_to_server()

# Recebe sample rate
sample_rate_data = client_socket.recv(4)
sample_rate = struct.unpack('I', sample_rate_data)[0]

# Função de callback para reprodução
def audio_callback(outdata, frames, time_info, status):
    if not play_flag.is_set() or len(buffer) < frames:
        outdata[:] = np.zeros((frames, 1))
    else:
        outdata[:] = np.array(buffer[:frames]).reshape(-1, 1)
        del buffer[:frames]

# Função que roda o loop de recepção de áudio
def receive_audio():
    try:
        while not stop_flag.is_set():
            size_data = client_socket.recv(4)
            if not size_data:
                break
            block_size = struct.unpack('I', size_data)[0]

            block_data = b''
            while len(block_data) < block_size:
                packet = client_socket.recv(block_size - len(block_data))
                if not packet:
                    break
                block_data += packet

            decompressed = zlib.decompress(block_data)
            chunk = pickle.loads(decompressed)

            buffer.extend(chunk.tolist())
    except Exception as e:
        st.error(f"Erro na recepção de áudio: {e}")
    finally:
        stop_flag.set()
        client_socket.close()

# Inicia o áudio
stream = sd.OutputStream(channels=1, samplerate=sample_rate, callback=audio_callback)
stream.start()

# Inicia thread para receber dados
threading.Thread(target=receive_audio, daemon=True).start()

# Loop de verificação para encerrar
while not stop_flag.is_set():
    sd.sleep(100)
stream.stop()
st.warning("⏹️ Reproduzido até o fim ou interrompido.")
