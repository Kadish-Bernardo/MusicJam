import socket
import threading
import librosa
import pickle
import struct
import zlib
import time
import os

# Configurações do servidor
HOST = '0.0.0.0'
AUDIO_PORT = 5050      # Porta para streaming de áudio
COMMAND_PORT = 5051    # Porta para receber comandos
CHUNK_SIZE = 2048

MUSIC_FOLDER = 'Music'  # Pasta com músicas .mp3

# Estado global
playlist = []
playlist_lock = threading.Lock()
current_track_index = 0

audio_data = None
sample_rate = None

play_event = threading.Event()
stop_event = threading.Event()
pause_event = threading.Event()

clients = []
clients_lock = threading.Lock()

# Índice global do ponto atual da música (para todos os clientes)
current_audio_index_lock = threading.Lock()
current_audio_index = 0

def load_playlist():
    global playlist
    playlist = sorted([f for f in os.listdir(MUSIC_FOLDER) if f.lower().endswith('.mp3')])
    print(f"[Servidor] Playlist carregada: {playlist}")

def load_track(index):
    global audio_data, sample_rate, current_audio_index
    track_path = os.path.join(MUSIC_FOLDER, playlist[index])
    audio_data, sample_rate = librosa.load(track_path, sr=None)
    with current_audio_index_lock:
        current_audio_index = 0  # Reseta índice ao carregar nova faixa
    print(f"[Servidor] Música carregada: {playlist[index]} Duração: {len(audio_data)/sample_rate:.2f}s")

def audio_stream_client(conn, addr):
    global audio_data, sample_rate, current_audio_index
    print(f"[Servidor] Cliente conectado para áudio: {addr}")

    try:
        # Envia sample rate para o cliente
        conn.sendall(struct.pack('I', sample_rate))

        total_samples = len(audio_data)

        while not stop_event.is_set():
            try:
                # Espera até play_event estar setado (play ou resume)
                play_event.wait()

                if pause_event.is_set():
                    time.sleep(0.1)
                    continue

                with current_audio_index_lock:
                    start = current_audio_index
                    end = min(start + CHUNK_SIZE, total_samples)
                    chunk = audio_data[start:end]

                    current_audio_index = end

                if len(chunk) == 0:
                    # Se chegou ao fim da música, vai para próxima
                    next_track()
                    continue

                serialized = pickle.dumps(chunk)
                compressed = zlib.compress(serialized)

                conn.sendall(struct.pack('I', len(compressed)))
                conn.sendall(compressed)

                # Delay para sincronizar a taxa de streaming
                time.sleep(CHUNK_SIZE / sample_rate)

            except (ConnectionResetError, BrokenPipeError):
                break

    except Exception as e:
        print(f"[Servidor] Erro com cliente {addr}: {e}")
    finally:
        with clients_lock:
            if conn in clients:
                clients.remove(conn)
        conn.close()
        print(f"[Servidor] Cliente de áudio desconectado: {addr}")

def audio_server_thread():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, AUDIO_PORT))
    server.listen(5)
    print(f"[Servidor] Servidor de áudio ouvindo em {HOST}:{AUDIO_PORT}")

    while not stop_event.is_set():
        try:
            conn, addr = server.accept()
            with clients_lock:
                clients.append(conn)
            threading.Thread(target=audio_stream_client, args=(conn, addr), daemon=True).start()
        except Exception as e:
            print(f"[Servidor] Erro ao aceitar cliente áudio: {e}")

def next_track():
    global current_track_index
    with playlist_lock:
        current_track_index = (current_track_index + 1) % len(playlist)
        load_track(current_track_index)
    pause_event.clear()
    play_event.set()
    print(f"[Servidor] Próxima música: {playlist[current_track_index]}")

def command_server_thread():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, COMMAND_PORT))
    server.listen(1)
    print(f"[Servidor] Servidor de comandos ouvindo em {HOST}:{COMMAND_PORT}")

    while not stop_event.is_set():
        try:
            conn, addr = server.accept()
            print(f"[Servidor] Cliente de comando conectado: {addr}")
            threading.Thread(target=handle_commands, args=(conn,), daemon=True).start()
        except Exception as e:
            print(f"[Servidor] Erro no servidor de comandos: {e}")

def handle_commands(conn):
    global stop_event
    try:
        with conn:
            while not stop_event.is_set():
                data = conn.recv(1024)
                if not data:
                    break
                cmd = data.decode().strip().lower()

                if cmd == 'play':
                    # Reinicia a música do zero
                    print("[Servidor] Comando PLAY recebido - iniciando música do zero")
                    pause_event.clear()
                    with current_audio_index_lock:
                        global current_audio_index
                        current_audio_index = 0
                    play_event.set()

                elif cmd == 'pause' or cmd == 'stop':
                    if play_event.is_set():
                        print("[Servidor] Comando PAUSE/STOP recebido - pausando reprodução")
                        pause_event.set()

                elif cmd == 'resume':
                    if pause_event.is_set():
                        print("[Servidor] Comando RESUME recebido - retomando reprodução")
                        pause_event.clear()
                        play_event.set()

                elif cmd == 'next':
                    print("[Servidor] Comando NEXT recebido - próxima música")
                    next_track()

                elif cmd == 'sair':
                    print("[Servidor] Comando SAIR recebido, encerrando servidor")
                    stop_event.set()
                    play_event.set()
                    pause_event.clear()
                    break

                else:
                    print(f"[Servidor] Comando desconhecido: {cmd}")
    except Exception as e:
        print(f"[Servidor] Erro ao tratar comandos: {e}")

def main():
    load_playlist()
    if not playlist:
        print("[Servidor] Nenhuma música encontrada na pasta Music")
        return

    load_track(0)
    play_event.clear()
    pause_event.set()

    threading.Thread(target=audio_server_thread, daemon=True).start()
    threading.Thread(target=command_server_thread, daemon=True).start()

    print("[Servidor] Servidor iniciado. Aguardando comandos...")

    # Apenas mantém o servidor rodando
    try:
        while not stop_event.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        print("[Servidor] Encerrando por KeyboardInterrupt")
        stop_event.set()

if __name__ == '__main__':
    main()
