import socket
import threading
import librosa
import pickle
import struct
import zlib
import time
import os
import sys

HOST = '0.0.0.0'
AUDIO_PORT = 5050
COMMAND_PORT = 5051
CHUNK_SIZE = 2048
MUSIC_FOLDER = 'Music'

playlist = []
playlist_lock = threading.Lock()
current_track_index = 0

audio_data = None
sample_rate = None

play_event = threading.Event()
stop_event = threading.Event()
pause_event = threading.Event()

audio_clients = []
command_clients = []
audio_clients_lock = threading.Lock()
command_clients_lock = threading.Lock()

current_audio_index_lock = threading.Lock()
current_audio_index = 0

master_conn = None
master_lock = threading.Lock()

def load_playlist():
    global playlist
    playlist = sorted([f for f in os.listdir(MUSIC_FOLDER) if f.lower().endswith('.mp3')])
    print(f"[Servidor] Playlist carregada: {playlist}")

def load_track(index):
    global audio_data, sample_rate, current_audio_index
    track_path = os.path.join(MUSIC_FOLDER, playlist[index])
    audio_data, sample_rate = librosa.load(track_path, sr=None)
    with current_audio_index_lock:
        current_audio_index = 0
    print(f"[Servidor] Música carregada: {playlist[index]} Duração: {len(audio_data)/sample_rate:.2f}s")

def broadcast_command(cmd):
    with command_clients_lock:
        to_remove = []
        for c in command_clients:
            try:
                c.sendall(cmd.encode())
            except:
                to_remove.append(c)
        for c in to_remove:
            command_clients.remove(c)

def next_track():
    global current_track_index
    with playlist_lock:
        current_track_index = (current_track_index + 1) % len(playlist)
        load_track(current_track_index)
    pause_event.clear()
    with current_audio_index_lock:
        global current_audio_index
        current_audio_index = 0
    play_event.set()
    broadcast_command('play')
    print(f"[Servidor] Próxima música: {playlist[current_track_index]}")

def audio_stream_client(conn, addr):
    global audio_data, sample_rate, current_audio_index
    print(f"[Servidor] Cliente conectado para áudio: {addr}")

    try:
        conn.sendall(struct.pack('I', sample_rate))
        total_samples = len(audio_data)

        while not stop_event.is_set():
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
                next_track()
                continue

            serialized = pickle.dumps(chunk)
            compressed = zlib.compress(serialized)

            try:
                conn.sendall(struct.pack('I', len(compressed)))
                conn.sendall(compressed)
            except (ConnectionResetError, BrokenPipeError):
                break

            time.sleep(CHUNK_SIZE / sample_rate)

    except Exception as e:
        print(f"[Servidor] Erro com cliente {addr}: {e}")
    finally:
        with audio_clients_lock:
            if conn in audio_clients:
                audio_clients.remove(conn)
        conn.close()
        print(f"[Servidor] Cliente de áudio desconectado: {addr}")

def audio_server_thread():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, AUDIO_PORT))
    server.listen(5)
    print(f"[Servidor] Servidor de áudio ouvindo em {HOST}:{AUDIO_PORT}")

    while not stop_event.is_set():
        try:
            server.settimeout(1.0)
            conn, addr = server.accept()
            with audio_clients_lock:
                audio_clients.append(conn)
            threading.Thread(target=audio_stream_client, args=(conn, addr), daemon=True).start()
        except socket.timeout:
            continue
        except Exception as e:
            print(f"[Servidor] Erro ao aceitar cliente áudio: {e}")

def handle_commands(conn, addr):
    global master_conn

    try:
        with conn:
            with command_clients_lock:
                command_clients.append(conn)

            with master_lock:
                if master_conn is None:
                    master_conn = conn
                    print(f"[Servidor] Cliente {addr} é o novo MESTRE")

            while not stop_event.is_set():
                data = conn.recv(1024)
                if not data:
                    break

                if conn != master_conn:
                    continue  # Apenas o mestre pode enviar comandos

                cmd = data.decode().strip().lower()
                print(f"[Servidor] Comando recebido do MESTRE {addr}: '{cmd}'")

                if cmd == 'play':
                    pause_event.clear()
                    with current_audio_index_lock:
                        global current_audio_index
                        current_audio_index = 0
                    play_event.set()
                    broadcast_command('play')

                elif cmd == 'pause' or cmd == 'stop':
                    if play_event.is_set():
                        pause_event.set()
                        broadcast_command('pause')

                elif cmd == 'resume':
                    if pause_event.is_set():
                        pause_event.clear()
                        play_event.set()
                        broadcast_command('resume')

                elif cmd == 'next':
                    next_track()

                elif cmd == 'sair':
                    print(f"[Servidor] Cliente mestre {addr} saiu voluntariamente.")
                    break

                else:
                    print(f"[Servidor] Comando desconhecido: {cmd}")

    except Exception as e:
        print(f"[Servidor] Erro ao tratar comandos: {e}")

    finally:
        with command_clients_lock:
            if conn in command_clients:
                command_clients.remove(conn)
        with master_lock:
            if conn == master_conn:
                print(f"[Servidor] Mestre {addr} desconectado. Promovendo novo mestre...")
                if command_clients:
                    master_conn = command_clients[0]
                    print(f"[Servidor] Novo mestre: {master_conn.getpeername()}")
                else:
                    master_conn = None
        conn.close()
        print(f"[Servidor] Cliente de comando desconectado: {addr}")

def command_server_thread():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, COMMAND_PORT))
    server.listen(5)
    print(f"[Servidor] Servidor de comandos ouvindo em {HOST}:{COMMAND_PORT}")

    while not stop_event.is_set():
        try:
            server.settimeout(1.0)
            conn, addr = server.accept()
            print(f"[Servidor] Cliente de comando conectado: {addr}")
            threading.Thread(target=handle_commands, args=(conn, addr), daemon=True).start()
        except socket.timeout:
            continue
        except Exception as e:
            print(f"[Servidor] Erro no servidor de comandos: {e}")

def terminal_input_thread():
    print("[Servidor] Thread de comando pelo terminal iniciada. Digite 'shutdown' para parar o servidor.")
    while not stop_event.is_set():
        try:
            cmd = input().strip().lower()
            if cmd == 'shutdown':
                print("[Servidor] Comando SHUTDOWN recebido no terminal - encerrando servidor")
                stop_event.set()
                broadcast_command('shutdown')
                break
            else:
                print(f"[Servidor] Comando '{cmd}' desconhecido no terminal")
        except EOFError:
            break
        except Exception as e:
            print(f"[Servidor] Erro lendo do terminal: {e}")

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
    threading.Thread(target=terminal_input_thread, daemon=True).start()

    print("[Servidor] Servidor iniciado. Aguardando comandos e entrada no terminal...")

    try:
        while not stop_event.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        print("[Servidor] Encerrando por KeyboardInterrupt")
        stop_event.set()

    print("[Servidor] Servidor encerrado.")

if __name__ == '__main__':
    main()